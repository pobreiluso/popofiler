import subprocess
import sys
from tqdm import tqdm
import time
import random
import string
import colorama
import shlex

# Constants for Kubernetes and profiling configuration
K8S_CONTEXT = 'k8s_context'
PROJECT_NAME = 'project-name'
POD_NAME_ANTI_PATTERN = 'anti-pattern'
NAMESPACE = 'namespace-name'

def generate_trace_key():
    """Generate a random key for tracing purposes."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=64))

def run_command(command, desc="Running Command"):
    """
    Ejecuta un comando en el sistema y captura su salida, mostrando una barra de progreso con color.

    Args:
        command (str or list): El comando a ejecutar como string o lista de argumentos.

    Returns:
        tuple: Una tupla conteniendo un booleano que indica éxito, y la salida del comando o el mensaje de error.
    """
    print(f"{desc}: ")
    colorama.init()
    process = None
    try:
        # Convierte string a lista de argumentos de manera segura
        if isinstance(command, str):
            cmd_args = shlex.split(command)
        else:
            cmd_args = command

        # Inicializa la barra de progreso
        with tqdm(total=100, desc="Ejecutando comando", bar_format="{l_bar}%s{bar}%s{r_bar}" % (colorama.Fore.BLUE, colorama.Fore.RESET)) as pbar:
            # Ejecuta el comando de manera segura sin shell=True
            process = subprocess.Popen(cmd_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            # Debido a que no sabemos el progreso real del comando, la barra se actualizará de manera artificial
            while process.poll() is None:  # Sigue mientras el proceso esté ejecutándose
                time.sleep(0.05)
                if pbar.n < 99:  # Evita que llegue a 100 antes de terminar
                    pbar.update(1)

            # Una vez terminado, completa la barra
            pbar.n = 100
            pbar.last_print_n = 100
            pbar.refresh()

        # Captura la salida y errores del comando después de que termine
        stdout, stderr = process.communicate()

        # Maneja el resultado del comando
        if process.returncode == 0:
            return True, stdout
        else:
            error_msg = stderr or f"Command failed with return code {process.returncode}"
            print(f"Error: {error_msg}", file=sys.stderr)
            return False, error_msg
            
    except (subprocess.CalledProcessError, OSError, ValueError) as e:
        print(f"Command execution failed: {str(e)}", file=sys.stderr)
        return False, str(e)
    except KeyboardInterrupt:
        if process:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        print("KeyboardInterrupt: Process terminated by user.", file=sys.stderr)
        return False, "KeyboardInterrupt: Process terminated by user."
    finally:
        colorama.deinit()


def pick_running_pod():
    """
    Selecciona un pod en ejecución basado en los criterios definidos.
    
    Returns:
        str or None: El nombre del pod seleccionado o None si no se encuentra ninguno.
    """
    command = f"kubectl --context {K8S_CONTEXT} get pods --field-selector=status.phase==Running --namespace {NAMESPACE}"
    print("command = ", command)
    success, output = run_command(command, desc="Listing Running Pods")
    if not success:
        print(f"Error: {output}")
        return None

    if not output or not output.strip():
        print("No pods found in the specified namespace")
        return None

    # Filtra la salida para obtener el pod deseado
    lines = output.strip().splitlines()
    # Salta la línea de headers si existe
    pod_lines = lines[1:] if lines and 'NAME' in lines[0] else lines
    
    for line in pod_lines:
        if PROJECT_NAME in line and POD_NAME_ANTI_PATTERN not in line:
            parts = line.split()
            if parts:  # Verifica que la línea tenga contenido
                pod_name = parts[0]
                return pod_name
    
    print(f"No suitable pod found with project name '{PROJECT_NAME}' excluding pattern '{POD_NAME_ANTI_PATTERN}'")
    return None



def execute_profiling_commands(commands):
    """
    Execute a list of commands for enabling or disabling profiling.

    Args:
        commands (list): A list of shell commands to be executed.
        
    Returns:
        bool: True if all commands executed successfully, False otherwise.
    """
    for i, command in enumerate(commands, 1):
        success, output = run_command(command, desc=f"Executing Command {i}/{len(commands)}")
        if not success:
            print(f"Command failed: {command}")
            print(f"Error output: {output}")
            return False
    print("Profiling configuration updated.")
    return True


def enable_profiling(donor_pod):
    """
    Habilita el perfilado de Xdebug en el pod especificado.
    
    Args:
        donor_pod (str): El nombre del pod donde habilitar el perfilado.
        
    Returns:
        bool: True si se habilitó correctamente, False en caso contrario.
    """
    if not donor_pod:
        print("Error: No pod specified")
        return False
        
    trace_key = generate_trace_key()
    commands = [
        f"kubectl cp --context {K8S_CONTEXT} --namespace={NAMESPACE} {donor_pod}:/usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini ./docker-php-ext-xdebug.ini-backup",
        f"kubectl exec -it --context {K8S_CONTEXT} --namespace={NAMESPACE} {donor_pod} -- bash -c 'echo -e \"zend_extension=xdebug\\nxdebug.mode=profile\\nxdebug.output_dir=/tmp/cachegrind/\\nxdebug.start_with_request=trigger\" > /usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini'",
        f"kubectl exec -it --context {K8S_CONTEXT} --namespace={NAMESPACE} {donor_pod} -- bash -c 'mkdir -p /tmp/cachegrind/ && chown www-data:www-data /tmp/cachegrind/'",
        f"kubectl exec -it --context {K8S_CONTEXT} --namespace={NAMESPACE} {donor_pod} -- bash -c 'pkill -USR2 php-fpm'"
    ]
    
    success = execute_profiling_commands(commands)
    if success:
        print(f"XDEBUG_TRIGGER: {trace_key}")
        print("Profiling enabled.")
    return success


def disable_profiling(donor_pod):
    """
    Deshabilita el perfilado de Xdebug en el pod especificado.
    
    Args:
        donor_pod (str): El nombre del pod donde deshabilitar el perfilado.
        
    Returns:
        bool: True si se deshabilitó correctamente, False en caso contrario.
    """
    if not donor_pod:
        print("Error: No pod specified")
        return False
        
    commands = [
        f"kubectl cp --context {K8S_CONTEXT} --namespace={NAMESPACE} ./docker-php-ext-xdebug.ini-backup {donor_pod}:/usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini",
        f"kubectl exec --context {K8S_CONTEXT} -it --namespace={NAMESPACE} {donor_pod} -- bash -c 'pkill -USR2 php-fpm'"
    ]
    
    success = execute_profiling_commands(commands)
    if success:
        print("Profiling disabled and configuration restored.")
    return success


def download_profiles(donor_pod):
    """
    Descarga los perfiles de Xdebug del pod especificado.
    
    Args:
        donor_pod (str): El nombre del pod del cual descargar los perfiles.
        
    Returns:
        bool: True si se descargaron correctamente, False en caso contrario.
    """
    if not donor_pod:
        print("Error: No pod specified")
        return False
        
    success, output = run_command(f"kubectl cp --context {K8S_CONTEXT} --namespace={NAMESPACE} {donor_pod}:/tmp/cachegrind/. ./cachegrind/", desc="Downloading profiles")
    if success:
        print("Profiles downloaded.")
    else:
        print(f"Failed to download profiles: {output}")
    return success


def install_xdebug(donor_pod):
    """
    Instala Xdebug en el pod especificado si no está ya instalado.
    
    Args:
        donor_pod (str): El nombre del pod donde instalar Xdebug.
        
    Returns:
        bool: True si Xdebug está disponible (ya instalado o recién instalado), False en caso contrario.
    """
    if not donor_pod:
        print("Error: No pod specified")
        return False
        
    # Primero verifica si Xdebug ya está instalado
    check_command = f"kubectl exec -it --context {K8S_CONTEXT} --namespace={NAMESPACE} {donor_pod} -- php -m"
    check_success, check_output = run_command(check_command, desc="Checking Xdebug installation")

    if not check_success:
        print(f"Error checking PHP modules: {check_output}")
        return False

    # Si encuentra 'xdebug' en la salida, asume que ya está instalado
    if 'xdebug' in check_output.lower():
        print("Xdebug ya está instalado.")
        return True

    # Si no encuentra Xdebug, procede con la instalación
    print("Xdebug no encontrado, procediendo con la instalación...")
    install_command = f"kubectl exec -it --context {K8S_CONTEXT} --namespace={NAMESPACE} {donor_pod} -- bash -c 'pecl install xdebug && docker-php-ext-enable xdebug'"
    success, output = run_command(install_command, desc="Installing Xdebug")
    
    if success:
        print("Xdebug instalado exitosamente.")
        return True
    else:
        print(f"Error instalando Xdebug: {output}")
        return False

def run_webgrind():
    """
    Ejecuta Webgrind en un contenedor Docker para analizar trazas de perfilado.
    
    Returns:
        bool: True si se ejecutó correctamente, False en caso contrario.
    """
    import os
    cachegrind_path = os.path.join(os.getcwd(), "cachegrind")
    
    # Verifica que el directorio de cachegrind existe
    if not os.path.exists(cachegrind_path):
        print(f"Error: Cachegrind directory not found at {cachegrind_path}")
        print("Please run 'download-profiles' first to download the profile files.")
        return False
    
    command = f"docker run -it --rm -v {cachegrind_path}:/tmp --platform=linux/amd64 -p 8003:80 jokkedk/webgrind:latest"
    success, output = run_command(command, desc="Running Webgrind")
    
    if success:
        print("Webgrind running on http://localhost:8003")
        print("Press Ctrl+C to stop the container.")
    else:
        print(f"Failed to run Webgrind: {output}")
    
    return success


def main():
    """Función principal que maneja los argumentos de línea de comandos y ejecuta las operaciones correspondientes."""
    if len(sys.argv) < 2 or sys.argv[1] == "help":
        print("Usage: python popofiler.py [COMMAND]")
        print("Commands:")
        print("  help               Show this help message")
        print("  enable-profiling   Enable Xdebug profiling in the pod")
        print("  disable-profiling  Disable Xdebug profiling, restoring previous configuration")
        print("  download-profiles  Download Xdebug profiling traces")
        print("  install-xdebug     Install Xdebug in the pod, if not already installed")
        print("  run-webgrind       Run Webgrind in a Docker container to analyze profiling traces")
        print()
        print("Note: Make sure to configure K8S_CONTEXT, PROJECT_NAME, POD_NAME_ANTI_PATTERN, and NAMESPACE constants")
        return
    
    command = sys.argv[1]
    
    # Para run-webgrind, no necesitamos un pod
    if command == "run-webgrind":
        success = run_webgrind()
        sys.exit(0 if success else 1)
    
    # Para otros comandos, necesitamos encontrar un pod
    donor_pod = pick_running_pod()
    print(f"Selected Pod: {donor_pod}")
    if not donor_pod:
        print("Error: No suitable pod found. Please check your configuration.")
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
    else:
        print(f"Invalid command: {command}")
        print("Use 'python popofiler.py help' to see available commands.")
        sys.exit(1)
    
    # Exit with appropriate code based on success
    sys.exit(0 if success else 1)


#Uncomment the call to main when running the script directly
if __name__ == "__main__":
    main()
