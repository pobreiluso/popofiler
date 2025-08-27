#!/bin/bash
set -euo pipefail  # Exit on error, undefined variables, and pipe failures

# TODO: Pasar contextos y apps por entorno en json o como sea.
K8S_CONTEXT='your_k8s_context_here'
PROJECT_NAME='your_project_name_here'
POD_NAME_PATTERN="" #NOT USED
POD_NAME_ANTI_PATTERN='your_pod_name_anti_pattern_here'
NAMESPACE='your_namespace_here'

# Function to generate secure random key
generate_trace_key() {
    LC_ALL=C tr -dc A-Za-z0-9 </dev/urandom | head -c 64 || {
        echo "Error: Failed to generate random key" >&2
        exit 1
    }
}

TRACE_RANDOM_KEY=$(generate_trace_key)

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

# Function to validate configuration
validate_config() {
    local errors=0
    
    if [[ "$K8S_CONTEXT" == "your_k8s_context_here" ]]; then
        echo "Error: K8S_CONTEXT must be configured" >&2
        ((errors++))
    fi
    
    if [[ "$PROJECT_NAME" == "your_project_name_here" ]]; then
        echo "Error: PROJECT_NAME must be configured" >&2
        ((errors++))
    fi
    
    if [[ "$POD_NAME_ANTI_PATTERN" == "your_pod_name_anti_pattern_here" ]]; then
        echo "Error: POD_NAME_ANTI_PATTERN must be configured" >&2
        ((errors++))
    fi
    
    if [[ "$NAMESPACE" == "your_namespace_here" ]]; then
        echo "Error: NAMESPACE must be configured" >&2
        ((errors++))
    fi
    
    if [[ $errors -gt 0 ]]; then
        echo "Please configure the required variables at the top of this script." >&2
        exit 1
    fi
    
    return 0
}

# Check if help is requested or no arguments provided
if [[ $# -eq 0 ]] || [[ "$1" = "help" ]]; then
    Help
    exit 0
fi

# Validate configuration for all commands except help
validate_config

# Function to pick running pod with error handling
pick_running_pod() {
    local pod_list
    pod_list=$(kubectl --context "$K8S_CONTEXT" get pods --field-selector=status.phase==Running --namespace "$NAMESPACE" 2>/dev/null) || {
        echo "Error: Failed to get pods from Kubernetes cluster" >&2
        exit 1
    }
    
    local donor_pod
    donor_pod=$(echo "$pod_list" | grep "$PROJECT_NAME" | grep -v "$POD_NAME_ANTI_PATTERN" | head -1 | awk '{print $1}')
    
    if [[ -z "$donor_pod" ]]; then
        echo "Error: No suitable pod found matching project '$PROJECT_NAME' and not matching anti-pattern '$POD_NAME_ANTI_PATTERN'" >&2
        exit 1
    fi
    
    echo "$donor_pod"
}

# Pick running pod (only for commands that need it)
if [[ "$1" != "run-webgrind" ]]; then
    DONOR_POD_NAME=$(pick_running_pod)
    echo "Selected pod: $DONOR_POD_NAME"
fi

# Function to execute command with error checking
execute_with_check() {
    local cmd="$1"
    local desc="$2"
    
    echo "Executing: $desc"
    if ! eval "$cmd"; then
        echo "Error: Failed to execute: $desc" >&2
        exit 1
    fi
}

# Main command processing
case "$1" in
    "enable-profiling")
        echo "Enabling Xdebug profiling..."
        # BACKUP DE 15-xdebug.ini
        execute_with_check "kubectl cp --context='$K8S_CONTEXT' --namespace='$NAMESPACE' '$DONOR_POD_NAME':/usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini ./docker-php-ext-xdebug.ini-backup" "Backing up xdebug configuration"
        
        # Enable xdebug under triggering
        execute_with_check "kubectl exec -it --context='$K8S_CONTEXT' --namespace='$NAMESPACE' '$DONOR_POD_NAME' -- bash -c 'echo -e \"zend_extension=xdebug\\nxdebug.mode=profile\\nxdebug.output_dir=/tmp/cachegrind/\\nxdebug.start_with_request=trigger\" > /usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini'" "Configuring xdebug"
        
        execute_with_check "kubectl exec -it --context='$K8S_CONTEXT' --namespace='$NAMESPACE' '$DONOR_POD_NAME' -- bash -c 'mkdir -p /tmp/cachegrind/ && chown www-data:www-data /tmp/cachegrind/'" "Creating cachegrind directory"
        
        echo "XDEBUG_TRIGGER: $TRACE_RANDOM_KEY"
        
        # Restart php-fpm
        execute_with_check "kubectl exec -it --context='$K8S_CONTEXT' --namespace='$NAMESPACE' '$DONOR_POD_NAME' -- bash -c 'pkill -USR2 php-fpm'" "Restarting php-fpm"
        
        echo "Profiling enabled successfully."
        ;;
        
    "disable-profiling")
        echo "Disabling Xdebug profiling..."
        
        # Check if backup file exists
        if [[ ! -f "./docker-php-ext-xdebug.ini-backup" ]]; then
            echo "Error: Backup file not found. Cannot restore previous configuration." >&2
            exit 1
        fi
        
        # Restore backup xdebug.ini
        execute_with_check "kubectl cp --context='$K8S_CONTEXT' --namespace='$NAMESPACE' ./docker-php-ext-xdebug.ini-backup '$DONOR_POD_NAME':/usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini" "Restoring xdebug configuration"
        
        # Restart php-fpm
        execute_with_check "kubectl exec -it --context='$K8S_CONTEXT' --namespace='$NAMESPACE' '$DONOR_POD_NAME' -- bash -c 'pkill -USR2 php-fpm'" "Restarting php-fpm"
        
        echo "Profiling disabled and configuration restored."
        ;;
        
    "download-profiles")
        echo "Downloading profiles..."
        
        # Create local directory if it doesn't exist
        mkdir -p ./cachegrind
        
        execute_with_check "kubectl cp --context='$K8S_CONTEXT' --namespace='$NAMESPACE' '$DONOR_POD_NAME':/tmp/cachegrind/. ./cachegrind/" "Downloading profiling traces"
        
        echo "Profiles downloaded successfully."
        ;;
        
    "install-xdebug")
        echo "Installing Xdebug..."
        
        # Check if Xdebug is already installed
        if kubectl exec -it --context="$K8S_CONTEXT" --namespace="$NAMESPACE" "$DONOR_POD_NAME" -- php -m | grep -q xdebug; then
            echo "Xdebug is already installed."
        else
            # Install xdebug
            execute_with_check "kubectl exec -it --context='$K8S_CONTEXT' --namespace='$NAMESPACE' '$DONOR_POD_NAME' -- bash -c 'pecl install xdebug && docker-php-ext-enable xdebug'" "Installing Xdebug"
            echo "Xdebug installed successfully."
        fi
        ;;
        
    "run-webgrind")
        echo "Running Webgrind..."
        
        # Check if cachegrind directory exists
        if [[ ! -d "./cachegrind" ]]; then
            echo "Error: cachegrind directory not found. Please download profiles first." >&2
            exit 1
        fi
        
        # Get absolute path for Docker volume mount
        CACHEGRIND_PATH=$(readlink -f ./cachegrind)
        
        execute_with_check "docker run -it --rm -v '$CACHEGRIND_PATH':/tmp --platform=linux/amd64 -p 8003:80 jokkedk/webgrind:latest" "Running Webgrind container"
        ;;
        
    *)
        echo "Error: Invalid command: $1" >&2
        echo "Valid commands: enable-profiling, disable-profiling, download-profiles, install-xdebug, run-webgrind" >&2
        Help
        exit 1
        ;;
esac

echo "Operation completed successfully."