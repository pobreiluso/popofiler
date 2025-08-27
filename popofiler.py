import subprocess
import sys
from tqdm import tqdm
import time
import random
import string
import colorama
import shlex
import os

# Constants for Kubernetes and profiling configuration
K8S_CONTEXT = 'k8s_context'
PROJECT_NAME = 'project-name'
POD_NAME_ANTI_PATTERN = 'anti-pattern'
NAMESPACE = 'namespace-name'

def generate_trace_key():
    """Generate a secure random key for tracing."""
    return ''.join(random.choices(
        string.ascii_letters + string.digits, k=64))

def run_command(command, desc="Running Command"):
    """
    Ejecuta un comando en el sistema y captura su salida, mostrando una barra de progreso con color.

    Args:
        command (str): El comando a ejecutar.
        desc (str): Descripción del comando para mostrar.

    Returns:
        tuple: Una tupla conteniendo un booleano que indica éxito, y la salida del comando o el mensaje de error.
    """
    if not command or not command.strip():
        return False, "Empty command provided"
    
    print(f"{desc}: ")
    colorama.init()  # Inicializa colorama para colores en la terminal
    
    process = None
    try:
        # Inicializa la barra de progreso
        with tqdm(total=100, desc="Ejecutando comando", bar_format="{l_bar}%s{bar}%s{r_bar}" % (colorama.Fore.BLUE, colorama.Fore.RESET)) as pbar:
            # Ejecuta el comando usando shlex para mayor seguridad
            # Nota: Para compatibilidad mantenemos shell=True pero validamos entrada
            sanitized_command = command.strip()
            process = subprocess.Popen(sanitized_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, text=True)

            # Debido a que no sabemos el progreso real del comando, la barra se actualizará de manera artificial
            progress = 0
            while process.poll() is None:  # Verifica si el comando ha terminado
                time.sleep(0.05)  # Espera un poco antes de la siguiente actualización
                progress = min(progress + 1, 99)  # No exceder 99 hasta completar
                pbar.update(1 if pbar.n < 99 else 0)
            
            # Comando completado
            pbar.n = 100
            pbar.last_print_n = 100
            pbar.refresh()

        # Captura la salida y errores del comando
        stdout, stderr = process.communicate(timeout=30)  # Añadir timeout

        # Maneja el resultado del comando
        if process.returncode == 0:
            return True, stdout  # Retorna True y la salida en caso de éxito
        else:
            # En caso de error, imprime y retorna el error
            print(f"Error: {stderr}  {command}", file=sys.stderr)
            return False, stderr  # Retorna False y el error
            
    except subprocess.TimeoutExpired:
        if process:
            process.kill()
            process.communicate()  # Limpia buffers
        error_msg = "Command timed out after 30 seconds"
        print(f"Error: {error_msg}", file=sys.stderr)
        return False, error_msg
    except subprocess.CalledProcessError as e:
        print(f"Command failed with {e.returncode}", file=sys.stderr)
        return False, str(e)
    except KeyboardInterrupt:
        if process:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        error_msg = "KeyboardInterrupt: Process terminated by user."
        print(error_msg, file=sys.stderr)
        return False, error_msg
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"Error: {error_msg}", file=sys.stderr)
        return False, error_msg
    finally:
        colorama.deinit()


def validate_k8s_config():
    """Validate that required Kubernetes configuration is available."""
    required_vars = {
        'K8S_CONTEXT': K8S_CONTEXT,
        'PROJECT_NAME': PROJECT_NAME,
        'NAMESPACE': NAMESPACE
    }
    
    for var_name, var_value in required_vars.items():
        if not var_value or var_value in ['k8s_context', 'project-name', 'namespace-name']:
            print(f"Error: {var_name} must be configured with a valid value", file=sys.stderr)
            return False
    return True

def pick_running_pod():
    """Select a running pod based on project name and anti-pattern filters."""
    if not validate_k8s_config():
        return None
        
    command = f"kubectl --context {K8S_CONTEXT} get pods --field-selector=status.phase==Running --namespace {NAMESPACE}"
    print("command = ", command)
    success, output = run_command(command, desc="Listing Running Pods")
    if not success:
        print(f"Error: {output}")
        return None

    if not output or not output.strip():
        print("No output received from kubectl command")
        return None

    # Filtra la salida para obtener el pod deseado
    lines = output.splitlines()
    if len(lines) <= 1:  # Solo header o vacío
        print("No running pods found")
        return None
        
    for line in lines[1:]:  # Skip header
        if not line.strip():
            continue
        if PROJECT_NAME in line and POD_NAME_ANTI_PATTERN not in line:
            parts = line.split()
            if len(parts) > 0:
                pod_name = parts[0]  # Asume que el nombre del pod está en la primera columna
                return pod_name
    
    print(f"No suitable pods found matching project '{PROJECT_NAME}' and not matching anti-pattern '{POD_NAME_ANTI_PATTERN}'")
    return None



def execute_profiling_commands(commands):
    """
    Execute a list of commands for enabling or disabling profiling.

    Args:
        commands (list): A list of shell commands to be executed.
        
    Returns:
        bool: True if all commands succeeded, False otherwise.
    """
    if not commands:
        print("No commands to execute")
        return False
        
    for i, command in enumerate(commands, 1):
        success, output = run_command(command, desc=f"Executing Command {i}/{len(commands)}")
        if not success:
            print(f"Command {i} failed: {output}", file=sys.stderr)
            return False
    print("Profiling configuration updated.")
    return True


def enable_profiling(donor_pod):
    """Enable Xdebug profiling on the specified pod."""
    if not donor_pod or not donor_pod.strip():
        print("Error: Invalid pod name provided", file=sys.stderr)
        return False
        
    trace_key = generate_trace_key()
    
    commands = [
        f"kubectl cp --context {K8S_CONTEXT} --namespace={NAMESPACE} {donor_pod}:/usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini ./docker-php-ext-xdebug.ini-backup",
        f"kubectl exec -it --context {K8S_CONTEXT} --namespace={NAMESPACE} {donor_pod} -- bash -c 'echo -e \"zend_extension=xdebug\\nxdebug.mode=profile\\nxdebug.output_dir=/tmp/cachegrind/\\nxdebug.start_with_request=trigger\" > /usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini'",
        f"kubectl exec -it --context {K8S_CONTEXT} --namespace={NAMESPACE} {donor_pod} -- bash -c 'mkdir -p /tmp/cachegrind/ && chown www-data:www-data /tmp/cachegrind/'",
        f"kubectl exec -it --context {K8S_CONTEXT} --namespace={NAMESPACE} {donor_pod} -- bash -c 'pkill -USR2 php-fpm'"
    ]
    
    if execute_profiling_commands(commands):
        print(f"XDEBUG_TRIGGER: {trace_key}")
        print("Profiling enabled.")
        return True
    else:
        print("Failed to enable profiling", file=sys.stderr)
        return False


def disable_profiling(donor_pod):
    """Disable Xdebug profiling on the specified pod."""
    if not donor_pod or not donor_pod.strip():
        print("Error: Invalid pod name provided", file=sys.stderr)
        return False
    
    # Check if backup file exists
    if not os.path.exists('./docker-php-ext-xdebug.ini-backup'):
        print("Warning: Backup file not found. Cannot restore previous configuration.", file=sys.stderr)
        return False
        
    commands = [
        f"kubectl cp --context {K8S_CONTEXT} --namespace={NAMESPACE} ./docker-php-ext-xdebug.ini-backup {donor_pod}:/usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini",
        f"kubectl exec --context {K8S_CONTEXT} -it --namespace={NAMESPACE} {donor_pod} -- bash -c 'pkill -USR2 php-fpm'"
    ]
    
    if execute_profiling_commands(commands):
        print("Profiling disabled and configuration restored.")
        return True
    else:
        print("Failed to disable profiling", file=sys.stderr)
        return False


def download_profiles(donor_pod):
    """Download profiling traces from the specified pod."""
    if not donor_pod or not donor_pod.strip():
        print("Error: Invalid pod name provided", file=sys.stderr)
        return False
        
    # Create local directory if it doesn't exist
    os.makedirs('./cachegrind', exist_ok=True)
    
    success, output = run_command(f"kubectl cp --context {K8S_CONTEXT} --namespace={NAMESPACE} {donor_pod}:/tmp/cachegrind/. ./cachegrind/", desc="Downloading Profiles")
    if success:
        print("Profiles downloaded.")
        return True
    else:
        print(f"Failed to download profiles: {output}", file=sys.stderr)
        return False


def install_xdebug(donor_pod):
    """Install Xdebug on the specified pod if not already present."""
    if not donor_pod or not donor_pod.strip():
        print("Error: Invalid pod name provided", file=sys.stderr)
        return False
        
    # Primero verifica si Xdebug ya está instalado ejecutando un comando que intente localizarlo
    check_command = f"kubectl exec -it --context {K8S_CONTEXT} --namespace={NAMESPACE} {donor_pod} -- php -m | grep xdebug"
    check_success, check_output = run_command(check_command, desc="Checking Xdebug installation")

    # Si encuentra 'xdebug' en la salida, asume que ya está instalado y sale
    if check_success and check_output and 'xdebug' in check_output.lower():
        print("Xdebug ya está instalado.")
        return True

    # Si no encuentra Xdebug, procede con la instalación
    install_command = f"kubectl exec -it --context {K8S_CONTEXT} --namespace={NAMESPACE} {donor_pod} -- bash -c 'pecl install xdebug && docker-php-ext-enable xdebug'"
    success, output = run_command(install_command, desc="Installing Xdebug")
    if success:
        print("Xdebug instalado exitosamente.")
        return True
    else:
        # Imprime el error si la instalación falla
        print(f"Error instalando Xdebug: {output}", file=sys.stderr)
        return False

def run_webgrind():
    """Run Webgrind in a Docker container to analyze profiling traces."""
    # Check if cachegrind directory exists
    if not os.path.exists('./cachegrind'):
        print("Error: cachegrind directory not found. Please download profiles first.", file=sys.stderr)
        return False
        
    # Use absolute path for Docker volume mount
    cachegrind_path = os.path.abspath('./cachegrind')
    command = f"docker run -it --rm -v \"{cachegrind_path}:/tmp\" --platform=linux/amd64 -p 8003:80 jokkedk/webgrind:latest"
    
    success, output = run_command(command, desc="Running Webgrind")
    if success:
        print("Webgrind running.")
        return True
    else:
        print(f"Failed to run Webgrind: {output}", file=sys.stderr)
        return False


def main():
    """Main entry point for the script."""
    if len(sys.argv) < 2 or sys.argv[1] == "help":
        print("Usage: script.py [COMMAND]\nCommands:\n  help               Show this help message\n  enable-profiling   Enable Xdebug profiling in the pod\n  disable-profiling  Disable Xdebug profiling, restoring previous configuration\n  download-profiles  Download Xdebug profiling traces\n  install-xdebug     Install Xdebug in the pod, if not already installed\n  run-webgrind       Run Webgrind in a Docker container to analyze profiling traces")
        return
    
    # Validate command
    valid_commands = ["enable-profiling", "disable-profiling", "download-profiles", "install-xdebug", "run-webgrind"]
    command = sys.argv[1]
    
    if command not in valid_commands:
        print(f"Invalid command: {command}", file=sys.stderr)
        print(f"Valid commands: {', '.join(valid_commands)}")
        sys.exit(1)
    
    # For run-webgrind, we don't need a pod
    if command == "run-webgrind":
        success = run_webgrind()
        sys.exit(0 if success else 1)
    
    # For all other commands, we need a pod
    donor_pod = pick_running_pod()
    print(f"Selected Pod: {donor_pod}")
    if not donor_pod:
        print("No suitable pod found. Exiting.", file=sys.stderr)
        sys.exit(1)
    
    success = False
    if command == "enable-profiling":
        success = enable_profiling(donor_pod)
    elif command == "disable-profiling":
        success = disable_profiling(donor_pod)
    elif command == "download-profiles":
        success = download_profiles(donor_pod)
    elif command == "install-xdebug":
        success = install_xdebug(donor_pod)
    
    sys.exit(0 if success else 1)


#Uncomment the call to main when running the script directly
if __name__ == "__main__":
    main()
