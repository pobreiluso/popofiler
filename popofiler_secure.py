#!/usr/bin/env python3
"""
Secure implementation of Kubernetes Xdebug Profiler Toolkit
This version addresses the critical security vulnerabilities found in the original implementation
"""

import subprocess
import sys
import os
import re
import json
import hashlib
import secrets
import logging
from pathlib import Path
from typing import Optional, Tuple, List
from datetime import datetime
import shlex

# Configure secure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('profiler_audit.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration should be loaded from environment or secure config file
class Config:
    """Secure configuration management"""
    
    def __init__(self):
        self.k8s_context = os.environ.get('K8S_CONTEXT', '')
        self.project_name = os.environ.get('PROJECT_NAME', '')
        self.namespace = os.environ.get('NAMESPACE', '')
        self.pod_anti_pattern = os.environ.get('POD_ANTI_PATTERN', '')
        self.validate_config()
    
    def validate_config(self):
        """Validate configuration values"""
        if not self.k8s_context:
            raise ValueError("K8S_CONTEXT environment variable not set")
        if not self.namespace:
            raise ValueError("NAMESPACE environment variable not set")
        if not self.project_name:
            raise ValueError("PROJECT_NAME environment variable not set")
        
        # Validate Kubernetes identifiers
        if not self._validate_k8s_name(self.namespace):
            raise ValueError(f"Invalid namespace: {self.namespace}")
        if not self._validate_k8s_name(self.k8s_context):
            raise ValueError(f"Invalid context: {self.k8s_context}")
    
    @staticmethod
    def _validate_k8s_name(name: str) -> bool:
        """Validate Kubernetes resource names"""
        pattern = r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$'
        return bool(re.match(pattern, name)) and len(name) <= 253


class SecureKubernetesProfiler:
    """Secure Kubernetes profiling operations"""
    
    def __init__(self, config: Config):
        self.config = config
        self.trace_key = secrets.token_urlsafe(32)
        self.audit_log = []
    
    def run_command(self, command_parts: List[str], description: str = "Running command") -> Tuple[bool, str]:
        """
        Securely execute a command without shell injection risks
        
        Args:
            command_parts: List of command arguments
            description: Description for logging
            
        Returns:
            Tuple of (success, output/error)
        """
        if not isinstance(command_parts, list):
            raise ValueError("Command must be provided as a list of arguments")
        
        # Log the operation
        logger.info(f"{description}: {' '.join(command_parts[:3])}...")  # Log only first 3 parts for security
        
        try:
            # Execute without shell - prevents injection
            result = subprocess.run(
                command_parts,
                capture_output=True,
                text=True,
                timeout=60,  # Add timeout to prevent hanging
                check=False  # Don't raise on non-zero exit
            )
            
            if result.returncode == 0:
                return True, result.stdout
            else:
                logger.error(f"Command failed with code {result.returncode}")
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            logger.error("Command timed out")
            return False, "Command execution timed out"
        except Exception as e:
            logger.error(f"Command execution failed: {str(e)}")
            return False, str(e)
    
    def validate_pod_name(self, pod_name: str) -> bool:
        """Validate pod name against Kubernetes naming conventions"""
        if not pod_name:
            return False
        
        # Kubernetes pod name regex
        pattern = r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$'
        if not re.match(pattern, pod_name):
            logger.warning(f"Invalid pod name format: {pod_name}")
            return False
        
        if len(pod_name) > 253:
            logger.warning(f"Pod name too long: {pod_name}")
            return False
        
        return True
    
    def get_running_pod(self) -> Optional[str]:
        """Securely get a running pod matching criteria"""
        command = [
            "kubectl",
            "--context", self.config.k8s_context,
            "--namespace", self.config.namespace,
            "get", "pods",
            "--field-selector=status.phase==Running",
            "-o", "json"  # Use JSON output for structured parsing
        ]
        
        success, output = self.run_command(command, "Listing running pods")
        if not success:
            logger.error(f"Failed to list pods: {output}")
            return None
        
        try:
            # Parse JSON output safely
            pods_data = json.loads(output)
            for item in pods_data.get('items', []):
                pod_name = item.get('metadata', {}).get('name', '')
                
                # Apply filters
                if (self.config.project_name in pod_name and 
                    self.config.pod_anti_pattern not in pod_name):
                    
                    # Validate pod name before returning
                    if self.validate_pod_name(pod_name):
                        logger.info(f"Selected pod: {pod_name}")
                        return pod_name
            
            logger.warning("No matching pods found")
            return None
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse pod list: {e}")
            return None
    
    def create_backup_directory(self) -> Path:
        """Create secure backup directory"""
        backup_dir = Path("./backups") / datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        return backup_dir
    
    def enable_profiling(self, pod_name: str) -> bool:
        """Enable Xdebug profiling with security checks"""
        if not self.validate_pod_name(pod_name):
            logger.error("Invalid pod name provided")
            return False
        
        logger.info(f"Enabling profiling for pod: {pod_name}")
        backup_dir = self.create_backup_directory()
        
        # Step 1: Backup current configuration
        backup_file = backup_dir / "xdebug.ini.backup"
        backup_command = [
            "kubectl", "--context", self.config.k8s_context,
            "--namespace", self.config.namespace,
            "cp", f"{pod_name}:/usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini",
            str(backup_file)
        ]
        
        success, _ = self.run_command(backup_command, "Backing up configuration")
        if not success:
            logger.error("Failed to backup configuration")
            return False
        
        # Step 2: Create new configuration file locally
        config_content = f"""zend_extension=xdebug
xdebug.mode=profile
xdebug.output_dir=/tmp/cachegrind/
xdebug.start_with_request=trigger
xdebug.trigger_value={self.trace_key}
"""
        
        temp_config = backup_dir / "xdebug.ini.new"
        temp_config.write_text(config_content)
        
        # Step 3: Copy new configuration to pod
        copy_command = [
            "kubectl", "--context", self.config.k8s_context,
            "--namespace", self.config.namespace,
            "cp", str(temp_config),
            f"{pod_name}:/usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini"
        ]
        
        success, _ = self.run_command(copy_command, "Updating configuration")
        if not success:
            logger.error("Failed to update configuration")
            return False
        
        # Step 4: Create profiling directory
        mkdir_command = [
            "kubectl", "exec",
            "--context", self.config.k8s_context,
            "--namespace", self.config.namespace,
            pod_name, "--",
            "mkdir", "-p", "/tmp/cachegrind/"
        ]
        
        success, _ = self.run_command(mkdir_command, "Creating profile directory")
        if not success:
            logger.error("Failed to create profile directory")
            return False
        
        # Step 5: Set permissions
        chown_command = [
            "kubectl", "exec",
            "--context", self.config.k8s_context,
            "--namespace", self.config.namespace,
            pod_name, "--",
            "chown", "www-data:www-data", "/tmp/cachegrind/"
        ]
        
        success, _ = self.run_command(chown_command, "Setting directory permissions")
        if not success:
            logger.error("Failed to set permissions")
            return False
        
        # Step 6: Reload PHP-FPM
        reload_command = [
            "kubectl", "exec",
            "--context", self.config.k8s_context,
            "--namespace", self.config.namespace,
            pod_name, "--",
            "pkill", "-USR2", "php-fpm"
        ]
        
        success, _ = self.run_command(reload_command, "Reloading PHP-FPM")
        if success:
            # Store trigger key securely (never log it)
            trigger_file = backup_dir / "trigger_key.txt"
            trigger_file.write_text(f"XDEBUG_TRIGGER={self.trace_key}")
            trigger_file.chmod(0o600)
            
            logger.info(f"Profiling enabled. Trigger key saved to: {trigger_file}")
            self._audit_log("enable_profiling", pod_name, "success")
            return True
        else:
            logger.error("Failed to reload PHP-FPM")
            self._audit_log("enable_profiling", pod_name, "failed")
            return False
    
    def disable_profiling(self, pod_name: str, backup_dir: str) -> bool:
        """Disable profiling and restore configuration"""
        if not self.validate_pod_name(pod_name):
            logger.error("Invalid pod name provided")
            return False
        
        backup_path = Path(backup_dir)
        if not backup_path.exists():
            logger.error(f"Backup directory not found: {backup_dir}")
            return False
        
        backup_file = backup_path / "xdebug.ini.backup"
        if not backup_file.exists():
            logger.error(f"Backup file not found: {backup_file}")
            return False
        
        # Restore configuration
        restore_command = [
            "kubectl", "--context", self.config.k8s_context,
            "--namespace", self.config.namespace,
            "cp", str(backup_file),
            f"{pod_name}:/usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini"
        ]
        
        success, _ = self.run_command(restore_command, "Restoring configuration")
        if not success:
            logger.error("Failed to restore configuration")
            return False
        
        # Reload PHP-FPM
        reload_command = [
            "kubectl", "exec",
            "--context", self.config.k8s_context,
            "--namespace", self.config.namespace,
            pod_name, "--",
            "pkill", "-USR2", "php-fpm"
        ]
        
        success, _ = self.run_command(reload_command, "Reloading PHP-FPM")
        if success:
            logger.info("Profiling disabled and configuration restored")
            self._audit_log("disable_profiling", pod_name, "success")
            return True
        else:
            logger.error("Failed to reload PHP-FPM")
            self._audit_log("disable_profiling", pod_name, "failed")
            return False
    
    def download_profiles(self, pod_name: str) -> bool:
        """Download profiling traces with validation"""
        if not self.validate_pod_name(pod_name):
            logger.error("Invalid pod name provided")
            return False
        
        download_dir = Path("./cachegrind") / datetime.now().strftime("%Y%m%d_%H%M%S")
        download_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        
        download_command = [
            "kubectl", "--context", self.config.k8s_context,
            "--namespace", self.config.namespace,
            "cp", f"{pod_name}:/tmp/cachegrind/.",
            str(download_dir)
        ]
        
        success, _ = self.run_command(download_command, "Downloading profiles")
        if success:
            # Validate downloaded files
            profile_files = list(download_dir.glob("cachegrind.*"))
            logger.info(f"Downloaded {len(profile_files)} profile files to {download_dir}")
            self._audit_log("download_profiles", pod_name, f"downloaded {len(profile_files)} files")
            return True
        else:
            logger.error("Failed to download profiles")
            self._audit_log("download_profiles", pod_name, "failed")
            return False
    
    def _audit_log(self, action: str, target: str, result: str):
        """Log security-relevant actions"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "target": target,
            "result": result,
            "user": os.environ.get("USER", "unknown")
        }
        self.audit_log.append(log_entry)
        logger.info(f"AUDIT: {json.dumps(log_entry)}")


def main():
    """Main entry point with error handling"""
    try:
        # Load and validate configuration
        config = Config()
        profiler = SecureKubernetesProfiler(config)
        
        # Parse command line arguments
        if len(sys.argv) < 2:
            print("Usage: python popofiler_secure.py [enable|disable|download] [options]")
            sys.exit(1)
        
        command = sys.argv[1]
        
        # Get pod name
        pod_name = profiler.get_running_pod()
        if not pod_name:
            logger.error("No suitable pod found")
            sys.exit(1)
        
        # Execute requested action
        if command == "enable":
            success = profiler.enable_profiling(pod_name)
        elif command == "disable":
            if len(sys.argv) < 3:
                print("Usage: python popofiler_secure.py disable <backup_directory>")
                sys.exit(1)
            success = profiler.disable_profiling(pod_name, sys.argv[2])
        elif command == "download":
            success = profiler.download_profiles(pod_name)
        else:
            logger.error(f"Unknown command: {command}")
            sys.exit(1)
        
        sys.exit(0 if success else 1)
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()