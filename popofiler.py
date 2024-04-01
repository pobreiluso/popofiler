import subprocess
import sys
from tqdm import tqdm
import time
import random
import string
import colorama

# Constants for Kubernetes and profiling configuration
K8S_CONTEXT = 'k8s_context'
PROJECT_NAME = 'project-name'
POD_NAME_ANTI_PATTERN = 'anti-pattern'
NAMESPACE = 'namespace-name'
TRACE_RANDOM_KEY = ''.join(random.choices(
    string.ascii_letters + string.digits, k=64))

def run_command(command, desc="Running Command"):
    """
    Ejecuta un comando en el sistema y captura su salida, mostrando una barra de progreso con color.

    Args:
        command (str): El comando a ejecutar.

    Returns:
        tuple: Una tupla conteniendo un booleano que indica éxito, y la salida del comando o el mensaje de error.
    """
    print(f"{desc}: ")
    colorama.init()  # Inicializa colorama para colores en la terminal
    try:
        # Inicializa la barra de progreso
        with tqdm(total=100, desc="Ejecutando comando", bar_format="{l_bar}%s{bar}%s{r_bar}" % (colorama.Fore.BLUE, colorama.Fore.RESET)) as pbar:
            # Ejecuta el comando
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, text=True)

            # Debido a que no sabemos el progreso real del comando, la barra se actualizará de manera artificial
            while True:
                if process.poll() is not None:  # Verifica si el comando ha terminado
                    pbar.n = 100
                    pbar.last_print_n = 100
                    pbar.refresh()
                    break
                time.sleep(0.05)  # Espera un poco antes de la siguiente actualización
                pbar.update(1)  # Actualiza la barra de progreso

        # Captura la salida y errores del comando
        stdout, stderr = process.communicate()

        # Cierra colorama
        colorama.deinit()

        # Maneja el resultado del comando
        if process.returncode == 0:
            return True, stdout  # Retorna True y la salida en caso de éxito
        else:
            # En caso de error, imprime y retorna el error
            print(f"Error: {stderr}  {command}", file=sys.stderr)
            return False, stderr  # Retorna False y el error
    except subprocess.CalledProcessError as e:
        print(f"Command failed with {e.returncode}", file=sys.stderr)
        return False, str(e)
    except KeyboardInterrupt:
        print("KeyboardInterrupt: Process terminated by user.", file=sys.stderr)
        return False, "KeyboardInterrupt: Process terminated by user."


def pick_running_pod():
    command = f"kubectl --context {K8S_CONTEXT} get pods --field-selector=status.phase==Running --namespace {NAMESPACE}"
    print("command = ", command)
    success, output = run_command(command, desc="Listing Running Pods")
    if not success:
        print(f"Error: {output}")
        return None

    # Filtra la salida para obtener el pod deseado
    for line in output.splitlines():
        if PROJECT_NAME in line and POD_NAME_ANTI_PATTERN not in line:
            pod_name = line.split()[0]  # Asume que el nombre del pod está en la primera columna
            return pod_name
    return None



def execute_profiling_commands(commands):
    """
    Execute a list of commands for enabling or disabling profiling.

    Args:
        commands (list): A list of shell commands to be executed.
    """
    for command in commands:
        success, _ = run_command(command, desc="Executing Command")
        if not success:
            return
    print("Profiling configuration updated.")


def enable_profiling(donor_pod):
    commands = [
        f"kubectl cp --context {K8S_CONTEXT} --namespace={NAMESPACE} {donor_pod}:/usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini ./docker-php-ext-xdebug.ini-backup",
        f"kubectl exec -it --context {K8S_CONTEXT} --namespace={NAMESPACE} {donor_pod} -- bash -c 'echo -e \"zend_extension=xdebug\\nxdebug.mode=profile\\nxdebug.output_dir=/tmp/cachegrind/\\nxdebug.start_with_request=trigger\" > /usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini'",
        f"kubectl exec -it --context {K8S_CONTEXT} --namespace={NAMESPACE} {donor_pod} -- bash -c 'mkdir -p /tmp/cachegrind/ && chown www-data:www-data /tmp/cachegrind/'",
        f"kubectl exec -it --context {K8S_CONTEXT} --namespace={NAMESPACE} {donor_pod} -- bash -c 'pkill -USR2 php-fpm'"
    ]
    execute_profiling_commands(commands)
    print(f"XDEBUG_TRIGGER: {TRACE_RANDOM_KEY}")
    print("Profiling enabled.")


def disable_profiling(donor_pod):
    commands = [
        f"kubectl cp --context {K8S_CONTEXT} --namespace={NAMESPACE} ./docker-php-ext-xdebug.ini-backup {donor_pod}:/usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini",
        f"kubectl exec --context {K8S_CONTEXT} -it --namespace={NAMESPACE} {donor_pod} -- bash -c 'pkill -USR2 php-fpm'"
    ]
    execute_profiling_commands(commands)
    print("Profiling disabled and configuration restored.")


def download_profiles(donor_pod):
    success, _ = run_command(f"kubectl cp --context {K8S_CONTEXT} --namespace={NAMESPACE} {donor_pod}:/tmp/cachegrind/. ./cachegrind/")
    if success:
        print("Profiles downloaded.")


def install_xdebug(donor_pod):
    # Primero verifica si Xdebug ya está instalado ejecutando un comando que intente localizarlo
    check_command = f"kubectl exec -it --context {K8S_CONTEXT} --namespace={NAMESPACE} {donor_pod} -- php -m | grep xdebug"
    check_success, check_output = run_command(check_command, desc="Checking Xdebug installation")

    # Si encuentra 'xdebug' en la salida, asume que ya está instalado y sale
    if 'xdebug' in check_output.lower():
        print("Xdebug ya está instalado.")
        return

    # Si no encuentra Xdebug, procede con la instalación
    install_command = f"kubectl exec -it --context {K8S_CONTEXT} --namespace={NAMESPACE} {donor_pod} -- bash -c 'pecl install xdebug && docker-php-ext-enable xdebug'"
    success, output = run_command(install_command, desc="Installing Xdebug")
    if success:
        print("Xdebug instalado exitosamente.")
    else:
        # Imprime el error si la instalación falla
        print(f"Error instalando Xdebug: {output}")

def run_webgrind():
    success, _ = run_command("docker run -it --rm -v \"$(pwd)/cachegrind/:/tmp\" --platform=linux/amd64 -p 8003:80 jokkedk/webgrind:latest", shell=True, progress_desc="Running Webgrind")
    if success:
        print("Webgrind running.")


def main():
    if len(sys.argv) < 2 or sys.argv[1] == "help":
        print("Usage: script.py [COMMAND]\nCommands:\n  help               Show this help message\n  enable-profiling   Enable Xdebug profiling in the pod\n  disable-profiling  Disable Xdebug profiling, restoring previous configuration\n  download-profiles  Download Xdebug profiling traces\n  install-xdebug     Install Xdebug in the pod, if not already installed\n  run-webgrind       Run Webgrind in a Docker container to analyze profiling traces")
        return
    donor_pod = pick_running_pod()
    print(f"Selected Pod: {donor_pod}")
    if not donor_pod:
        return
    if sys.argv[1] == "enable-profiling":
        enable_profiling(donor_pod)
    elif sys.argv[1] == "disable-profiling":
        disable_profiling(donor_pod)
    elif sys.argv[1] == "download-profiles":
        download_profiles(donor_pod)
    elif sys.argv[1] == "install-xdebug":
        install_xdebug(donor_pod)
    elif sys.argv[1] == "run-webgrind":
        run_webgrind()
    else:
        print(f"Invalid command: {sys.argv[1]}")
        sys.exit(1)


#Uncomment the call to main when running the script directly
if __name__ == "__main__":
    main()
