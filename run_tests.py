#!/usr/bin/env python3
"""
Test runner script for popofiler test suite.
Provides easy execution of all test types with proper configuration.
"""

import sys
import subprocess
import os
import argparse
from pathlib import Path


def run_command(cmd, description="Running command"):
    """Execute a command and return success status."""
    print(f"\n🔄 {description}...")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        if result.stdout:
            print(f"Output: {result.stdout[:500]}{'...' if len(result.stdout) > 500 else ''}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed with exit code {e.returncode}")
        if e.stdout:
            print(f"Stdout: {e.stdout}")
        if e.stderr:
            print(f"Stderr: {e.stderr}")
        return False
    except FileNotFoundError:
        print(f"❌ Command not found: {cmd[0]}")
        return False


def check_dependencies():
    """Check if required dependencies are available."""
    print("🔍 Checking dependencies...")
    
    # Check Python version
    if sys.version_info < (3, 7):
        print("❌ Python 3.7+ required")
        return False
    
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    
    # Try to import required modules
    required_modules = ['unittest', 'subprocess', 'tqdm', 'colorama']
    missing_modules = []
    
    for module in required_modules:
        try:
            __import__(module)
            print(f"✅ {module} available")
        except ImportError:
            print(f"❌ {module} not available")
            missing_modules.append(module)
    
    if missing_modules:
        print(f"\n📦 Install missing dependencies:")
        print(f"pip install {' '.join(missing_modules)}")
        return False
    
    return True


def run_unit_tests(verbose=False):
    """Run unit tests using unittest."""
    print("\n🧪 Running Unit Tests")
    print("=" * 50)
    
    cmd = [sys.executable, '-m', 'unittest']
    if verbose:
        cmd.extend(['-v'])
    
    # Discover and run unit tests
    cmd.extend(['discover', '-s', '.', '-p', 'test_popofiler.py'])
    
    return run_command(cmd, "Unit tests")


def run_integration_tests(verbose=False):
    """Run integration tests."""
    print("\n🔗 Running Integration Tests")
    print("=" * 50)
    
    cmd = [sys.executable, '-m', 'unittest']
    if verbose:
        cmd.extend(['-v'])
    
    cmd.extend(['discover', '-s', '.', '-p', 'test_integration_popofiler.py'])
    
    return run_command(cmd, "Integration tests")


def run_security_tests(verbose=False):
    """Run security tests."""
    print("\n🔒 Running Security Tests")
    print("=" * 50)
    
    cmd = [sys.executable, '-m', 'unittest']
    if verbose:
        cmd.extend(['-v'])
    
    cmd.extend(['discover', '-s', '.', '-p', 'test_security_popofiler.py'])
    
    return run_command(cmd, "Security tests")


def run_coverage_analysis():
    """Run coverage analysis if coverage is available."""
    print("\n📊 Running Coverage Analysis")
    print("=" * 50)
    
    try:
        import coverage
        
        # Run tests with coverage
        cmd = ['coverage', 'run', '-m', 'unittest', 'discover', '-s', '.', '-p', 'test_*.py']
        if not run_command(cmd, "Coverage collection"):
            return False
        
        # Generate coverage report
        cmd = ['coverage', 'report', '-m']
        if not run_command(cmd, "Coverage report generation"):
            return False
        
        # Generate HTML report
        cmd = ['coverage', 'html']
        if run_command(cmd, "HTML coverage report generation"):
            print("📋 HTML coverage report generated in 'htmlcov/' directory")
        
        return True
    
    except ImportError:
        print("ℹ️  Coverage module not available. Install with: pip install coverage")
        return True  # Not a failure, just not available


def run_linting():
    """Run code linting if available."""
    print("\n🔍 Running Code Quality Checks")
    print("=" * 50)
    
    linters = [
        (['flake8', 'popofiler.py', 'test_*.py'], "Flake8 linting"),
        (['pylint', 'popofiler.py'], "Pylint analysis"),
        (['black', '--check', 'popofiler.py', 'test_*.py'], "Black formatting check"),
    ]
    
    results = []
    for cmd, description in linters:
        try:
            results.append(run_command(cmd, description))
        except:
            print(f"ℹ️  {cmd[0]} not available")
            results.append(True)  # Don't fail if linter not available
    
    return all(results)


def run_performance_tests():
    """Run basic performance tests."""
    print("\n⚡ Running Performance Tests")
    print("=" * 50)
    
    # Simple performance test
    test_script = '''
import time
import popofiler
from unittest.mock import patch

def test_performance():
    with patch("popofiler.run_command", return_value=(True, "success")):
        start = time.time()
        for i in range(100):
            popofiler.pick_running_pod()
        end = time.time()
        
        avg_time = (end - start) / 100
        print(f"Average time per pick_running_pod call: {avg_time:.4f}s")
        
        if avg_time > 0.01:  # 10ms threshold
            print("⚠️  Performance warning: operations taking longer than expected")
        else:
            print("✅ Performance test passed")

if __name__ == "__main__":
    test_performance()
'''
    
    # Write and run performance test
    with open('temp_perf_test.py', 'w') as f:
        f.write(test_script)
    
    try:
        result = run_command([sys.executable, 'temp_perf_test.py'], "Performance tests")
        return result
    finally:
        # Clean up
        if os.path.exists('temp_perf_test.py'):
            os.remove('temp_perf_test.py')


def run_all_tests(verbose=False, include_optional=True):
    """Run all test suites."""
    print("🚀 Running Complete Test Suite")
    print("=" * 70)
    
    results = []
    
    # Core tests (always run)
    results.append(run_unit_tests(verbose))
    results.append(run_integration_tests(verbose))
    results.append(run_security_tests(verbose))
    
    if include_optional:
        # Optional tests (may not be available on all systems)
        results.append(run_coverage_analysis())
        results.append(run_linting())
        results.append(run_performance_tests())
    
    # Summary
    print("\n📋 Test Summary")
    print("=" * 50)
    
    passed = sum(results)
    total = len(results)
    
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed!")
        return True
    else:
        print("⚠️  Some tests failed. Check output above for details.")
        return False


def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(description='Popofiler Test Runner')
    parser.add_argument('--type', choices=['unit', 'integration', 'security', 'all'], 
                       default='all', help='Type of tests to run')
    parser.add_argument('--verbose', '-v', action='store_true', 
                       help='Verbose output')
    parser.add_argument('--no-optional', action='store_true',
                       help='Skip optional tests (coverage, linting, performance)')
    parser.add_argument('--coverage-only', action='store_true',
                       help='Run only coverage analysis')
    
    args = parser.parse_args()
    
    print("🧪 Popofiler Test Suite")
    print("=" * 50)
    print(f"Python: {sys.version}")
    print(f"Working directory: {os.getcwd()}")
    print()
    
    # Check dependencies first
    if not check_dependencies():
        print("❌ Dependency check failed")
        return 1
    
    success = True
    
    if args.coverage_only:
        success = run_coverage_analysis()
    elif args.type == 'unit':
        success = run_unit_tests(args.verbose)
    elif args.type == 'integration':
        success = run_integration_tests(args.verbose)
    elif args.type == 'security':
        success = run_security_tests(args.verbose)
    elif args.type == 'all':
        success = run_all_tests(args.verbose, not args.no_optional)
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())