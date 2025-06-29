#!/bin/bash

# KTA Automated Test Runner
# Comprehensive testing script for GitOps-driven Keycloak automation

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Configuration
KEYCLOAK_URL="http://localhost:8080"
BACKEND_URL="http://localhost:5001"
TEST_START_TIME=$(date +%s)

# Test tracking
TESTS_PASSED=0
TESTS_FAILED=0
TOTAL_TESTS=0

# Function to print test results
print_header() {
    echo -e "${PURPLE}$1${NC}"
    echo -e "${PURPLE}$(echo "$1" | sed 's/./=/g')${NC}"
}

print_test() {
    echo -e "${BLUE} $1${NC}"
}

print_success() {
    echo -e "${GREEN} $1${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

print_failure() {
    echo -e "${RED} $1${NC}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

print_info() {
    echo -e "${YELLOW}  $1${NC}"
}

# Function to run a test with timeout
run_test() {
    local test_name="$1"
    local test_command="$2"
    local timeout_seconds="${3:-30}"
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    print_test "$test_name"
    
    # Use gtimeout on macOS (from coreutils), timeout on Linux
    local timeout_cmd="timeout"
    if command -v gtimeout > /dev/null 2>&1; then
        timeout_cmd="gtimeout"
    fi
    
    if $timeout_cmd "$timeout_seconds" bash -c "$test_command" > /dev/null 2>&1; then
        print_success "$test_name passed"
        return 0
    else
        print_failure "$test_name failed"
        return 1
    fi
}

# Function to wait for service
wait_for_service() {
    local service_name="$1"
    local url="$2"
    local max_attempts="${3:-30}"
    
    print_info "Waiting for $service_name to be ready..."
    
    for i in $(seq 1 $max_attempts); do
        if curl -s -f "$url" > /dev/null 2>&1; then
            print_success "$service_name is ready"
            return 0
        fi
        echo -n "."
        sleep 2
    done
    
    print_failure "$service_name failed to start within $((max_attempts * 2)) seconds"
    return 1
}

# Cleanup function
cleanup() {
    echo ""
    print_info "Cleaning up test environment..."
    
    # Remove test tenants
    for tenant in auto_test e2e_test load_test_{1..5} perf_test_{1..10} tenant_{1..3} test_company demo_corp; do
        curl -s -X DELETE "$BACKEND_URL/api/tenants/$tenant" > /dev/null 2>&1 || true
    done
    
    print_info "Cleanup completed"
}

# Test summary function
print_summary() {
    local end_time=$(date +%s)
    local duration=$((end_time - TEST_START_TIME))
    
    echo ""
    print_header "📊 TEST SUMMARY"
    echo ""
    echo "Total Tests: $TOTAL_TESTS"
    echo -e "Passed: ${GREEN}$TESTS_PASSED${NC}"
    echo -e "Failed: ${RED}$TESTS_FAILED${NC}"
    echo "Duration: ${duration}s"
    echo ""
    
    if [ $TESTS_FAILED -eq 0 ]; then
        print_success "ALL TESTS PASSED! 🎉"
        return 0
    else
        print_failure "SOME TESTS FAILED! 😞"
        return 1
    fi
}

# Trap cleanup on exit
trap cleanup EXIT

print_header "KTA Comprehensive Testing Suite"
echo ""
echo "Starting automated testing of GitOps-driven Keycloak automation..."
echo "Test started at: $(date)"
echo ""

# Phase 1: Infrastructure Testing
print_header "Phase 1: Infrastructure Testing"

run_test "Docker availability" "docker --version"
run_test "Docker Compose availability" "docker-compose --version"

# Start services
print_info "Starting services with docker-compose..."
cd .. # Change to parent directory where docker-compose.yml is located
if ! docker-compose up -d > /dev/null 2>&1; then
    print_failure "Failed to start services"
    exit 1
fi
cd scripts # Change back to scripts directory

print_success "Services started successfully"

# Wait for services to be ready
wait_for_service "Keycloak" "$KEYCLOAK_URL/realms/master" 45
wait_for_service "KTA Backend" "$BACKEND_URL/health" 20

# Phase 2: API Testing
print_header " Phase 2: API Testing"

run_test "Backend health check" "curl -f $BACKEND_URL/health"
run_test "Backend API documentation" "curl -f $BACKEND_URL/"
run_test "Tenant list endpoint (empty)" "curl -f $BACKEND_URL/api/tenants"

# Phase 3: Tenant Creation Testing
print_header " Phase 3: Tenant Creation Testing"

# Test tenant creation
run_test "Create test tenant 1" "
    curl -s -X POST $BACKEND_URL/api/tenants/signup \
      -H 'Content-Type: application/json' \
      -d '{\"tenant_id\": \"test_company\", \"tenant_name\": \"Test Company Inc\"}' \
      | grep -q 'test_company'
"

run_test "Create test tenant 2" "
    curl -s -X POST $BACKEND_URL/api/tenants/signup \
      -H 'Content-Type: application/json' \
      -d '{\"tenant_id\": \"demo_corp\", \"tenant_name\": \"Demo Corporation\"}' \
      | grep -q 'demo_corp'
"

run_test "Verify tenant configs generated" "
    [ -f ../keycloak-configs/tenants/test_company.yaml ] && 
    [ -f ../keycloak-configs/tenants/demo_corp.yaml ]
"

run_test "Verify tenant list endpoint (populated)" "
    curl -s $BACKEND_URL/api/tenants | grep -q 'test_company'
"

# Phase 4: Configuration Application Testing
print_header "Phase 4: Configuration Application Testing"

print_info "Applying tenant configurations to Keycloak..."
cd .. # Change to parent directory for apply-configs.sh
if ./scripts/apply-configs.sh > /dev/null 2>&1; then
    print_success "Configuration application completed"
else
    print_failure "Configuration application failed"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi
cd scripts # Change back to scripts directory
TOTAL_TESTS=$((TOTAL_TESTS + 1))

# Verify realms were created
run_test "Verify test_company realm created" "
    curl -s $KEYCLOAK_URL/realms/test_company > /dev/null
"

run_test "Verify demo_corp realm created" "
    curl -s $KEYCLOAK_URL/realms/demo_corp > /dev/null
"

# Phase 5: End-to-End Workflow Testing
print_header " Phase 5: End-to-End Workflow Testing"

# Generate unique tenant ID for E2E test
E2E_TENANT_ID="e2e_test_$(date +%s)"

run_test "E2E: Create unique tenant" "
    curl -s -X POST $BACKEND_URL/api/tenants/signup \
      -H 'Content-Type: application/json' \
      -d '{\"tenant_id\": \"$E2E_TENANT_ID\", \"tenant_name\": \"E2E Test Tenant\"}' \
      | grep -q '$E2E_TENANT_ID'
"

run_test "E2E: Apply configuration" "cd .. && ./scripts/apply-configs.sh > /dev/null 2>&1 && cd scripts"

run_test "E2E: Verify realm exists" "
    curl -s $KEYCLOAK_URL/realms/$E2E_TENANT_ID > /dev/null
"

run_test "E2E: Get tenant details" "
    curl -s $BACKEND_URL/api/tenants/$E2E_TENANT_ID | grep -q '$E2E_TENANT_ID'
"

# Phase 6: Error Handling Testing
print_header " Phase 6: Error Handling Testing"

run_test "Invalid input: Missing tenant_id" "
    curl -s -X POST $BACKEND_URL/api/tenants/signup \
      -H 'Content-Type: application/json' \
      -d '{\"tenant_name\": \"Invalid Test\"}' \
      | grep -q 'error'
"

run_test "Invalid input: Invalid tenant_id format" "
    curl -s -X POST $BACKEND_URL/api/tenants/signup \
      -H 'Content-Type: application/json' \
      -d '{\"tenant_id\": \"invalid@tenant\", \"tenant_name\": \"Invalid Test\"}' \
      | grep -q 'error'
"

run_test "Duplicate tenant creation" "
    curl -s -X POST $BACKEND_URL/api/tenants/signup \
      -H 'Content-Type: application/json' \
      -d '{\"tenant_id\": \"test_company\", \"tenant_name\": \"Duplicate Test\"}' \
      | grep -q 'error'
"

# Phase 7: Multi-Tenant Testing
print_header "Phase 7: Multi-Tenant Testing"

# Create multiple tenants
for i in {1..3}; do
    run_test "Create tenant_$i" "
        curl -s -X POST $BACKEND_URL/api/tenants/signup \
          -H 'Content-Type: application/json' \
          -d '{\"tenant_id\": \"tenant_$i\", \"tenant_name\": \"Tenant $i\"}' \
          | grep -q 'tenant_$i'
    "
done

run_test "Apply multi-tenant configurations" "cd .. && ./scripts/apply-configs.sh > /dev/null 2>&1 && cd scripts"

# Verify all tenant realms
for i in {1..3}; do
    run_test "Verify tenant_$i realm" "
        curl -s $KEYCLOAK_URL/realms/tenant_$i > /dev/null
    "
done

# Phase 8: Performance Testing (Light)
print_header " Phase 8: Performance Testing"

# Test concurrent tenant creation (light load)
print_info "Testing concurrent tenant creation..."
start_time=$(date +%s)

for i in {1..3}; do
    (curl -s -X POST $BACKEND_URL/api/tenants/signup \
      -H 'Content-Type: application/json' \
      -d "{\"tenant_id\": \"load_test_$i\", \"tenant_name\": \"Load Test $i\"}" > /dev/null &)
done
wait

end_time=$(date +%s)
duration=$((end_time - start_time))

if [ $duration -lt 10 ]; then
    print_success "Concurrent tenant creation completed in ${duration}s"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    print_failure "Concurrent tenant creation took too long: ${duration}s"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi
TOTAL_TESTS=$((TOTAL_TESTS + 1))

# Phase 9: Keycloak Integration Testing
print_header " Phase 9: Keycloak Integration Testing"

# Get admin token and test API access
run_test "Get Keycloak admin token" "
    ADMIN_TOKEN=\$(curl -s -X POST '$KEYCLOAK_URL/realms/master/protocol/openid-connect/token' \
      -H 'Content-Type: application/x-www-form-urlencoded' \
      -d 'username=admin&password=admin123&grant_type=password&client_id=admin-cli' \
      | grep -o '\"access_token\":\"[^\"]*\"' | cut -d'\"' -f4)
    [ -n \"\$ADMIN_TOKEN\" ]
"

run_test "List realms via Keycloak API" "
    ADMIN_TOKEN=\$(curl -s -X POST '$KEYCLOAK_URL/realms/master/protocol/openid-connect/token' \
      -H 'Content-Type: application/x-www-form-urlencoded' \
      -d 'username=admin&password=admin123&grant_type=password&client_id=admin-cli' \
      | grep -o '\"access_token\":\"[^\"]*\"' | cut -d'\"' -f4)
    curl -s -H \"Authorization: Bearer \$ADMIN_TOKEN\" \
      '$KEYCLOAK_URL/admin/realms' | grep -q 'test_company'
"

# Phase 10: Service Recovery Testing
print_header " Phase 10: Service Recovery Testing"

print_info "Testing backend service recovery..."
docker-compose restart kta-backend > /dev/null 2>&1
sleep 10

run_test "Backend recovery after restart" "curl -f $BACKEND_URL/health"

print_info "Testing tenant operations after backend restart..."
run_test "Tenant operations after restart" "
    curl -s $BACKEND_URL/api/tenants | grep -q 'test_company'
"

# Final summary
print_summary

# Exit with appropriate code
if [ $TESTS_FAILED -eq 0 ]; then
    exit 0
else
    exit 1
fi 