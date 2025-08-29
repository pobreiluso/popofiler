#!/usr/bin/env python3
"""
Secure version of popofiler.py with security vulnerabilities fixed.
This is a defensive security tool for monitoring and profiling Kubernetes pods.
"""

import subprocess
import sys
import os
import re
import shlex
import secrets
import time
import json
import logging
from pathlib import Path
from typing import Optional, Tuple, List
from tqdm import tqdm
import colorama

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration should be loaded from environment variables or config file
class Config:
    def __init__(self):
        self.k8s_context = os.environ.get('K8S_CONTEXT', '')
        self.project_name = os.environ.get('PROJECT_NAME', '')
        self.pod_name_anti_pattern = os.environ.get('POD_NAME_ANTI_PATTERN', '')
        self.namespace = os.environ.get('NAMESPACE', 'default')
        self.trace_key = secrets.token_urlsafe(32)  # Use cryptographically secure random
        self.command_timeout = 30  # seconds
        
        # Validate configuration
        self._validate_config()
    
    def _validate_config(self):
        """Validate configuration values."""
        if not self._is_valid_k8s_name(self.namespace):
            raise ValueError(f"Invalid namespace: {self.namespace}")
        if not self.k8s_context:
            raise ValueError("K8S_CONTEXT environment variable not set")
        if not self.project_name:
            raise ValueError("PROJECT_NAME environment variable not set")
    
    @staticmethod
    def _is_valid_k8s_name(name: str) -> bool:
        """Validate Kubernetes resource names."""
        pattern = r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$'
        return bool(re.match(pattern, name)) and len(name) <= 253


class SecureCommandRunner:
    """Secure command execution with proper error handling and validation."""
    
    @staticmethod
    def validate_pod_name(pod_name: str) -> str:
        """Validate pod name to prevent injection attacks."""
        if not pod_name:
            raise ValueError("Pod name cannot be empty")
        
        # Kubernetes pod names must match this pattern
        pattern = r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$'
        if not re.match(pattern, pod_name):
            raise ValueError(f"Invalid pod name: {pod_name}")
        
        if len(pod_name) > 253:
            raise ValueError(f"Pod name too long: {pod_name}")
        
        return pod_name
    
    @staticmethod
    def run_kubectl_command(args: List[str], timeout: int = 30) -> Tuple[bool, str]:
        """
        Run kubectl command securely without shell injection.
        
        Args:
            args: List of command arguments
            timeout: Command timeout in seconds
            
        Returns:
            Tuple of (success, output/error)
        """
        cmd = ['kubectl'] + args
        
        logger.debug(f"Running command: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False  # We'll handle the return code ourselves
            )
            
            if result.returncode == 0:
                return True, result.stdout
            else:
                logger.error(f"Command failed with return code {result.returncode}")
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out after {timeout} seconds")
            return False, f"Command timed out after {timeout} seconds"
        except Exception as e:
            logger.error(f"Unexpected error running command: {e}")
            return False, str(e)


class PodManager:
    """Manage Kubernetes pod operations securely."""
    
    def __init__(self, config: Config, command_runner: SecureCommandRunner):
        self.config = config
        self.runner = command_runner
    
    def get_running_pod(self) -> Optional[str]:
        """Get a running pod matching the project criteria."""
        args = [
            '--context', self.config.k8s_context,
            'get', 'pods',
            '--field-selector=status.phase=Running',
            '--namespace', self.config.namespace,
            '-o', 'json'
        ]
        
        success, output = self.runner.run_kubectl_command(args)
        
        if not success:
            logger.error(f"Failed to get pods: {output}")
            return None
        
        try:
            pods_data = json.loads(output)
            
            for pod in pods_data.get('items', []):
                pod_name = pod.get('metadata', {}).get('name', '')
                
                if (self.config.project_name in pod_name and 
                    self.config.pod_name_anti_pattern not in pod_name):
                    
                    # Validate pod name before returning
                    try:
                        return self.runner.validate_pod_name(pod_name)
                    except ValueError as e:
                        logger.warning(f"Invalid pod name found: {e}")
                        continue
            
            logger.warning("No matching pod found")
            return None
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse kubectl output: {e}")
            return None
    
    def execute_in_pod(self, pod_name: str, command: List[str]) -> Tuple[bool, str]:
        """Execute command in pod securely."""
        pod_name = self.runner.validate_pod_name(pod_name)
        
        args = [
            '--context', self.config.k8s_context,
            '--namespace', self.config.namespace,
            'exec', pod_name,
            '--'
        ] + command
        
        return self.runner.run_kubectl_command(args)
    
    def copy_from_pod(self, pod_name: str, src: str, dest: str) -> Tuple[bool, str]:
        """Copy files from pod securely."""
        pod_name = self.runner.validate_pod_name(pod_name)
        
        # Validate paths
        if '..' in src or '..' in dest:
            return False, "Path traversal detected"
        
        # Create destination directory if it doesn't exist
        dest_path = Path(dest)
        if dest_path.is_dir():
            dest_path.mkdir(parents=True, exist_ok=True)
        
        args = [
            'cp',
            '--context', self.config.k8s_context,
            '--namespace', self.config.namespace,
            f"{pod_name}:{src}",
            dest
        ]
        
        return self.runner.run_kubectl_command(args)
    
    def copy_to_pod(self, pod_name: str, src: str, dest: str) -> Tuple[bool, str]:
        """Copy files to pod securely."""
        pod_name = self.runner.validate_pod_name(pod_name)
        
        # Validate paths
        if '..' in src or '..' in dest:
            return False, "Path traversal detected"
        
        # Check if source file exists
        if not Path(src).exists():
            return False, f"Source file not found: {src}"
        
        args = [
            'cp',
            '--context', self.config.k8s_context,
            '--namespace', self.config.namespace,
            src,
            f"{pod_name}:{dest}"
        ]
        
        return self.runner.run_kubectl_command(args)


class XdebugProfiler:
    """Manage Xdebug profiling operations."""
    
    def __init__(self, pod_manager: PodManager, config: Config):
        self.pod_manager = pod_manager
        self.config = config
        self.backup_dir = Path("./backups")
        self.profile_dir = Path("./cachegrind")
        
        # Create directories with restricted permissions
        self.backup_dir.mkdir(mode=0o700, exist_ok=True)
        self.profile_dir.mkdir(mode=0o700, exist_ok=True)
    
    def enable_profiling(self, pod_name: str) -> bool:
        """Enable Xdebug profiling on the pod."""
        pod_name = SecureCommandRunner.validate_pod_name(pod_name)
        
        # Backup existing configuration
        backup_file = self.backup_dir / f"xdebug-{pod_name}-{int(time.time())}.ini"
        success, _ = self.pod_manager.copy_from_pod(
            pod_name,
            "/usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini",
            str(backup_file)
        )
        
        if not success:
            logger.warning("Could not backup existing configuration")
        
        # Create new Xdebug configuration
        xdebug_config = [
            "zend_extension=xdebug",
            "xdebug.mode=profile",
            "xdebug.output_dir=/tmp/cachegrind/",
            "xdebug.start_with_request=trigger",
            f"xdebug.trigger_value={self.config.trace_key}"
        ]
        
        # Write configuration to pod
        config_cmd = ['bash', '-c', 
                     f'echo "{chr(10).join(xdebug_config)}" > /usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini']
        success, output = self.pod_manager.execute_in_pod(pod_name, config_cmd)
        
        if not success:
            logger.error(f"Failed to write Xdebug configuration: {output}")
            return False
        
        # Create profile directory with proper permissions
        mkdir_cmd = ['bash', '-c', 'mkdir -p /tmp/cachegrind/ && chown www-data:www-data /tmp/cachegrind/']
        success, output = self.pod_manager.execute_in_pod(pod_name, mkdir_cmd)
        
        if not success:
            logger.error(f"Failed to create profile directory: {output}")
            return False
        
        # Restart PHP-FPM
        restart_cmd = ['bash', '-c', 'pkill -USR2 php-fpm']
        success, output = self.pod_manager.execute_in_pod(pod_name, restart_cmd)
        
        if success:
            logger.info(f"Profiling enabled. XDEBUG_TRIGGER: {self.config.trace_key}")
            logger.info(f"Configuration backed up to: {backup_file}")
        
        return success
    
    def disable_profiling(self, pod_name: str, backup_file: str = None) -> bool:
        """Disable Xdebug profiling and restore configuration."""
        pod_name = SecureCommandRunner.validate_pod_name(pod_name)
        
        if backup_file and Path(backup_file).exists():
            # Restore from specific backup
            success, output = self.pod_manager.copy_to_pod(
                pod_name,
                backup_file,
                "/usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini"
            )
            
            if not success:
                logger.error(f"Failed to restore configuration: {output}")
                return False
        else:
            # Disable Xdebug by removing configuration
            remove_cmd = ['bash', '-c', 'rm -f /usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini']
            success, output = self.pod_manager.execute_in_pod(pod_name, remove_cmd)
            
            if not success:
                logger.error(f"Failed to remove Xdebug configuration: {output}")
                return False
        
        # Restart PHP-FPM
        restart_cmd = ['bash', '-c', 'pkill -USR2 php-fpm']
        success, output = self.pod_manager.execute_in_pod(pod_name, restart_cmd)
        
        if success:
            logger.info("Profiling disabled and configuration restored")
        
        return success
    
    def download_profiles(self, pod_name: str) -> bool:
        """Download profiling traces from the pod."""
        pod_name = SecureCommandRunner.validate_pod_name(pod_name)
        
        success, output = self.pod_manager.copy_from_pod(
            pod_name,
            "/tmp/cachegrind/",
            str(self.profile_dir)
        )
        
        if success:
            logger.info(f"Profiles downloaded to: {self.profile_dir}")
        else:
            logger.error(f"Failed to download profiles: {output}")
        
        return success
    
    def check_xdebug_installed(self, pod_name: str) -> bool:
        """Check if Xdebug is installed in the pod."""
        pod_name = SecureCommandRunner.validate_pod_name(pod_name)
        
        check_cmd = ['php', '-m']
        success, output = self.pod_manager.execute_in_pod(pod_name, check_cmd)
        
        if success and 'xdebug' in output.lower():
            return True
        return False
    
    def install_xdebug(self, pod_name: str) -> bool:
        """Install Xdebug in the pod."""
        pod_name = SecureCommandRunner.validate_pod_name(pod_name)
        
        if self.check_xdebug_installed(pod_name):
            logger.info("Xdebug is already installed")
            return True
        
        install_cmd = ['bash', '-c', 'pecl install xdebug && docker-php-ext-enable xdebug']
        success, output = self.pod_manager.execute_in_pod(pod_name, install_cmd)
        
        if success:
            logger.info("Xdebug installed successfully")
        else:
            logger.error(f"Failed to install Xdebug: {output}")
        
        return success


def main():
    """Main entry point."""
    try:
        # Load configuration
        config = Config()
        
        # Initialize components
        command_runner = SecureCommandRunner()
        pod_manager = PodManager(config, command_runner)
        profiler = XdebugProfiler(pod_manager, config)
        
        # Parse command line arguments
        if len(sys.argv) < 2 or sys.argv[1] == "help":
            print("""Usage: secure_popofiler.py [COMMAND]
Commands:
  help               Show this help message
  enable-profiling   Enable Xdebug profiling in the pod
  disable-profiling  Disable Xdebug profiling, restoring previous configuration
  download-profiles  Download Xdebug profiling traces
  install-xdebug     Install Xdebug in the pod, if not already installed
  check-xdebug       Check if Xdebug is installed""")
            return 0
        
        # Get target pod
        pod_name = pod_manager.get_running_pod()
        if not pod_name:
            logger.error("No suitable pod found")
            return 1
        
        logger.info(f"Selected Pod: {pod_name}")
        
        # Execute command
        command = sys.argv[1]
        
        if command == "enable-profiling":
            success = profiler.enable_profiling(pod_name)
        elif command == "disable-profiling":
            # Look for most recent backup
            backups = sorted(profiler.backup_dir.glob(f"xdebug-{pod_name}-*.ini"))
            backup_file = str(backups[-1]) if backups else None
            success = profiler.disable_profiling(pod_name, backup_file)
        elif command == "download-profiles":
            success = profiler.download_profiles(pod_name)
        elif command == "install-xdebug":
            success = profiler.install_xdebug(pod_name)
        elif command == "check-xdebug":
            installed = profiler.check_xdebug_installed(pod_name)
            print(f"Xdebug {'is' if installed else 'is not'} installed")
            success = True
        else:
            logger.error(f"Invalid command: {command}")
            return 1
        
        return 0 if success else 1
        
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return 1
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        return 130
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())