#!/bin/bash

# KTA Local Pipeline Setup Script
# This script helps set up a local GitOps demonstration

set -e

echo " KTA Local Pipeline Setup"
echo "================================"

# Checkprerequisites
echo "Checking prerequisites..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo " Docker is not running. Please start Docker and try again."
    exit 1
fi

# Check if Git is available
if ! command -v git &> /dev/null; then
    echo " Git is not installed. Please install Git and try again."
    exit 1
fi

# Check if jq is available (for API verification)
if ! command -v jq &> /dev/null; then
    echo "⚠️  jq is not installed. Installing jq for API verification..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew install jq
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        sudo apt-get update && sudo apt-get install -y jq
    else
        echo "Please install jq manually for your system"
        exit 1
    fi
fi

echo "Prerequisites check complete"

# Option 1: Local Git Hooks (Simplest)
echo ""
echo "🔧 Setting up local Git hooks for automated pipeline simulation..."

# Create local git hook
mkdir -p .git/hooks

cat > .git/hooks/post-commit << 'EOF'
#!/bin/bash

# KTA Local Pipeline Hook
echo "KTA Pipeline: Detected commit with tenant configuration changes"

# Check if there are changes in keycloak-configs/tenants/
if git diff-tree --no-commit-id --name-only -r HEAD | grep -q "keycloak-configs/tenants/.*\.yaml"; then
    echo "Tenant configuration changes detected"
    
    # Get the changed files
    changed_files=$(git diff-tree --no-commit-id --name-only -r HEAD | grep "keycloak-configs/tenants/.*\.yaml" || true)
    
    if [ -n "$changed_files" ]; then
        echo "Applying configurations..."
        
        # Check if Keycloak is running
        if curl -f http://localhost:8080/realms/master/.well-known/openid_configuration > /dev/null 2>&1; then
            echo " Keycloak is running, applying configurations..."
            
            for file in $changed_files; do
                if [ -f "$file" ]; then
                    filename=$(basename "$file")
                    echo "⚙️  Applying: $filename"
                    
                    docker run --rm \
                        --network host \
                        -e KEYCLOAK_URL=http://localhost:8080 \
                        -e KEYCLOAK_USER=admin \
                        -e KEYCLOAK_PASSWORD=admin123 \
                        -e IMPORT_FILES_LOCATIONS="/config/tenants/$filename" \
                        -v $(pwd)/keycloak-configs:/config \
                        adorsys/keycloak-config-cli:latest
                    
                    echo "Applied: $filename"
                fi
            done
            
            echo " Pipeline complete! Check Keycloak Admin Console to see new realms."
        else
            echo "  Keycloak is not running. Start it with: docker-compose up -d"
            echo " Then manually apply configs with: ./scripts/apply-tenant-config.sh <tenant_file>"
        fi
    fi
else
    echo "ℹNo tenant configuration changes detected"
fi
EOF

# Make the hook executable
chmod +x .git/hooks/post-commit

echo "Local Git hook installed"

# Create a manual apply script
cat > scripts/apply-tenant-config.sh << 'EOF'
#!/bin/bash

# Manual tenant configuration apply script
if [ -z "$1" ]; then
    echo "Usage: $0 <tenant_file.yaml>"
    echo "Example: $0 revolut.yaml"
    exit 1
fi

TENANT_FILE="$1"
TENANT_PATH="keycloak-configs/tenants/$TENANT_FILE"

if [ ! -f "$TENANT_PATH" ]; then
    echo "File not found: $TENANT_PATH"
    exit 1
fi

echo " Applying tenant configuration: $TENANT_FILE"

# Check if Keycloak is running
if ! curl -f http://localhost:8080/realms/master/.well-known/openid_configuration > /dev/null 2>&1; then
    echo " Keycloak is not running. Start it with: docker-compose up -d"
    exit 1
fi

docker run --rm \
    --network host \
    -e KEYCLOAK_URL=http://localhost:8080 \
    -e KEYCLOAK_USER=admin \
    -e KEYCLOAK_PASSWORD=admin123 \
    -e IMPORT_FILES_LOCATIONS="/config/tenants/$TENANT_FILE" \
    -v $(pwd)/keycloak-configs:/config \
    adorsys/keycloak-config-cli:latest

echo " Configuration applied successfully!"
echo " Check Keycloak Admin Console: http://localhost:8080"
EOF

chmod +x scripts/apply-tenant-config.sh

# Create a demo script
cat > scripts/demo-pipeline.sh << 'EOF'
#!/bin/bash

# KTA Pipeline Demo Script
echo "🎬 KTA GitOps Pipeline Demo"
echo "============================"

# Check if Keycloak is running
if ! curl -f http://localhost:8080/realms/master/.well-known/openid_configuration > /dev/null 2>&1; then
    echo " Keycloak is not running. Starting services..."
    docker-compose up -d
    
    echo " Waiting for Keycloak to start..."
    until curl -f http://localhost:8080/realms/master/.well-known/openid_configuration > /dev/null 2>&1; do
        echo "  Still starting..."
        sleep 5
    done
fi

echo "Keycloak is ready!"

# Generate a demo tenant
TENANT_ID="demo-$(date +%s)"
TENANT_NAME="Demo Company $(date +%H%M)"

echo " Creating demo tenant: $TENANT_ID"

# Call the Flask API to generate tenant config
curl -X POST http://localhost:5001/api/tenants/signup \
    -H "Content-Type: application/json" \
    -d "{
        \"tenant_id\": \"$TENANT_ID\",
        \"tenant_name\": \"$TENANT_NAME\"
    }" || echo "  API call failed, creating tenant file manually..."

# If API is not running, create a simple tenant file
if [ ! -f "keycloak-configs/tenants/$TENANT_ID.yaml" ]; then
    echo "📝 Creating tenant configuration manually..."
    
    cat > "keycloak-configs/tenants/$TENANT_ID.yaml" << EOT
realm: "$TENANT_ID"
enabled: true
displayName: "$TENANT_NAME Services"

clients:
  - clientId: "$TENANT_ID-webapp"
    name: "$TENANT_NAME Web Application"
    enabled: true
    publicClient: true
    redirectUris:
      - "https://$TENANT_ID.kta.app/*"
      - "http://localhost:3000/*"

roles:
  realm:
    - name: "tenant_admin"
      description: "Administrator role for $TENANT_NAME tenant"
    - name: "tenant_user"
      description: "Standard user role for $TENANT_NAME tenant"
EOT
fi

# Commit the changes (this will trigger the pipeline)
git add "keycloak-configs/tenants/$TENANT_ID.yaml"
git commit -m "feat: Add tenant $TENANT_ID ($TENANT_NAME)"

echo ""
echo " Demo Complete!"
echo " Results:"
echo "   - Tenant ID: $TENANT_ID"
echo "   - Configuration: keycloak-configs/tenants/$TENANT_ID.yaml"
echo "   - Keycloak Admin: http://localhost:8080 (admin/admin123)"
echo ""
echo "🔍 Check the '$TENANT_ID' realm in Keycloak Admin Console!"
EOF

chmod +x scripts/demo-pipeline.sh

echo ""
echo "KTA Local Pipeline Setup Complete!"
echo ""
echo "How to use:"
echo "   1. Start services: docker-compose up -d"
echo "   2. Run demo: ./scripts/demo-pipeline.sh"
echo "   3. Or manually apply: ./scripts/apply-tenant-config.sh <file.yaml>"
echo ""
echo "The pipeline will automatically run when you commit tenant config changes!"
echo "Access Keycloak: http://localhost:8080 (admin/admin123)" 