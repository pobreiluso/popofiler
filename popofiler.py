import subprocess
import sys
import time
import random
import string
from typing import Tuple, List, Optional, Dict, Any
from dataclasses import dataclass, field
import logging
from pathlib import Path
from contextlib import contextmanager
import json
import os

# Optional imports with fallbacks
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

try:
    import colorama
    HAS_COLORAMA = True
except ImportError:
    HAS_COLORAMA = False


class PopofilerConstants:
    """Application constants and default values."""
    
    # Default configuration values
    DEFAULT_K8S_CONTEXT = 'k8s_context'
    DEFAULT_PROJECT_NAME = 'project-name' 
    DEFAULT_POD_NAME_ANTI_PATTERN = 'anti-pattern'
    DEFAULT_NAMESPACE = 'namespace-name'
    DEFAULT_TRACE_KEY_LENGTH = 64
    
    # File paths
    BACKUP_FILENAME = 'docker-php-ext-xdebug.ini-backup'
    CACHEGRIND_DIR = './cachegrind/'
    CONFIG_FILENAME = 'popofiler-config.json'
    
    # Docker/Kubernetes paths
    XDEBUG_CONFIG_PATH = '/usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini'
    PROFILE_OUTPUT_DIR = '/tmp/cachegrind'
    
    # Commands
    WEBGRIND_IMAGE = 'jokkedk/webgrind:latest'
    WEBGRIND_PORT = 8003


class PopofilerError(Exception):
    """Base exception for Popofiler operations."""
    pass


class KubernetesError(PopofilerError):
    """Exception raised for Kubernetes operation errors."""
    pass


class XdebugError(PopofilerError):
    """Exception raised for Xdebug operation errors."""
    pass


class DockerError(PopofilerError):
    """Exception raised for Docker operation errors."""
    pass


@dataclass
class KubernetesConfig:
    """Configuration for Kubernetes operations."""
    context: str = field(default_factory=lambda: PopofilerConstants.DEFAULT_K8S_CONTEXT)
    project_name: str = field(default_factory=lambda: PopofilerConstants.DEFAULT_PROJECT_NAME)
    pod_name_anti_pattern: str = field(default_factory=lambda: PopofilerConstants.DEFAULT_POD_NAME_ANTI_PATTERN)
    namespace: str = field(default_factory=lambda: PopofilerConstants.DEFAULT_NAMESPACE)
    trace_random_key: str = field(init=False)
    
    def __post_init__(self) -> None:
        """Initialize derived configuration values."""
        self.trace_random_key = self._generate_trace_key()
    
    @classmethod
    def from_file(cls, config_path: Optional[Path] = None) -> 'KubernetesConfig':
        """Load configuration from JSON file."""
        if config_path is None:
            config_path = Path(PopofilerConstants.CONFIG_FILENAME)
        
        if not config_path.exists():
            return cls()
        
        try:
            with open(config_path, 'r') as f:
                config_data = json.load(f)
            return cls(**config_data)
        except (json.JSONDecodeError, TypeError) as e:
            logging.warning(f"Failed to load config from {config_path}: {e}")
            return cls()
    
    @classmethod
    def from_env(cls) -> 'KubernetesConfig':
        """Load configuration from environment variables."""
        return cls(
            context=os.getenv('POPOFILER_K8S_CONTEXT', PopofilerConstants.DEFAULT_K8S_CONTEXT),
            project_name=os.getenv('POPOFILER_PROJECT_NAME', PopofilerConstants.DEFAULT_PROJECT_NAME),
            pod_name_anti_pattern=os.getenv('POPOFILER_POD_ANTI_PATTERN', PopofilerConstants.DEFAULT_POD_NAME_ANTI_PATTERN),
            namespace=os.getenv('POPOFILER_NAMESPACE', PopofilerConstants.DEFAULT_NAMESPACE)
        )
    
    def to_file(self, config_path: Optional[Path] = None) -> None:
        """Save configuration to JSON file."""
        if config_path is None:
            config_path = Path(PopofilerConstants.CONFIG_FILENAME)
        
        config_data = {
            'context': self.context,
            'project_name': self.project_name,
            'pod_name_anti_pattern': self.pod_name_anti_pattern,
            'namespace': self.namespace
        }
        
        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=2)
    
    @staticmethod
    def _generate_trace_key(length: int = PopofilerConstants.DEFAULT_TRACE_KEY_LENGTH) -> str:
        """Generate a random trace key for profiling."""
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


class KubectlCommandBuilder:
    """Builder for kubectl commands."""
    
    def __init__(self, config: KubernetesConfig):
        self.config = config
    
    def build_base_command(self) -> str:
        """Build base kubectl command with context and namespace."""
        return f"kubectl --context {self.config.context} --namespace={self.config.namespace}"
    
    def build_exec_command(self, pod_name: str, command: str, interactive: bool = True) -> str:
        """Build kubectl exec command."""
        base_cmd = self.build_base_command()
        interactive_flag = "-it" if interactive else ""
        return f"{base_cmd} exec {interactive_flag} {pod_name} -- {command}"
    
    def build_copy_command(self, source: str, destination: str) -> str:
        """Build kubectl cp command."""
        base_cmd = self.build_base_command()
        return f"{base_cmd} cp {source} {destination}"
    
    def build_get_pods_command(self) -> str:
        """Build kubectl get pods command for running pods."""
        base_cmd = self.build_base_command()
        return f"{base_cmd} get pods --field-selector=status.phase==Running"


class ProgressBarManager:
    """Manages progress bar display for command execution."""
    
    def __init__(self) -> None:
        """Initialize the progress bar manager."""
        self._colorama_initialized = False
    
    @contextmanager
    def progress_bar(self, description: str):
        """Context manager for progress bar creation and cleanup."""
        if not HAS_TQDM:
            yield None
            return
            
        pbar = None
        try:
            if HAS_COLORAMA and not self._colorama_initialized:
                colorama.init()
                self._colorama_initialized = True
                pbar = tqdm(
                    total=100,
                    desc=description,
                    bar_format=f"{colorama.Fore.BLUE}{{l_bar}}{{bar}}{colorama.Fore.RESET}{{r_bar}}"
                )
            else:
                pbar = tqdm(total=100, desc=description)
            
            yield pbar
        finally:
            if pbar is not None:
                pbar.close()
    
    def update_progress_bar(self, pbar, process: subprocess.Popen) -> None:
        """Update progress bar while process is running."""
        if pbar is None:
            while process.poll() is None:
                time.sleep(0.1)
            return
            
        while process.poll() is None:
            time.sleep(0.05)
            if pbar.n < 95:  # Prevent going over 100%
                pbar.update(1)
        
        pbar.n = 100
        pbar.last_print_n = 100
        pbar.refresh()


class CommandExecutor:
    """Handles command execution with proper error handling and logging."""
    
    def __init__(self) -> None:
        """Initialize the command executor."""
        self.logger = logging.getLogger(__name__)
        self.progress_manager = ProgressBarManager()
    
    def execute_command(self, command: str, description: str = "Executing command") -> Tuple[bool, str]:
        """Execute a shell command with progress tracking and error handling."""
        self.logger.info(f"{description}: {command}")
        if not HAS_TQDM:
            print(f"{description}...")
        
        try:
            with self.progress_manager.progress_bar(description) as pbar:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=True,
                    text=True
                )
                
                self.progress_manager.update_progress_bar(pbar, process)
                stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                self.logger.debug(f"Command succeeded: {command}")
                return True, stdout
            else:
                error_msg = f"Command failed (exit code {process.returncode}): {stderr.strip()}"
                self.logger.error(error_msg)
                raise PopofilerError(error_msg)
                
        except subprocess.CalledProcessError as e:
            error_msg = f"Command failed with return code {e.returncode}: {e}"
            self.logger.error(error_msg)
            raise PopofilerError(error_msg) from e
        except KeyboardInterrupt:
            error_msg = "Process terminated by user (KeyboardInterrupt)"
            self.logger.warning(error_msg)
            raise PopofilerError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error executing command: {e}"
            self.logger.error(error_msg)
            raise PopofilerError(error_msg) from e
    
    def execute_multiple_commands(self, commands: List[str], description: str = "Executing commands") -> None:
        """Execute multiple commands in sequence, raising exception on failure."""
        for i, command in enumerate(commands, 1):
            try:
                self.execute_command(command, f"{description} ({i}/{len(commands)})")
            except PopofilerError:
                self.logger.error(f"Failed at command {i}/{len(commands)}")
                raise



class PodManager:
    """Manages Kubernetes pod operations."""
    
    def __init__(self, config: KubernetesConfig) -> None:
        """Initialize the pod manager."""
        self.config = config
        self.kubectl_builder = KubectlCommandBuilder(config)
        self.executor = CommandExecutor()
        self.logger = logging.getLogger(__name__)
    
    def find_running_pod(self) -> str:
        """Find a running pod that matches the project criteria.
        
        Raises:
            KubernetesError: If no suitable pod is found or listing fails.
        """
        command = self.kubectl_builder.build_get_pods_command()
        self.logger.info(f"Searching for running pods: {command}")
        
        try:
            success, output = self.executor.execute_command(command, "Listing Running Pods")
            pod_name = self._extract_pod_name_from_output(output)
            
            if not pod_name:
                raise KubernetesError(
                    f"No running pod found matching project '{self.config.project_name}' "
                    f"in namespace '{self.config.namespace}'"
                )
            
            self.logger.info(f"Selected pod: {pod_name}")
            return pod_name
            
        except PopofilerError as e:
            raise KubernetesError(f"Failed to find running pod: {e}") from e
    
    def _extract_pod_name_from_output(self, output: str) -> Optional[str]:
        """Extract the appropriate pod name from kubectl output."""
        for line in output.splitlines():
            if (self.config.project_name in line and 
                self.config.pod_name_anti_pattern not in line):
                pod_name = line.split()[0]
                return pod_name
        
        return None


class XdebugProfiler:
    """Handles Xdebug profiling operations."""
    
    def __init__(self, config: KubernetesConfig) -> None:
        """Initialize the Xdebug profiler."""
        self.config = config
        self.kubectl_builder = KubectlCommandBuilder(config)
        self.executor = CommandExecutor()
        self.logger = logging.getLogger(__name__)
    
    def enable_profiling(self, pod_name: str) -> None:
        """Enable Xdebug profiling on the specified pod.
        
        Args:
            pod_name: Name of the pod to enable profiling on.
            
        Raises:
            XdebugError: If profiling cannot be enabled.
        """
        try:
            commands = self._build_enable_profiling_commands(pod_name)
            self.executor.execute_multiple_commands(commands, "Enabling profiling")
            
            print(f"XDEBUG_TRIGGER: {self.config.trace_random_key}")
            print("Profiling enabled.")
            self.logger.info(f"Profiling enabled on pod {pod_name}")
            
        except PopofilerError as e:
            self.logger.error(f"Failed to enable profiling on pod {pod_name}")
            raise XdebugError(f"Failed to enable profiling on pod {pod_name}: {e}") from e
    
    def disable_profiling(self, pod_name: str) -> None:
        """Disable Xdebug profiling and restore configuration.
        
        Args:
            pod_name: Name of the pod to disable profiling on.
            
        Raises:
            XdebugError: If profiling cannot be disabled.
        """
        try:
            commands = self._build_disable_profiling_commands(pod_name)
            self.executor.execute_multiple_commands(commands, "Disabling profiling")
            
            print("Profiling disabled and configuration restored.")
            self.logger.info(f"Profiling disabled on pod {pod_name}")
            
        except PopofilerError as e:
            self.logger.error(f"Failed to disable profiling on pod {pod_name}")
            raise XdebugError(f"Failed to disable profiling on pod {pod_name}: {e}") from e
    
    def download_profiles(self, pod_name: str) -> None:
        """Download profiling traces from the pod.
        
        Args:
            pod_name: Name of the pod to download profiles from.
            
        Raises:
            XdebugError: If profiles cannot be downloaded.
        """
        try:
            source = f"{pod_name}:{PopofilerConstants.PROFILE_OUTPUT_DIR}/."
            destination = PopofilerConstants.CACHEGRIND_DIR
            command = self.kubectl_builder.build_copy_command(source, destination)
            
            self.executor.execute_command(command, "Downloading profiles")
            
            print("Profiles downloaded.")
            self.logger.info(f"Profiles downloaded from pod {pod_name}")
            
        except PopofilerError as e:
            self.logger.error(f"Failed to download profiles from pod {pod_name}")
            raise XdebugError(f"Failed to download profiles from pod {pod_name}: {e}") from e
    
    def install_xdebug(self, pod_name: str) -> None:
        """Install Xdebug on the pod if not already installed.
        
        Args:
            pod_name: Name of the pod to install Xdebug on.
            
        Raises:
            XdebugError: If Xdebug cannot be installed.
        """
        if self._is_xdebug_installed(pod_name):
            print("Xdebug is already installed.")
            return
        
        try:
            install_command = self.kubectl_builder.build_exec_command(
                pod_name, 
                "bash -c 'pecl install xdebug && docker-php-ext-enable xdebug'"
            )
            
            self.executor.execute_command(install_command, "Installing Xdebug")
            
            print("Xdebug installed successfully.")
            self.logger.info(f"Xdebug installed on pod {pod_name}")
            
        except PopofilerError as e:
            self.logger.error(f"Failed to install Xdebug on pod {pod_name}")
            raise XdebugError(f"Failed to install Xdebug on pod {pod_name}: {e}") from e
    
    def _is_xdebug_installed(self, pod_name: str) -> bool:
        """Check if Xdebug is already installed on the pod."""
        try:
            check_command = self.kubectl_builder.build_exec_command(
                pod_name, "php -m | grep xdebug", interactive=False
            )
            
            success, output = self.executor.execute_command(
                check_command, "Checking Xdebug installation"
            )
            is_installed = 'xdebug' in output.lower()
            
            if is_installed:
                self.logger.info(f"Xdebug is already installed on pod {pod_name}")
            
            return is_installed
            
        except PopofilerError:
            # If we can't check, assume it's not installed
            return False
    
    def _build_enable_profiling_commands(self, pod_name: str) -> List[str]:
        """Build commands to enable profiling."""
        xdebug_config = (
            f"zend_extension=xdebug\\n"
            f"xdebug.mode=profile\\n"
            f"xdebug.output_dir={PopofilerConstants.PROFILE_OUTPUT_DIR}/\\n"
            f"xdebug.start_with_request=trigger"
        )
        
        return [
            # Backup current configuration
            self.kubectl_builder.build_copy_command(
                f"{pod_name}:{PopofilerConstants.XDEBUG_CONFIG_PATH}",
                PopofilerConstants.BACKUP_FILENAME
            ),
            # Write new profiling configuration
            self.kubectl_builder.build_exec_command(
                pod_name,
                f"bash -c 'echo -e \"{xdebug_config}\" > {PopofilerConstants.XDEBUG_CONFIG_PATH}'"
            ),
            # Create and set permissions for profile directory
            self.kubectl_builder.build_exec_command(
                pod_name,
                f"bash -c 'mkdir -p {PopofilerConstants.PROFILE_OUTPUT_DIR}/ && chown www-data:www-data {PopofilerConstants.PROFILE_OUTPUT_DIR}/'"
            ),
            # Restart PHP-FPM
            self.kubectl_builder.build_exec_command(
                pod_name,
                "bash -c 'pkill -USR2 php-fpm'"
            )
        ]
    
    def _build_disable_profiling_commands(self, pod_name: str) -> List[str]:
        """Build commands to disable profiling."""
        return [
            # Restore backed up configuration
            self.kubectl_builder.build_copy_command(
                PopofilerConstants.BACKUP_FILENAME,
                f"{pod_name}:{PopofilerConstants.XDEBUG_CONFIG_PATH}"
            ),
            # Restart PHP-FPM
            self.kubectl_builder.build_exec_command(
                pod_name,
                "bash -c 'pkill -USR2 php-fpm'"
            )
        ]


class WebgrindManager:
    """Manages Webgrind Docker operations."""
    
    def __init__(self) -> None:
        """Initialize the Webgrind manager."""
        self.executor = CommandExecutor()
        self.logger = logging.getLogger(__name__)
    
    def run_webgrind(self) -> None:
        """Run Webgrind in a Docker container.
        
        Raises:
            DockerError: If Webgrind cannot be started.
        """
        try:
            # Ensure cachegrind directory exists
            Path(PopofilerConstants.CACHEGRIND_DIR).mkdir(exist_ok=True)
            
            command = (
                f'docker run -it --rm '
                f'-v "$(pwd)/{PopofilerConstants.CACHEGRIND_DIR}:/tmp" '
                f'--platform=linux/amd64 '
                f'-p {PopofilerConstants.WEBGRIND_PORT}:80 '
                f'{PopofilerConstants.WEBGRIND_IMAGE}'
            )
            
            self.executor.execute_command(command, "Running Webgrind")
            
            print(f"Webgrind is running on http://localhost:{PopofilerConstants.WEBGRIND_PORT}")
            self.logger.info("Webgrind started successfully")
            
        except PopofilerError as e:
            self.logger.error("Failed to start Webgrind")
            raise DockerError(f"Failed to start Webgrind: {e}") from e




class PopofilerCLI:
    """Command-line interface for the Popofiler tool."""
    
    VALID_COMMANDS = {
        'enable-profiling': 'Enable Xdebug profiling in the pod',
        'disable-profiling': 'Disable Xdebug profiling, restoring previous configuration',
        'download-profiles': 'Download Xdebug profiling traces',
        'install-xdebug': 'Install Xdebug in the pod, if not already installed',
        'run-webgrind': 'Run Webgrind in a Docker container to analyze profiling traces',
        'config-create': 'Create a configuration file with current settings',
        'config-show': 'Show current configuration'
    }
    
    def __init__(self) -> None:
        """Initialize the CLI application."""
        # Try to load configuration from file first, then environment, then defaults
        self.config = self._load_config()
        self.pod_manager = PodManager(self.config)
        self.profiler = XdebugProfiler(self.config)
        self.webgrind_manager = WebgrindManager()
        self.logger = logging.getLogger(__name__)
        
        # Setup logging
        self._setup_logging()
    
    def _load_config(self) -> KubernetesConfig:
        """Load configuration in priority order: file > env > defaults."""
        config_file = Path(PopofilerConstants.CONFIG_FILENAME)
        
        if config_file.exists():
            print(f"Loading configuration from {config_file}")
            return KubernetesConfig.from_file(config_file)
        elif any(var.startswith('POPOFILER_') for var in os.environ):
            print("Loading configuration from environment variables")
            return KubernetesConfig.from_env()
        else:
            print("Using default configuration")
            return KubernetesConfig()
    
    def _setup_logging(self) -> None:
        """Setup application logging."""
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('popofiler.log')
            ]
        )
    
    def show_help(self) -> None:
        """Display help information."""
        print("Usage: python popofiler.py [COMMAND]")
        print("\nKubernetes Xdebug Profiler Toolkit")
        print("Manage Xdebug profiling in Kubernetes pods")
        print("\nCommands:")
        print("  help               Show this help message")
        for command, description in self.VALID_COMMANDS.items():
            print(f"  {command:<18} {description}")
        print("\nConfiguration:")
        print("  Configuration is loaded from (in order of priority):")
        print(f"    1. {PopofilerConstants.CONFIG_FILENAME} (JSON file)")
        print("    2. Environment variables (POPOFILER_*)")
        print("    3. Default values")
        print("\nEnvironment Variables:")
        print("  POPOFILER_K8S_CONTEXT        Kubernetes context")
        print("  POPOFILER_PROJECT_NAME        Project name to match in pod names")
        print("  POPOFILER_POD_ANTI_PATTERN    Pattern to exclude from pod names")
        print("  POPOFILER_NAMESPACE          Kubernetes namespace")
    
    def show_config(self) -> None:
        """Show current configuration."""
        print("Current Configuration:")
        print(f"  Context: {self.config.context}")
        print(f"  Project Name: {self.config.project_name}")
        print(f"  Pod Anti-Pattern: {self.config.pod_name_anti_pattern}")
        print(f"  Namespace: {self.config.namespace}")
        print(f"  Current Trace Key: {self.config.trace_random_key}")
    
    def create_config_file(self) -> None:
        """Create a configuration file with current settings."""
        try:
            self.config.to_file()
            print(f"Configuration saved to {PopofilerConstants.CONFIG_FILENAME}")
        except Exception as e:
            print(f"Error creating configuration file: {e}")
            sys.exit(1)
    
    def run(self) -> None:
        """Run the CLI application."""
        if len(sys.argv) < 2 or sys.argv[1] == "help":
            self.show_help()
            return
        
        command = sys.argv[1]
        
        if command not in self.VALID_COMMANDS:
            print(f"Invalid command: {command}")
            print("Use 'help' to see available commands.")
            sys.exit(1)
        
        try:
            # Handle config commands
            if command == 'config-show':
                self.show_config()
                return
            elif command == 'config-create':
                self.create_config_file()
                return
            elif command == 'run-webgrind':
                self.webgrind_manager.run_webgrind()
                return
            
            # For other commands, we need to find a pod
            pod_name = self.pod_manager.find_running_pod()
            print(f"Selected Pod: {pod_name}")
            self._execute_command(command, pod_name)
            
        except PopofilerError as e:
            print(f"Error: {e}")
            sys.exit(1)
        except KeyboardInterrupt:
            print("\nOperation cancelled by user")
            sys.exit(1)
        except Exception as e:
            self.logger.exception("Unexpected error occurred")
            print(f"Unexpected error: {e}")
            sys.exit(1)
    
    def _execute_command(self, command: str, pod_name: str) -> None:
        """Execute the specified command on the pod."""
        if command == "enable-profiling":
            self.profiler.enable_profiling(pod_name)
        elif command == "disable-profiling":
            self.profiler.disable_profiling(pod_name)
        elif command == "download-profiles":
            self.profiler.download_profiles(pod_name)
        elif command == "install-xdebug":
            self.profiler.install_xdebug(pod_name)
        else:
            raise PopofilerError(f"Unknown command: {command}")


def main() -> None:
    """Main entry point."""
    cli = PopofilerCLI()
    cli.run()


if __name__ == "__main__":
    main()
