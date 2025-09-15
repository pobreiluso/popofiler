#!/usr/bin/env python3
"""
Integration test suite for popofiler.py
Tests end-to-end workflows and external system interactions.
"""

import unittest
from unittest.mock import patch, MagicMock, call
import subprocess
import sys
import os
from io import StringIO
import tempfile
import json

import popofiler


class TestPopofileIntegration(unittest.TestCase):
    """Integration tests for popofiler workflows."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_pod = "integration-test-pod-12345"
        self.test_namespace = "test-namespace"
        self.test_context = "test-context"

    @patch('popofiler.run_command')
    @patch('sys.stdout', new_callable=StringIO)
    def test_complete_profiling_lifecycle(self, mock_stdout, mock_run_command):
        """Test the complete profiling enable -> use -> disable lifecycle."""
        # Arrange - Mock all kubectl and docker commands to succeed
        kubectl_list_response = f"NAME\tREADY\tSTATUS\tRESTARTS\tAGE\n{popofiler.PROJECT_NAME}-pod-123\t1/1\tRunning\t0\t1h"
        
        mock_run_command.side_effect = [
            (True, kubectl_list_response),  # pick_running_pod
            (True, "backup created"),       # backup config
            (True, "config updated"),       # update xdebug config
            (True, "directory created"),    # create cachegrind dir
            (True, "php-fpm restarted"),    # restart php-fpm
            (True, "profiles downloaded"),  # download profiles
            (True, "config restored"),      # restore original config
            (True, "php-fpm restarted"),    # final restart
        ]

        # Act - Execute full workflow
        with patch.object(sys, 'argv', ['popofiler.py', 'enable-profiling']):
            popofiler.main()

        # Simulate profile download
        with patch.object(sys, 'argv', ['popofiler.py', 'download-profiles']):
            with patch('popofiler.pick_running_pod', return_value=f"{popofiler.PROJECT_NAME}-pod-123"):
                popofiler.main()

        # Disable profiling
        with patch.object(sys, 'argv', ['popofiler.py', 'disable-profiling']):
            with patch('popofiler.pick_running_pod', return_value=f"{popofiler.PROJECT_NAME}-pod-123"):
                popofiler.main()

        # Assert - Verify all expected commands were called
        self.assertEqual(mock_run_command.call_count, 8)
        output = mock_stdout.getvalue()
        self.assertIn("Profiling enabled", output)
        self.assertIn("Profiles downloaded", output)
        self.assertIn("Profiling disabled", output)

    @patch('popofiler.run_command')
    @patch('sys.stdout', new_callable=StringIO)
    def test_xdebug_installation_and_profiling(self, mock_stdout, mock_run_command):
        """Test installing Xdebug and then enabling profiling."""
        # Arrange
        kubectl_list_response = f"NAME\tREADY\tSTATUS\tRESTARTS\tAGE\n{popofiler.PROJECT_NAME}-pod-456\t1/1\tRunning\t0\t2h"
        
        mock_run_command.side_effect = [
            (True, kubectl_list_response),    # pick_running_pod for install
            (True, "no xdebug module found"), # check xdebug (not installed)
            (True, "xdebug installation success"), # install xdebug
            (True, kubectl_list_response),    # pick_running_pod for enable
            (True, "backup created"),         # backup config
            (True, "config updated"),         # update config
            (True, "directory created"),      # create directory
            (True, "php-fpm restarted"),      # restart php-fpm
        ]

        # Act - Install Xdebug first
        with patch.object(sys, 'argv', ['popofiler.py', 'install-xdebug']):
            popofiler.main()

        # Then enable profiling
        with patch.object(sys, 'argv', ['popofiler.py', 'enable-profiling']):
            popofiler.main()

        # Assert
        self.assertEqual(mock_run_command.call_count, 8)
        output = mock_stdout.getvalue()
        self.assertIn("Xdebug instalado exitosamente", output)
        self.assertIn("Profiling enabled", output)

    @patch('popofiler.run_command')
    def test_resilient_command_execution(self, mock_run_command):
        """Test that the system handles partial command failures gracefully."""
        # Arrange - Some commands fail
        mock_run_command.side_effect = [
            (True, f"NAME\tREADY\tSTATUS\tRESTARTS\tAGE\n{popofiler.PROJECT_NAME}-pod-789\t1/1\tRunning\t0\t1h"),
            (True, "backup success"),
            (False, "config update failed"),  # This command fails
            (True, "would not be called"),    # This shouldn't be called due to early return
        ]

        # Act
        with patch.object(sys, 'argv', ['popofiler.py', 'enable-profiling']):
            popofiler.main()

        # Assert - Only first 3 commands should be called due to failure handling
        self.assertEqual(mock_run_command.call_count, 3)

    @patch('popofiler.run_command')
    @patch('sys.stdout', new_callable=StringIO)
    def test_webgrind_container_workflow(self, mock_stdout, mock_run_command):
        """Test running Webgrind container for profile analysis."""
        # Arrange
        mock_run_command.return_value = (True, "webgrind container started on port 8003")

        # Act
        with patch.object(sys, 'argv', ['popofiler.py', 'run-webgrind']):
            popofiler.main()

        # Assert
        expected_docker_command = 'docker run -it --rm -v "$(pwd)/cachegrind/:/tmp" --platform=linux/amd64 -p 8003:80 jokkedk/webgrind:latest'
        mock_run_command.assert_called_once_with(expected_docker_command, shell=True, progress_desc="Running Webgrind")
        self.assertIn("Webgrind running", mock_stdout.getvalue())

    @patch('popofiler.run_command')
    def test_pod_selection_with_multiple_candidates(self, mock_run_command):
        """Test pod selection logic with multiple matching pods."""
        # Arrange - Multiple pods, some with anti-pattern
        complex_kubectl_output = f"""NAME\tREADY\tSTATUS\tRESTARTS\tAGE
{popofiler.PROJECT_NAME}-{popofiler.POD_NAME_ANTI_PATTERN}-111\t1/1\tRunning\t0\t3h
{popofiler.PROJECT_NAME}-main-222\t1/1\tRunning\t0\t2h
{popofiler.PROJECT_NAME}-worker-333\t1/1\tRunning\t0\t1h
other-project-pod-444\t1/1\tRunning\t0\t30m"""

        mock_run_command.return_value = (True, complex_kubectl_output)

        # Act
        selected_pod = popofiler.pick_running_pod()

        # Assert - Should pick first matching pod that doesn't contain anti-pattern
        self.assertEqual(selected_pod, f"{popofiler.PROJECT_NAME}-main-222")

    @patch('popofiler.run_command')
    @patch('sys.stdout', new_callable=StringIO)
    def test_error_handling_and_recovery(self, mock_stdout, mock_run_command):
        """Test error handling in various failure scenarios."""
        # Test 1: kubectl command failure
        mock_run_command.return_value = (False, "kubectl: command not found")
        
        with patch.object(sys, 'argv', ['popofiler.py', 'enable-profiling']):
            popofiler.main()
        
        output = mock_stdout.getvalue()
        self.assertIn("Error: kubectl: command not found", output)

        # Reset stdout buffer
        mock_stdout.seek(0)
        mock_stdout.truncate(0)

        # Test 2: No pods found scenario
        mock_run_command.return_value = (True, "NAME\tREADY\tSTATUS\tRESTARTS\tAGE")
        
        with patch.object(sys, 'argv', ['popofiler.py', 'enable-profiling']):
            popofiler.main()

        # Should handle gracefully without crashing

    def test_configuration_constants(self):
        """Test that configuration constants are properly set."""
        # Verify all required constants exist
        required_constants = ['K8S_CONTEXT', 'PROJECT_NAME', 'POD_NAME_ANTI_PATTERN', 'NAMESPACE', 'TRACE_RANDOM_KEY']
        
        for constant in required_constants:
            self.assertTrue(hasattr(popofiler, constant), f"Missing constant: {constant}")
            self.assertIsNotNone(getattr(popofiler, constant), f"Constant {constant} is None")

        # Verify TRACE_RANDOM_KEY properties
        self.assertEqual(len(popofiler.TRACE_RANDOM_KEY), 64)
        self.assertTrue(all(c.isalnum() for c in popofiler.TRACE_RANDOM_KEY))

    @patch('popofiler.run_command')
    def test_concurrent_pod_operations(self, mock_run_command):
        """Test that operations handle concurrent pod states correctly."""
        # Simulate a pod that changes state between commands
        mock_run_command.side_effect = [
            (True, f"{popofiler.PROJECT_NAME}-pod-999\t1/1\tRunning\t0\t1h"),  # Initial pod list
            (False, "pod not found"),  # Pod disappeared during operation
        ]

        # Should handle gracefully without crashing
        popofiler.enable_profiling(f"{popofiler.PROJECT_NAME}-pod-999")

        # Verify that it attempted the operation and handled failure
        self.assertEqual(mock_run_command.call_count, 2)


class TestSecurityIntegration(unittest.TestCase):
    """Security-focused integration tests."""

    @patch('popofiler.run_command')
    def test_command_parameter_sanitization(self, mock_run_command):
        """Test that commands properly handle special characters in parameters."""
        mock_run_command.return_value = (True, "success")
        
        # Test with pod names containing special characters
        special_pod_names = [
            "pod-name-with-hyphens",
            "podname123",
            "pod.with.dots",
        ]
        
        for pod_name in special_pod_names:
            mock_run_command.reset_mock()
            popofiler.enable_profiling(pod_name)
            
            # Verify commands were called (basic sanitization test)
            self.assertTrue(mock_run_command.called)
            
            # Check that pod name appears in commands
            calls = mock_run_command.call_args_list
            for call in calls:
                command = call[0][0]
                if pod_name in command:
                    # Verify basic structure is maintained
                    self.assertIn("kubectl", command)

    @patch('popofiler.run_command')
    def test_resource_cleanup_on_failure(self, mock_run_command):
        """Test that resources are properly handled when operations fail."""
        # Simulate partial failure during enable profiling
        mock_run_command.side_effect = [
            (True, "backup success"),
            (False, "config update failed"),
            (True, "should not reach here")
        ]
        
        # Execute enable profiling (should fail gracefully)
        popofiler.execute_profiling_commands([
            "backup command",
            "failing config command",
            "cleanup command"
        ])
        
        # Verify it stopped after failure and didn't continue
        self.assertEqual(mock_run_command.call_count, 2)

    def test_input_validation(self):
        """Test input validation for various functions."""
        # Test empty command list
        result = popofiler.execute_profiling_commands([])
        # Should not crash
        
        # Test None/empty parameters
        with patch('popofiler.run_command', return_value=(True, "success")):
            # These should not crash the system
            popofiler.enable_profiling("")
            popofiler.disable_profiling("")
            popofiler.download_profiles("")
            popofiler.install_xdebug("")


class TestPerformanceIntegration(unittest.TestCase):
    """Performance and timing integration tests."""

    @patch('popofiler.run_command')
    def test_command_timeout_handling(self, mock_run_command):
        """Test that long-running commands are handled appropriately."""
        import time
        
        # Simulate a slow command
        def slow_command(*args, **kwargs):
            time.sleep(0.1)  # Short delay for testing
            return (True, "slow command completed")
        
        mock_run_command.side_effect = slow_command
        
        # Execute command and measure time
        start_time = time.time()
        popofiler.download_profiles("test-pod")
        end_time = time.time()
        
        # Should complete in reasonable time
        self.assertLess(end_time - start_time, 1.0)

    @patch('popofiler.run_command')
    def test_large_output_handling(self, mock_run_command):
        """Test handling of large command outputs."""
        # Simulate large kubectl output
        large_pod_list = "NAME\tREADY\tSTATUS\tRESTARTS\tAGE\n"
        for i in range(100):
            large_pod_list += f"{popofiler.PROJECT_NAME}-pod-{i:03d}\t1/1\tRunning\t0\t1h\n"
        
        mock_run_command.return_value = (True, large_pod_list)
        
        # Should handle large output without issues
        selected_pod = popofiler.pick_running_pod()
        self.assertIsNotNone(selected_pod)
        self.assertIn(popofiler.PROJECT_NAME, selected_pod)


if __name__ == '__main__':
    # Run integration tests
    unittest.main(verbosity=2, buffer=True)