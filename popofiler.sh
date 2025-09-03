#!/bin/bash

# Exit on any error
set -e

# Configuration - Please update these values for your environment
K8S_CONTEXT='your_k8s_context_here'
PROJECT_NAME='your_project_name_here'
POD_NAME_PATTERN="" #NOT USED
POD_NAME_ANTI_PATTERN='your_pod_name_anti_pattern_here'
NAMESPACE='your_namespace_here'

# Generate random trace key
TRACE_RANDOM_KEY=$(LC_ALL=C tr -dc A-Za-z0-9 </dev/urandom | head -c 64)

# Function to check if required variables are set
check_config() {
    local missing=()
    
    if [[ "$K8S_CONTEXT" == "your_k8s_context_here" ]]; then
        missing+=("K8S_CONTEXT")
    fi
    if [[ "$PROJECT_NAME" == "your_project_name_here" ]]; then
        missing+=("PROJECT_NAME")
    fi
    if [[ "$POD_NAME_ANTI_PATTERN" == "your_pod_name_anti_pattern_here" ]]; then
        missing+=("POD_NAME_ANTI_PATTERN")
    fi
    if [[ "$NAMESPACE" == "your_namespace_here" ]]; then
        missing+=("NAMESPACE")
    fi
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        echo "Error: Please configure the following variables in the script:" >&2
        printf ' - %s\n' "${missing[@]}" >&2
        echo "These are currently set to placeholder values." >&2
        exit 1
    fi
}

Help() {
    # Display Help
    echo "Este script gestiona Xdebug en un pod remoto de Kubernetes específicamente para el namespace especificado."
    echo "Permite activar o desactivar Xdebug, instalarlo, guardar y descargar trazas de perfiles, y ejecutar Webgrind para analizar dichas trazas."
    echo
    echo "Sintaxis: bash script.sh [subcomando]"
    echo "Ejemplos: "
    echo "    bash script.sh enable-profiling # Activa el perfilado Xdebug en el pod."
    echo "    bash script.sh disable-profiling # Desactiva el perfilado Xdebug en el pod."
    echo "    bash script.sh download-profiles # Descarga las trazas de perfilado de Xdebug."
    echo "    bash script.sh install-xdebug # Instala Xdebug en el pod."
    echo "    bash script.sh run-webgrind # Ejecuta Webgrind en un contenedor Docker para analizar las trazas."
    echo " "
    echo -e "\033[1mSubcomandos:\033[0m"
    echo ""
    echo "enable-profiling     Activa el perfilado Xdebug en el pod seleccionado."
    echo "disable-profiling    Desactiva el perfilado Xdebug, restaurando la configuración previa."
    echo "download-profiles    Descarga las trazas de perfilado generadas por Xdebug."
    echo "install-xdebug       Instala Xdebug en el pod, si aún no está instalado."
    echo "run-webgrind         Ejecuta Webgrind en un contenedor Docker para analizar las trazas de perfilado."
    echo
}

# Show help if requested or no arguments provided
if [[ $# -eq 0 ]] || [[ "$1" == "help" ]]; then
    Help
    exit 0
fi

# Check configuration before proceeding
check_config

# Security: Validate namespace format
if ! validate_k8s_name "$NAMESPACE"; then
    echo "Error: Invalid namespace format: $NAMESPACE" >&2
    exit 1
fi

# Function to validate Kubernetes resource names
validate_k8s_name() {
    local name="$1"
    if [[ ! "$name" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]] || [[ ${#name} -gt 63 ]]; then
        return 1
    fi
    return 0
}

# Function to safely pick a running pod
pick_running_pod() {
    local pods_output
    if ! pods_output=$(kubectl --context "$K8S_CONTEXT" get pods --field-selector=status.phase==Running --namespace "$NAMESPACE" 2>/dev/null); then
        echo "Error: Failed to get pods. Check your kubectl configuration and context." >&2
        exit 1
    fi
    
    local donor_pod
    donor_pod=$(echo "$pods_output" | grep "$PROJECT_NAME" | grep -v "$POD_NAME_ANTI_PATTERN" | head -1 | awk '{print $1}')
    
    if [[ -z "$donor_pod" ]]; then
        echo "Error: No suitable pod found with project name '$PROJECT_NAME' excluding pattern '$POD_NAME_ANTI_PATTERN'" >&2
        exit 1
    fi
    
    # Security: Validate pod name format to prevent injection
    if ! validate_k8s_name "$donor_pod"; then
        echo "Error: Invalid pod name format: $donor_pod" >&2
        exit 1
    fi
    
    echo "$donor_pod"
}

# Get the pod name
DONOR_POD_NAME=$(pick_running_pod)
echo "Selected pod: $DONOR_POD_NAME"

# Execute the requested command
case "$1" in
    "enable-profiling")
        echo "Enabling Xdebug profiling..."
        # Backup original xdebug configuration
        if ! kubectl cp --context="$K8S_CONTEXT" --namespace="$NAMESPACE" "$DONOR_POD_NAME:/usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini" ./docker-php-ext-xdebug.ini-backup; then
            echo "Warning: Could not backup original xdebug configuration. Proceeding anyway." >&2
        fi
        
        # Enable xdebug with profiling configuration
        kubectl exec -it --context="$K8S_CONTEXT" --namespace="$NAMESPACE" "$DONOR_POD_NAME" -- bash -c 'echo -e "zend_extension=xdebug\nxdebug.mode=profile\nxdebug.output_dir=/tmp/cachegrind/\nxdebug.start_with_request=trigger" > /usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini'
        
        # Create and set permissions for cachegrind directory
        kubectl exec -it --context="$K8S_CONTEXT" --namespace="$NAMESPACE" "$DONOR_POD_NAME" -- bash -c 'mkdir -p /tmp/cachegrind/ && chown www-data:www-data /tmp/cachegrind/'
        
        echo "XDEBUG_TRIGGER: $TRACE_RANDOM_KEY"
        
        # Restart php-fpm to apply changes
        kubectl exec -it --context="$K8S_CONTEXT" --namespace="$NAMESPACE" "$DONOR_POD_NAME" -- bash -c 'pkill -USR2 php-fpm'
        echo "Profiling enabled successfully."
        ;;
        
    "disable-profiling")
        echo "Disabling Xdebug profiling..."
        if [[ ! -f "./docker-php-ext-xdebug.ini-backup" ]]; then
            echo "Error: Backup file './docker-php-ext-xdebug.ini-backup' not found." >&2
            echo "Cannot restore original configuration." >&2
            exit 1
        fi
        
        # Restore backup configuration
        kubectl cp --context="$K8S_CONTEXT" --namespace="$NAMESPACE" ./docker-php-ext-xdebug.ini-backup "$DONOR_POD_NAME:/usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini"
        
        # Restart php-fpm
        kubectl exec -it --context="$K8S_CONTEXT" --namespace="$NAMESPACE" "$DONOR_POD_NAME" -- bash -c 'pkill -USR2 php-fpm'
        echo "Profiling disabled and configuration restored."
        ;;
        
    "download-profiles")
        echo "Downloading profiles..."
        # Create local directory if it doesn't exist
        mkdir -p ./cachegrind/
        
        # Download profiles from pod
        kubectl cp --context="$K8S_CONTEXT" --namespace="$NAMESPACE" "$DONOR_POD_NAME:/tmp/cachegrind/." ./cachegrind/
        echo "Profiles downloaded to ./cachegrind/"
        ;;
        
    "install-xdebug")
        echo "Installing Xdebug..."
        # Check if Xdebug is already installed
        if kubectl exec -it --context="$K8S_CONTEXT" --namespace="$NAMESPACE" "$DONOR_POD_NAME" -- php -m | grep -q xdebug; then
            echo "Xdebug is already installed."
        else
            # Install Xdebug
            kubectl exec -it --context="$K8S_CONTEXT" --namespace="$NAMESPACE" "$DONOR_POD_NAME" -- bash -c 'pecl install xdebug && docker-php-ext-enable xdebug'
            echo "Xdebug installed successfully."
        fi
        ;;
        
    "run-webgrind")
        echo "Starting Webgrind..."
        if [[ ! -d "./cachegrind" ]]; then
            echo "Warning: ./cachegrind directory not found." >&2
            echo "Please run 'download-profiles' first to download profile files." >&2
            exit 1
        fi
        
        echo "Running Webgrind on http://localhost:8003"
        echo "Press Ctrl+C to stop the container."
        docker run -it --rm -v "$(pwd)/cachegrind":/tmp --platform=linux/amd64 -p 8003:80 jokkedk/webgrind:latest
        ;;
        
    *)
        echo "Error: Invalid command '$1'" >&2
        echo "Use '$0 help' to see available commands." >&2
        exit 1
        ;;
esac
