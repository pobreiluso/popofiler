# Makefile for popofiler testing and development

.PHONY: help install test test-unit test-integration test-security test-coverage clean lint format security-check setup-dev

# Default target
help:
	@echo "Available targets:"
	@echo "  help           - Show this help message"
	@echo "  setup-dev      - Set up development environment"
	@echo "  install        - Install test dependencies"
	@echo "  test           - Run all tests"
	@echo "  test-unit      - Run unit tests only"
	@echo "  test-integration - Run integration tests only" 
	@echo "  test-security  - Run security tests only"
	@echo "  test-coverage  - Run tests with coverage report"
	@echo "  lint           - Run code linting"
	@echo "  format         - Format code with black and isort"
	@echo "  security-check - Run security vulnerability checks"
	@echo "  clean          - Clean up test artifacts"

# Development setup
setup-dev: install
	@echo "Development environment setup complete"

# Install dependencies
install:
	pip install -r requirements-test.txt

# Run all tests
test:
	python -m pytest -v

# Run unit tests only
test-unit:
	python -m pytest test_popofiler.py::TestRunCommand -v
	python -m pytest test_popofiler.py::TestPickRunningPod -v
	python -m pytest test_popofiler.py::TestExecuteProfilingCommands -v
	python -m pytest test_popofiler.py::TestEnableProfiling -v
	python -m pytest test_popofiler.py::TestDisableProfiling -v
	python -m pytest test_popofiler.py::TestDownloadProfiles -v
	python -m pytest test_popofiler.py::TestInstallXdebug -v
	python -m pytest test_popofiler.py::TestRunWebgrind -v
	python -m pytest test_popofiler.py::TestMainFunction -v
	python -m pytest test_popofiler.py::TestSecurityAndEdgeCases -v

# Run integration tests only
test-integration:
	python -m pytest test_integration.py -v

# Run security tests only  
test-security:
	python -m pytest test_security.py -v

# Run tests with coverage
test-coverage:
	python -m pytest --cov=popofiler --cov-report=html --cov-report=term-missing --cov-fail-under=85

# Lint code
lint:
	flake8 popofiler.py test_*.py
	black --check popofiler.py test_*.py
	isort --check-only popofiler.py test_*.py

# Format code
format:
	black popofiler.py test_*.py
	isort popofiler.py test_*.py

# Security checks
security-check:
	bandit -r popofiler.py
	safety check -r requirements-test.txt

# Clean up artifacts
clean:
	rm -rf __pycache__/
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf coverage.xml
	rm -rf test_report.html
	rm -rf test_report.json
	rm -rf .tox/
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete

# Quick test command for development
quick-test:
	python -m pytest test_popofiler.py::TestRunCommand::test_run_command_success -v

# Run specific test file
test-file:
	@read -p "Enter test file name (e.g., test_popofiler.py): " file; \
	python -m pytest $$file -v

# Run tests matching pattern
test-pattern:
	@read -p "Enter test pattern (e.g., test_enable): " pattern; \
	python -m pytest -k $$pattern -v

# Generate test report
report:
	python -m pytest --html=test_report.html --self-contained-html --json-report --json-report-file=test_report.json

# Check test dependencies
check-deps:
	pip check
	pip list --outdated

# Performance testing
test-performance:
	python -m pytest --benchmark-only -v

# Run tests in parallel (if pytest-xdist is installed)
test-parallel:
	python -c "import pytest_xdist" 2>/dev/null && python -m pytest -n auto || python -m pytest

# Verbose testing with all output
test-verbose:
	python -m pytest -v -s --tb=long

# Test with specific Python version
test-python:
	@read -p "Enter Python version (e.g., 3.9): " version; \
	python$$version -m pytest -v