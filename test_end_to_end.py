"""
End-to-end tests for popofiler.py
Tests complete user workflows and system integration
"""
import unittest
from unittest.mock import patch, MagicMock, call
import subprocess
import sys
import tempfile
import os

import popofiler


class TestCompleteWorkflows(unittest.TestCase):
    """Test complete end-to-end workflows"""

    def setUp(self):
        self.test_pod = "test-project-web-123" 
        self.kubectl_output = f"NAME\tREADY\tSTATUS\tRESTARTS\tAGE\n{self.test_pod}\t1/1\tRunning\t0\t1d"

    @patch('popofiler.run_command')
    def test_complete_profiling_workflow(self, mock_run_command):
        """Test complete profiling enable -> use -> download -> disable workflow"""
        # Mock all command responses
        mock_responses = [
            (True, self.kubectl_output),  # pick_running_pod
            (True, "backup created"),     # enable: backup
            (True, "config updated"),     # enable: config
            (True, "directory created"),  # enable: mkdir
            (True, "php-fpm reloaded"),   # enable: reload
            (True, "profiles downloaded"), # download
            (True, "config restored"),    # disable: restore
            (True, "php-fpm reloaded"),   # disable: reload
        ]
        mock_run_command.side_effect = mock_responses

        # Execute complete workflow
        
        # 1. Enable profiling
        pod = popofiler.pick_running_pod()
        self.assertEqual(pod, self.test_pod)
        
        popofiler.enable_profiling(pod)
        
        # 2. Download profiles (simulating after some profiling)
        popofiler.download_profiles(pod)
        
        # 3. Disable profiling
        popofiler.disable_profiling(pod)

        # Verify all expected commands were called
        self.assertEqual(mock_run_command.call_count, 8)
        
        # Verify command sequence
        calls = [call[0][0] for call in mock_run_command.call_args_list]
        
        # Check key commands are present
        self.assertTrue(any("get pods" in call for call in calls))
        self.assertTrue(any("docker-php-ext-xdebug.ini-backup" in call for call in calls))
        self.assertTrue(any("xdebug.mode=profile" in call for call in calls))
        self.assertTrue(any("/tmp/cachegrind/" in call for call in calls))
        self.assertTrue(any("pkill -USR2 php-fpm" in call for call in calls))

    @patch('popofiler.run_command')
    def test_xdebug_installation_and_profiling_workflow(self, mock_run_command):
        """Test complete workflow: install Xdebug -> enable profiling -> use"""
        mock_responses = [
            (True, self.kubectl_output),     # pick_running_pod
            (True, "no xdebug found"),       # install: check
            (True, "xdebug installed"),      # install: install
            (True, "backup created"),        # enable: backup
            (True, "config updated"),        # enable: config
            (True, "directory created"),     # enable: mkdir
            (True, "php-fpm reloaded"),      # enable: reload
        ]
        mock_run_command.side_effect = mock_responses

        # Execute workflow
        pod = popofiler.pick_running_pod()
        popofiler.install_xdebug(pod)
        popofiler.enable_profiling(pod)

        # Verify installation and profiling setup
        self.assertEqual(mock_run_command.call_count, 7)
        
        calls = [call[0][0] for call in mock_run_command.call_args_list]
        
        # Verify installation commands
        self.assertTrue(any("php -m | grep xdebug" in call for call in calls))
        self.assertTrue(any("pecl install xdebug" in call for call in calls))
        
        # Verify profiling setup
        self.assertTrue(any("xdebug.mode=profile" in call for call in calls))

    @patch('popofiler.run_command')
    def test_analysis_workflow_with_webgrind(self, mock_run_command):
        """Test complete analysis workflow: profile -> download -> analyze"""
        mock_responses = [
            (True, self.kubectl_output),     # pick_running_pod
            (True, "profiles downloaded"),   # download
            (True, "webgrind started"),      # webgrind
        ]
        mock_run_command.side_effect = mock_responses

        # Execute workflow
        pod = popofiler.pick_running_pod()
        popofiler.download_profiles(pod)
        popofiler.run_webgrind()

        # Verify analysis workflow
        self.assertEqual(mock_run_command.call_count, 3)
        
        calls = [call[0][0] for call in mock_run_command.call_args_list]
        
        # Verify download and webgrind commands
        self.assertTrue(any("cachegrind" in call for call in calls))
        self.assertTrue(any("webgrind" in call for call in calls))
        self.assertTrue(any("docker run" in call for call in calls))


class TestCommandLineIntegration(unittest.TestCase):
    """Test command-line interface integration"""

    def setUp(self):
        self.original_argv = sys.argv.copy()
        self.test_pod = "test-project-web-123"
        self.kubectl_output = f"NAME\tREADY\tSTATUS\tRESTARTS\tAGE\n{self.test_pod}\t1/1\tRunning\t0\t1d"

    def tearDown(self):
        sys.argv[:] = self.original_argv

    @patch('popofiler.run_command')
    def test_cli_enable_profiling_workflow(self, mock_run_command):
        """Test CLI workflow for enabling profiling"""
        mock_responses = [
            (True, self.kubectl_output),  # pick_running_pod
            (True, "backup created"),     # backup
            (True, "config updated"),     # config
            (True, "directory created"),  # mkdir
            (True, "php-fpm reloaded"),   # reload
        ]
        mock_run_command.side_effect = mock_responses
        
        # Simulate CLI call
        sys.argv = ["popofiler.py", "enable-profiling"]
        
        # Run main function
        popofiler.main()
        
        # Verify commands were executed
        self.assertEqual(mock_run_command.call_count, 5)

    @patch('popofiler.run_command')  
    def test_cli_complete_cycle(self, mock_run_command):
        """Test complete CLI cycle: enable -> download -> disable"""
        mock_run_command.return_value = (True, "success")
        
        # Test enable-profiling
        sys.argv = ["popofiler.py", "enable-profiling"]
        with patch('popofiler.pick_running_pod', return_value=self.test_pod):
            popofiler.main()
        
        # Reset mock for download
        mock_run_command.reset_mock()
        
        # Test download-profiles  
        sys.argv = ["popofiler.py", "download-profiles"]
        with patch('popofiler.pick_running_pod', return_value=self.test_pod):
            popofiler.main()
            
        # Reset mock for disable
        mock_run_command.reset_mock()
        
        # Test disable-profiling
        sys.argv = ["popofiler.py", "disable-profiling"] 
        with patch('popofiler.pick_running_pod', return_value=self.test_pod):
            popofiler.main()

        # Each command should have been executed
        self.assertTrue(mock_run_command.called)

    def test_cli_help_and_invalid_commands(self):
        """Test CLI help and error handling"""
        from io import StringIO
        
        # Test help command
        sys.argv = ["popofiler.py", "help"]
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            popofiler.main()
            self.assertIn("Usage:", mock_stdout.getvalue())
            self.assertIn("Commands:", mock_stdout.getvalue())

        # Test no arguments (should show help)
        sys.argv = ["popofiler.py"]
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            popofiler.main()
            self.assertIn("Usage:", mock_stdout.getvalue())

        # Test invalid command
        sys.argv = ["popofiler.py", "invalid-command"]
        with patch('popofiler.pick_running_pod', return_value=self.test_pod):
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                with patch('sys.exit') as mock_exit:
                    popofiler.main()
                    self.assertIn("Invalid command:", mock_stdout.getvalue())
                    mock_exit.assert_called_once_with(1)


class TestErrorRecoveryWorkflows(unittest.TestCase):
    """Test error recovery and resilience in workflows"""

    def setUp(self):
        self.test_pod = "test-project-web-123"

    @patch('popofiler.run_command')
    def test_partial_failure_recovery(self, mock_run_command):
        """Test recovery from partial command failures"""
        # Simulate backup success, config failure
        mock_responses = [
            (True, "backup success"),
            (False, "config failed"),
        ]
        mock_run_command.side_effect = mock_responses

        # Should stop after config failure
        popofiler.enable_profiling(self.test_pod)
        
        # Verify it stopped after failure
        self.assertEqual(mock_run_command.call_count, 2)

    @patch('popofiler.run_command')
    def test_kubectl_connectivity_failure_handling(self, mock_run_command):
        """Test handling of kubectl connectivity failures"""
        # Simulate kubectl failure
        mock_run_command.return_value = (False, "Unable to connect to server")
        
        # Should handle gracefully
        pod = popofiler.pick_running_pod()
        self.assertIsNone(pod)

    @patch('popofiler.run_command')
    def test_pod_disappearance_during_workflow(self, mock_run_command):
        """Test handling when pod disappears during workflow"""
        # First call succeeds (pod exists), subsequent calls fail (pod gone)
        mock_run_command.side_effect = [
            (True, "backup success"),
            (False, "pod not found"),
        ]
        
        # Should handle pod disappearance gracefully
        popofiler.enable_profiling(self.test_pod)
        
        # Should have attempted both commands
        self.assertEqual(mock_run_command.call_count, 2)

    @patch('popofiler.run_command')
    def test_permission_denied_recovery(self, mock_run_command):
        """Test recovery from permission denied errors"""
        mock_run_command.return_value = (False, "permission denied")
        
        # Should not crash on permission errors
        try:
            popofiler.enable_profiling(self.test_pod)
            popofiler.download_profiles(self.test_pod)
            popofiler.install_xdebug(self.test_pod)
        except Exception as e:
            self.fail(f"Should handle permission errors gracefully: {e}")


class TestRealWorldScenarios(unittest.TestCase):
    """Test scenarios that simulate real-world usage"""

    def setUp(self):
        self.production_pod = "myapp-production-web-abc123"
        self.staging_pod = "myapp-staging-api-def456"

    @patch('popofiler.run_command')
    def test_production_environment_workflow(self, mock_run_command):
        """Test typical production environment workflow"""
        # Simulate production kubectl output with multiple pods
        production_output = f"""NAME\tREADY\tSTATUS\tRESTARTS\tAGE
{self.production_pod}\t1/1\tRunning\t0\t7d
myapp-production-worker-xyz789\t1/1\tRunning\t0\t7d
myapp-production-cache-123abc\t1/1\tRunning\t0\t7d"""

        mock_responses = [
            (True, production_output),       # pick pod
            (True, "backup created"),        # backup config
            (True, "config updated"),        # update config
            (True, "directory created"),     # create dir
            (True, "php-fpm reloaded"),      # reload php-fpm
            (True, "profiles downloaded"),   # download profiles
            (True, "config restored"),       # restore config
            (True, "php-fpm reloaded"),      # reload php-fpm
        ]
        mock_run_command.side_effect = mock_responses

        # Execute production workflow
        pod = popofiler.pick_running_pod()
        self.assertEqual(pod, self.production_pod)  # Should pick first matching pod
        
        popofiler.enable_profiling(pod)
        # Simulate some time for profiling...
        popofiler.download_profiles(pod)
        popofiler.disable_profiling(pod)

        # Verify all steps executed
        self.assertEqual(mock_run_command.call_count, 8)

    @patch('popofiler.run_command')
    def test_multiple_environment_handling(self, mock_run_command):
        """Test handling different environments (staging vs production)"""
        # Test with different PROJECT_NAME values
        with patch('popofiler.PROJECT_NAME', 'staging-app'):
            staging_output = f"NAME\tREADY\tSTATUS\tRESTARTS\tAGE\nstaging-app-web-123\t1/1\tRunning\t0\t1d"
            mock_run_command.return_value = (True, staging_output)
            
            pod = popofiler.pick_running_pod()
            self.assertEqual(pod, "staging-app-web-123")

        with patch('popofiler.PROJECT_NAME', 'production-app'):
            prod_output = f"NAME\tREADY\tSTATUS\tRESTARTS\tAGE\nproduction-app-web-456\t1/1\tRunning\t0\t7d"
            mock_run_command.return_value = (True, prod_output)
            
            pod = popofiler.pick_running_pod()
            self.assertEqual(pod, "production-app-web-456")

    @patch('popofiler.run_command')
    def test_large_scale_environment(self, mock_run_command):
        """Test handling large-scale environments with many pods"""
        # Simulate large kubectl output
        large_output_lines = ["NAME\tREADY\tSTATUS\tRESTARTS\tAGE"]
        for i in range(100):
            if i == 0:  # First matching pod should be selected
                large_output_lines.append(f"myapp-web-{i:03d}\t1/1\tRunning\t0\t1d")
            else:
                large_output_lines.append(f"other-app-web-{i:03d}\t1/1\tRunning\t0\t1d")
                
        large_output = "\n".join(large_output_lines)
        
        with patch('popofiler.PROJECT_NAME', 'myapp'):
            mock_run_command.return_value = (True, large_output)
            
            pod = popofiler.pick_running_pod()
            self.assertEqual(pod, "myapp-web-000")

    @patch('popofiler.run_command')
    def test_anti_pattern_filtering(self, mock_run_command):
        """Test that anti-pattern pods are correctly filtered out"""
        # Include pods with anti-pattern that should be excluded
        mixed_output = f"""NAME\tREADY\tSTATUS\tRESTARTS\tAGE
myapp-{popofiler.POD_NAME_ANTI_PATTERN}-web-123\t1/1\tRunning\t0\t1d
myapp-web-456\t1/1\tRunning\t0\t1d
myapp-{popofiler.POD_NAME_ANTI_PATTERN}-api-789\t1/1\tRunning\t0\t1d"""

        with patch('popofiler.PROJECT_NAME', 'myapp'):
            mock_run_command.return_value = (True, mixed_output)
            
            pod = popofiler.pick_running_pod()
            # Should select the pod without anti-pattern
            self.assertEqual(pod, "myapp-web-456")


class TestConcurrentUsageScenarios(unittest.TestCase):
    """Test scenarios involving concurrent usage"""

    @patch('popofiler.run_command')
    def test_rapid_successive_operations(self, mock_run_command):
        """Test rapid successive operations on same pod"""
        mock_run_command.return_value = (True, "success")
        test_pod = "test-pod-123"

        # Simulate rapid operations
        operations = [
            lambda: popofiler.enable_profiling(test_pod),
            lambda: popofiler.download_profiles(test_pod),
            lambda: popofiler.disable_profiling(test_pod),
            lambda: popofiler.install_xdebug(test_pod),
        ]

        # Execute all operations rapidly
        for operation in operations:
            operation()

        # All should complete without interference
        self.assertGreater(mock_run_command.call_count, 4)

    @patch('popofiler.run_command')
    def test_webgrind_isolation(self, mock_run_command):
        """Test that Webgrind runs independently of other operations"""
        mock_run_command.return_value = (True, "success")

        # Webgrind doesn't need a pod, should work independently
        popofiler.run_webgrind()
        
        # Verify Webgrind command structure
        command = mock_run_command.call_args[0][0]
        self.assertIn("docker run", command)
        self.assertIn("webgrind", command)


if __name__ == '__main__':
    unittest.main(verbosity=2)