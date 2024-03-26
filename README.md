# Xdebug Kubernetes Profiler Toolkit README

## Descripción
Este conjunto de scripts proporciona una herramienta completa para gestionar Xdebug en pods de Kubernetes, específicamente orientado a entornos de producción y desarrollo. Permite a los usuarios activar o desactivar el perfilado, instalar Xdebug, guardar y descargar trazas de perfil, y utilizar Webgrind para analizar dichas trazas.

## Características
- **Activación/Desactivación de Xdebug**: Controla el estado de Xdebug en el pod seleccionado para perfilar tu aplicación de manera eficiente.
- **Instalación de Xdebug**: Facilita la instalación de Xdebug en el pod para comenzar el perfilado rápidamente.
- **Descarga de Trazas de Perfilado**: Permite descargar las trazas generadas por Xdebug para un análisis posterior.
- **Análisis con Webgrind**: Integra la ejecución de Webgrind en un contenedor Docker para una interpretación gráfica de las trazas.

## Uso
El script se maneja mediante subcomandos específicos dependiendo de la acción que se desee realizar:

`bash script.sh [subcomando]

### Subcomandos Disponibles
- `enable-profiling`: Activa el perfilado Xdebug en el pod.
- `disable-profiling`: Desactiva el perfilado Xdebug, restaurando la configuración previa.
- `download-profiles`: Descarga las trazas de perfilado generadas por Xdebug.
- `install-xdebug`: Instala Xdebug en el pod.
- `run-webgrind`: Ejecuta Webgrind en un contenedor Docker para analizar las trazas de perfilado.

## Precauciones
- **Rendimiento**: La activación de Xdebug en producción puede impactar el rendimiento. Usar con cautela.
- **Seguridad**: Asegúrate de no exponer información sensible al usar el script.
- **Backups**: Realiza copias de seguridad de configuraciones importantes antes de realizar cambios.
- **Reversión**: Es crucial poder revertir los cambios realizados por el script para mantener la estabilidad del entorno.

## Contribuciones
Tus contribuciones son bienvenidas. Si tienes sugerencias o mejoras, por favor, no dudes en abrir un issue o un pull request en el repositorio.

## Licencia
Este proyecto se publica bajo [incluir tipo de licencia], lo que permite su uso y distribución bajo los términos especificados.
