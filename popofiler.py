import subprocess
import sys
import os
import re
import secrets
import shlex
from tqdm import tqdm
import time
import colorama
import logging

# Configure secure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def validate_k8s_name(name, field_name):
    """Validate Kubernetes resource names to prevent injection attacks."""
    if not name or not isinstance(name, str):
        raise ValueError(f"Invalid {field_name}: must be a non-empty string")
    
    # Kubernetes naming constraints: lowercase alphanumeric plus hyphens
    if not re.match(r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$', name) and name != 'default':
        # Allow some flexibility for contexts that might have different patterns
        if not re.match(r'^[a-zA-Z0-9._-]+$', name):
            raise ValueError(f"Invalid {field_name}: {name} contains invalid characters")
    return name

def validate_project_name(name):
    """Validate project names with more flexible patterns."""
    if not name or not isinstance(name, str):
        raise ValueError("Project name must be a non-empty string")
    
    # Allow alphanumeric, hyphens, underscores
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        raise ValueError(f"Invalid project name: {name}")
    return name

# Constants for Kubernetes and profiling configuration with environment variable support
K8S_CONTEXT = validate_k8s_name(
    os.getenv('K8S_CONTEXT', 'k8s_context'), 'Kubernetes context'
)
PROJECT_NAME = validate_project_name(
    os.getenv('PROJECT_NAME', 'project-name')
)
POD_NAME_ANTI_PATTERN = os.getenv('POD_NAME_ANTI_PATTERN', 'anti-pattern')
NAMESPACE = validate_k8s_name(
    os.getenv('NAMESPACE', 'namespace-name'), 'namespace'
)

# Generate cryptographically secure random key
TRACE_RANDOM_KEY = secrets.token_urlsafe(48)

def run_command(command_args, desc="Running Command"):
    """
    Executes a system command securely and captures its output with progress display.

    Args:
        command_args (list): List of command arguments for secure execution.
        desc (str): Description of the command being executed.

    Returns:
        tuple: A tuple containing success boolean and command output or error message.
    """
    print(f"{desc}: ")
    colorama.init()
    
    # Log command execution (without sensitive details)
    logger.info(f"Executing command: {command_args[0]}")
    
    try:
        with tqdm(total=100, desc="Executing command", 
                 bar_format="{l_bar}%s{bar}%s{r_bar}" % (colorama.Fore.BLUE, colorama.Fore.RESET)) as pbar:
            
            # Execute command securely without shell=True
            process = subprocess.Popen(
                command_args, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True
            )

            # Progress bar updates
            while True:
                if process.poll() is not None:
                    pbar.n = 100
                    pbar.last_print_n = 100
                    pbar.refresh()
                    break
                time.sleep(0.05)
                pbar.update(1)

        stdout, stderr = process.communicate()
        colorama.deinit()

        if process.returncode == 0:
            logger.info("Command executed successfully")
            return True, stdout
        else:
            # Sanitized error reporting - don't expose full command
            logger.error(f"Command failed with return code {process.returncode}")
            print(f"Command execution failed with return code {process.returncode}", file=sys.stderr)
            return False, stderr
            
    except FileNotFoundError as e:
        error_msg = "Required command not found. Please ensure kubectl/docker is installed."
        logger.error(error_msg)
        print(error_msg, file=sys.stderr)
        return False, error_msg
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed with return code {e.returncode}")
        print(f"Command failed with return code {e.returncode}", file=sys.stderr)
        return False, str(e)
    except KeyboardInterrupt:
        logger.info("Process terminated by user")
        print("KeyboardInterrupt: Process terminated by user.", file=sys.stderr)
        return False, "KeyboardInterrupt: Process terminated by user."


def pick_running_pod():
    """Select a running pod based on project name and exclusion pattern."""
    command_args = [
        'kubectl', '--context', K8S_CONTEXT, 
        'get', 'pods', 
        '--field-selector=status.phase==Running',
        '--namespace', NAMESPACE
    ]
    
    success, output = run_command(command_args, desc="Listing Running Pods")
    if not success:
        logger.error("Failed to list running pods")
        print(f"Error listing pods")
        return None

    # Filter output to find the desired pod
    for line in output.splitlines():
        if PROJECT_NAME in line and POD_NAME_ANTI_PATTERN not in line:
            pod_name = line.split()[0]
            
            # Validate pod name format
            try:
                validate_k8s_name(pod_name, "pod name")
                return pod_name
            except ValueError as e:
                logger.warning(f"Invalid pod name found: {e}")
                continue
                
    logger.warning(f"No suitable pod found matching project name '{PROJECT_NAME}'")
    return None



def execute_profiling_commands(commands):
    """
    Execute a list of commands for enabling or disabling profiling.

    Args:
        commands (list): A list of command argument lists to be executed securely.
    """
    for command_args in commands:
        success, _ = run_command(command_args, desc="Executing Profiling Command")
        if not success:
            logger.error("Profiling command execution failed, aborting sequence")
            return False
    
    logger.info("Profiling configuration updated successfully")
    print("Profiling configuration updated.")
    return True


def enable_profiling(donor_pod):
    """Enable Xdebug profiling on the specified pod."""
    # Validate donor_pod name
    try:
        validate_k8s_name(donor_pod, "donor pod")
    except ValueError as e:
        logger.error(f"Invalid pod name: {e}")
        print(f"Error: Invalid pod name")
        return False
    
    # Secure command construction using argument lists
    commands = [
        # Backup current xdebug configuration
        ['kubectl', 'cp', '--context', K8S_CONTEXT, '--namespace', NAMESPACE,
         f'{donor_pod}:/usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini',
         './docker-php-ext-xdebug.ini-backup'],
        
        # Configure xdebug for profiling
        ['kubectl', 'exec', '-it', '--context', K8S_CONTEXT, '--namespace', NAMESPACE,
         donor_pod, '--', 'bash', '-c',
         'echo -e "zend_extension=xdebug\\nxdebug.mode=profile\\nxdebug.output_dir=/tmp/cachegrind/\\nxdebug.start_with_request=trigger" > /usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini'],
        
        # Create and set permissions for cachegrind directory
        ['kubectl', 'exec', '-it', '--context', K8S_CONTEXT, '--namespace', NAMESPACE,
         donor_pod, '--', 'bash', '-c',
         'mkdir -p /tmp/cachegrind/ && chown www-data:www-data /tmp/cachegrind/'],
        
        # Restart PHP-FPM
        ['kubectl', 'exec', '-it', '--context', K8S_CONTEXT, '--namespace', NAMESPACE,
         donor_pod, '--', 'bash', '-c', 'pkill -USR2 php-fpm']
    ]
    
    if execute_profiling_commands(commands):
        print(f"XDEBUG_TRIGGER: {TRACE_RANDOM_KEY}")
        print("Profiling enabled.")
        logger.info(f"Profiling enabled on pod {donor_pod}")
        return True
    return False


def disable_profiling(donor_pod):
    """Disable Xdebug profiling and restore original configuration."""
    # Validate donor_pod name
    try:
        validate_k8s_name(donor_pod, "donor pod")
    except ValueError as e:
        logger.error(f"Invalid pod name: {e}")
        print(f"Error: Invalid pod name")
        return False
    
    # Check if backup file exists
    if not os.path.exists('./docker-php-ext-xdebug.ini-backup'):
        logger.error("Backup configuration file not found")
        print("Error: Backup configuration file not found. Cannot restore.")
        return False
    
    commands = [
        # Restore backup configuration
        ['kubectl', 'cp', '--context', K8S_CONTEXT, '--namespace', NAMESPACE,
         './docker-php-ext-xdebug.ini-backup',
         f'{donor_pod}:/usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini'],
        
        # Restart PHP-FPM
        ['kubectl', 'exec', '--context', K8S_CONTEXT, '-it', '--namespace', NAMESPACE,
         donor_pod, '--', 'bash', '-c', 'pkill -USR2 php-fpm']
    ]
    
    if execute_profiling_commands(commands):
        print("Profiling disabled and configuration restored.")
        logger.info(f"Profiling disabled on pod {donor_pod}")
        return True
    return False


def download_profiles(donor_pod):
    """Download profiling traces from the pod."""
    # Validate donor_pod name
    try:
        validate_k8s_name(donor_pod, "donor pod")
    except ValueError as e:
        logger.error(f"Invalid pod name: {e}")
        print(f"Error: Invalid pod name")
        return False
    
    # Ensure local cachegrind directory exists
    os.makedirs('./cachegrind/', exist_ok=True)
    
    command_args = [
        'kubectl', 'cp', '--context', K8S_CONTEXT, '--namespace', NAMESPACE,
        f'{donor_pod}:/tmp/cachegrind/.',
        './cachegrind/'
    ]
    
    success, _ = run_command(command_args, desc="Downloading Profiles")
    if success:
        print("Profiles downloaded.")
        logger.info(f"Profiles downloaded from pod {donor_pod}")
        return True
    else:
        logger.error("Failed to download profiles")
        return False


def install_xdebug(donor_pod):
    """Install Xdebug on the specified pod if not already installed."""
    # Validate donor_pod name
    try:
        validate_k8s_name(donor_pod, "donor pod")
    except ValueError as e:
        logger.error(f"Invalid pod name: {e}")
        print(f"Error: Invalid pod name")
        return False
    
    # Check if Xdebug is already installed
    check_command_args = [
        'kubectl', 'exec', '-it', '--context', K8S_CONTEXT, '--namespace', NAMESPACE,
        donor_pod, '--', 'php', '-m'
    ]
    
    check_success, check_output = run_command(check_command_args, desc="Checking Xdebug installation")
    
    if check_success and 'xdebug' in check_output.lower():
        print("Xdebug is already installed.")
        logger.info(f"Xdebug already installed on pod {donor_pod}")
        return True

    # Install Xdebug if not found
    install_command_args = [
        'kubectl', 'exec', '-it', '--context', K8S_CONTEXT, '--namespace', NAMESPACE,
        donor_pod, '--', 'bash', '-c',
        'pecl install xdebug && docker-php-ext-enable xdebug'
    ]
    
    success, output = run_command(install_command_args, desc="Installing Xdebug")
    if success:
        print("Xdebug installed successfully.")
        logger.info(f"Xdebug installed successfully on pod {donor_pod}")
        return True
    else:
        logger.error(f"Xdebug installation failed on pod {donor_pod}")
        print("Error: Xdebug installation failed.")
        return False

def run_webgrind():
    """Run Webgrind in a Docker container to analyze profiling traces."""
    # Validate and create cachegrind directory
    cachegrind_path = os.path.abspath("./cachegrind/")
    if not os.path.exists(cachegrind_path):
        logger.warning("Cachegrind directory doesn't exist, creating it")
        os.makedirs(cachegrind_path, exist_ok=True)
    
    # Secure Docker command construction
    command_args = [
        'docker', 'run', '-it', '--rm',
        '-v', f'{cachegrind_path}:/tmp',
        '--platform=linux/amd64',
        '-p', '8003:80',
        'jokkedk/webgrind:latest'
    ]
    
    success, _ = run_command(command_args, desc="Running Webgrind")
    if success:
        print("Webgrind running on http://localhost:8003")
        logger.info("Webgrind container started successfully")
        return True
    else:
        logger.error("Failed to start Webgrind container")
        print("Error: Failed to start Webgrind container")
        return False


def main():
    """Main function to handle command line arguments and execute operations."""
    if len(sys.argv) < 2 or sys.argv[1] == "help":
        print("Usage: python popofiler.py [COMMAND]")
        print("Commands:")
        print("  help               Show this help message")
        print("  enable-profiling   Enable Xdebug profiling in the pod")
        print("  disable-profiling  Disable Xdebug profiling, restoring previous configuration")
        print("  download-profiles  Download Xdebug profiling traces")
        print("  install-xdebug     Install Xdebug in the pod, if not already installed")
        print("  run-webgrind       Run Webgrind in a Docker container to analyze profiling traces")
        print("\nEnvironment Variables:")
        print("  K8S_CONTEXT        Kubernetes context to use")
        print("  PROJECT_NAME       Project name for pod selection")
        print("  NAMESPACE          Kubernetes namespace")
        print("  POD_NAME_ANTI_PATTERN  Pattern to exclude from pod selection")
        return
    
    command = sys.argv[1]
    valid_commands = {
        'enable-profiling', 'disable-profiling', 'download-profiles',
        'install-xdebug', 'run-webgrind'
    }
    
    if command not in valid_commands:
        print(f"Invalid command: {command}")
        print("Use 'python popofiler.py help' to see available commands")
        sys.exit(1)
    
    # Commands that don't require a pod
    if command == 'run-webgrind':
        success = run_webgrind()
        sys.exit(0 if success else 1)
    
    # Commands that require pod selection
    try:
        donor_pod = pick_running_pod()
        if not donor_pod:
            logger.error("No suitable pod found")
            print("Error: No suitable pod found for the specified criteria")
            sys.exit(1)
        
        print(f"Selected Pod: {donor_pod}")
        
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
        
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        print(f"Configuration error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)


#Uncomment the call to main when running the script directly
if __name__ == "__main__":
    main()
