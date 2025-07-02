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
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_REPO = os.getenv('GITHUB_REPO')
PORT = int(os.getenv('PORT', 5001))

TENANT_TEMPLATE_PATH = os.path.join(KEYCLOAK_CONFIGS_REPO_PATH, '_templates', 'tenant-template.yaml')
SIMPLE_TEMPLATE_PATH = os.path.join(KEYCLOAK_CONFIGS_REPO_PATH, '_templates', 'simple-tenant-template.yaml')
TENANTS_DIR = os.path.join(KEYCLOAK_CONFIGS_REPO_PATH, 'tenants')

# Ensure directories exist
os.makedirs(TENANTS_DIR, exist_ok=True)

def setup_git_credentials():
    """Setup git credentials for authenticated push operations"""
    if GITHUB_TOKEN and GITHUB_REPO:
        try:
            # Configure git to use token for authentication
            repo_url = f"https://{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"
            subprocess.run([
                "git", "-C", KEYCLOAK_CONFIGS_REPO_PATH,
                "remote", "set-url", "origin", repo_url
            ], capture_output=True, text=True)
            app.logger.info("Git credentials configured successfully")
            return True
        except Exception as e:
            app.logger.warning(f"Failed to setup git credentials: {e}")
            return False
    else:
        app.logger.warning("GITHUB_TOKEN or GITHUB_REPO not set - Git push may fail")
        return False

setup_git_credentials()

def generate_secure_password(length=16):
    """Generate a secure random password"""
    alphabet = string.ascii_letters + string.digits + "!@#$"
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
            subprocess.run([
                "git", "-C", KEYCLOAK_CONFIGS_REPO_PATH, 
                "add", f"tenants/{tenant_filename}"
            ], check=True, capture_output=True, text=True)
            
            commit_message = f"feat: Add tenant configuration for {tenant_id}"
            subprocess.run([
                "git", "-C", KEYCLOAK_CONFIGS_REPO_PATH,
                "commit", "-m", commit_message
            ], check=True, capture_output=True, text=True)
            
            # Push to remote
            push_result = subprocess.run([
                "git", "-C", KEYCLOAK_CONFIGS_REPO_PATH,
                "push", "origin", "main"
            ], capture_output=True, text=True)
            
            if push_result.returncode != 0:
                app.logger.warning(f"Git push failed: {push_result.stderr}")
                if not GITHUB_TOKEN or not GITHUB_REPO:
                    app.logger.info("Git push failed - check GITHUB_TOKEN and GITHUB_REPO environment variables")
                return True, "Committed locally but push failed - check Git configuration"
        
        return True, None
    
    except subprocess.CalledProcessError as e:
        error_msg = f"Git operation failed: {e.stderr if e.stderr else str(e)}"
        app.logger.error(error_msg)
        return False, error_msg

@app.route('/')
def index():
    """Landing page with tenant creation UI"""
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>KTA - Keycloak Tenant Automation</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', roboto, oxygen, ubuntu, cantarell, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            .header { text-align: center; margin-bottom: 30px; }
            .form-group { margin-bottom: 20px; }
            label { display: block; margin-bottom: 5px; font-weight: 600; color: #333; }
            input[type="text"], select { width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px; font-size: 16px; box-sizing: border-box; }
            input[type="text"]:focus, select:focus { outline: none; border-color: #007bff; box-shadow: 0 0 0 2px rgba(0,123,255,0.25); }
            .btn { background: #007bff; color: white; padding: 12px 24px; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; font-weight: 600; }
            .btn:hover { background: #0056b3; }
            .btn:disabled { background: #6c757d; cursor: not-allowed; }
            .result { margin-top: 20px; padding: 15px; border-radius: 4px; }
            .success { background: #d4edda; border: 1px solid #c3e6cb; color: #155724; }
            .error { background: #f8d7da; border: 1px solid #f5c6cb; color: #721c24; }
            .loading { background: #cce7ff; border: 1px solid #b3d9ff; color: #004085; }
            .template-info { background: #e2e3e5; padding: 15px; border-radius: 4px; margin-bottom: 20px; }
            .tenants-list { margin-top: 30px; }
            .tenant-item { background: #f8f9fa; padding: 10px; margin: 5px 0; border-radius: 4px; border-left: 4px solid #007bff; }
            small { color: #666; font-size: 14px; }
            .spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid #f3f3f3; border-top: 2px solid #007bff; border-radius: 50%; animation: spin 1s linear infinite; }
            @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1> KTA - Keycloak Tenant Automation</h1>
                <p>Create and deploy Keycloak tenant configurations with GitOps</p>
            </div>
            
            <div class="template-info">
                <h3> Template Options:</h3>
                <p><strong>Simple Template:</strong> Basic realm with working user creation (recommended for demos)</p>
                <p><strong>Complex Template:</strong> Full-featured realm with all advanced Keycloak capabilities</p>
            </div>
            
            <form id="tenantForm">
                <div class="form-group">
                    <label for="tenant_id">Tenant ID:</label>
                    <input type="text" id="tenant_id" name="tenant_id" placeholder="e.g., acme_corp, demo_company" required>
                    <small>Only letters, numbers, hyphens, and underscores. 3-50 characters.</small>
                </div>
                
                <div class="form-group">
                    <label for="tenant_name">Tenant Name:</label>
                    <input type="text" id="tenant_name" name="tenant_name" placeholder="e.g., ACME Corporation" required>
                </div>
                
                <div class="form-group">
                    <label for="template_type">Template Type:</label>
                    <select id="template_type" name="template_type">
                        <option value="simple">Simple Template (with user creation)</option>
                        <option value="complex">Complex Template (all features)</option>
                    </select>
                </div>
                
                <button type="submit" class="btn" id="submitBtn">🚀 Create Tenant</button>
            </form>
            
            <div id="result"></div>
            
            <div class="tenants-list">
                <h2> Recent Tenants</h2>
                <div id="tenants">Loading...</div>
            </div>
        </div>
        
        <script>
            // Load existing tenants on page load
            loadTenants();
            
            function loadTenants() {
                fetch('/api/tenants')
                    .then(response => response.json())
                    .then(data => {
                        const tenantsDiv = document.getElementById('tenants');
                        if (data.tenants && data.tenants.length > 0) {
                            tenantsDiv.innerHTML = data.tenants.map(t => 
                                `<div class="tenant-item">
                                    <strong>${t.tenant_id}</strong> 
                                    ${t.tenant_name ? `- ${t.tenant_name}` : ''}
                                    <small style="color: #666; margin-left: 10px;">(${t.created_at ? new Date(t.created_at).toLocaleDateString() : 'Unknown'})</small>
                                    <a href="/api/tenants/${t.tenant_id}" target="_blank" style="margin-left: 10px;">View Config</a>
                                </div>`
                            ).join('');
                        } else {
                            tenantsDiv.innerHTML = '<p>No tenants created yet. Create your first tenant above!</p>';
                        }
                    })
                    .catch(error => {
                        document.getElementById('tenants').innerHTML = '<p>Error loading tenants.</p>';
                    });
            }
            
            // Handle form submission
            document.getElementById('tenantForm').addEventListener('submit', function(e) {
                e.preventDefault();
                
                const submitBtn = document.getElementById('submitBtn');
                const resultDiv = document.getElementById('result');
                
                // Show loading state
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<span class="spinner"></span> Creating...';
                resultDiv.innerHTML = '<div class="result loading">Creating tenant configuration and triggering deployment...</div>';
                
                const formData = new FormData(e.target);
                const data = {
                    tenant_id: formData.get('tenant_id'),
                    tenant_name: formData.get('tenant_name'),
                    template_type: formData.get('template_type')
                };
                
                fetch('/api/tenants/signup', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(data)
                })
                .then(response => response.json())
                .then(result => {
                    // Reset button
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = 'Create Tenant';
                    
                    if (result.error) {
                        resultDiv.innerHTML = `<div class="result error"><strong>Error:</strong> ${result.error}</div>`;
                    } else {
                        resultDiv.innerHTML = `
                            <div class="result success">
                                <h3>Tenant Created Successfully!</h3>
                                <p><strong>Tenant ID:</strong> ${result.tenant_id}</p>
                                <p><strong>Template:</strong> ${result.template_type} (${result.template_features})</p>
                                <p><strong>Config File:</strong> ${result.config_file}</p>
                                <p><strong>Git Status:</strong> ${result.git_committed ? 'Committed - Pipeline triggered!' : '⚠️ Local only'}</p>
                                <p><em>The GitHub Actions pipeline is now deploying your configuration to Keycloak...</em></p>
                                <p><strong>Realm URL:</strong> <a href="${result.keycloak_realm_url}" target="_blank">${result.keycloak_realm_url}</a></p>
                                <div style="background: #fff3cd; border: 1px solid #ffeeba; color: #856404; padding: 15px; border-radius: 4px; margin-top: 15px;">
                                    <h4>Security Notice</h4>
                                    <p><strong>Admin credentials have been generated but are not displayed for security.</strong></p>
                                    <p>To access your realm:</p>
                                    <ol>
                                        <li>Go to <a href="http://localhost:8080/admin" target="_blank">Keycloak Admin Console</a></li>
                                        <li>Login with: admin / admin123</li>
                                        <li>Select realm: <strong>${result.tenant_id}</strong></li>
                                        <li>Create users manually via Users → Add User</li>
                                    </ol>
                                    <p><em>Manual user creation is the industry standard for security.</em></p>
                                </div>
                            </div>
                        `;
                        // Clear form and reload tenant list
                        e.target.reset();
                        setTimeout(loadTenants, 1000);
                    }
                })
                .catch(error => {
                    // Reset button
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = 'Create Tenant';
                    resultDiv.innerHTML = `<div class="result error"><strong>Network Error:</strong> ${error.message}</div>`;
                });
            });
        </script>
    </body>
    </html>
    """
    
    return render_template_string(html_template)

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
        template_type = data.get('template_type', 'complex').strip().lower()  # 'complex' or 'simple'
        
        if not tenant_id or not tenant_name:
            return jsonify({
                "error": "Both tenant_id and tenant_name are required"
            }), 400
        
        if template_type not in ['complex', 'simple']:
            return jsonify({
                "error": "template_type must be 'complex' or 'simple'"
            }), 400
        
        is_valid, error_msg = validate_tenant_id(tenant_id)
        if not is_valid:
            return jsonify({"error": error_msg}), 400
        
        if check_tenant_exists(tenant_id):
            return jsonify({
                "error": f"Tenant '{tenant_id}' already exists"
            }), 409
        
        initial_password = generate_secure_password()
        
        if template_type == 'simple':
            template_path = SIMPLE_TEMPLATE_PATH
        else:
            template_path = TENANT_TEMPLATE_PATH  # complex template
        
        if not os.path.exists(template_path):
            return jsonify({
                "error": f"Template not found at {template_path}"
            }), 500
        
        with open(template_path, 'r') as f:
            template_content = f.read()
        
        template = Template(template_content)
        if template_type == 'simple':
            config_content = template.render(
                TENANT_ID=tenant_id,
                TENANT_NAME=tenant_name,
                ADMIN_PASSWORD=initial_password
            )
        else:
            config_content = template.render(
                tenant_id=tenant_id,
                tenant_name=tenant_name,
                initial_admin_password=initial_password
            )
        
        tenant_config_path = os.path.join(TENANTS_DIR, f"{tenant_id}.yaml")
        with open(tenant_config_path, 'w') as f:
            f.write(config_content)
        
        # Perform Git operations
        git_success, git_error = git_operations(tenant_id, "add")
        
        response_data = {
            "message": f"Tenant {tenant_id} signup completed successfully",
            "tenant_id": tenant_id,
            "tenant_name": tenant_name,
            "template_type": template_type,
            "template_features": "User creation + basic features" if template_type == 'simple' else "All advanced keycloak-config-cli features",
            "keycloak_realm_url": f"http://localhost:8080/realms/{tenant_id}",
            "config_file": f"tenants/{tenant_id}.yaml",
            "git_committed": git_success,
            "security_notice": "Admin credentials generated but not returned for security. Create users manually via Keycloak Admin Console.",
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
                    
                    mtime = os.path.getmtime(tenant_path)
                    created_at = datetime.fromtimestamp(mtime).isoformat() + "Z"
                    
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
                pass  
            
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
        "simple_template_exists": os.path.exists(SIMPLE_TEMPLATE_PATH),
        "tenants_dir_exists": os.path.exists(TENANTS_DIR),
        "git_configured": bool(GITHUB_TOKEN and GITHUB_REPO),
        "environment": {
            "PORT": PORT,
            "GITHUB_REPO": GITHUB_REPO,
            "GITHUB_TOKEN_SET": bool(GITHUB_TOKEN),
            "REPO_PATH": KEYCLOAK_CONFIGS_REPO_PATH
        }
    })

if __name__ == '__main__':
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
    
    app.run(host='0.0.0.0', port=PORT, debug=False)
