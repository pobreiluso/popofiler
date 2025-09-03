import subprocess
import sys
import time
import random
import string
from typing import Tuple, List, Optional
from dataclasses import dataclass
import logging

# Optional imports with fallbacks
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    print("Warning: tqdm not available. Progress bars will be disabled.")

try:
    import colorama
    HAS_COLORAMA = True
except ImportError:
    HAS_COLORAMA = False
    print("Warning: colorama not available. Colors will be disabled.")


@dataclass
class KubernetesConfig:
    """Configuration for Kubernetes operations."""
    context: str = 'k8s_context'
    project_name: str = 'project-name'
    pod_name_anti_pattern: str = 'anti-pattern'
    namespace: str = 'namespace-name'
    
    def __post_init__(self):
        self.trace_random_key = self._generate_trace_key()
    
    @staticmethod
    def _generate_trace_key(length: int = 64) -> str:
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
    
    @staticmethod
    def create_progress_bar(description: str):
        """Create a progress bar if tqdm is available, otherwise return None."""
        if not HAS_TQDM:
            return None
            
        if HAS_COLORAMA:
            colorama.init()
            return tqdm(
                total=100,
                desc=description,
                bar_format=f"{colorama.Fore.BLUE}{{l_bar}}{{bar}}{colorama.Fore.RESET}{{r_bar}}"
            )
        else:
            return tqdm(total=100, desc=description)
    
    @staticmethod
    def update_progress_bar(pbar, process: subprocess.Popen) -> None:
        """Update progress bar while process is running."""
        if pbar is None:
            # Fallback: just wait for process to complete
            while process.poll() is None:
                time.sleep(0.1)
            return
            
        while process.poll() is None:
            time.sleep(0.05)
            pbar.update(1)
        
        pbar.n = 100
        pbar.last_print_n = 100
        pbar.refresh()


class CommandExecutor:
    """Handles command execution with proper error handling and logging."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.progress_manager = ProgressBarManager()
    
    def execute_command(self, command: str, description: str = "Executing command") -> Tuple[bool, str]:
        """Execute a shell command with progress tracking and error handling."""
        self.logger.info(f"{description}: {command}")
        print(f"{description}: ")
        
        try:
            pbar = self.progress_manager.create_progress_bar(description)
            
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True,
                text=True
            )
            
            self.progress_manager.update_progress_bar(pbar, process)
            stdout, stderr = process.communicate()
            
            if pbar is not None:
                pbar.close()
                
            if HAS_COLORAMA:
                colorama.deinit()
            
            if process.returncode == 0:
                return True, stdout
            else:
                error_msg = f"Command failed: {stderr} | Command: {command}"
                self.logger.error(error_msg)
                print(error_msg, file=sys.stderr)
                return False, stderr
                
        except subprocess.CalledProcessError as e:
            error_msg = f"Command failed with return code {e.returncode}: {e}"
            self.logger.error(error_msg)
            print(error_msg, file=sys.stderr)
            return False, str(e)
        except KeyboardInterrupt:
            error_msg = "Process terminated by user (KeyboardInterrupt)"
            self.logger.warning(error_msg)
            print(error_msg, file=sys.stderr)
            return False, error_msg
    
    def execute_multiple_commands(self, commands: List[str], description: str = "Executing commands") -> bool:
        """Execute multiple commands in sequence."""
        for i, command in enumerate(commands, 1):
            success, _ = self.execute_command(command, f"{description} ({i}/{len(commands)})")
            if not success:
                self.logger.error(f"Failed at command {i}/{len(commands)}")
                return False
        return True

# Legacy function for backward compatibility
def run_command(command: str, desc: str = "Running Command") -> Tuple[bool, str]:
    """Legacy command execution function. Use CommandExecutor.execute_command instead."""
    executor = CommandExecutor()
    return executor.execute_command(command, desc)


class PodManager:
    """Manages Kubernetes pod operations."""
    
    def __init__(self, config: KubernetesConfig):
        self.config = config
        self.kubectl_builder = KubectlCommandBuilder(config)
        self.executor = CommandExecutor()
        self.logger = logging.getLogger(__name__)
    
    def find_running_pod(self) -> Optional[str]:
        """Find a running pod that matches the project criteria."""
        command = self.kubectl_builder.build_get_pods_command()
        self.logger.info(f"Searching for running pods: {command}")
        
        success, output = self.executor.execute_command(command, "Listing Running Pods")
        if not success:
            self.logger.error(f"Failed to list pods: {output}")
            return None
        
        return self._extract_pod_name_from_output(output)
    
    def _extract_pod_name_from_output(self, output: str) -> Optional[str]:
        """Extract the appropriate pod name from kubectl output."""
        for line in output.splitlines():
            if (self.config.project_name in line and 
                self.config.pod_name_anti_pattern not in line):
                pod_name = line.split()[0]
                self.logger.info(f"Selected pod: {pod_name}")
                return pod_name
        
        self.logger.warning("No suitable pod found")
        return None


class XdebugProfiler:
    """Handles Xdebug profiling operations."""
    
    def __init__(self, config: KubernetesConfig):
        self.config = config
        self.kubectl_builder = KubectlCommandBuilder(config)
        self.executor = CommandExecutor()
        self.logger = logging.getLogger(__name__)
    
    def enable_profiling(self, pod_name: str) -> bool:
        """Enable Xdebug profiling on the specified pod."""
        commands = self._build_enable_profiling_commands(pod_name)
        
        success = self.executor.execute_multiple_commands(commands, "Enabling profiling")
        if success:
            print(f"XDEBUG_TRIGGER: {self.config.trace_random_key}")
            print("Profiling enabled.")
            self.logger.info(f"Profiling enabled on pod {pod_name}")
        else:
            self.logger.error(f"Failed to enable profiling on pod {pod_name}")
        
        return success
    
    def disable_profiling(self, pod_name: str) -> bool:
        """Disable Xdebug profiling and restore configuration."""
        commands = self._build_disable_profiling_commands(pod_name)
        
        success = self.executor.execute_multiple_commands(commands, "Disabling profiling")
        if success:
            print("Profiling disabled and configuration restored.")
            self.logger.info(f"Profiling disabled on pod {pod_name}")
        else:
            self.logger.error(f"Failed to disable profiling on pod {pod_name}")
        
        return success
    
    def download_profiles(self, pod_name: str) -> bool:
        """Download profiling traces from the pod."""
        source = f"{pod_name}:/tmp/cachegrind/."
        destination = "./cachegrind/"
        command = self.kubectl_builder.build_copy_command(source, destination)
        
        success, _ = self.executor.execute_command(command, "Downloading profiles")
        if success:
            print("Profiles downloaded.")
            self.logger.info(f"Profiles downloaded from pod {pod_name}")
        else:
            self.logger.error(f"Failed to download profiles from pod {pod_name}")
        
        return success
    
    def install_xdebug(self, pod_name: str) -> bool:
        """Install Xdebug on the pod if not already installed."""
        if self._is_xdebug_installed(pod_name):
            print("Xdebug is already installed.")
            return True
        
        install_command = self.kubectl_builder.build_exec_command(
            pod_name, 
            "bash -c 'pecl install xdebug && docker-php-ext-enable xdebug'"
        )
        
        success, output = self.executor.execute_command(install_command, "Installing Xdebug")
        if success:
            print("Xdebug installed successfully.")
            self.logger.info(f"Xdebug installed on pod {pod_name}")
        else:
            print(f"Error installing Xdebug: {output}")
            self.logger.error(f"Failed to install Xdebug on pod {pod_name}: {output}")
        
        return success
    
    def _is_xdebug_installed(self, pod_name: str) -> bool:
        """Check if Xdebug is already installed on the pod."""
        check_command = self.kubectl_builder.build_exec_command(
            pod_name, "php -m | grep xdebug"
        )
        
        success, output = self.executor.execute_command(check_command, "Checking Xdebug installation")
        is_installed = success and 'xdebug' in output.lower()
        
        if is_installed:
            self.logger.info(f"Xdebug is already installed on pod {pod_name}")
        
        return is_installed
    
    def _build_enable_profiling_commands(self, pod_name: str) -> List[str]:
        """Build commands to enable profiling."""
        return [
            self.kubectl_builder.build_copy_command(
                f"{pod_name}:/usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini",
                "./docker-php-ext-xdebug.ini-backup"
            ),
            self.kubectl_builder.build_exec_command(
                pod_name,
                "bash -c 'echo -e \"zend_extension=xdebug\\nxdebug.mode=profile\\nxdebug.output_dir=/tmp/cachegrind/\\nxdebug.start_with_request=trigger\" > /usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini'"
            ),
            self.kubectl_builder.build_exec_command(
                pod_name,
                "bash -c 'mkdir -p /tmp/cachegrind/ && chown www-data:www-data /tmp/cachegrind/'"
            ),
            self.kubectl_builder.build_exec_command(
                pod_name,
                "bash -c 'pkill -USR2 php-fpm'"
            )
        ]
    
    def _build_disable_profiling_commands(self, pod_name: str) -> List[str]:
        """Build commands to disable profiling."""
        return [
            self.kubectl_builder.build_copy_command(
                "./docker-php-ext-xdebug.ini-backup",
                f"{pod_name}:/usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini"
            ),
            self.kubectl_builder.build_exec_command(
                pod_name,
                "bash -c 'pkill -USR2 php-fpm'"
            )
        ]


class WebgrindManager:
    """Manages Webgrind Docker operations."""
    
    def __init__(self):
        self.executor = CommandExecutor()
        self.logger = logging.getLogger(__name__)
    
    def run_webgrind(self) -> bool:
        """Run Webgrind in a Docker container."""
        command = (
            'docker run -it --rm '
            '-v "$(pwd)/cachegrind/:/tmp" '
            '--platform=linux/amd64 '
            '-p 8003:80 '
            'jokkedk/webgrind:latest'
        )
        
        success, _ = self.executor.execute_command(command, "Running Webgrind")
        if success:
            print("Webgrind is running on http://localhost:8003")
            self.logger.info("Webgrind started successfully")
        else:
            self.logger.error("Failed to start Webgrind")
        
        return success


# Legacy functions for backward compatibility
def pick_running_pod() -> Optional[str]:
    """Legacy function. Use PodManager.find_running_pod instead."""
    config = KubernetesConfig()
    pod_manager = PodManager(config)
    return pod_manager.find_running_pod()



def execute_profiling_commands(commands: List[str]) -> None:
    """Legacy function. Use CommandExecutor.execute_multiple_commands instead."""
    executor = CommandExecutor()
    success = executor.execute_multiple_commands(commands, "Updating profiling configuration")
    if success:
        print("Profiling configuration updated.")


def enable_profiling(donor_pod: str) -> bool:
    """Legacy function. Use XdebugProfiler.enable_profiling instead."""
    config = KubernetesConfig()
    profiler = XdebugProfiler(config)
    return profiler.enable_profiling(donor_pod)


def disable_profiling(donor_pod: str) -> bool:
    """Legacy function. Use XdebugProfiler.disable_profiling instead."""
    config = KubernetesConfig()
    profiler = XdebugProfiler(config)
    return profiler.disable_profiling(donor_pod)


def download_profiles(donor_pod: str) -> bool:
    """Legacy function. Use XdebugProfiler.download_profiles instead."""
    config = KubernetesConfig()
    profiler = XdebugProfiler(config)
    return profiler.download_profiles(donor_pod)


def install_xdebug(donor_pod: str) -> bool:
    """Legacy function. Use XdebugProfiler.install_xdebug instead."""
    config = KubernetesConfig()
    profiler = XdebugProfiler(config)
    return profiler.install_xdebug(donor_pod)

def run_webgrind() -> bool:
    """Legacy function. Use WebgrindManager.run_webgrind instead."""
    webgrind_manager = WebgrindManager()
    return webgrind_manager.run_webgrind()


class PopofilerCLI:
    """Command-line interface for the Popofiler tool."""
    
    VALID_COMMANDS = {
        'enable-profiling': 'Enable Xdebug profiling in the pod',
        'disable-profiling': 'Disable Xdebug profiling, restoring previous configuration',
        'download-profiles': 'Download Xdebug profiling traces',
        'install-xdebug': 'Install Xdebug in the pod, if not already installed',
        'run-webgrind': 'Run Webgrind in a Docker container to analyze profiling traces'
    }
    
    def __init__(self):
        self.config = KubernetesConfig()
        self.pod_manager = PodManager(self.config)
        self.profiler = XdebugProfiler(self.config)
        self.webgrind_manager = WebgrindManager()
        self.logger = logging.getLogger(__name__)
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    def show_help(self) -> None:
        """Display help information."""
        print("Usage: python popofiler.py [COMMAND]")
        print("\nCommands:")
        print("  help               Show this help message")
        for command, description in self.VALID_COMMANDS.items():
            print(f"  {command:<18} {description}")
    
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
        
        # For webgrind, we don't need a pod
        if command == 'run-webgrind':
            success = self.webgrind_manager.run_webgrind()
            sys.exit(0 if success else 1)
        
        # For other commands, we need to find a pod
        donor_pod = self.pod_manager.find_running_pod()
        if not donor_pod:
            print("No suitable pod found. Please check your configuration.")
            sys.exit(1)
        
        print(f"Selected Pod: {donor_pod}")
        success = self._execute_command(command, donor_pod)
        sys.exit(0 if success else 1)
    
    def _execute_command(self, command: str, pod_name: str) -> bool:
        """Execute the specified command on the pod."""
        try:
            if command == "enable-profiling":
                return self.profiler.enable_profiling(pod_name)
            elif command == "disable-profiling":
                return self.profiler.disable_profiling(pod_name)
            elif command == "download-profiles":
                return self.profiler.download_profiles(pod_name)
            elif command == "install-xdebug":
                return self.profiler.install_xdebug(pod_name)
            else:
                self.logger.error(f"Unknown command: {command}")
                return False
        except Exception as e:
            self.logger.error(f"Error executing command {command}: {e}")
            print(f"Error: {e}")
            return False


def main() -> None:
    """Main entry point."""
    cli = PopofilerCLI()
    cli.run()


if __name__ == "__main__":
    main()
