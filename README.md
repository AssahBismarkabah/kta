# KTA - Keycloak Tenant Accelerator

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](docker-compose.yml)
[![Keycloak](https://img.shields.io/badge/Keycloak-26.1.2-red.svg)](https://www.keycloak.org/)
[![Organizations](https://img.shields.io/badge/Organizations-Supported-green.svg)](#organizations-mode-new)

A comprehensive solution for automating Keycloak tenant onboarding using GitOps principles and `keycloak-config-cli`. KTA demonstrates how to scale from manual "Click-Ops" to fully automated, template-driven tenant provisioning.

## Features

### Multi-Mode Support (NEW!)
- **Realm-per-Tenant Mode**: Traditional approach with isolated realms for each tenant
- **Organizations Mode**: Modern approach using Keycloak 26+ Organizations feature
- **Hybrid Support**: Run both modes simultaneously during migration

### Core Capabilities
- **Template-Driven Configuration**: Jinja2-based YAML templates for tenant customization
- **GitOps Automation**: Automatic deployment via GitHub Actions
- **RESTful API**: Flask backend for tenant signup and management
- **Docker Compose Ready**: Complete development environment setup
- **Comprehensive Testing**: Scripts for validation and testing

## 🏗️ Architecture

![KTA Architecture](./docs/image.png)

The KTA system consists of four main components working together in a GitOps workflow.

### Workflow
1. **Tenant Signup** → API generates config from template
2. **Git Commit** → Configuration stored with version control
3. **CI/CD Trigger** → GitHub Actions deploys changes
4. **Keycloak Update** → Realm created/updated automatically


## 🛠️ Quick Start


### 2. Choose Your Mode

#### Option A: Traditional Realm-per-Tenant Mode
```bash
# Start with default realm-per-tenant mode
docker-compose up -d

# Test tenant creation
curl -X POST http://localhost:5001/api/tenants/signup \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "demo_corp",
    "tenant_name": "Demo Corporation",
    "template_type": "simple"
  }'
```

#### Option B: Modern Organizations Mode (NEW!)
```bash
# Start with Organizations mode
KTA_MODE=organizations docker-compose up -d

# Setup the Organizations realm
./scripts/setup-organizations-realm.sh

# Test organization creation
curl -X POST http://localhost:5001/api/organizations/signup \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "demo_corp",
    "tenant_name": "Demo Corporation",
    "admin_email": "admin@demo-corp.com"
  }'
```

### 3. Access Keycloak

- **Keycloak Admin Console**: http://localhost:8080/admin/master/console/
  - Username: `admin`
  - Password: `admin123`
- **KTA Backend**: http://localhost:5001
- **Health Check**: http://localhost:5001/health

## 🔧 Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KTA_MODE` | `realm` | Mode: `realm` or `organizations` |
| `ORGANIZATIONS_REALM` | `kta-organizations` | Realm name for Organizations mode |
| `KEYCLOAK_URL` | `http://localhost:8080` | Keycloak server URL |
| `KEYCLOAK_ADMIN_USER` | `admin` | Keycloak admin username |
| `KEYCLOAK_ADMIN_PASSWORD` | `admin123` | Keycloak admin password |
| `KTA_BACKEND_PORT` | `5001` | Backend API port |

### Tenant Template

# Verify mode configuration
curl http://localhost:5001/api/mode

- **Realm Settings**: Security policies, token lifespans, internationalization
- **Clients**: Web application and API clients with OIDC configuration
- **Roles**: Hierarchical role structure (admin, manager, user, viewer)
- **Groups**: Organizational structure with role mappings
- **Users**: Initial tenant administrator with secure credentials
- **Authentication Flows**: Custom authentication workflows
- **Security Features**: Brute force protection, password policies



## 📚 Additional Resources

- [Keycloak Community](https://www.keycloak.org/community) for the excellent IAM platform
- [GitOps Working Group](https://github.com/gitops-working-group) for GitOps principles
- [Keycloak Documentation](https://www.keycloak.org/documentation)
- [keycloak-config-cli Documentation](https://github.com/adorsys/keycloak-config-cli)
- [GitOps Principles](https://www.gitops.tech/)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.


**Built with ❤️ for the DevOps and Identity Management community**

For more detailed information, see the [complete article](docs/article_draft.md) that accompanies this project.
