#!/usr/bin/env python3
"""
Test runner script for popofiler test suite
Provides convenient test execution with detailed reporting
"""
import sys
import os
import subprocess
import argparse
from pathlib import Path
import json
from datetime import datetime


class TestRunner:
    """Test runner for popofiler test suite"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.test_files = [
            'test_popofiler.py',
            'test_integration.py', 
            'test_security.py',
            'test_end_to_end.py'
        ]
    
    def run_command(self, command, description=""):
        """Run a shell command and return result"""
        print(f"\n{'='*60}")
        print(f"Running: {description}")
        print(f"Command: {command}")
        print('='*60)
        
        try:
            result = subprocess.run(
                command, 
                shell=True, 
                cwd=self.project_root,
                capture_output=True, 
                text=True,
                timeout=300
            )
            
            print("STDOUT:")
            print(result.stdout)
            
            if result.stderr:
                print("\nSTDERR:")
                print(result.stderr)
            
            print(f"\nReturn code: {result.returncode}")
            return result.returncode == 0, result
            
        except subprocess.TimeoutExpired:
            print("❌ Command timed out after 5 minutes")
            return False, None
        except Exception as e:
            print(f"❌ Command failed with exception: {e}")
            return False, None
    
    def check_dependencies(self):
        """Check if required dependencies are installed"""
        print("\n🔍 Checking dependencies...")
        
        required_packages = ['pytest', 'pytest-cov', 'coverage']
        missing_packages = []
        
        for package in required_packages:
            success, _ = self.run_command(
                f"python -c 'import {package.replace('-', '_')}'",
                f"Checking {package}"
            )
            if not success:
                missing_packages.append(package)
        
        if missing_packages:
            print(f"\n❌ Missing packages: {missing_packages}")
            print("Install them with: pip install -r requirements-test.txt")
            return False
        
        print("✅ All required packages are available")
        return True
    
    def run_unit_tests(self):
        """Run unit tests"""
        command = "python -m pytest test_popofiler.py -v --tb=short"
        return self.run_command(command, "Unit Tests")
    
    def run_integration_tests(self):
        """Run integration tests"""  
        command = "python -m pytest test_integration.py -v --tb=short"
        return self.run_command(command, "Integration Tests")
    
    def run_security_tests(self):
        """Run security tests"""
        command = "python -m pytest test_security.py -v --tb=short"
        return self.run_command(command, "Security Tests")
    
    def run_end_to_end_tests(self):
        """Run end-to-end tests"""
        command = "python -m pytest test_end_to_end.py -v --tb=short"
        return self.run_command(command, "End-to-End Tests")
    
    def run_all_tests(self):
        """Run all tests"""
        command = f"python -m pytest {' '.join(self.test_files)} -v --tb=short"
        return self.run_command(command, "All Tests")
    
    def run_coverage_tests(self):
        """Run tests with coverage"""
        command = (
            "python -m pytest "
            "--cov=popofiler "
            "--cov-report=html:htmlcov "
            "--cov-report=xml:coverage.xml "
            "--cov-report=term-missing "
            "--cov-fail-under=85 "
            "-v"
        )
        return self.run_command(command, "Coverage Tests")
    
    def run_specific_test(self, test_pattern):
        """Run specific test by pattern"""
        command = f"python -m pytest -k '{test_pattern}' -v --tb=short"
        return self.run_command(command, f"Tests matching: {test_pattern}")
    
    def run_specific_file(self, test_file):
        """Run specific test file"""
        if test_file not in self.test_files:
            print(f"❌ Test file '{test_file}' not found. Available: {self.test_files}")
            return False, None
        
        command = f"python -m pytest {test_file} -v --tb=short"
        return self.run_command(command, f"Test file: {test_file}")
    
    def lint_code(self):
        """Run code linting"""
        commands = [
            ("flake8 popofiler.py test_*.py", "Flake8 Linting"),
            ("python -m py_compile popofiler.py", "Python Syntax Check"),
        ]
        
        all_passed = True
        for command, description in commands:
            success, _ = self.run_command(command, description)
            if not success:
                all_passed = False
        
        return all_passed
    
    def security_check(self):
        """Run security checks"""
        commands = [
            ("python -c \"import bandit; print('Bandit available')\"", "Check Bandit"),
            ("python -c \"import safety; print('Safety available')\"", "Check Safety"),
        ]
        
        # Check if security tools are available
        bandit_available = True
        safety_available = True
        
        try:
            import bandit
        except ImportError:
            bandit_available = False
            print("⚠️  Bandit not available, skipping security scan")
        
        try:
            import safety
        except ImportError:
            safety_available = False
            print("⚠️  Safety not available, skipping dependency check")
        
        results = []
        
        if bandit_available:
            success, _ = self.run_command(
                "python -m bandit -r popofiler.py", 
                "Bandit Security Scan"
            )
            results.append(success)
        
        if safety_available:
            success, _ = self.run_command(
                "python -m safety check", 
                "Safety Dependency Check"
            )
            results.append(success)
        
        return all(results) if results else True
    
    def generate_report(self):
        """Generate comprehensive test report"""
        print("\n" + "="*80)
        print("📊 GENERATING COMPREHENSIVE TEST REPORT")
        print("="*80)
        
        # Run coverage tests to generate reports
        success, result = self.run_coverage_tests()
        
        if success:
            print("\n✅ Test report generated successfully!")
            print(f"📁 HTML Report: {self.project_root}/htmlcov/index.html")
            print(f"📄 XML Report: {self.project_root}/coverage.xml")
        else:
            print("\n❌ Failed to generate test report")
        
        return success
    
    def clean_artifacts(self):
        """Clean test artifacts"""
        artifacts = [
            '__pycache__',
            '.pytest_cache',
            'htmlcov',
            '.coverage',
            'coverage.xml',
            'test_report.html',
            'test_report.json'
        ]
        
        print("\n🧹 Cleaning test artifacts...")
        
        for artifact in artifacts:
            artifact_path = self.project_root / artifact
            if artifact_path.exists():
                if artifact_path.is_dir():
                    success, _ = self.run_command(f"rm -rf {artifact_path}", f"Remove {artifact}")
                else:
                    success, _ = self.run_command(f"rm -f {artifact_path}", f"Remove {artifact}")
        
        print("✅ Cleanup completed")
    
    def main(self):
        """Main test runner entry point"""
        parser = argparse.ArgumentParser(description="Popofiler Test Runner")
        
        parser.add_argument(
            'action',
            choices=[
                'all', 'unit', 'integration', 'security', 'e2e',
                'coverage', 'lint', 'security-check', 'report', 'clean'
            ],
            nargs='?',
            default='all',
            help='Test action to perform'
        )
        
        parser.add_argument(
            '--file',
            help='Run specific test file'
        )
        
        parser.add_argument(
            '--pattern', '-k',
            help='Run tests matching pattern'
        )
        
        parser.add_argument(
            '--no-deps-check',
            action='store_true',
            help='Skip dependency check'
        )
        
        args = parser.parse_args()
        
        print("🧪 POPOFILER TEST RUNNER")
        print("="*50)
        print(f"📅 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📂 Project root: {self.project_root}")
        print(f"🎯 Action: {args.action}")
        
        # Check dependencies unless skipped
        if not args.no_deps_check:
            if not self.check_dependencies():
                print("\n❌ Dependency check failed. Use --no-deps-check to skip.")
                return 1
        
        # Execute requested action
        success = True
        
        if args.file:
            success, _ = self.run_specific_file(args.file)
        elif args.pattern:
            success, _ = self.run_specific_test(args.pattern)
        elif args.action == 'unit':
            success, _ = self.run_unit_tests()
        elif args.action == 'integration':
            success, _ = self.run_integration_tests()
        elif args.action == 'security':
            success, _ = self.run_security_tests()
        elif args.action == 'e2e':
            success, _ = self.run_end_to_end_tests()
        elif args.action == 'coverage':
            success, _ = self.run_coverage_tests()
        elif args.action == 'lint':
            success = self.lint_code()
        elif args.action == 'security-check':
            success = self.security_check()
        elif args.action == 'report':
            success = self.generate_report()
        elif args.action == 'clean':
            self.clean_artifacts()
            success = True
        elif args.action == 'all':
            # Run comprehensive test suite
            print("\n🚀 Running comprehensive test suite...")
            
            test_results = []
            
            # Run all test categories
            test_results.append(("Unit Tests", self.run_unit_tests()[0]))
            test_results.append(("Integration Tests", self.run_integration_tests()[0]))
            test_results.append(("Security Tests", self.run_security_tests()[0]))
            test_results.append(("End-to-End Tests", self.run_end_to_end_tests()[0]))
            test_results.append(("Code Linting", self.lint_code()))
            test_results.append(("Security Check", self.security_check()))
            
            # Generate final report
            print("\n" + "="*80)
            print("📋 FINAL TEST REPORT")
            print("="*80)
            
            for test_name, result in test_results:
                status = "✅ PASSED" if result else "❌ FAILED"
                print(f"{test_name:<20}: {status}")
            
            all_passed = all(result for _, result in test_results)
            
            if all_passed:
                print("\n🎉 ALL TESTS PASSED!")
                # Generate coverage report
                self.generate_report()
            else:
                print("\n💥 SOME TESTS FAILED!")
            
            success = all_passed
        
        # Final status
        print("\n" + "="*80)
        if success:
            print("🎉 TEST RUN COMPLETED SUCCESSFULLY!")
        else:
            print("💥 TEST RUN FAILED!")
        print(f"📅 Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80)
        
        return 0 if success else 1


if __name__ == '__main__':
    runner = TestRunner()
    sys.exit(runner.main())