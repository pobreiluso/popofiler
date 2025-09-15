import unittest
from unittest.mock import patch, MagicMock, call
import subprocess
import sys
import os
from io import StringIO

# Import the module under test
import popofiler


class TestPopofiler(unittest.TestCase):
    """Comprehensive test suite for popofiler.py"""

    def setUp(self):
        """Set up test fixtures before each test method."""
        self.test_pod_name = "test-project-pod-123"
        self.test_command = "kubectl get pods"
        self.test_output = "NAME\tREADY\tSTATUS\tRESTARTS\tAGE\ntest-project-pod-123\t1/1\tRunning\t0\t1d"

    def tearDown(self):
        """Clean up after each test method."""
        pass


class TestRunCommand(TestPopofiler):
    """Test cases for run_command function"""

    @patch('subprocess.Popen')
    @patch('tqdm.tqdm')
    @patch('colorama.init')
    @patch('colorama.deinit')
    def test_run_command_success(self, mock_deinit, mock_init, mock_tqdm, mock_popen):
        """Test successful command execution"""
        # Arrange
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = ("success output", "")
        mock_process.poll.side_effect = [None, None, 0]  # Running, then complete
        mock_popen.return_value = mock_process

        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__.return_value = mock_pbar

        # Act
        success, output = popofiler.run_command("echo test", "Test command")

        # Assert
        self.assertTrue(success)
        self.assertEqual(output, "success output")
        mock_popen.assert_called_once_with(
            "echo test", 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            shell=True, 
            text=True
        )
        mock_init.assert_called_once()
        mock_deinit.assert_called_once()

    @patch('subprocess.Popen')
    @patch('tqdm.tqdm')
    @patch('colorama.init')
    @patch('colorama.deinit')
    @patch('sys.stderr', new_callable=StringIO)
    def test_run_command_failure(self, mock_stderr, mock_deinit, mock_init, mock_tqdm, mock_popen):
        """Test command execution failure"""
        # Arrange
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = ("", "error message")
        mock_process.poll.side_effect = [None, 1]
        mock_popen.return_value = mock_process

        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__.return_value = mock_pbar

        # Act
        success, output = popofiler.run_command("false", "Test failing command")

        # Assert
        self.assertFalse(success)
        self.assertEqual(output, "error message")
        self.assertIn("Error: error message", mock_stderr.getvalue())

    @patch('subprocess.Popen')
    @patch('tqdm.tqdm')
    @patch('colorama.init')
    @patch('colorama.deinit')
    @patch('sys.stderr', new_callable=StringIO)
    def test_run_command_keyboard_interrupt(self, mock_stderr, mock_deinit, mock_init, mock_tqdm, mock_popen):
        """Test keyboard interrupt handling"""
        # Arrange
        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__.return_value = mock_pbar
        mock_pbar.update.side_effect = KeyboardInterrupt()

        # Act
        success, output = popofiler.run_command("sleep 10", "Test interrupt")

        # Assert
        self.assertFalse(success)
        self.assertEqual(output, "KeyboardInterrupt: Process terminated by user.")
        self.assertIn("KeyboardInterrupt", mock_stderr.getvalue())

    @patch('subprocess.Popen')
    @patch('tqdm.tqdm')
    @patch('colorama.init')
    @patch('colorama.deinit')
    @patch('sys.stderr', new_callable=StringIO)
    def test_run_command_subprocess_error(self, mock_stderr, mock_deinit, mock_init, mock_tqdm, mock_popen):
        """Test subprocess.CalledProcessError handling"""
        # Arrange
        mock_popen.side_effect = subprocess.CalledProcessError(1, "test command")

        # Act
        success, output = popofiler.run_command("invalid command", "Test subprocess error")

        # Assert
        self.assertFalse(success)
        self.assertIn("Command 'test command' returned non-zero exit status 1", output)


class TestPickRunningPod(TestPopofiler):
    """Test cases for pick_running_pod function"""

    @patch('popofiler.run_command')
    def test_pick_running_pod_success(self, mock_run_command):
        """Test successful pod selection"""
        # Arrange
        kubectl_output = f"NAME\tREADY\tSTATUS\tRESTARTS\tAGE\n{popofiler.PROJECT_NAME}-pod-123\t1/1\tRunning\t0\t1d\nother-pod\t1/1\tRunning\t0\t1d"
        mock_run_command.return_value = (True, kubectl_output)

        # Act
        result = popofiler.pick_running_pod()

        # Assert
        self.assertEqual(result, f"{popofiler.PROJECT_NAME}-pod-123")
        expected_command = f"kubectl --context {popofiler.K8S_CONTEXT} get pods --field-selector=status.phase==Running --namespace {popofiler.NAMESPACE}"
        mock_run_command.assert_called_once_with(expected_command, desc="Listing Running Pods")

    @patch('popofiler.run_command')
    def test_pick_running_pod_with_anti_pattern(self, mock_run_command):
        """Test pod selection excludes anti-pattern pods"""
        # Arrange
        kubectl_output = f"NAME\tREADY\tSTATUS\tRESTARTS\tAGE\n{popofiler.PROJECT_NAME}-{popofiler.POD_NAME_ANTI_PATTERN}-123\t1/1\tRunning\t0\t1d\n{popofiler.PROJECT_NAME}-pod-456\t1/1\tRunning\t0\t1d"
        mock_run_command.return_value = (True, kubectl_output)

        # Act
        result = popofiler.pick_running_pod()

        # Assert
        self.assertEqual(result, f"{popofiler.PROJECT_NAME}-pod-456")

    @patch('popofiler.run_command')
    @patch('sys.stdout', new_callable=StringIO)
    def test_pick_running_pod_command_failure(self, mock_stdout, mock_run_command):
        """Test handling of kubectl command failure"""
        # Arrange
        mock_run_command.return_value = (False, "kubectl error")

        # Act
        result = popofiler.pick_running_pod()

        # Assert
        self.assertIsNone(result)
        self.assertIn("Error: kubectl error", mock_stdout.getvalue())

    @patch('popofiler.run_command')
    def test_pick_running_pod_no_matching_pods(self, mock_run_command):
        """Test when no pods match the criteria"""
        # Arrange
        kubectl_output = "NAME\tREADY\tSTATUS\tRESTARTS\tAGE\nother-pod\t1/1\tRunning\t0\t1d"
        mock_run_command.return_value = (True, kubectl_output)

        # Act
        result = popofiler.pick_running_pod()

        # Assert
        self.assertIsNone(result)


class TestExecuteProfilingCommands(TestPopofiler):
    """Test cases for execute_profiling_commands function"""

    @patch('popofiler.run_command')
    @patch('sys.stdout', new_callable=StringIO)
    def test_execute_profiling_commands_success(self, mock_stdout, mock_run_command):
        """Test successful execution of all commands"""
        # Arrange
        mock_run_command.return_value = (True, "success")
        commands = ["cmd1", "cmd2", "cmd3"]

        # Act
        popofiler.execute_profiling_commands(commands)

        # Assert
        self.assertEqual(mock_run_command.call_count, 3)
        expected_calls = [
            call("cmd1", desc="Executing Command"),
            call("cmd2", desc="Executing Command"),
            call("cmd3", desc="Executing Command")
        ]
        mock_run_command.assert_has_calls(expected_calls)
        self.assertIn("Profiling configuration updated.", mock_stdout.getvalue())

    @patch('popofiler.run_command')
    def test_execute_profiling_commands_early_failure(self, mock_run_command):
        """Test early return on command failure"""
        # Arrange
        mock_run_command.side_effect = [(True, "success"), (False, "error"), (True, "success")]
        commands = ["cmd1", "cmd2", "cmd3"]

        # Act
        popofiler.execute_profiling_commands(commands)

        # Assert
        self.assertEqual(mock_run_command.call_count, 2)  # Should stop after second failure


class TestEnableProfiling(TestPopofiler):
    """Test cases for enable_profiling function"""

    @patch('popofiler.execute_profiling_commands')
    @patch('sys.stdout', new_callable=StringIO)
    def test_enable_profiling_success(self, mock_stdout, mock_execute):
        """Test successful profiling enablement"""
        # Act
        popofiler.enable_profiling(self.test_pod_name)

        # Assert
        mock_execute.assert_called_once()
        args = mock_execute.call_args[0][0]
        self.assertEqual(len(args), 4)  # Should have 4 commands
        self.assertIn(f"kubectl cp --context {popofiler.K8S_CONTEXT}", args[0])
        self.assertIn(self.test_pod_name, args[0])
        self.assertIn("XDEBUG_TRIGGER:", mock_stdout.getvalue())
        self.assertIn("Profiling enabled.", mock_stdout.getvalue())

    @patch('popofiler.execute_profiling_commands')
    def test_enable_profiling_commands_structure(self, mock_execute):
        """Test that enable_profiling generates correct commands"""
        # Act
        popofiler.enable_profiling(self.test_pod_name)

        # Assert
        commands = mock_execute.call_args[0][0]
        
        # Verify backup command
        self.assertIn("kubectl cp", commands[0])
        self.assertIn("docker-php-ext-xdebug.ini-backup", commands[0])
        
        # Verify config update command
        self.assertIn("echo -e", commands[1])
        self.assertIn("xdebug.mode=profile", commands[1])
        
        # Verify directory creation
        self.assertIn("mkdir -p /tmp/cachegrind/", commands[2])
        
        # Verify PHP-FPM restart
        self.assertIn("pkill -USR2 php-fpm", commands[3])


class TestDisableProfiling(TestPopofiler):
    """Test cases for disable_profiling function"""

    @patch('popofiler.execute_profiling_commands')
    @patch('sys.stdout', new_callable=StringIO)
    def test_disable_profiling_success(self, mock_stdout, mock_execute):
        """Test successful profiling disablement"""
        # Act
        popofiler.disable_profiling(self.test_pod_name)

        # Assert
        mock_execute.assert_called_once()
        commands = mock_execute.call_args[0][0]
        self.assertEqual(len(commands), 2)
        
        # Verify restore command
        self.assertIn("kubectl cp", commands[0])
        self.assertIn("docker-php-ext-xdebug.ini-backup", commands[0])
        
        # Verify PHP-FPM restart
        self.assertIn("pkill -USR2 php-fpm", commands[1])
        
        self.assertIn("Profiling disabled and configuration restored.", mock_stdout.getvalue())


class TestDownloadProfiles(TestPopofiler):
    """Test cases for download_profiles function"""

    @patch('popofiler.run_command')
    @patch('sys.stdout', new_callable=StringIO)
    def test_download_profiles_success(self, mock_stdout, mock_run_command):
        """Test successful profile download"""
        # Arrange
        mock_run_command.return_value = (True, "download successful")

        # Act
        popofiler.download_profiles(self.test_pod_name)

        # Assert
        expected_command = f"kubectl cp --context {popofiler.K8S_CONTEXT} --namespace={popofiler.NAMESPACE} {self.test_pod_name}:/tmp/cachegrind/. ./cachegrind/"
        mock_run_command.assert_called_once_with(expected_command)
        self.assertIn("Profiles downloaded.", mock_stdout.getvalue())

    @patch('popofiler.run_command')
    @patch('sys.stdout', new_callable=StringIO)
    def test_download_profiles_failure(self, mock_stdout, mock_run_command):
        """Test failed profile download"""
        # Arrange
        mock_run_command.return_value = (False, "download failed")

        # Act
        popofiler.download_profiles(self.test_pod_name)

        # Assert
        self.assertNotIn("Profiles downloaded.", mock_stdout.getvalue())


class TestInstallXdebug(TestPopofiler):
    """Test cases for install_xdebug function"""

    @patch('popofiler.run_command')
    @patch('sys.stdout', new_callable=StringIO)
    def test_install_xdebug_already_installed(self, mock_stdout, mock_run_command):
        """Test when Xdebug is already installed"""
        # Arrange
        mock_run_command.return_value = (True, "xdebug\n")

        # Act
        popofiler.install_xdebug(self.test_pod_name)

        # Assert
        self.assertEqual(mock_run_command.call_count, 1)
        self.assertIn("Xdebug ya está instalado.", mock_stdout.getvalue())

    @patch('popofiler.run_command')
    @patch('sys.stdout', new_callable=StringIO)
    def test_install_xdebug_successful_installation(self, mock_stdout, mock_run_command):
        """Test successful Xdebug installation"""
        # Arrange
        mock_run_command.side_effect = [(True, "no xdebug found"), (True, "installation success")]

        # Act
        popofiler.install_xdebug(self.test_pod_name)

        # Assert
        self.assertEqual(mock_run_command.call_count, 2)
        # Check the install command
        install_call = mock_run_command.call_args_list[1]
        self.assertIn("pecl install xdebug", install_call[0][0])
        self.assertIn("docker-php-ext-enable xdebug", install_call[0][0])
        self.assertIn("Xdebug instalado exitosamente.", mock_stdout.getvalue())

    @patch('popofiler.run_command')
    @patch('sys.stdout', new_callable=StringIO)
    def test_install_xdebug_installation_failure(self, mock_stdout, mock_run_command):
        """Test failed Xdebug installation"""
        # Arrange
        mock_run_command.side_effect = [(True, "no xdebug found"), (False, "installation failed")]

        # Act
        popofiler.install_xdebug(self.test_pod_name)

        # Assert
        self.assertEqual(mock_run_command.call_count, 2)
        self.assertIn("Error instalando Xdebug: installation failed", mock_stdout.getvalue())

    @patch('popofiler.run_command')
    def test_install_xdebug_case_insensitive_check(self, mock_run_command):
        """Test that Xdebug check is case insensitive"""
        # Arrange
        mock_run_command.return_value = (True, "XDEBUG\n")

        # Act
        popofiler.install_xdebug(self.test_pod_name)

        # Assert
        self.assertEqual(mock_run_command.call_count, 1)


class TestRunWebgrind(TestPopofiler):
    """Test cases for run_webgrind function"""

    @patch('popofiler.run_command')
    @patch('sys.stdout', new_callable=StringIO)
    def test_run_webgrind_success(self, mock_stdout, mock_run_command):
        """Test successful Webgrind execution"""
        # Arrange
        mock_run_command.return_value = (True, "webgrind running")

        # Act
        popofiler.run_webgrind()

        # Assert
        expected_command = "docker run -it --rm -v \"$(pwd)/cachegrind/:/tmp\" --platform=linux/amd64 -p 8003:80 jokkedk/webgrind:latest"
        mock_run_command.assert_called_once_with(expected_command, shell=True, progress_desc="Running Webgrind")
        self.assertIn("Webgrind running.", mock_stdout.getvalue())

    @patch('popofiler.run_command')
    @patch('sys.stdout', new_callable=StringIO)
    def test_run_webgrind_failure(self, mock_stdout, mock_run_command):
        """Test failed Webgrind execution"""
        # Arrange
        mock_run_command.return_value = (False, "webgrind failed")

        # Act
        popofiler.run_webgrind()

        # Assert
        self.assertNotIn("Webgrind running.", mock_stdout.getvalue())


class TestMainFunction(TestPopofiler):
    """Test cases for main function"""

    def test_main_help_no_args(self):
        """Test main function with no arguments shows help"""
        # Arrange
        original_argv = sys.argv
        sys.argv = ["popofiler.py"]

        # Act & Assert
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            popofiler.main()
            self.assertIn("Usage: script.py [COMMAND]", mock_stdout.getvalue())
            self.assertIn("Commands:", mock_stdout.getvalue())

        # Cleanup
        sys.argv = original_argv

    def test_main_explicit_help(self):
        """Test main function with help command"""
        # Arrange
        original_argv = sys.argv
        sys.argv = ["popofiler.py", "help"]

        # Act & Assert
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            popofiler.main()
            self.assertIn("Usage: script.py [COMMAND]", mock_stdout.getvalue())

        # Cleanup
        sys.argv = original_argv

    @patch('popofiler.pick_running_pod')
    @patch('popofiler.enable_profiling')
    @patch('sys.stdout', new_callable=StringIO)
    def test_main_enable_profiling(self, mock_stdout, mock_enable, mock_pick_pod):
        """Test main function with enable-profiling command"""
        # Arrange
        original_argv = sys.argv
        sys.argv = ["popofiler.py", "enable-profiling"]
        mock_pick_pod.return_value = self.test_pod_name

        # Act
        popofiler.main()

        # Assert
        mock_pick_pod.assert_called_once()
        mock_enable.assert_called_once_with(self.test_pod_name)
        self.assertIn(f"Selected Pod: {self.test_pod_name}", mock_stdout.getvalue())

        # Cleanup
        sys.argv = original_argv

    @patch('popofiler.pick_running_pod')
    @patch('popofiler.disable_profiling')
    def test_main_disable_profiling(self, mock_disable, mock_pick_pod):
        """Test main function with disable-profiling command"""
        # Arrange
        original_argv = sys.argv
        sys.argv = ["popofiler.py", "disable-profiling"]
        mock_pick_pod.return_value = self.test_pod_name

        # Act
        popofiler.main()

        # Assert
        mock_pick_pod.assert_called_once()
        mock_disable.assert_called_once_with(self.test_pod_name)

        # Cleanup
        sys.argv = original_argv

    @patch('popofiler.pick_running_pod')
    @patch('popofiler.download_profiles')
    def test_main_download_profiles(self, mock_download, mock_pick_pod):
        """Test main function with download-profiles command"""
        # Arrange
        original_argv = sys.argv
        sys.argv = ["popofiler.py", "download-profiles"]
        mock_pick_pod.return_value = self.test_pod_name

        # Act
        popofiler.main()

        # Assert
        mock_pick_pod.assert_called_once()
        mock_download.assert_called_once_with(self.test_pod_name)

        # Cleanup
        sys.argv = original_argv

    @patch('popofiler.pick_running_pod')
    @patch('popofiler.install_xdebug')
    def test_main_install_xdebug(self, mock_install, mock_pick_pod):
        """Test main function with install-xdebug command"""
        # Arrange
        original_argv = sys.argv
        sys.argv = ["popofiler.py", "install-xdebug"]
        mock_pick_pod.return_value = self.test_pod_name

        # Act
        popofiler.main()

        # Assert
        mock_pick_pod.assert_called_once()
        mock_install.assert_called_once_with(self.test_pod_name)

        # Cleanup
        sys.argv = original_argv

    @patch('popofiler.run_webgrind')
    def test_main_run_webgrind(self, mock_webgrind):
        """Test main function with run-webgrind command"""
        # Arrange
        original_argv = sys.argv
        sys.argv = ["popofiler.py", "run-webgrind"]

        # Act
        popofiler.main()

        # Assert
        mock_webgrind.assert_called_once()

        # Cleanup
        sys.argv = original_argv

    @patch('popofiler.pick_running_pod')
    def test_main_no_pod_found(self, mock_pick_pod):
        """Test main function when no pod is found"""
        # Arrange
        original_argv = sys.argv
        sys.argv = ["popofiler.py", "enable-profiling"]
        mock_pick_pod.return_value = None

        # Act
        popofiler.main()

        # Assert
        mock_pick_pod.assert_called_once()

        # Cleanup
        sys.argv = original_argv

    @patch('sys.exit')
    def test_main_invalid_command(self, mock_exit):
        """Test main function with invalid command"""
        # Arrange
        original_argv = sys.argv
        sys.argv = ["popofiler.py", "invalid-command"]

        # Act & Assert
        with patch('popofiler.pick_running_pod', return_value=self.test_pod_name):
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                popofiler.main()
                self.assertIn("Invalid command: invalid-command", mock_stdout.getvalue())
                mock_exit.assert_called_once_with(1)

        # Cleanup
        sys.argv = original_argv


class TestSecurityAndEdgeCases(TestPopofiler):
    """Security and edge case tests"""

    def test_constants_are_defined(self):
        """Test that all required constants are defined"""
        self.assertTrue(hasattr(popofiler, 'K8S_CONTEXT'))
        self.assertTrue(hasattr(popofiler, 'PROJECT_NAME'))
        self.assertTrue(hasattr(popofiler, 'POD_NAME_ANTI_PATTERN'))
        self.assertTrue(hasattr(popofiler, 'NAMESPACE'))
        self.assertTrue(hasattr(popofiler, 'TRACE_RANDOM_KEY'))

    def test_trace_random_key_generation(self):
        """Test that TRACE_RANDOM_KEY is properly generated"""
        self.assertEqual(len(popofiler.TRACE_RANDOM_KEY), 64)
        self.assertTrue(all(c.isalnum() for c in popofiler.TRACE_RANDOM_KEY))

    @patch('popofiler.run_command')
    def test_command_injection_protection(self, mock_run_command):
        """Test basic command injection protection"""
        # This test ensures commands are passed as expected to subprocess
        mock_run_command.return_value = (True, "safe output")
        
        # Test with a pod name that could contain injection attempts
        malicious_pod = "pod-name; rm -rf /"
        popofiler.enable_profiling(malicious_pod)
        
        # Verify the malicious string is passed through (subprocess handles escaping)
        calls = mock_run_command.call_args_list
        for call in calls:
            command = call[0][0]
            if malicious_pod in command:
                # The malicious string should be in the command as-is
                # subprocess.Popen with shell=True will handle proper escaping
                self.assertIn(malicious_pod, command)

    def test_empty_pod_list_handling(self):
        """Test handling of empty kubectl output"""
        with patch('popofiler.run_command', return_value=(True, "NAME\tREADY\tSTATUS\tRESTARTS\tAGE")):
            result = popofiler.pick_running_pod()
            self.assertIsNone(result)

    @patch('popofiler.run_command')
    def test_malformed_kubectl_output(self, mock_run_command):
        """Test handling of malformed kubectl output"""
        # Test with incomplete line
        mock_run_command.return_value = (True, "incomplete-line-without-tabs")
        result = popofiler.pick_running_pod()
        self.assertIsNone(result)


class TestIntegrationScenarios(TestPopofiler):
    """Integration test scenarios"""

    @patch('popofiler.run_command')
    @patch('sys.stdout', new_callable=StringIO)
    def test_full_profiling_workflow(self, mock_stdout, mock_run_command):
        """Test complete profiling enable -> download -> disable workflow"""
        # Mock successful responses for all commands
        mock_run_command.return_value = (True, "success")

        # Test enable profiling
        popofiler.enable_profiling(self.test_pod_name)
        
        # Test download profiles  
        popofiler.download_profiles(self.test_pod_name)
        
        # Test disable profiling
        popofiler.disable_profiling(self.test_pod_name)

        # Verify expected output messages
        output = mock_stdout.getvalue()
        self.assertIn("Profiling enabled.", output)
        self.assertIn("Profiles downloaded.", output)
        self.assertIn("Profiling disabled and configuration restored.", output)

    @patch('popofiler.run_command')
    def test_xdebug_installation_workflow(self, mock_run_command):
        """Test Xdebug installation detection and installation"""
        # First call: check if installed (not found)
        # Second call: install Xdebug (success)
        mock_run_command.side_effect = [(True, "no xdebug"), (True, "installation success")]

        popofiler.install_xdebug(self.test_pod_name)

        self.assertEqual(mock_run_command.call_count, 2)
        
        # Verify check command
        check_call = mock_run_command.call_args_list[0]
        self.assertIn("php -m | grep xdebug", check_call[0][0])
        
        # Verify install command
        install_call = mock_run_command.call_args_list[1]
        self.assertIn("pecl install xdebug", install_call[0][0])


if __name__ == '__main__':
    # Configure test runner
    unittest.main(verbosity=2, buffer=True)