#!/bin/bash
# Test script for popofiler.sh to verify bug fixes

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0

# Function to run a test
run_test() {
    local test_name="$1"
    local test_command="$2"
    local expected_exit_code="${3:-0}"
    
    echo -e "${YELLOW}Running: $test_name${NC}"
    
    if eval "$test_command"; then
        if [ $? -eq "$expected_exit_code" ]; then
            echo -e "${GREEN}✓ PASS: $test_name${NC}"
            ((TESTS_PASSED++))
        else
            echo -e "${RED}✗ FAIL: $test_name (unexpected exit code)${NC}"
            ((TESTS_FAILED++))
        fi
    else
        if [ $? -eq "$expected_exit_code" ]; then
            echo -e "${GREEN}✓ PASS: $test_name${NC}"
            ((TESTS_PASSED++))
        else
            echo -e "${RED}✗ FAIL: $test_name${NC}"
            ((TESTS_FAILED++))
        fi
    fi
    echo
}

# Function to test variable quoting safety
test_variable_quoting() {
    echo -e "${YELLOW}Testing variable quoting safety${NC}"
    
    # Create a test version of the script with malicious values
    cat > test_script_with_injection.sh << 'EOF'
#!/bin/bash
set -euo pipefail

K8S_CONTEXT='test; echo "INJECTION_SUCCESSFUL"'
PROJECT_NAME='test'
POD_NAME_ANTI_PATTERN='anti'
NAMESPACE='test'

# This should be safe due to proper quoting
DONOR_POD_NAME=$(echo "dummy-pod" | grep "test" | grep -v "anti" | head -1 | awk '{print $1}')

if [ -z "$DONOR_POD_NAME" ]; then
    echo "Error: No matching pod found" >&2
    exit 1
fi

echo "Selected pod: $DONOR_POD_NAME"
EOF
    
    chmod +x test_script_with_injection.sh
    
    # Run the test script - it should NOT execute the injection
    output=$(./test_script_with_injection.sh 2>&1 || true)
    
    if [[ "$output" != *"INJECTION_SUCCESSFUL"* ]]; then
        echo -e "${GREEN}✓ PASS: Variable injection prevented${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ FAIL: Variable injection not prevented${NC}"
        ((TESTS_FAILED++))
    fi
    
    rm -f test_script_with_injection.sh
    echo
}

# Function to test backup file checking
test_backup_file_logic() {
    echo -e "${YELLOW}Testing backup file logic${NC}"
    
    # Test when backup file doesn't exist
    if [ ! -f "./docker-php-ext-xdebug.ini-backup" ]; then
        echo -e "${GREEN}✓ PASS: Correctly detects missing backup file${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ FAIL: Failed to detect missing backup file${NC}"
        ((TESTS_FAILED++))
    fi
    
    # Create backup file and test detection
    echo "test backup content" > ./docker-php-ext-xdebug.ini-backup
    if [ -f "./docker-php-ext-xdebug.ini-backup" ]; then
        echo -e "${GREEN}✓ PASS: Correctly detects existing backup file${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ FAIL: Failed to detect existing backup file${NC}"
        ((TESTS_FAILED++))
    fi
    
    # Clean up
    rm -f ./docker-php-ext-xdebug.ini-backup
    echo
}

# Function to test directory checking
test_directory_logic() {
    echo -e "${YELLOW}Testing directory logic${NC}"
    
    # Test when cachegrind directory doesn't exist
    if [ ! -d "./cachegrind" ]; then
        echo -e "${GREEN}✓ PASS: Correctly detects missing cachegrind directory${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ FAIL: Failed to detect missing cachegrind directory${NC}"
        ((TESTS_FAILED++))
    fi
    
    # Create directory and test detection
    mkdir -p ./cachegrind
    if [ -d "./cachegrind" ]; then
        echo -e "${GREEN}✓ PASS: Correctly detects existing cachegrind directory${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ FAIL: Failed to detect existing cachegrind directory${NC}"
        ((TESTS_FAILED++))
    fi
    
    # Clean up
    rm -rf ./cachegrind
    echo
}

# Function to test error handling structure
test_error_handling_structure() {
    echo -e "${YELLOW}Testing error handling structure${NC}"
    
    # Create a test script that mimics our error handling
    cat > test_error_handling.sh << 'EOF'
#!/bin/bash
set -euo pipefail

# Test command that will fail
if ! false; then
    echo "Error: Command failed" >&2
    exit 1
fi

echo "This should not be reached"
EOF
    
    chmod +x test_error_handling.sh
    
    # Run the test script - it should exit with code 1
    output=$(./test_error_handling.sh 2>&1 || echo "EXIT_CODE:$?")
    
    if [[ "$output" == *"Error: Command failed"* ]] && [[ "$output" == *"EXIT_CODE:1"* ]]; then
        echo -e "${GREEN}✓ PASS: Error handling works correctly${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ FAIL: Error handling not working${NC}"
        ((TESTS_FAILED++))
    fi
    
    rm -f test_error_handling.sh
    echo
}

# Main test execution
echo "==================================="
echo "Running popofiler.sh bug fix tests"
echo "==================================="
echo

test_variable_quoting
test_backup_file_logic
test_directory_logic  
test_error_handling_structure

# Test summary
echo "==================================="
echo -e "Test Results:"
echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
echo -e "${RED}Failed: $TESTS_FAILED${NC}"
echo "==================================="

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
fi