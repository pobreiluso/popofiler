#!/bin/bash
set -euo pipefail
#TODO: Pasar contextos y apps por entorno en json o como sea.
K8S_CONTEXT='your_k8s_context_here'
PROJECT_NAME='your_project_name_here'
POD_NAME_PATTERN="" #NOT USED
POD_NAME_ANTI_PATTERN='your_pod_name_anti_pattern_here'
NAMESPACE='your_namespace_here'
#TRACE_RANDOM_KEY='StartProfileForMe'
TRACE_RANDOM_KEY=$(LC_ALL=C tr -dc A-Za-z0-9 </dev/urandom | head -c 64)

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

if [ "$1" = "help" ]; then
    Help
    exit 0
fi

#Pick running pod
# Use printf to safely handle variables that might contain special characters
DONOR_POD_NAME=$(kubectl --context "$K8S_CONTEXT" get pods --field-selector=status.phase==Running --namespace "$NAMESPACE" | grep "$PROJECT_NAME" | grep -v "$POD_NAME_ANTI_PATTERN" | head -1 | awk '{print $1}')

if [ -z "$DONOR_POD_NAME" ]; then
    echo "Error: No matching pod found" >&2
    exit 1
fi

echo "Selected pod: $DONOR_POD_NAME"

if [ "$1" = "enable-profiling" ]; then
	#BACKUP DE 15-xdebug.ini
	if ! kubectl cp --context="$K8S_CONTEXT" --namespace="$NAMESPACE" "$DONOR_POD_NAME":/usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini ./docker-php-ext-xdebug.ini-backup; then
		echo "Error: Failed to backup xdebug configuration" >&2
		exit 1
	fi
	#Enable xdebug under triggering
	if ! kubectl exec -it --context="$K8S_CONTEXT" --namespace="$NAMESPACE" "$DONOR_POD_NAME" -- bash -c 'echo -e "zend_extension=xdebug.so\nxdebug.mode=profile\nxdebug.output_dir=/tmp/cachegrind/\nxdebug.start_with_request=trigger" > /usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini'; then
		echo "Error: Failed to configure xdebug" >&2
		exit 1
	fi
	if ! kubectl exec -it --context="$K8S_CONTEXT" --namespace="$NAMESPACE" "$DONOR_POD_NAME" -- bash -c 'mkdir -p /tmp/cachegrind/ && chown www-data:www-data /tmp/cachegrind/'; then
		echo "Error: Failed to create cachegrind directory" >&2
		exit 1
	fi
	echo "XDEBUG_TRIGGER: $TRACE_RANDOM_KEY"
	#Restart php-fpm
	if ! kubectl exec -it --context="$K8S_CONTEXT" --namespace="$NAMESPACE" "$DONOR_POD_NAME" -- bash -c 'pkill -USR2 php-fpm'; then
		echo "Warning: Failed to restart php-fpm" >&2
	fi
elif [ "$1" = "disable-profiling" ]; then
	#Restore backup xdebug.ini
	if [ ! -f "./docker-php-ext-xdebug.ini-backup" ]; then
		echo "Error: Backup file not found. Cannot restore configuration." >&2
		exit 1
	fi
	if ! kubectl cp --context="$K8S_CONTEXT" --namespace="$NAMESPACE" ./docker-php-ext-xdebug.ini-backup "$DONOR_POD_NAME":/usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini; then
		echo "Error: Failed to restore xdebug configuration" >&2
		exit 1
	fi
	#Restart php-fpm
	if ! kubectl exec -it --context="$K8S_CONTEXT" --namespace="$NAMESPACE" "$DONOR_POD_NAME" -- bash -c 'pkill -USR2 php-fpm'; then
		echo "Warning: Failed to restart php-fpm" >&2
	fi
elif [ "$1" = "download-profiles" ]; then
	if ! kubectl cp --context="$K8S_CONTEXT" --namespace="$NAMESPACE" "$DONOR_POD_NAME":/tmp/cachegrind/. ./cachegrind/; then
		echo "Error: Failed to download profiles" >&2
		exit 1
	fi
elif [ "$1" = "install-xdebug" ]; then
	#Install xdebug
	if ! kubectl exec -it --context="$K8S_CONTEXT" --namespace="$NAMESPACE" "$DONOR_POD_NAME" -- bash -c 'pecl install xdebug && docker-php-ext-enable xdebug'; then
		echo "Error: Failed to install xdebug" >&2
		exit 1
	fi
elif [ "$1" = "run-webgrind" ]; then
	if [ ! -d "./cachegrind" ]; then
		echo "Error: cachegrind directory not found. Please download profiles first." >&2
		exit 1
	fi
	if ! docker run -it --rm -v "$(pwd)/cachegrind/:/tmp" --platform=linux/amd64 -p 8003:80 jokkedk/webgrind:latest; then
		echo "Error: Failed to run webgrind" >&2
		exit 1
	fi
	#docker run --rm -p 8003:80 clue/webgrind:latest
fi
