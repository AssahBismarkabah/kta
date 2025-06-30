#!/bin/bash
# Deploy KTA Backend + Keycloak to Render (Free Tier)

set -e

echo "KTA Stack Deployment to Render"
echo "==============================="
echo ""

# Generate secure password
ADMIN_PASSWORD=$(openssl rand -base64 20 | tr -d "=+/" | cut -c1-16)

echo "Generated Keycloak admin password: $ADMIN_PASSWORD"
echo ""

# Create Keycloak Dockerfile
cat > Dockerfile.keycloak << 'EOF'
FROM quay.io/keycloak/keycloak:26.1.0 as builder
RUN /opt/keycloak/bin/kc.sh build --db=postgres

FROM quay.io/keycloak/keycloak:26.1.0
COPY --from=builder /opt/keycloak/ /opt/keycloak/

ENV KC_DB=postgres
ENV KC_HTTP_ENABLED=true
ENV KC_HOSTNAME_STRICT=false
ENV KC_HOSTNAME_STRICT_HTTPS=false
ENV KC_PROXY=edge

EXPOSE 8080
ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
CMD ["start", "--optimized"]
EOF

# Backend will use project-level Dockerfile.backend (no copy needed)
echo "Backend will use Dockerfile.backend (references original keycloak-configs)"

# Create render.yaml with all secrets as variables
cat > render.yaml << EOF
services:
  - type: web
    name: kta-backend
    env: docker
    dockerfilePath: ./kta-backend/Dockerfile
    rootDir: ./kta-backend
    plan: free
    healthCheckPath: /health
    envVars:
      - key: PORT
        value: 5001
      - key: GITHUB_TOKEN
        sync: false
      - key: GITHUB_REPO
        sync: false
      - key: KEYCLOAK_CONFIGS_REPO_PATH
        value: /app/keycloak-configs

  - type: web
    name: kta-keycloak
    env: docker
    dockerfilePath: ./Dockerfile.keycloak
    plan: free
    healthCheckPath: /health
    envVars:
      - key: KEYCLOAK_ADMIN
        sync: false
      - key: KEYCLOAK_ADMIN_PASSWORD
        sync: false
      - key: KC_DB_URL
        fromDatabase:
          name: kta-postgres
          property: connectionString
      - key: KC_HOSTNAME
        value: \${RENDER_EXTERNAL_HOSTNAME}

databases:
  - name: kta-postgres
    plan: free
EOF

echo "Created deployment files:"
echo "- Dockerfile.keycloak"
echo "- Dockerfile.backend" 
echo "- render.yaml"
echo ""
echo "=== DEPLOYMENT STEPS ==="
echo ""
echo "1. Commit files:"
echo "   git add Dockerfile.keycloak Dockerfile.backend render.yaml"
echo "   git commit -m 'Add Render deployment'"  
echo "   git push"
echo ""
echo "2. Deploy to Render:"
echo "   - Go to render.com → New → Blueprint"
echo "   - Connect your GitHub repo"
echo "   - Deploy"
echo ""
echo "3. Set Environment Variables in Render Dashboard:"
echo ""
echo "For kta-backend service:"
echo "   GITHUB_TOKEN=$GITHUB_TOKEN_HERE"
echo "   GITHUB_REPO=yourusername/your-repo-name"
echo ""
echo "For kta-keycloak service:"
echo "   KEYCLOAK_ADMIN=admin"
echo "   KEYCLOAK_ADMIN_PASSWORD=$ADMIN_PASSWORD"
echo ""
echo "4. Set GitHub Repository Secrets:"
echo "   KEYCLOAK_URL=https://kta-keycloak.onrender.com"
echo "   KEYCLOAK_ADMIN_USER=admin"
echo "   KEYCLOAK_ADMIN_PASSWORD=$ADMIN_PASSWORD"
echo ""
echo "=== AFTER DEPLOYMENT ==="
echo "🌐 KTA UI: https://kta-backend.onrender.com"
echo "🔐 Keycloak Admin: https://kta-keycloak.onrender.com/admin"
echo ""
echo "💡 Your UI already has a tenant creation form!"
echo "   Just open the KTA UI and fill the form to create tenants." 