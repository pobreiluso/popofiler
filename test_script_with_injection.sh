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
