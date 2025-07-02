# KTA Organizations Implementation

## Overview

The KTA project implements Organizations support using a hybrid approach that combines `keycloak-config-cli` for realm setup and direct Keycloak Admin API calls for organization management.

## Why a Hybrid Approach?

1. **keycloak-config-cli Limitation**: The tool doesn't support Organizations API yet (as of v5.12.0)
2. **Authentication Complexity**: Backend authentication to Keycloak from Docker containers requires careful token management
3. **CI/CD Compatibility**: GitHub Actions workflows need reliable, scriptable solutions

## Implementation Architecture

```
┌─────────────────────────┐     ┌──────────────────────┐
│  GitHub Actions         │     │  keycloak-config-cli │
│  Workflow               │────▶│  (Realm Setup)       │
└─────────────────────────┘     └──────────────────────┘
            │                              │
            ▼                              ▼
┌─────────────────────────┐     ┌──────────────────────┐
│  Direct API Script      │     │  Organizations Realm │
│  (Org Creation)         │────▶│  in Keycloak        │
└─────────────────────────┘     └──────────────────────┘
```

## Components

### 1. Organizations Realm Setup
- **Tool**: `keycloak-config-cli`
- **Template**: `organizations-realm-template.yaml`
- **Purpose**: Creates the base realm with Organizations feature enabled

### 2. Organization Creation
- **Tool**: Direct Keycloak Admin API via `create-organization-direct.sh`
- **Config**: `*_org.yaml` files in `tenants/` directory
- **Purpose**: Creates individual organizations within the realm

### 3. GitHub Actions Workflow
- **File**: `apply-organizations-config.yml`
- **Steps**:
  1. Setup Organizations realm using keycloak-config-cli
  2. Create organizations using direct API script

## Key Scripts

### create-organization-direct.sh
```bash
# Authenticates with Keycloak master realm
# Creates organizations with required domains
# Handles error cases gracefully
```

### apply-organizations.sh
```bash
# Wrapper script for CI/CD integration
# Processes organization YAML files
# Calls create-organization-direct.sh
```

## Configuration Format

```yaml
# Example: techcorp_org.yaml
tenant_id: techcorp
tenant_name: "TechCorp Solutions"
tenant_domain: "techcorp.io"
admin_email: "admin@techcorp.io"
```

## Testing

1. **Manual Testing**:
   ```bash
   ./scripts/create-organization-direct.sh keycloak-configs/tenants/techcorp_org.yaml
   ```

2. **CI/CD Testing**:
   ```bash
   # Triggers GitHub Actions workflow
   git add keycloak-configs/tenants/neworg_org.yaml
   git commit -m "Add new organization"
   git push
   ```

## Current Status

✅ **Working Features**:
- Organizations realm creation via keycloak-config-cli
- Direct API organization creation
- GitHub Actions workflow integration
- Multiple organization support

⚠️ **Known Limitations**:
- Backend API authentication issues (workaround: direct API calls)
- No keycloak-config-cli support for Organizations
- Manual domain verification required

## Future Improvements

1. **keycloak-config-cli Enhancement**: Contribute Organizations support
2. **Backend Authentication**: Fix Docker container token management
3. **Full API Integration**: Complete Organizations API implementation

## Viewing Organizations

Access the Keycloak Admin Console:
- URL: http://localhost:8080/admin/master/console/#/kta-organizations/organizations
- Username: admin
- Password: admin123

You should see all created organizations with their domains. 