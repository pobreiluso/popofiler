import subprocess
import sys
import os
import re
from tqdm import tqdm
import time
import random
import string
import colorama
import shlex
from typing import Optional, Tuple, List

# Constants for Kubernetes and profiling configuration
# These should be configured before use
K8S_CONTEXT = os.getenv('K8S_CONTEXT', 'k8s_context')
PROJECT_NAME = os.getenv('PROJECT_NAME', 'project-name')
POD_NAME_ANTI_PATTERN = os.getenv('POD_NAME_ANTI_PATTERN', 'anti-pattern')
NAMESPACE = os.getenv('NAMESPACE', 'namespace-name')

# Security: Validate configuration values
KUBERNETES_NAME_PATTERN = re.compile(r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$')
KUBERNETES_LABEL_PATTERN = re.compile(r'^[a-z0-9A-Z]([-a-z0-9A-Z_.]*[a-z0-9A-Z])?$')

def generate_trace_key() -> str:
    """Generate a random key for tracing purposes."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=64))

def validate_kubernetes_name(name: str) -> bool:
    """Validate Kubernetes resource names to prevent injection attacks."""
    if not name or len(name) > 63:
        return False
    return bool(KUBERNETES_NAME_PATTERN.match(name))

def validate_configuration() -> bool:
    """Validate that all required configuration is properly set."""
    required_configs = {
        'K8S_CONTEXT': K8S_CONTEXT,
        'PROJECT_NAME': PROJECT_NAME, 
        'POD_NAME_ANTI_PATTERN': POD_NAME_ANTI_PATTERN,
        'NAMESPACE': NAMESPACE
    }
    
    placeholder_values = {'k8s_context', 'project-name', 'anti-pattern', 'namespace-name'}
    
    for config_name, config_value in required_configs.items():
        if not config_value or config_value in placeholder_values:
            print(f"Error: {config_name} must be configured with a valid value.", file=sys.stderr)
            return False
            
    # Validate Kubernetes names
    if not validate_kubernetes_name(NAMESPACE):
        print(f"Error: Invalid namespace name: {NAMESPACE}", file=sys.stderr)
        return False
        
    return True

def run_command(command: List[str], desc: str = "Running Command") -> Tuple[bool, str]:
    """
    Ejecuta un comando en el sistema y captura su salida, mostrando una barra de progreso con color.
    
    SECURITY: Only accepts command as list to prevent shell injection attacks.

    Args:
        command (List[str]): El comando a ejecutar como lista de argumentos.
        desc (str): Descripción del comando para mostrar.

    Returns:
        Tuple[bool, str]: Una tupla conteniendo un booleano que indica éxito, y la salida del comando o el mensaje de error.
    """
    print(f"{desc}: ")
    colorama.init()
    process = None
    try:
        # Security: Only accept command as list to prevent injection
        if not isinstance(command, list):
            raise ValueError("Command must be provided as a list of arguments for security reasons")
        
        cmd_args = command
        
        # Validate that kubectl is the only allowed command for this tool
        if cmd_args and cmd_args[0] not in ['kubectl', 'docker', 'php']:
            raise ValueError(f"Command '{cmd_args[0]}' is not allowed")

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


def pick_running_pod() -> Optional[str]:
    """
    Selecciona un pod en ejecución basado en los criterios definidos.
    
    Returns:
        str or None: El nombre del pod seleccionado o None si no se encuentra ninguno.
    """
    # Security: Validate inputs before using in command
    if not validate_kubernetes_name(NAMESPACE):
        print(f"Error: Invalid namespace name: {NAMESPACE}", file=sys.stderr)
        return None
    
    # Security: Use command list format to prevent injection
    command = [
        "kubectl", 
        "--context", K8S_CONTEXT,
        "get", "pods",
        "--field-selector=status.phase==Running",
        "--namespace", NAMESPACE
    ]
    print("command = ", ' '.join(command))
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
                # Security: Validate pod name before returning
                if validate_kubernetes_name(pod_name):
                    return pod_name
                else:
                    print(f"Warning: Invalid pod name format: {pod_name}", file=sys.stderr)
                    continue
    
    print(f"No suitable pod found with project name '{PROJECT_NAME}' excluding pattern '{POD_NAME_ANTI_PATTERN}'")
    return None



def execute_profiling_commands(commands: List[List[str]]) -> bool:
    """
    Execute a list of commands for enabling or disabling profiling.

    Args:
        commands (List[List[str]]): A list of command arrays to be executed securely.
        
    Returns:
        bool: True if all commands executed successfully, False otherwise.
    """
    if not isinstance(commands, list):
        print("Error: Commands must be provided as a list", file=sys.stderr)
        return False
        
    for i, command in enumerate(commands, 1):
        if not isinstance(command, list):
            print(f"Error: Command {i} must be a list for security", file=sys.stderr)
            return False
            
        success, output = run_command(command, desc=f"Executing Command {i}/{len(commands)}")
        if not success:
            print(f"Command failed: {' '.join(command) if isinstance(command, list) else str(command)}")
            print(f"Error output: {output}")
            return False
    print("Profiling configuration updated.")
    return True


def enable_profiling(donor_pod: str) -> bool:
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
    
    # Security: Validate pod name
    if not validate_kubernetes_name(donor_pod):
        print(f"Error: Invalid pod name: {donor_pod}", file=sys.stderr)
        return False
        
    trace_key = generate_trace_key()
    
    # Security: Use command arrays instead of f-strings to prevent injection
    commands = [
        [
            "kubectl", "cp", 
            "--context", K8S_CONTEXT,
            "--namespace", NAMESPACE,
            f"{donor_pod}:/usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini",
            "./docker-php-ext-xdebug.ini-backup"
        ],
        [
            "kubectl", "exec", "-it",
            "--context", K8S_CONTEXT,
            "--namespace", NAMESPACE,
            donor_pod, "--",
            "bash", "-c",
            'echo -e "zend_extension=xdebug\\nxdebug.mode=profile\\nxdebug.output_dir=/tmp/cachegrind/\\nxdebug.start_with_request=trigger" > /usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini'
        ],
        [
            "kubectl", "exec", "-it",
            "--context", K8S_CONTEXT,
            "--namespace", NAMESPACE,
            donor_pod, "--",
            "bash", "-c",
            "mkdir -p /tmp/cachegrind/ && chown www-data:www-data /tmp/cachegrind/"
        ],
        [
            "kubectl", "exec", "-it",
            "--context", K8S_CONTEXT,
            "--namespace", NAMESPACE,
            donor_pod, "--",
            "bash", "-c",
            "pkill -USR2 php-fpm"
        ]
    ]
    
    success = execute_profiling_commands(commands)
    if success:
        print(f"XDEBUG_TRIGGER: {trace_key}")
        print("Profiling enabled.")
    return success


def disable_profiling(donor_pod: str) -> bool:
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
    
    # Security: Validate pod name
    if not validate_kubernetes_name(donor_pod):
        print(f"Error: Invalid pod name: {donor_pod}", file=sys.stderr)
        return False
    
    # Security: Validate backup file exists before attempting to restore
    backup_file = "./docker-php-ext-xdebug.ini-backup"
    if not os.path.exists(backup_file):
        print(f"Error: Backup file not found: {backup_file}", file=sys.stderr)
        print("Cannot restore original configuration. Please run 'enable-profiling' first.")
        return False
        
    # Security: Use command arrays instead of f-strings to prevent injection
    commands = [
        [
            "kubectl", "cp",
            "--context", K8S_CONTEXT,
            "--namespace", NAMESPACE,
            backup_file,
            f"{donor_pod}:/usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini"
        ],
        [
            "kubectl", "exec",
            "--context", K8S_CONTEXT,
            "-it",
            "--namespace", NAMESPACE,
            donor_pod, "--",
            "bash", "-c",
            "pkill -USR2 php-fpm"
        ]
    ]
    
    success = execute_profiling_commands(commands)
    if success:
        print("Profiling disabled and configuration restored.")
    return success


def download_profiles(donor_pod: str) -> bool:
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
    
    # Security: Validate pod name
    if not validate_kubernetes_name(donor_pod):
        print(f"Error: Invalid pod name: {donor_pod}", file=sys.stderr)
        return False
        
    # Security: Use command array instead of f-string to prevent injection
    command = [
        "kubectl", "cp",
        "--context", K8S_CONTEXT,
        "--namespace", NAMESPACE,
        f"{donor_pod}:/tmp/cachegrind/.",
        "./cachegrind/"
    ]
    
    success, output = run_command(command, desc="Downloading profiles")
    if success:
        print("Profiles downloaded.")
    else:
        print(f"Failed to download profiles: {output}")
    return success


def install_xdebug(donor_pod: str) -> bool:
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
    
    # Security: Validate pod name
    if not validate_kubernetes_name(donor_pod):
        print(f"Error: Invalid pod name: {donor_pod}", file=sys.stderr)
        return False
        
    # Security: Use command array instead of f-string to prevent injection
    check_command = [
        "kubectl", "exec", "-it",
        "--context", K8S_CONTEXT,
        "--namespace", NAMESPACE,
        donor_pod, "--",
        "php", "-m"
    ]
    
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
    
    # Security: Use command array instead of f-string to prevent injection
    install_command = [
        "kubectl", "exec", "-it",
        "--context", K8S_CONTEXT,
        "--namespace", NAMESPACE,
        donor_pod, "--",
        "bash", "-c",
        "pecl install xdebug && docker-php-ext-enable xdebug"
    ]
    
    success, output = run_command(install_command, desc="Installing Xdebug")
    
    if success:
        print("Xdebug instalado exitosamente.")
        return True
    else:
        print(f"Error instalando Xdebug: {output}")
        return False

def run_webgrind() -> bool:
    """
    Ejecuta Webgrind en un contenedor Docker para analizar trazas de perfilado.
    
    Returns:
        bool: True si se ejecutó correctamente, False en caso contrario.
    """
    import os
    
    cachegrind_path = os.path.join(os.getcwd(), "cachegrind")
    
    # Security: Validate that the path exists and is a directory
    if not os.path.exists(cachegrind_path):
        print(f"Error: Cachegrind directory not found at {cachegrind_path}")
        print("Please run 'download-profiles' first to download the profile files.")
        return False
        
    if not os.path.isdir(cachegrind_path):
        print(f"Error: {cachegrind_path} is not a directory")
        return False
    
    # Security: Validate that the path is within expected bounds to prevent path traversal
    try:
        cachegrind_realpath = os.path.realpath(cachegrind_path)
        current_dir_realpath = os.path.realpath(os.getcwd())
        if not cachegrind_realpath.startswith(current_dir_realpath):
            print(f"Error: Invalid cachegrind path detected: {cachegrind_path}")
            return False
    except (OSError, ValueError) as e:
        print(f"Error validating cachegrind path: {e}", file=sys.stderr)
        return False
    
    # Security: Use command array instead of f-string to prevent injection
    command = [
        "docker", "run",
        "-it", "--rm",
        "-v", f"{cachegrind_path}:/tmp",
        "--platform=linux/amd64",
        "-p", "8003:80",
        "jokkedk/webgrind:latest"
    ]
    
    success, output = run_command(command, desc="Running Webgrind")
    
    if success:
        print("Webgrind running on http://localhost:8003")
        print("Press Ctrl+C to stop the container.")
    else:
        print(f"Failed to run Webgrind: {output}")
    
    return success


def main() -> None:
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
        print("Note: Configure environment variables K8S_CONTEXT, PROJECT_NAME, POD_NAME_ANTI_PATTERN, and NAMESPACE")
        print("or modify the constants at the top of this script.")
        return
        
    # Validate configuration before proceeding
    if not validate_configuration():
        print("Error: Configuration validation failed.", file=sys.stderr)
        sys.exit(1)
    
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
