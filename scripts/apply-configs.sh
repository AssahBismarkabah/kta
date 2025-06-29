#!/bin/bash

# Apply Keycloak Configurations Script
# This script applies tenant configurations to Keycloak using keycloak-config-cli

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN} $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}  $1${NC}"
}

print_error() {
    echo -e "${RED} $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Configuration
KEYCLOAK_URL=${KEYCLOAK_URL:-"http://localhost:8080"}
KEYCLOAK_USER=${KEYCLOAK_USER:-"admin"}
KEYCLOAK_PASSWORD=${KEYCLOAK_PASSWORD:-"admin123"}
CONFIGS_DIR="./keycloak-configs/tenants"
KEYCLOAK_CONFIG_CLI_IMAGE="adorsys/keycloak-config-cli:latest"

# Function to check if Keycloak is running
check_keycloak() {
    print_info "Checking Keycloak availability at $KEYCLOAK_URL..."
    
    max_attempts=30
    attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s -f "$KEYCLOAK_URL/realms/master" > /dev/null 2>&1; then
            print_status "Keycloak is ready"
            return 0
        fi
        
        echo -n "."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    print_error "Keycloak is not accessible at $KEYCLOAK_URL"
    print_info "Make sure Keycloak is running: docker-compose up -d keycloak"
    exit 1
}

# Function to validate configuration files
validate_configs() {
    print_info "Validating configuration files..."
    
    if [ ! -d "$CONFIGS_DIR" ]; then
        print_error "Configurations directory not found: $CONFIGS_DIR"
        exit 1
    fi
    
    config_files=$(find "$CONFIGS_DIR" -name "*.yaml" -o -name "*.yml" 2>/dev/null || true)
    
    if [ -z "$config_files" ]; then
        print_warning "No configuration files found in $CONFIGS_DIR"
        print_info "Create a tenant first using: curl -X POST http://localhost:5001/api/tenants/signup ..."
        exit 0
    fi
    
    # Validate YAML syntax (if PyYAML is available)
    for file in $config_files; do
        if command -v python3 &> /dev/null && python3 -c "import yaml" 2>/dev/null; then
            if ! python3 -c "import yaml; yaml.safe_load(open('$file'))" 2>/dev/null; then
                print_error "Invalid YAML syntax in $file"
                exit 1
            fi
        else
            print_info "Skipping YAML validation (PyYAML not available)"
            break  # Only show this message once
        fi
    done
    
    print_status "Configuration files are valid"
    echo "Found configurations:"
    for file in $config_files; do
        tenant_id=$(basename "$file" .yaml | sed 's/.yml$//')
        echo "  - $tenant_id (from $file)"
    done
}

# Function to apply configurations
apply_configs() {
    print_info "Applying configurations to Keycloak..."
    
    # Create absolute path for volume mounting
    abs_configs_dir=$(realpath "$CONFIGS_DIR")
    
    # Run keycloak-config-cli
    docker run --rm \
        --network host \
        -v "$abs_configs_dir:/config" \
        -e KEYCLOAK_URL="$KEYCLOAK_URL" \
        -e KEYCLOAK_USER="$KEYCLOAK_USER" \
        -e KEYCLOAK_PASSWORD="$KEYCLOAK_PASSWORD" \
        -e KEYCLOAK_AVAILABILITYCHECK_ENABLED=true \
        -e KEYCLOAK_AVAILABILITYCHECK_TIMEOUT=60s \
        -e IMPORT_FILES_LOCATIONS='/config/*.yaml' \
        -e IMPORT_VAR_SUBSTITUTION_ENABLED=false \
        -e IMPORT_CACHE_ENABLED=false \
        -e LOGGING_LEVEL_KEYCLOAKCONFIGCLI=INFO \
        "$KEYCLOAK_CONFIG_CLI_IMAGE"
    
    print_status "Configurations applied successfully!"
}

# Function to show results
show_results() {
    print_info "Deployment completed! Access your tenants:"
    echo ""
    
    config_files=$(find "$CONFIGS_DIR" -name "*.yaml" -o -name "*.yml" 2>/dev/null || true)
    
    for file in $config_files; do
        tenant_id=$(basename "$file" .yaml | sed 's/.yml$//')
        echo "🏢 Tenant: $tenant_id"
        echo "   Realm URL: ${BLUE}$KEYCLOAK_URL/realms/$tenant_id${NC}"
        echo "   Admin Console: ${BLUE}$KEYCLOAK_URL/admin/master/console/#/$tenant_id${NC}"
        echo "   Login URL: ${BLUE}$KEYCLOAK_URL/realms/$tenant_id/account${NC}"
        echo ""
    done
    
    echo "🔧 Keycloak Admin Console: ${BLUE}$KEYCLOAK_URL/admin${NC}"
    echo "   Username: admin"
    echo "   Password: admin123"
    echo ""
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Apply Keycloak tenant configurations using keycloak-config-cli"
    echo ""
    echo "Options:"
    echo "  -h, --help              Show this help message"
    echo "  -u, --url URL           Keycloak URL (default: http://localhost:8080)"
    echo "  --user USER             Keycloak admin username (default: admin)"
    echo "  --password PASSWORD     Keycloak admin password (default: admin123)"
    echo "  -d, --dir DIRECTORY     Configurations directory (default: ./keycloak-configs/tenants)"
    echo "  --dry-run               Validate configurations without applying"
    echo ""
    echo "Environment variables:"
    echo "  KEYCLOAK_URL            Keycloak URL"
    echo "  KEYCLOAK_USER           Keycloak admin username"
    echo "  KEYCLOAK_PASSWORD       Keycloak admin password"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Apply all configurations"
    echo "  $0 --url http://keycloak.example.com # Use different Keycloak URL"
    echo "  $0 --dry-run                         # Validate only"
}

# Parse command line arguments
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_usage
            exit 0
            ;;
        -u|--url)
            KEYCLOAK_URL="$2"
            shift 2
            ;;
        --user)
            KEYCLOAK_USER="$2"
            shift 2
            ;;
        --password)
            KEYCLOAK_PASSWORD="$2"
            shift 2
            ;;
        -d|--dir)
            CONFIGS_DIR="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Main execution
main() {
    echo " Applying Keycloak Configurations"
    echo "===================================="
    echo ""
    echo "Keycloak URL: $KEYCLOAK_URL"
    echo "Configurations: $CONFIGS_DIR"
    echo ""
    
    validate_configs
    
    if [ "$DRY_RUN" = true ]; then
        print_status "Dry run completed - configurations are valid"
        exit 0
    fi
    
    check_keycloak
    apply_configs
    show_results
}

# Run main function
main
