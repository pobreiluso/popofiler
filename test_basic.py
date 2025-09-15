#!/usr/bin/env python3
"""
Basic tests for popofiler.py that don't require external dependencies
These tests verify the test framework setup and basic functionality
"""
import unittest
import sys
import os
from unittest.mock import patch, MagicMock

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class TestFrameworkSetup(unittest.TestCase):
    """Test that the testing framework is properly set up"""
    
    def test_python_version(self):
        """Test that we're running on a supported Python version"""
        self.assertGreaterEqual(sys.version_info.major, 3)
        self.assertGreaterEqual(sys.version_info.minor, 6)
    
    def test_unittest_import(self):
        """Test that unittest module is available"""
        import unittest
        self.assertTrue(hasattr(unittest, 'TestCase'))
        self.assertTrue(hasattr(unittest, 'main'))
    
    def test_mock_import(self):
        """Test that unittest.mock is available"""
        from unittest.mock import patch, MagicMock
        self.assertTrue(callable(patch))
        self.assertTrue(callable(MagicMock))
    
    def test_sys_and_os_modules(self):
        """Test that required system modules are available"""
        import sys
        import os
        import subprocess
        
        self.assertTrue(hasattr(sys, 'argv'))
        self.assertTrue(hasattr(os, 'path'))
        self.assertTrue(hasattr(subprocess, 'Popen'))


class TestPopofilerImportWithMocks(unittest.TestCase):
    """Test popofiler import with mocked dependencies"""
    
    def setUp(self):
        """Set up mocks for external dependencies"""
        # Mock all external dependencies
        self.patchers = []
        
        # Mock colorama
        colorama_mock = MagicMock()
        colorama_patcher = patch.dict('sys.modules', {'colorama': colorama_mock})
        self.patchers.append(colorama_patcher)
        
        # Mock tqdm
        tqdm_mock = MagicMock()
        tqdm_patcher = patch.dict('sys.modules', {'tqdm': tqdm_mock})
        self.patchers.append(tqdm_patcher)
        
        # Start all patchers
        for patcher in self.patchers:
            patcher.start()
    
    def tearDown(self):
        """Clean up patchers"""
        for patcher in self.patchers:
            patcher.stop()
    
    def test_popofiler_import(self):
        """Test that popofiler can be imported with mocked dependencies"""
        try:
            import popofiler
            self.assertTrue(hasattr(popofiler, 'main'))
            self.assertTrue(hasattr(popofiler, 'run_command'))
            self.assertTrue(hasattr(popofiler, 'pick_running_pod'))
        except ImportError as e:
            self.fail(f"Failed to import popofiler: {e}")
    
    def test_popofiler_constants(self):
        """Test that popofiler constants are defined"""
        import popofiler
        
        required_constants = [
            'K8S_CONTEXT',
            'PROJECT_NAME', 
            'POD_NAME_ANTI_PATTERN',
            'NAMESPACE',
            'TRACE_RANDOM_KEY'
        ]
        
        for constant in required_constants:
            self.assertTrue(
                hasattr(popofiler, constant),
                f"Missing constant: {constant}"
            )
    
    def test_popofiler_functions(self):
        """Test that popofiler functions are defined"""
        import popofiler
        
        required_functions = [
            'run_command',
            'pick_running_pod',
            'execute_profiling_commands',
            'enable_profiling',
            'disable_profiling',
            'download_profiles',
            'install_xdebug',
            'run_webgrind',
            'main'
        ]
        
        for function in required_functions:
            self.assertTrue(
                hasattr(popofiler, function),
                f"Missing function: {function}"
            )
            self.assertTrue(
                callable(getattr(popofiler, function)),
                f"Function {function} is not callable"
            )


class TestBasicFunctionality(unittest.TestCase):
    """Test basic functionality with minimal dependencies"""
    
    def setUp(self):
        """Set up mocks for tests"""
        # Mock external dependencies
        colorama_mock = MagicMock()
        tqdm_mock = MagicMock()
        
        self.patchers = [
            patch.dict('sys.modules', {'colorama': colorama_mock}),
            patch.dict('sys.modules', {'tqdm': tqdm_mock})
        ]
        
        for patcher in self.patchers:
            patcher.start()
        
        # Import after mocking
        import popofiler
        self.popofiler = popofiler
    
    def tearDown(self):
        """Clean up patchers"""
        for patcher in self.patchers:
            patcher.stop()
    
    @patch('subprocess.Popen')
    def test_run_command_basic_structure(self, mock_popen):
        """Test basic structure of run_command function"""
        # Mock successful process
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = ("output", "")
        mock_process.poll.return_value = 0
        mock_popen.return_value = mock_process
        
        # Test the function exists and can be called
        result = self.popofiler.run_command("echo test", "Test command")
        
        # Should return tuple
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        
        # First element should be boolean (success)
        self.assertIsInstance(result[0], bool)
        
        # Second element should be string (output)
        self.assertIsInstance(result[1], str)
    
    def test_constants_have_correct_types(self):
        """Test that constants have expected types"""
        self.assertIsInstance(self.popofiler.K8S_CONTEXT, str)
        self.assertIsInstance(self.popofiler.PROJECT_NAME, str)
        self.assertIsInstance(self.popofiler.POD_NAME_ANTI_PATTERN, str)
        self.assertIsInstance(self.popofiler.NAMESPACE, str)
        self.assertIsInstance(self.popofiler.TRACE_RANDOM_KEY, str)
    
    def test_trace_key_properties(self):
        """Test properties of the trace random key"""
        key = self.popofiler.TRACE_RANDOM_KEY
        
        # Should be non-empty string
        self.assertTrue(key)
        self.assertIsInstance(key, str)
        
        # Should have reasonable length (at least 10 characters)
        self.assertGreaterEqual(len(key), 10)
        
        # Should be alphanumeric
        self.assertTrue(key.replace('_', '').replace('-', '').isalnum())


class TestProjectStructure(unittest.TestCase):
    """Test that the project structure is correct"""
    
    def test_required_files_exist(self):
        """Test that required files exist"""
        required_files = [
            'popofiler.py',
            'test_popofiler.py',
            'test_integration.py',
            'test_security.py',
            'test_end_to_end.py',
            'test_runner.py',
            'requirements-test.txt',
            'pytest.ini',
            'conftest.py',
            '.coveragerc',
            'Makefile'
        ]
        
        for filename in required_files:
            file_path = os.path.join(os.path.dirname(__file__), filename)
            self.assertTrue(
                os.path.exists(file_path),
                f"Required file missing: {filename}"
            )
    
    def test_test_files_are_python(self):
        """Test that test files are valid Python files"""
        test_files = [
            'test_popofiler.py',
            'test_integration.py', 
            'test_security.py',
            'test_end_to_end.py',
            'test_runner.py',
            'conftest.py'
        ]
        
        for filename in test_files:
            file_path = os.path.join(os.path.dirname(__file__), filename)
            
            # File should exist
            self.assertTrue(os.path.exists(file_path))
            
            # File should be readable
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                    # Should contain Python code indicators
                    self.assertTrue(
                        'import' in content or 'def' in content or 'class' in content,
                        f"File {filename} doesn't appear to contain Python code"
                    )
            except Exception as e:
                self.fail(f"Failed to read {filename}: {e}")
    
    def test_configuration_files_valid(self):
        """Test that configuration files are valid"""
        config_files = {
            'pytest.ini': '[tool:pytest]',
            '.coveragerc': '[run]',
            'requirements-test.txt': 'pytest',
            'Makefile': 'help:'
        }
        
        for filename, expected_content in config_files.items():
            file_path = os.path.join(os.path.dirname(__file__), filename)
            
            self.assertTrue(os.path.exists(file_path), f"Config file missing: {filename}")
            
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                    self.assertIn(
                        expected_content, content,
                        f"Config file {filename} missing expected content: {expected_content}"
                    )
            except Exception as e:
                self.fail(f"Failed to read config file {filename}: {e}")


if __name__ == '__main__':
    # Run with high verbosity
    unittest.main(verbosity=2)