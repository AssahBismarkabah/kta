#!/bin/bash
set -e

# Apply Keycloak Organization Configurations
# This script iterates through organization config files and applies them

# --- Configuration ---
KTA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$KTA_DIR" || exit 1

KEYCLOAK_URL="http://keycloak:8080"
KEYCLOAK_USER="admin"
KEYCLOAK_PASSWORD="admin123"
ORGS_DIR="$KTA_DIR/keycloak-configs/organizations"

CURL_IMAGE="curlimages/curl:latest"
KEYCLOAK_CONFIG_CLI_IMAGE="adorsys/keycloak-config-cli:latest"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
print_status() { echo -e "${GREEN} $1${NC}"; }
print_error() { echo -e "${RED} $1${NC}"; }
print_info() { echo -e "${BLUE} $1${NC}"; }

# --- Functions ---

get_network_name() {
    print_info "Detecting Docker network..."
    NETWORK_NAME=$(docker inspect kta-keycloak --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}' 2>/dev/null)
    if [ -z "$NETWORK_NAME" ]; then
        print_error "Could not determine Docker network. Is 'kta-keycloak' running?"
        exit 1
    fi
    print_info "Using Docker network: $NETWORK_NAME"
}

wait_for_keycloak() {
    print_info "Waiting for Keycloak to be ready..."
    for attempt in {1..30}; do
        if docker run --rm --network "$NETWORK_NAME" "$CURL_IMAGE" -s --fail "$KEYCLOAK_URL/realms/master" > /dev/null; then
            print_status "Keycloak is ready!"
            return 0
        fi
        echo -n "."
        sleep 5
    done
    print_error "Keycloak did not become ready in time."
    exit 1
}

apply_all_org_configs() {
    print_info "Applying all organization configurations..."
    
    if [ ! -d "$ORGS_DIR" ] || [ -z "$(ls -A "$ORGS_DIR")" ]; then
        print_info "No organization files found in $ORGS_DIR. Nothing to apply."
        return
    fi

    for file in "$ORGS_DIR"/*.yaml; do
        if [ -f "$file" ]; then
            filename=$(basename "$file")
            print_info "Applying organization config: $filename"
            
            docker run --rm \
                --network "$NETWORK_NAME" \
                -v "$ORGS_DIR:/config/organizations" \
                -e KEYCLOAK_URL="$KEYCLOAK_URL" \
                -e KEYCLOAK_USER="$KEYCLOAK_USER" \
                -e KEYCLOAK_PASSWORD="$KEYCLOAK_PASSWORD" \
                -e IMPORT_FILES_LOCATIONS="/config/organizations/$filename" \
                -e IMPORT_VAR_SUBSTITUTION_ENABLED=false \
                -e LOGGING_LEVEL_DE_ADORSYS_KEYCLOAK_CONFIG_CLI=INFO \
                "$KEYCLOAK_CONFIG_CLI_IMAGE"
        fi
    done

    print_status "All organization configurations applied."
}

# --- Main Execution ---
get_network_name
wait_for_keycloak
apply_all_org_configs

print_info "Organizations deployment script finished successfully."
echo "" 