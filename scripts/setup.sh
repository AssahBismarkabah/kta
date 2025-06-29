#!/bin/bash

# kta Setup Script
# This script sets up the development environment for the kta project

set -e

echo " Setting up kta - GitOps-driven Keycloak Automation"
echo "========================================================="

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
    echo -e "${BLUE}  $1${NC}"
}

# Check if Docker is installed and running
check_docker() {
    print_info "Checking Docker installation..."
    
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        echo "Visit: https://docs.docker.com/get-docker/"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        print_error "Docker is not running. Please start Docker first."
        exit 1
    fi
    
    print_status "Docker is installed and running"
}

# Check if Docker Compose is available
check_docker_compose() {
    print_info "Checking Docker Compose..."
    
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        print_error "Docker Compose is not available. Please install Docker Compose."
        exit 1
    fi
    
    print_status "Docker Compose is available"
}

# Initialize Git repository for keycloak-configs
init_git_repo() {
    print_info "Initializing Git repository for keycloak-configs..."
    
    cd keycloak-configs
    
    if [ ! -d ".git" ]; then
        git init
        git config user.name "kta Setup"
        git config user.email "setup@kta.local"
        
        # Create initial commit with template
        git add _templates/
        git commit -m "feat: Add initial tenant template"
        
        print_status "Git repository initialized"
    else
        print_status "Git repository already exists"
    fi
    
    cd ..
}

# Create environment file
create_env_file() {
    print_info "Creating environment configuration..."
    
    if [ ! -f ".env" ]; then
        cat > .env << EOF
# kta Environment Configuration

# Keycloak Configuration
KEYCLOAK_URL=http://localhost:8080
KEYCLOAK_ADMIN_USER=admin
KEYCLOAK_ADMIN_PASSWORD=admin123

# Backend Configuration
kta_BACKEND_PORT=5001
KEYCLOAK_CONFIGS_REPO_PATH=./keycloak-configs

# Development Settings
COMPOSE_PROJECT_NAME=kta
EOF
        print_status "Environment file created (.env)"
    else
        print_status "Environment file already exists"
    fi
}

# Pull required Docker images
pull_docker_images() {
    print_info "Pulling required Docker images..."
    
    echo "Pulling Keycloak image..."
    docker pull quay.io/keycloak/keycloak:26.0.4
    
    echo "Pulling keycloak-config-cli image..."
    docker pull adorsys/keycloak-config-cli:latest
    
    print_status "Docker images pulled successfully"
}

# Build the kta backend
build_backend() {
    print_info "Building kta backend..."
    
    if command -v docker-compose &> /dev/null; then
        docker-compose build kta-backend
    else
        docker compose build kta-backend
    fi
    
    print_status "Backend built successfully"
}

# Create demo tenant configuration
create_demo_tenant() {
    print_info "Creating demo tenant configuration..."
    
    # Create a demo tenant using the template
    python3 -c "
import os
from jinja2 import Template

template_path = 'keycloak-configs/_templates/tenant-template.yaml'
output_path = 'keycloak-configs/tenants/demo_company.yaml'

if os.path.exists(template_path) and not os.path.exists(output_path):
    with open(template_path, 'r') as f:
        template_content = f.read()
    
    template = Template(template_content)
    config_content = template.render(
        tenant_id='demo_company',
        tenant_name='Demo Company Inc',
        initial_admin_password='DemoPassword123!'
    )
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(config_content)
    
    print('Demo tenant configuration created')
else:
    print('Demo tenant already exists or template not found')
" 2>/dev/null || print_warning "Could not create demo tenant (Python/Jinja2 not available)"
    
    print_status "Demo setup completed"
}

# Display next steps
show_next_steps() {
    echo ""
    echo "🎉 kta setup completed successfully!"
    echo "======================================"
    echo ""
    echo "Next steps:"
    echo ""
    echo "1. Start the services:"
    echo "   ${BLUE}docker-compose up -d${NC}"
    echo ""
    echo "2. Wait for Keycloak to start (about 30-60 seconds), then access:"
    echo "   • Keycloak Admin Console: ${BLUE}http://localhost:8080/admin${NC}"
    echo "     (admin / admin123)"
    echo "   • kta Backend: ${BLUE}http://localhost:5001${NC}"
    echo ""
    echo "3. Test tenant creation:"
    echo "   ${BLUE}curl -X POST http://localhost:5001/api/tenants/signup \\${NC}"
    echo "   ${BLUE}  -H \"Content-Type: application/json\" \\${NC}"
    echo "   ${BLUE}  -d '{\"tenant_id\": \"test_company\", \"tenant_name\": \"Test Company\"}'${NC}"
    echo ""
    echo "4. Apply configurations to Keycloak:"
    echo "   ${BLUE}./scripts/apply-configs.sh${NC}"
    echo ""
    echo "5. View logs:"
    echo "   ${BLUE}docker-compose logs -f${NC}"
    echo ""
    echo "For more information, see the README.md file."
}

# Main execution
main() {
    echo ""
    check_docker
    check_docker_compose
    create_env_file
    init_git_repo
    pull_docker_images
    build_backend
    create_demo_tenant
    show_next_steps
}

# Run main function
main
