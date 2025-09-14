# 🛡️ Security Guide for Popofiler

## ⚠️ CRITICAL SECURITY NOTICE

**The bash script (`popofiler.sh`) contains critical security vulnerabilities and should NOT be used in production environments.**

**Use only the Python implementation (`popofiler.py`) which includes comprehensive security hardening.**

---

## 🔒 Security Features in Python Implementation

### ✅ Input Validation & Sanitization
- **Kubernetes Name Validation**: All K8s resource names are validated using regex patterns
- **Project Name Validation**: Strict validation prevents injection attacks
- **Command Parameter Validation**: All inputs are validated before use

### ✅ Secure Command Execution
- **No Shell Injection**: Uses `subprocess` with argument arrays instead of `shell=True`
- **Parameterized Commands**: All commands are constructed as parameter arrays
- **Error Sanitization**: Error messages don't expose sensitive command details

### ✅ Cryptographic Security
- **Secure Random Generation**: Uses `secrets.token_urlsafe()` for trace keys
- **48-byte Random Keys**: Cryptographically secure random key generation
- **No Hardcoded Secrets**: All sensitive values use environment variables

### ✅ Environment Variable Security
- **No Hardcoded Credentials**: All configuration via environment variables
- **Input Validation**: Environment variables are validated before use
- **Secure Defaults**: Safe fallback values where appropriate

### ✅ Logging & Monitoring Security
- **Sanitized Logging**: Logs don't expose sensitive information
- **Structured Logging**: Uses proper logging framework
- **Command Auditing**: Tracks command executions without exposing details

---

## 🚨 Vulnerability Details in Bash Script

The `popofiler.sh` script contains the following critical vulnerabilities:

### 1. Command Injection (CWE-78)
```bash
# VULNERABLE - Direct variable interpolation
kubectl exec -it --namespace=$NAMESPACE $DONOR_POD_NAME -- bash -c 'command'
```

### 2. Hardcoded Configuration (CWE-798)
```bash
# VULNERABLE - Hardcoded values
K8S_CONTEXT='your_k8s_context_here'
PROJECT_NAME='your_project_name_here'
```

### 3. Unvalidated Input (CWE-20)
```bash
# VULNERABLE - No input validation
DONOR_POD_NAME=$(kubectl ... | grep $PROJECT_NAME | awk '{print $1}')
```

---

## 🛠️ Secure Usage Guidelines

### Environment Variables Setup
```bash
# Required environment variables
export K8S_CONTEXT="your-k8s-context"
export PROJECT_NAME="your-project"
export NAMESPACE="your-namespace"
export POD_NAME_ANTI_PATTERN="pattern-to-exclude"
```

### Kubernetes RBAC Requirements
Ensure your user/service account has minimal required permissions:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  namespace: your-namespace
  name: popofiler-role
rules:
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list"]
- apiGroups: [""]
  resources: ["pods/exec"]
  verbs: ["create"]
- apiGroups: [""]
  resources: ["pods"]
  resourceNames: ["specific-pod-name"]  # Restrict to specific pods
  verbs: ["get"]
```

### Secure Execution
```bash
# Use only the Python version
python3 popofiler.py enable-profiling

# Never use the bash version in production
# ❌ bash popofiler.sh enable-profiling  # DANGEROUS!
```

---

## 🔍 Security Validation Checklist

Before using popofiler in production:

- [ ] **Environment Validation**: All required environment variables set
- [ ] **RBAC Configuration**: Minimal required permissions configured
- [ ] **Network Security**: Appropriate network policies in place
- [ ] **Audit Logging**: Kubernetes audit logging enabled
- [ ] **Python Version**: Using `popofiler.py` (not `popofiler.sh`)
- [ ] **Dependencies**: All Python dependencies are from trusted sources
- [ ] **Monitoring**: Command execution monitoring in place

---

## 🚨 Incident Response

If you suspect the bash version was used in production:

1. **Immediate Actions**:
   - Stop using `popofiler.sh` immediately
   - Rotate any potentially exposed credentials
   - Audit kubectl command history
   - Check for unauthorized pod access

2. **Investigation**:
   - Review all kubectl operations in affected timeframe
   - Check for unusual pod modifications
   - Validate integrity of affected pods
   - Review network logs for suspicious activity

3. **Recovery**:
   - Migrate to Python implementation
   - Update all documentation and procedures
   - Implement monitoring for future usage

---

## 📞 Security Contact

For security-related issues or questions:
- Create a private issue in the repository
- Follow responsible disclosure practices
- Include detailed reproduction steps
- Provide impact assessment

---

## 🔄 Security Updates

This security guide will be updated as new threats are identified or security enhancements are implemented. Always use the latest version of the Python implementation for the most current security protections.