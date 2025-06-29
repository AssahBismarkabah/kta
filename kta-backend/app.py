"""
kta Backend - Tenant Signup and Keycloak Configuration Automation
This Flask application handles tenant signup requests and automatically generates
Keycloak realm configurations using the tenant template.
"""

import os
import subprocess
import uuid
import secrets
import string
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify, render_template_string
from jinja2 import Template
import yaml

app = Flask(__name__)

# Configuration
KEYCLOAK_CONFIGS_REPO_PATH = os.getenv('KEYCLOAK_CONFIGS_REPO_PATH', '/app/keycloak-configs')
TENANT_TEMPLATE_PATH = os.path.join(KEYCLOAK_CONFIGS_REPO_PATH, '_templates', 'tenant-template.yaml')
TENANTS_DIR = os.path.join(KEYCLOAK_CONFIGS_REPO_PATH, 'tenants')

# Ensure directories exist
os.makedirs(TENANTS_DIR, exist_ok=True)

def generate_secure_password(length=16):
    """Generate a secure random password"""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    password = ''.join(secrets.choice(alphabet) for _ in range(length))
    return password

def validate_tenant_id(tenant_id):
    """Validate tenant ID format"""
    if not tenant_id:
        return False, "Tenant ID is required"
    
    if len(tenant_id) < 3 or len(tenant_id) > 50:
        return False, "Tenant ID must be between 3 and 50 characters"
    
    if not tenant_id.replace('_', '').replace('-', '').isalnum():
        return False, "Tenant ID can only contain letters, numbers, hyphens, and underscores"
    
    if tenant_id.startswith('-') or tenant_id.endswith('-'):
        return False, "Tenant ID cannot start or end with a hyphen"
    
    return True, None

def check_tenant_exists(tenant_id):
    """Check if tenant configuration already exists"""
    tenant_config_path = os.path.join(TENANTS_DIR, f"{tenant_id}.yaml")
    return os.path.exists(tenant_config_path)

def git_operations(tenant_id, action="add"):
    """Perform Git operations for tenant configuration"""
    try:
        tenant_filename = f"{tenant_id}.yaml"
        
        if action == "add":
            # Add the new tenant file
            subprocess.run([
                "git", "-C", KEYCLOAK_CONFIGS_REPO_PATH, 
                "add", f"tenants/{tenant_filename}"
            ], check=True, capture_output=True, text=True)
            
            # Commit the changes
            commit_message = f"feat: Add tenant configuration for {tenant_id}"
            subprocess.run([
                "git", "-C", KEYCLOAK_CONFIGS_REPO_PATH,
                "commit", "-m", commit_message
            ], check=True, capture_output=True, text=True)
            
            # Push to remote (if configured)
            try:
                subprocess.run([
                    "git", "-C", KEYCLOAK_CONFIGS_REPO_PATH,
                    "push"
                ], check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError:
                # Push might fail if no remote is configured (local development)
                app.logger.warning("Git push failed - might be running in local mode")
        
        return True, None
    
    except subprocess.CalledProcessError as e:
        error_msg = f"Git operation failed: {e.stderr if e.stderr else str(e)}"
        app.logger.error(error_msg)
        return False, error_msg

@app.route('/')
def index():
    """Landing page with API documentation"""
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>kta Backend - Keycloak Tenant Automation</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }
            .container { max-width: 800px; margin: 0 auto; }
            .endpoint { background: #f4f4f4; padding: 15px; margin: 10px 0; border-radius: 5px; }
            .method { color: #fff; padding: 3px 8px; border-radius: 3px; font-weight: bold; }
            .post { background: #28a745; }
            .get { background: #007bff; }
            .delete { background: #dc3545; }
            code { background: #f8f9fa; padding: 2px 4px; border-radius: 3px; }
            pre { background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 kta Backend</h1>
            <p>GitOps-driven Keycloak tenant automation service</p>
            
            <h2>📋 API Endpoints</h2>
            
            <div class="endpoint">
                <h3><span class="method post">POST</span> /api/tenants/signup</h3>
                <p>Create a new tenant and generate Keycloak realm configuration</p>
                <h4>Request Body:</h4>
                <pre>{
  "tenant_id": "acme_corp",
  "tenant_name": "ACME Corporation"
}</pre>
                <h4>Response:</h4>
                <pre>{
  "message": "Tenant acme_corp signup completed successfully",
  "tenant_id": "acme_corp",
  "tenant_name": "ACME Corporation",
  "initial_admin_username": "admin-acme_corp",
  "initial_admin_password": "SecurePassword123!",
  "keycloak_realm_url": "http://localhost:8080/realms/acme_corp",
  "config_file": "tenants/acme_corp.yaml",
  "git_committed": true
}</pre>
            </div>
            
            <div class="endpoint">
                <h3><span class="method get">GET</span> /api/tenants</h3>
                <p>List all existing tenants</p>
            </div>
            
            <div class="endpoint">
                <h3><span class="method get">GET</span> /api/tenants/{tenant_id}</h3>
                <p>Get information about a specific tenant</p>
            </div>
            
            <div class="endpoint">
                <h3><span class="method delete">DELETE</span> /api/tenants/{tenant_id}</h3>
                <p>Remove a tenant configuration (for cleanup/testing)</p>
            </div>
            
            <h2>🔧 Usage Example</h2>
            <pre>curl -X POST http://localhost:5001/api/tenants/signup \\
  -H "Content-Type: application/json" \\
  -d '{
    "tenant_id": "demo_company",
    "tenant_name": "Demo Company Inc"
  }'</pre>
            
            <h2> System Status</h2>
            <p><strong>Template Path:</strong> <code>{{ template_path }}</code></p>
            <p><strong>Tenants Directory:</strong> <code>{{ tenants_dir }}</code></p>
            <p><strong>Git Repository:</strong> <code>{{ repo_path }}</code></p>
        </div>
    </body>
    </html>
    """
    
    return render_template_string(html_template,
        template_path=TENANT_TEMPLATE_PATH,
        tenants_dir=TENANTS_DIR,
        repo_path=KEYCLOAK_CONFIGS_REPO_PATH
    )

@app.route('/api/tenants/signup', methods=['POST'])
def signup_tenant():
    """Handle tenant signup and generate Keycloak configuration"""
    try:
        # Parse request data
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body must be JSON"}), 400
        
        tenant_id = data.get('tenant_id', '').strip().lower()
        tenant_name = data.get('tenant_name', '').strip()
        
        # Validate input
        if not tenant_id or not tenant_name:
            return jsonify({
                "error": "Both tenant_id and tenant_name are required"
            }), 400
        
        # Validate tenant ID format
        is_valid, error_msg = validate_tenant_id(tenant_id)
        if not is_valid:
            return jsonify({"error": error_msg}), 400
        
        # Check if tenant already exists
        if check_tenant_exists(tenant_id):
            return jsonify({
                "error": f"Tenant '{tenant_id}' already exists"
            }), 409
        
        # Generate secure initial password
        initial_password = generate_secure_password()
        
        # Read and process template
        if not os.path.exists(TENANT_TEMPLATE_PATH):
            return jsonify({
                "error": f"Tenant template not found at {TENANT_TEMPLATE_PATH}"
            }), 500
        
        with open(TENANT_TEMPLATE_PATH, 'r') as f:
            template_content = f.read()
        
        # Use Jinja2 for template substitution
        template = Template(template_content)
        config_content = template.render(
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            initial_admin_password=initial_password
        )
        
        # Save tenant configuration
        tenant_config_path = os.path.join(TENANTS_DIR, f"{tenant_id}.yaml")
        with open(tenant_config_path, 'w') as f:
            f.write(config_content)
        
        # Perform Git operations
        git_success, git_error = git_operations(tenant_id, "add")
        
        # Prepare response
        response_data = {
            "message": f"Tenant {tenant_id} signup completed successfully",
            "tenant_id": tenant_id,
            "tenant_name": tenant_name,
            "initial_admin_username": f"admin-{tenant_id}",
            "initial_admin_password": initial_password,
            "keycloak_realm_url": f"http://localhost:8080/realms/{tenant_id}",
            "config_file": f"tenants/{tenant_id}.yaml",
            "git_committed": git_success,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        if not git_success:
            response_data["git_warning"] = f"Configuration saved but Git operation failed: {git_error}"
        
        app.logger.info(f"Successfully created tenant: {tenant_id}")
        return jsonify(response_data), 201
    
    except Exception as e:
        app.logger.error(f"Error creating tenant: {str(e)}")
        return jsonify({
            "error": "Internal server error occurred while creating tenant",
            "details": str(e) if app.debug else None
        }), 500

@app.route('/api/tenants', methods=['GET'])
def list_tenants():
    """List all existing tenants"""
    try:
        tenants = []
        
        if os.path.exists(TENANTS_DIR):
            for filename in os.listdir(TENANTS_DIR):
                if filename.endswith('.yaml'):
                    tenant_id = filename[:-5]  # Remove .yaml extension
                    tenant_path = os.path.join(TENANTS_DIR, filename)
                    
                    # Get file modification time
                    mtime = os.path.getmtime(tenant_path)
                    created_at = datetime.fromtimestamp(mtime).isoformat() + "Z"
                    
                    # Try to extract tenant name from config
                    tenant_name = None
                    try:
                        with open(tenant_path, 'r') as f:
                            config = yaml.safe_load(f)
                            display_name = config.get('displayName', '')
                            if display_name and ' Services' in display_name:
                                tenant_name = display_name.replace(' Services', '')
                    except:
                        pass
                    
                    tenants.append({
                        "tenant_id": tenant_id,
                        "tenant_name": tenant_name,
                        "config_file": f"tenants/{filename}",
                        "created_at": created_at,
                        "keycloak_realm_url": f"http://localhost:8080/realms/{tenant_id}"
                    })
        
        return jsonify({
            "tenants": sorted(tenants, key=lambda x: x['created_at'], reverse=True),
            "total_count": len(tenants)
        })
    
    except Exception as e:
        app.logger.error(f"Error listing tenants: {str(e)}")
        return jsonify({
            "error": "Failed to list tenants",
            "details": str(e) if app.debug else None
        }), 500

@app.route('/api/tenants/<tenant_id>', methods=['GET'])
def get_tenant(tenant_id):
    """Get information about a specific tenant"""
    try:
        tenant_config_path = os.path.join(TENANTS_DIR, f"{tenant_id}.yaml")
        
        if not os.path.exists(tenant_config_path):
            return jsonify({"error": f"Tenant '{tenant_id}' not found"}), 404
        
        # Get file info
        mtime = os.path.getmtime(tenant_config_path)
        created_at = datetime.fromtimestamp(mtime).isoformat() + "Z"
        
        # Load and parse config
        with open(tenant_config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Extract key information
        tenant_info = {
            "tenant_id": tenant_id,
            "tenant_name": config.get('displayName', '').replace(' Services', ''),
            "realm_enabled": config.get('enabled', False),
            "config_file": f"tenants/{tenant_id}.yaml",
            "created_at": created_at,
            "keycloak_realm_url": f"http://localhost:8080/realms/{tenant_id}",
            "admin_console_url": f"http://localhost:8080/admin/master/console/#/{tenant_id}",
            "clients": [client.get('clientId') for client in config.get('clients', [])],
            "roles": [role.get('name') for role in config.get('roles', {}).get('realm', [])],
            "groups": [group.get('name') for group in config.get('groups', [])],
            "users": [user.get('username') for user in config.get('users', [])]
        }
        
        return jsonify(tenant_info)
    
    except Exception as e:
        app.logger.error(f"Error getting tenant {tenant_id}: {str(e)}")
        return jsonify({
            "error": f"Failed to get tenant information",
            "details": str(e) if app.debug else None
        }), 500

@app.route('/api/tenants/<tenant_id>', methods=['DELETE'])
def delete_tenant(tenant_id):
    """Delete a tenant configuration (for cleanup/testing)"""
    try:
        tenant_config_path = os.path.join(TENANTS_DIR, f"{tenant_id}.yaml")
        
        if not os.path.exists(tenant_config_path):
            return jsonify({"error": f"Tenant '{tenant_id}' not found"}), 404
        
        # Remove the file
        os.remove(tenant_config_path)
        
        # Git operations for removal
        try:
            subprocess.run([
                "git", "-C", KEYCLOAK_CONFIGS_REPO_PATH,
                "rm", f"tenants/{tenant_id}.yaml"
            ], check=True, capture_output=True, text=True)
            
            subprocess.run([
                "git", "-C", KEYCLOAK_CONFIGS_REPO_PATH,
                "commit", "-m", f"feat: Remove tenant configuration for {tenant_id}"
            ], check=True, capture_output=True, text=True)
            
            try:
                subprocess.run([
                    "git", "-C", KEYCLOAK_CONFIGS_REPO_PATH,
                    "push"
                ], check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError:
                pass  # Push might fail in local development
            
            git_success = True
        except subprocess.CalledProcessError as e:
            git_success = False
            app.logger.warning(f"Git operations failed for tenant deletion: {e}")
        
        return jsonify({
            "message": f"Tenant '{tenant_id}' configuration deleted successfully",
            "tenant_id": tenant_id,
            "git_committed": git_success,
            "note": "This only removes the configuration file. The Keycloak realm may still exist."
        })
    
    except Exception as e:
        app.logger.error(f"Error deleting tenant {tenant_id}: {str(e)}")
        return jsonify({
            "error": f"Failed to delete tenant",
            "details": str(e) if app.debug else None
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "kta-backend",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "template_exists": os.path.exists(TENANT_TEMPLATE_PATH),
        "tenants_dir_exists": os.path.exists(TENANTS_DIR)
    })

if __name__ == '__main__':
    # Initialize Git repository if it doesn't exist
    if not os.path.exists(os.path.join(KEYCLOAK_CONFIGS_REPO_PATH, '.git')):
        try:
            subprocess.run([
                "git", "-C", KEYCLOAK_CONFIGS_REPO_PATH, "init"
            ], check=True, capture_output=True, text=True)
            
            subprocess.run([
                "git", "-C", KEYCLOAK_CONFIGS_REPO_PATH,
                "config", "user.name", "kta Backend"
            ], check=True, capture_output=True, text=True)
            
            subprocess.run([
                "git", "-C", KEYCLOAK_CONFIGS_REPO_PATH,
                "config", "user.email", "kta@example.com"
            ], check=True, capture_output=True, text=True)
            
            print("Initialized Git repository for keycloak-configs")
        except subprocess.CalledProcessError as e:
            print(f" Failed to initialize Git repository: {e}")
    
    app.run(host='0.0.0.0', port=5001, debug=True)
