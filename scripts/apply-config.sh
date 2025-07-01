#!/bin/bash

# This script helps apply Keycloak configurations from the correct directory
# and using the correct Docker network

# Get the KTA project directory
KTA_DIR="/Users/adorsys123/Desktop/dev1.1/personal/pv1/kta"
cd "$KTA_DIR" || exit 1

echo "Ensuring Keycloak is running..."
if ! docker ps | grep -q kta-keycloak; then
  echo "Starting Keycloak..."
  docker-compose up -d
fi

# Get the Docker network
NETWORK_NAME=$(docker inspect kta-keycloak --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}')
echo "Using Docker network: $NETWORK_NAME"

# Wait for Keycloak to be ready
echo "Waiting for Keycloak..."
for attempt in {1..30}; do
  if docker run --rm \
     --network "$NETWORK_NAME" \
     curlimages/curl:8.00.1 \
     -f http://kta-keycloak:8080/realms/master/.well-known/openid-configuration > /dev/null 2>&1; then
    echo "Keycloak is ready!"
    break
  else
    echo "Attempt $attempt/30: Keycloak not ready, waiting 5 seconds..."
    sleep 5
  fi
  
  if [ $attempt -eq 30 ]; then
    echo "Keycloak failed to become ready. Debug info:"
    docker ps
    docker logs kta-keycloak
    exit 1
  fi
done

# Apply configuration
if [ -n "$1" ]; then
  # Apply specific file
  TENANT_FILE="$1"
  echo "Applying specific tenant file: $TENANT_FILE"
  
  if [ ! -f "keycloak-configs/tenants/$TENANT_FILE" ]; then
    echo "File not found: keycloak-configs/tenants/$TENANT_FILE"
    exit 1
  fi
  
  echo "Running keycloak-config-cli for $TENANT_FILE..."
  docker run --rm \
    --network "$NETWORK_NAME" \
    -e KEYCLOAK_URL=http://kta-keycloak:8080 \
    -e KEYCLOAK_USER=admin \
    -e KEYCLOAK_PASSWORD=admin123 \
    -e IMPORT_FILES_LOCATIONS="/config/tenants/$TENANT_FILE" \
    -v "$KTA_DIR/keycloak-configs:/config" \
    adorsys/keycloak-config-cli:latest
else
  # Apply all files
  echo "Applying all tenant configurations..."
  
  for file in keycloak-configs/tenants/*.yaml; do
    if [ -f "$file" ]; then
      filename=$(basename "$file")
      echo "Applying: $filename"
      
      docker run --rm \
        --network "$NETWORK_NAME" \
        -e KEYCLOAK_URL=http://kta-keycloak:8080 \
        -e KEYCLOAK_USER=admin \
        -e KEYCLOAK_PASSWORD=admin123 \
        -e IMPORT_FILES_LOCATIONS="/config/tenants/$filename" \
        -v "$KTA_DIR/keycloak-configs:/config" \
        adorsys/keycloak-config-cli:latest
    fi
  done
fi 