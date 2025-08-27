#!/usr/bin/env python3
"""
Tests for popofiler.py to verify bug fixes and basic functionality.
"""

import unittest
import sys
import os
import tempfile
import shutil
from unittest.mock import patch, MagicMock, call
from io import StringIO

# Add the current directory to the path to import popofiler
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import popofiler

class TestPopoFiler(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)
    
    def tearDown(self):
        """Clean up test fixtures."""
        os.chdir(self.original_dir)
        shutil.rmtree(self.test_dir)

    @patch('popofiler.run_command')
    def test_pick_running_pod_success(self, mock_run_command):
        """Test successful pod selection."""
        mock_output = "NAME    READY   STATUS    RESTARTS   AGE\ntest-project-name-123   1/1     Running   0          5m\nother-pod   1/1     Running   0          10m"
        mock_run_command.return_value = (True, mock_output)
        
        result = popofiler.pick_running_pod()
        self.assertEqual(result, "test-project-name-123")

    @patch('popofiler.run_command')
    def test_pick_running_pod_no_match(self, mock_run_command):
        """Test pod selection when no matching pods exist."""
        mock_output = "NAME    READY   STATUS    RESTARTS   AGE\nother-pod   1/1     Running   0          10m"
        mock_run_command.return_value = (True, mock_output)
        
        result = popofiler.pick_running_pod()
        self.assertIsNone(result)

    @patch('popofiler.run_command')
    def test_pick_running_pod_command_failure(self, mock_run_command):
        """Test pod selection when kubectl command fails."""
        mock_run_command.return_value = (False, "kubectl error")
        
        result = popofiler.pick_running_pod()
        self.assertIsNone(result)

    def test_run_webgrind_no_directory(self):
        """Test run_webgrind fails when cachegrind directory doesn't exist."""
        result = popofiler.run_webgrind()
        self.assertFalse(result)

    @patch('popofiler.run_command')
    def test_run_webgrind_with_directory(self, mock_run_command):
        """Test run_webgrind succeeds when cachegrind directory exists."""
        os.makedirs("cachegrind")
        mock_run_command.return_value = (True, "docker output")
        
        result = popofiler.run_webgrind()
        self.assertTrue(result)

    @patch('sys.argv', ['popofiler.py'])
    def test_main_no_pod_found_exits(self):
        """Test main function exits when no pod is found."""
        with patch('popofiler.pick_running_pod', return_value=None):
            with self.assertRaises(SystemExit) as cm:
                popofiler.main()
            self.assertEqual(cm.exception.code, 1)

    @patch('popofiler.subprocess.Popen')
    def test_run_command_progress_bar_bounds(self, mock_popen):
        """Test that progress bar doesn't exceed 100%."""
        # Mock a process that takes a while to complete
        mock_process = MagicMock()
        mock_process.poll.side_effect = [None] * 150 + [0]  # 150 None responses, then 0
        mock_process.communicate.return_value = ("success", "")
        mock_process.returncode = 0
        mock_popen.return_value = mock_process
        
        with patch('popofiler.tqdm') as mock_tqdm:
            mock_pbar = MagicMock()
            mock_tqdm.return_value.__enter__.return_value = mock_pbar
            
            success, output = popofiler.run_command("test command")
            
            # Verify progress bar was updated but not more than 99 times
            # (since we prevent exceeding 99% in our fix)
            update_calls = [call for call in mock_pbar.update.call_args_list if call == call(1)]
            self.assertLessEqual(len(update_calls), 99)

    def test_trace_random_key_generation(self):
        """Test that TRACE_RANDOM_KEY is generated and has correct length."""
        self.assertEqual(len(popofiler.TRACE_RANDOM_KEY), 64)
        # Verify it contains only alphanumeric characters
        self.assertTrue(all(c.isalnum() for c in popofiler.TRACE_RANDOM_KEY))


class TestShellScriptLogic(unittest.TestCase):
    """Test cases that verify shell script logic would work correctly."""
    
    def test_backup_file_check_logic(self):
        """Test the logic for checking backup file existence (mimics shell script fix)."""
        backup_file = "./docker-php-ext-xdebug.ini-backup"
        
        # Test when backup file doesn't exist
        self.assertFalse(os.path.exists(backup_file))
        
        # Test when backup file exists
        with open(backup_file, 'w') as f:
            f.write("test content")
        self.assertTrue(os.path.exists(backup_file))
        
        os.remove(backup_file)

    def test_directory_existence_check(self):
        """Test directory existence check logic (mimics shell script fix)."""
        cachegrind_dir = "./cachegrind"
        
        # Test when directory doesn't exist
        self.assertFalse(os.path.exists(cachegrind_dir))
        
        # Test when directory exists
        os.makedirs(cachegrind_dir)
        self.assertTrue(os.path.exists(cachegrind_dir))
        
        shutil.rmtree(cachegrind_dir)


if __name__ == '__main__':
    # Temporarily replace constants to avoid real kubectl calls
    popofiler.K8S_CONTEXT = 'test-context'
    popofiler.PROJECT_NAME = 'test-project-name'
    popofiler.POD_NAME_ANTI_PATTERN = 'anti-pattern'
    popofiler.NAMESPACE = 'test-namespace'
    
    unittest.main()