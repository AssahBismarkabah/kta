#!/bin/bash

# kta Demo Script
# This script demonstrates the complete GitOps workflow for Keycloak tenant automation

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Function to print colored output
print_header() {
    echo -e "${PURPLE}$1${NC}"
    echo -e "${PURPLE}$(echo "$1" | sed 's/./=/g')${NC}"
}

print_step() {
    echo -e "${CYAN}▶ $1${NC}"
}

print_status() {
    echo -e "${GREEN} $1${NC}"
}

print_warning() {
    echo -e "${YELLOW} $1${NC}"
}

print_error() {
    echo -e "${RED} $1${NC}"
}

print_info() {
    echo -e "${BLUE}  $1${NC}"
}

# Configuration
BACKEND_URL="http://localhost:5001"
KEYCLOAK_URL="http://localhost:8080"
DEMO_TENANTS=("acme_corp" "tech_startup" "global_enterprise")
DEMO_TENANT_NAMES=("ACME Corporation" "Tech Startup Inc" "Global Enterprise Ltd")

# Function to wait for user input
wait_for_user() {
    echo ""
    read -p "Press Enter to continue..." -r
    echo ""
}

# Function to check if services are running
check_services() {
    print_step "Checking if services are running..."
    
    # Check backend
    if ! curl -s -f "$BACKEND_URL/health" > /dev/null 2>&1; then
        print_error "kta backend is not running at $BACKEND_URL"
        print_info "Start services with: docker-compose up -d"
        exit 1
    fi
    
    # Check Keycloak
    if ! curl -s -f "$KEYCLOAK_URL/realms/master" > /dev/null 2>&1; then
        print_error "Keycloak is not running at $KEYCLOAK_URL"
        print_info "Start services with: docker-compose up -d"
        exit 1
    fi
    
    print_status "All services are running"
}

# Function to show current tenant list
show_tenant_list() {
    print_step "Current tenants in the system:"
    
    response=$(curl -s "$BACKEND_URL/api/tenants" || echo '{"tenants": []}')
    
    if command -v jq &> /dev/null; then
        tenant_count=$(echo "$response" | jq -r '.total_count // 0')
        if [ "$tenant_count" -eq 0 ]; then
            echo "  No tenants found"
        else
            echo "$response" | jq -r '.tenants[] | "  - \(.tenant_id): \(.tenant_name // "Unknown")"'
        fi
    else
        echo "  (Install jq for better formatting)"
        echo "$response"
    fi
}

# Function to create a demo tenant
create_demo_tenant() {
    local tenant_id="$1"
    local tenant_name="$2"
    
    print_step "Creating tenant: $tenant_id ($tenant_name)"
    
    response=$(curl -s -X POST "$BACKEND_URL/api/tenants/signup" \
        -H "Content-Type: application/json" \
        -d "{\"tenant_id\": \"$tenant_id\", \"tenant_name\": \"$tenant_name\"}")
    
    if echo "$response" | grep -q "error"; then
        print_warning "Tenant creation response: $response"
    else
        print_status "Tenant $tenant_id created successfully"
        
        if command -v jq &> /dev/null; then
            echo "  Admin Username: $(echo "$response" | jq -r '.initial_admin_username')"
            echo "  Admin Password: $(echo "$response" | jq -r '.initial_admin_password')"
            echo "  Realm URL: $(echo "$response" | jq -r '.keycloak_realm_url')"
        fi
    fi
}

# Function to apply configurations
apply_configurations() {
    print_step "Applying tenant configurations to Keycloak..."
    
    if [ -x "./scripts/apply-configs.sh" ]; then
        ./scripts/apply-configs.sh
    else
        print_error "apply-configs.sh script not found or not executable"
        return 1
    fi
}

# Function to show Keycloak realms
show_keycloak_realms() {
    print_step "Verifying realms in Keycloak..."
    
    # Try to get realm list from Keycloak admin API
    admin_token=$(curl -s -X POST "$KEYCLOAK_URL/realms/master/protocol/openid-connect/token" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "username=admin&password=admin123&grant_type=password&client_id=admin-cli" \
        2>/dev/null | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4 || echo "")
    
    if [ -n "$admin_token" ]; then
        realms=$(curl -s -H "Authorization: Bearer $admin_token" \
            "$KEYCLOAK_URL/admin/realms" 2>/dev/null || echo "[]")
        
        if command -v jq &> /dev/null; then
            echo "  Keycloak Realms:"
            echo "$realms" | jq -r '.[] | "    - \(.realm): \(.displayName // "No display name")"'
        else
            echo "  Realms created (install jq for better formatting)"
        fi
    else
        print_warning "Could not retrieve realm list from Keycloak API"
        print_info "Check manually at: $KEYCLOAK_URL/admin"
    fi
}

# Function to show access URLs
show_access_urls() {
    print_step "Access URLs for your tenants:"
    echo ""
    
    for i in "${!DEMO_TENANTS[@]}"; do
        tenant_id="${DEMO_TENANTS[$i]}"
        tenant_name="${DEMO_TENANT_NAMES[$i]}"
        
        echo "🏢 $tenant_name ($tenant_id):"
        echo "   Realm URL: ${BLUE}$KEYCLOAK_URL/realms/$tenant_id${NC}"
        echo "   Admin Console: ${BLUE}$KEYCLOAK_URL/admin/master/console/#/$tenant_id${NC}"
        echo "   Account Console: ${BLUE}$KEYCLOAK_URL/realms/$tenant_id/account${NC}"
        echo ""
    done
    
    echo "🔧 System URLs:"
    echo "   Keycloak Admin: ${BLUE}$KEYCLOAK_URL/admin${NC} (admin/admin123)"
    echo "   kta Backend: ${BLUE}$BACKEND_URL${NC}"
    echo ""
}

# Function to demonstrate API usage
demonstrate_api() {
    print_step "Demonstrating API endpoints..."
    
    echo "1. Health Check:"
    curl -s "$BACKEND_URL/health" | head -c 200
    echo "..."
    echo ""
    
    echo "2. List Tenants:"
    curl -s "$BACKEND_URL/api/tenants" | head -c 300
    echo "..."
    echo ""
    
    if [ ${#DEMO_TENANTS[@]} -gt 0 ]; then
        echo "3. Get Tenant Details (${DEMO_TENANTS[0]}):"
        curl -s "$BACKEND_URL/api/tenants/${DEMO_TENANTS[0]}" | head -c 400
        echo "..."
        echo ""
    fi
}

# Function to show Git repository status
show_git_status() {
    print_step "Git repository status:"
    
    cd keycloak-configs
    
    echo "Recent commits:"
    git log --oneline -5 2>/dev/null || echo "  No git history found"
    
    echo ""
    echo "Current files:"
    find tenants -name "*.yaml" 2>/dev/null | head -10 | while read -r file; do
        echo "  - $file"
    done
    
    cd ..
}

# Function to cleanup demo tenants
cleanup_demo() {
    print_step "Cleaning up demo tenants..."
    
    for tenant_id in "${DEMO_TENANTS[@]}"; do
        echo "Removing $tenant_id..."
        curl -s -X DELETE "$BACKEND_URL/api/tenants/$tenant_id" > /dev/null 2>&1 || true
    done
    
    print_status "Demo cleanup completed"
}

# Main demo function
run_demo() {
    print_header "🚀 kta Demo - GitOps-Driven Keycloak Automation"
    echo ""
    echo "This demo will showcase:"
    echo "• Automated tenant onboarding"
    echo "• Configuration as Code with YAML templates"
    echo "• GitOps workflow with automatic commits"
    echo "• Keycloak realm creation via keycloak-config-cli"
    echo ""
    
    wait_for_user
    
    # Step 1: Check services
    print_header "Step 1: Service Health Check"
    check_services
    wait_for_user
    
    # Step 2: Show initial state
    print_header "Step 2: Initial System State"
    show_tenant_list
    wait_for_user
    
    # Step 3: Create demo tenants
    print_header "Step 3: Creating Demo Tenants"
    for i in "${!DEMO_TENANTS[@]}"; do
        create_demo_tenant "${DEMO_TENANTS[$i]}" "${DEMO_TENANT_NAMES[$i]}"
        sleep 1
    done
    wait_for_user
    
    # Step 4: Show updated tenant list
    print_header "Step 4: Updated Tenant List"
    show_tenant_list
    wait_for_user
    
    # Step 5: Show Git status
    print_header "Step 5: Git Repository Status"
    show_git_status
    wait_for_user
    
    # Step 6: Apply configurations
    print_header "Step 6: Applying Configurations to Keycloak"
    apply_configurations
    wait_for_user
    
    # Step 7: Verify in Keycloak
    print_header "Step 7: Verification in Keycloak"
    show_keycloak_realms
    wait_for_user
    
    # Step 8: Show access URLs
    print_header "Step 8: Access Your Tenants"
    show_access_urls
    wait_for_user
    
    # Step 9: API demonstration
    print_header "Step 9: API Demonstration"
    demonstrate_api
    wait_for_user
    
    # Step 10: Completion
    print_header "🎉 Demo Completed Successfully!"
    echo ""
    echo "What you've seen:"
    echo " Automated tenant creation via REST API"
    echo " YAML configuration generation from templates"
    echo " Git-based configuration management"
    echo " Automated Keycloak realm deployment"
    echo " Multi-tenant isolation and security"
    echo ""
    echo "Next steps:"
    echo "• Explore the Keycloak Admin Console"
    echo "• Test authentication flows"
    echo "• Customize the tenant template"
    echo "• Set up GitHub Actions for CI/CD"
    echo ""
    
    # Optional cleanup
    echo "Would you like to clean up the demo tenants? (y/N)"
    read -r cleanup_choice
    if [[ $cleanup_choice =~ ^[Yy]$ ]]; then
        cleanup_demo
    else
        print_info "Demo tenants preserved for exploration"
    fi
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "kta Demo - GitOps-driven Keycloak automation demonstration"
    echo ""
    echo "Options:"
    echo "  -h, --help              Show this help message"
    echo "  --cleanup               Clean up demo tenants only"
    echo "  --quick                 Run demo without pauses"
    echo "  --backend-url URL       Backend URL (default: http://localhost:5001)"
    echo "  --keycloak-url URL      Keycloak URL (default: http://localhost:8080)"
    echo ""
    echo "Examples:"
    echo "  $0                      # Run interactive demo"
    echo "  $0 --quick              # Run demo without pauses"
    echo "  $0 --cleanup            # Clean up demo tenants"
}

# Parse command line arguments
QUICK_MODE=false
CLEANUP_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_usage
            exit 0
            ;;
        --cleanup)
            CLEANUP_ONLY=true
            shift
            ;;
        --quick)
            QUICK_MODE=true
            shift
            ;;
        --backend-url)
            BACKEND_URL="$2"
            shift 2
            ;;
        --keycloak-url)
            KEYCLOAK_URL="$2"
            shift 2
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Override wait function for quick mode
if [ "$QUICK_MODE" = true ]; then
    wait_for_user() {
        sleep 2
    }
fi

# Main execution
if [ "$CLEANUP_ONLY" = true ]; then
    print_header "🧹 Cleaning Up Demo Tenants"
    check_services
    cleanup_demo
else
    run_demo
fi
 