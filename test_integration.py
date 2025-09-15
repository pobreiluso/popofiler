"""
Integration tests for popofiler.py
Tests interactions with external systems and services
"""
import unittest
from unittest.mock import patch, MagicMock, call
import subprocess
import tempfile
import os
import json

import popofiler


class TestKubernetesIntegration(unittest.TestCase):
    """Test Kubernetes API interactions"""

    def setUp(self):
        self.test_context = 'test-context'
        self.test_namespace = 'test-namespace'
        self.test_project = 'test-project'
        
        # Patch constants for testing
        self.context_patcher = patch('popofiler.K8S_CONTEXT', self.test_context)
        self.namespace_patcher = patch('popofiler.NAMESPACE', self.test_namespace)
        self.project_patcher = patch('popofiler.PROJECT_NAME', self.test_project)
        
        self.context_patcher.start()
        self.namespace_patcher.start()
        self.project_patcher.start()

    def tearDown(self):
        self.context_patcher.stop()
        self.namespace_patcher.stop()
        self.project_patcher.stop()

    @patch('subprocess.Popen')
    def test_kubectl_command_structure(self, mock_popen):
        """Test that kubectl commands are properly structured"""
        # Arrange
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = ("pod-123\t1/1\tRunning\t0\t1d", "")
        mock_process.poll.return_value = 0
        mock_popen.return_value = mock_process

        # Act
        with patch('tqdm.tqdm'), patch('colorama.init'), patch('colorama.deinit'):
            success, output = popofiler.run_command("kubectl get pods", "Test kubectl")

        # Assert
        mock_popen.assert_called_once()
        args = mock_popen.call_args
        self.assertEqual(args[1]['shell'], True)
        self.assertIn('kubectl get pods', args[0][0])

    @patch('popofiler.run_command')
    def test_pod_selection_with_multiple_matches(self, mock_run_command):
        """Test pod selection when multiple pods match criteria"""
        # Arrange
        kubectl_output = f"""NAME\tREADY\tSTATUS\tRESTARTS\tAGE
{self.test_project}-web-123\t1/1\tRunning\t0\t1d
{self.test_project}-worker-456\t1/1\tRunning\t0\t2d
other-project-pod\t1/1\tRunning\t0\t1d"""
        mock_run_command.return_value = (True, kubectl_output)

        # Act
        result = popofiler.pick_running_pod()

        # Assert - should return first matching pod
        self.assertEqual(result, f"{self.test_project}-web-123")

    @patch('popofiler.run_command')
    def test_kubectl_context_and_namespace_usage(self, mock_run_command):
        """Test that kubectl commands use correct context and namespace"""
        # Arrange
        mock_run_command.return_value = (True, "success")

        # Act
        popofiler.pick_running_pod()

        # Assert
        command = mock_run_command.call_args[0][0]
        self.assertIn(f"--context {self.test_context}", command)
        self.assertIn(f"--namespace {self.test_namespace}", command)
        self.assertIn("--field-selector=status.phase==Running", command)


class TestDockerIntegration(unittest.TestCase):
    """Test Docker integration for Webgrind"""

    @patch('popofiler.run_command')
    def test_webgrind_docker_command(self, mock_run_command):
        """Test Webgrind Docker command structure"""
        # Arrange
        mock_run_command.return_value = (True, "webgrind started")

        # Act
        popofiler.run_webgrind()

        # Assert
        command = mock_run_command.call_args[0][0]
        self.assertIn("docker run", command)
        self.assertIn("jokkedk/webgrind:latest", command)
        self.assertIn("-p 8003:80", command)
        self.assertIn("--platform=linux/amd64", command)
        self.assertIn("-v", command)
        self.assertIn("/tmp", command)

    @patch('popofiler.run_command')
    def test_webgrind_volume_mapping(self, mock_run_command):
        """Test that Webgrind correctly maps cachegrind volume"""
        # Arrange
        mock_run_command.return_value = (True, "container running")

        # Act
        popofiler.run_webgrind()

        # Assert
        command = mock_run_command.call_args[0][0]
        self.assertIn("$(pwd)/cachegrind/:/tmp", command)


class TestFileSystemIntegration(unittest.TestCase):
    """Test file system operations"""

    @patch('popofiler.run_command')
    def test_backup_file_operations(self, mock_run_command):
        """Test backup and restore file operations"""
        # Arrange
        mock_run_command.return_value = (True, "file copied")
        test_pod = "test-pod-123"

        # Act - Test enable profiling (creates backup)
        popofiler.enable_profiling(test_pod)

        # Assert - Check backup command
        calls = mock_run_command.call_args_list
        backup_call = calls[0]  # First call should be backup
        self.assertIn("kubectl cp", backup_call[0][0])
        self.assertIn("docker-php-ext-xdebug.ini-backup", backup_call[0][0])
        self.assertIn(":/usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini", backup_call[0][0])

    @patch('popofiler.run_command')  
    def test_restore_file_operations(self, mock_run_command):
        """Test file restore operations"""
        # Arrange
        mock_run_command.return_value = (True, "file restored")
        test_pod = "test-pod-123"

        # Act - Test disable profiling (restores backup)
        popofiler.disable_profiling(test_pod)

        # Assert - Check restore command
        calls = mock_run_command.call_args_list
        restore_call = calls[0]  # First call should be restore
        self.assertIn("kubectl cp", restore_call[0][0])
        self.assertIn("docker-php-ext-xdebug.ini-backup", restore_call[0][0])
        self.assertIn(":/usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini", restore_call[0][0])

    @patch('popofiler.run_command')
    def test_profile_download_directory_structure(self, mock_run_command):
        """Test profile download creates correct directory structure"""
        # Arrange
        mock_run_command.return_value = (True, "profiles downloaded")
        test_pod = "test-pod-123"

        # Act
        popofiler.download_profiles(test_pod)

        # Assert
        command = mock_run_command.call_args[0][0]
        self.assertIn(":/tmp/cachegrind/.", command)
        self.assertIn("./cachegrind/", command)


class TestPHPIntegration(unittest.TestCase):
    """Test PHP and Xdebug integration"""

    @patch('popofiler.run_command')
    def test_xdebug_configuration_commands(self, mock_run_command):
        """Test Xdebug configuration is properly set"""
        # Arrange
        mock_run_command.return_value = (True, "config updated")
        test_pod = "test-pod-123"

        # Act
        popofiler.enable_profiling(test_pod)

        # Assert - Check configuration command
        calls = mock_run_command.call_args_list
        config_call = calls[1]  # Second call should be config
        command = config_call[0][0]
        
        self.assertIn("echo -e", command)
        self.assertIn("zend_extension=xdebug", command)
        self.assertIn("xdebug.mode=profile", command)
        self.assertIn("xdebug.output_dir=/tmp/cachegrind/", command)
        self.assertIn("xdebug.start_with_request=trigger", command)

    @patch('popofiler.run_command')
    def test_php_fpm_reload_commands(self, mock_run_command):
        """Test PHP-FPM reload is triggered correctly"""
        # Arrange  
        mock_run_command.return_value = (True, "php-fpm reloaded")
        test_pod = "test-pod-123"

        # Act - Both enable and disable should reload PHP-FPM
        popofiler.enable_profiling(test_pod)
        
        # Reset mock to check disable profiling
        mock_run_command.reset_mock()
        mock_run_command.return_value = (True, "php-fpm reloaded")
        popofiler.disable_profiling(test_pod)

        # Assert - Both workflows should contain PHP-FPM reload
        calls = mock_run_command.call_args_list
        reload_call = calls[-1]  # Last call should be PHP-FPM reload
        self.assertIn("pkill -USR2 php-fpm", reload_call[0][0])

    @patch('popofiler.run_command')
    def test_xdebug_installation_check(self, mock_run_command):
        """Test Xdebug installation detection logic"""
        # Arrange - Mock PHP module check
        mock_run_command.return_value = (True, "xdebug\nother_module\nanother_module")
        test_pod = "test-pod-123"

        # Act
        popofiler.install_xdebug(test_pod)

        # Assert - Should only call check command, not install
        self.assertEqual(mock_run_command.call_count, 1)
        command = mock_run_command.call_args[0][0]
        self.assertIn("php -m | grep xdebug", command)

    @patch('popofiler.run_command')
    def test_xdebug_installation_process(self, mock_run_command):
        """Test Xdebug installation when not present"""
        # Arrange - First call: not installed, Second call: install success
        mock_run_command.side_effect = [
            (True, "no xdebug found"),  # Check result
            (True, "installation successful")  # Install result
        ]
        test_pod = "test-pod-123"

        # Act
        popofiler.install_xdebug(test_pod)

        # Assert
        self.assertEqual(mock_run_command.call_count, 2)
        
        # Check install command
        install_call = mock_run_command.call_args_list[1]
        command = install_call[0][0]
        self.assertIn("pecl install xdebug", command)
        self.assertIn("docker-php-ext-enable xdebug", command)


class TestErrorHandlingIntegration(unittest.TestCase):
    """Test error handling in integrated scenarios"""

    @patch('popofiler.run_command')
    def test_kubectl_connectivity_failure(self, mock_run_command):
        """Test handling of kubectl connectivity issues"""
        # Arrange
        mock_run_command.return_value = (False, "Unable to connect to the server")

        # Act
        result = popofiler.pick_running_pod()

        # Assert
        self.assertIsNone(result)

    @patch('popofiler.run_command')
    def test_partial_command_failure_in_profiling(self, mock_run_command):
        """Test behavior when some commands in profiling workflow fail"""
        # Arrange - First command succeeds, second fails
        mock_run_command.side_effect = [(True, "backup success"), (False, "config failed")]
        test_pod = "test-pod-123"

        # Act
        popofiler.enable_profiling(test_pod)

        # Assert - Should stop after first failure
        self.assertEqual(mock_run_command.call_count, 2)

    @patch('popofiler.run_command')
    def test_docker_unavailable_for_webgrind(self, mock_run_command):
        """Test handling when Docker is not available"""
        # Arrange
        mock_run_command.return_value = (False, "docker: command not found")

        # Act
        popofiler.run_webgrind()

        # Assert - Should handle gracefully without crashing
        mock_run_command.assert_called_once()

    @patch('popofiler.run_command')
    def test_permission_denied_scenarios(self, mock_run_command):
        """Test handling of permission denied errors"""
        # Arrange
        mock_run_command.return_value = (False, "permission denied")
        test_pod = "test-pod-123"

        # Act & Assert - Should not crash on permission errors
        popofiler.download_profiles(test_pod)
        popofiler.install_xdebug(test_pod)
        
        # Should handle gracefully
        self.assertEqual(mock_run_command.call_count, 2)


class TestConcurrencyAndRaceConditions(unittest.TestCase):
    """Test concurrent operations and race condition handling"""

    @patch('popofiler.run_command')
    def test_simultaneous_profiling_operations(self, mock_run_command):
        """Test that operations handle concurrent access properly"""
        # This test simulates the scenario where multiple operations
        # might be attempted simultaneously
        mock_run_command.return_value = (True, "success")
        test_pod = "test-pod-123"

        # Act - Simulate rapid successive operations
        popofiler.enable_profiling(test_pod)
        popofiler.download_profiles(test_pod)
        popofiler.disable_profiling(test_pod)

        # Assert - All operations should complete
        self.assertGreater(mock_run_command.call_count, 5)

    @patch('popofiler.run_command')
    def test_pod_state_changes_during_operation(self, mock_run_command):
        """Test handling when pod state changes during operation"""
        # Arrange - Simulate pod going away during operation
        mock_run_command.side_effect = [
            (True, "success"),  # First command succeeds
            (False, "pod not found"),  # Second command fails due to pod absence
        ]
        test_pod = "test-pod-123"

        # Act
        popofiler.enable_profiling(test_pod)

        # Assert - Should handle pod disappearance gracefully
        self.assertEqual(mock_run_command.call_count, 2)


class TestPerformanceIntegration(unittest.TestCase):
    """Test performance aspects of integrations"""

    @patch('time.sleep')
    @patch('subprocess.Popen')
    def test_command_timeout_behavior(self, mock_popen, mock_sleep):
        """Test behavior with long-running commands"""
        # Arrange
        mock_process = MagicMock()
        mock_process.poll.side_effect = [None] * 100 + [0]  # Long-running then complete
        mock_process.returncode = 0
        mock_process.communicate.return_value = ("success", "")
        mock_popen.return_value = mock_process

        # Act
        with patch('tqdm.tqdm'), patch('colorama.init'), patch('colorama.deinit'):
            success, output = popofiler.run_command("sleep 1", "Test long command")

        # Assert
        self.assertTrue(success)
        self.assertGreater(mock_sleep.call_count, 0)  # Should have waited

    @patch('popofiler.run_command')
    def test_large_output_handling(self, mock_run_command):
        """Test handling of commands with large output"""
        # Arrange - Simulate large kubectl output
        large_output = "NAME\tREADY\tSTATUS\tRESTARTS\tAGE\n" + "\n".join([
            f"test-project-pod-{i}\t1/1\tRunning\t0\t1d" for i in range(1000)
        ])
        mock_run_command.return_value = (True, large_output)

        # Act
        result = popofiler.pick_running_pod()

        # Assert - Should handle large output and return first match
        self.assertEqual(result, "test-project-pod-0")


if __name__ == '__main__':
    unittest.main(verbosity=2)