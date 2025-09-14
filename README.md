# 🛡️ Xdebug Kubernetes Profiler Toolkit - Security Hardened

## 🚨 CRITICAL SECURITY NOTICE

**⚠️ USE ONLY THE PYTHON VERSION (`popofiler.py`)**

The bash script (`popofiler.sh`) contains critical security vulnerabilities and should NOT be used in production. Always use the security-hardened Python implementation.

## 📋 Description
This toolkit provides a comprehensive solution for managing Xdebug in Kubernetes pods, specifically designed for production and development environments with enterprise-grade security. It enables users to activate/deactivate profiling, install Xdebug, download profiling traces, and analyze them using Webgrind.

## ✨ Key Features
- **🔒 Security-First Design**: Input validation, secure command execution, and environment-based configuration
- **⚡ Xdebug Management**: Safely control Xdebug state in selected pods with comprehensive validation
- **📦 Automated Installation**: Secure Xdebug installation with proper error handling
- **📊 Profile Analysis**: Secure download and analysis of profiling traces
- **🐳 Webgrind Integration**: Containerized Webgrind execution for trace visualization

## 🚀 Secure Usage

### Prerequisites
- Python 3.7+
- kubectl configured with appropriate RBAC permissions
- Docker (for Webgrind analysis)

### Environment Setup
```bash
# Required environment variables
export K8S_CONTEXT="your-k8s-context"
export PROJECT_NAME="your-project"
export NAMESPACE="your-namespace"  
export POD_NAME_ANTI_PATTERN="pattern-to-exclude"
```

### Command Usage
```bash
# Use the secure Python implementation
python3 popofiler.py [command]
```

### Available Commands
- `help` - Show detailed usage information
- `enable-profiling` - Securely enable Xdebug profiling with validation
- `disable-profiling` - Safely disable profiling and restore configuration
- `download-profiles` - Download profiling traces with path validation
- `install-xdebug` - Install Xdebug with proper error handling
- `run-webgrind` - Launch Webgrind container for analysis

## 🔐 Security Features

### ✅ Input Validation
- Kubernetes resource name validation
- Project name sanitization  
- Command parameter validation
- Environment variable validation

### ✅ Secure Execution
- No shell injection vulnerabilities
- Parameterized command execution
- Comprehensive error handling
- Sanitized logging and error messages

### ✅ Cryptographic Security
- Cryptographically secure random key generation
- No hardcoded credentials or secrets
- Environment-based configuration

## 🛡️ Security Guidelines

### RBAC Configuration
Ensure minimal required permissions:
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
rules:
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list"]
- apiGroups: [""]
  resources: ["pods/exec"]  
  verbs: ["create"]
```

### Production Safety
- **Performance Impact**: Profiling affects application performance - use judiciously
- **Access Control**: Validate RBAC permissions before deployment
- **Monitoring**: Enable audit logging for all operations
- **Backup**: Always backup configurations before modifications

## Contribuciones
Tus contribuciones son bienvenidas. Si tienes sugerencias o mejoras, por favor, no dudes en abrir un issue o un pull request en el repositorio.

## Licencia
Este proyecto se publica bajo [incluir tipo de licencia], lo que permite su uso y distribución bajo los términos especificados.
