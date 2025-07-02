"""
kta Backend - Tenant Signup and Keycloak Configuration Automation
This Flask application handles tenant signup requests and automatically generates
Keycloak realm configurations using the tenant template.

Updated to support both:
1. Traditional realm-per-tenant mode
2. New Keycloak Organizations mode (single realm, multiple organizations)
"""

import os
import subprocess
import uuid
import secrets
import string
import requests
import json
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify, render_template_string
from jinja2 import Template
import yaml

app = Flask(__name__)

# Configuration
KEYCLOAK_CONFIGS_REPO_PATH = os.getenv('KEYCLOAK_CONFIGS_REPO_PATH', '/app/keycloak-configs')
KEYCLOAK_URL = os.getenv('KEYCLOAK_URL', 'http://localhost:8080')
KEYCLOAK_ADMIN_USER = os.getenv('KEYCLOAK_ADMIN_USER', 'admin')
KEYCLOAK_ADMIN_PASSWORD = os.getenv('KEYCLOAK_ADMIN_PASSWORD', 'admin123')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_REPO = os.getenv('GITHUB_REPO')
PORT = int(os.getenv('PORT', 5001))

# KTA Mode Configuration
KTA_MODE = os.getenv('KTA_MODE', 'realm')  # 'realm' or 'organizations'
ORGANIZATIONS_REALM = os.getenv('ORGANIZATIONS_REALM', 'kta-organizations')

TENANT_TEMPLATE_PATH = os.path.join(KEYCLOAK_CONFIGS_REPO_PATH, '_templates', 'tenant-template.yaml')
SIMPLE_TEMPLATE_PATH = os.path.join(KEYCLOAK_CONFIGS_REPO_PATH, '_templates', 'simple-tenant-template.yaml')
ORG_TEMPLATE_PATH = os.path.join(KEYCLOAK_CONFIGS_REPO_PATH, '_templates', 'organization-template.yaml.j2')
ORG_REALM_TEMPLATE_PATH = os.path.join(KEYCLOAK_CONFIGS_REPO_PATH, '_templates', 'organizations-realm-template.yaml')
TENANTS_DIR = os.path.join(KEYCLOAK_CONFIGS_REPO_PATH, 'tenants')
ORGS_DIR = os.path.join(KEYCLOAK_CONFIGS_REPO_PATH, 'organizations')
APPLY_SCRIPT_PATH = os.path.join(os.path.dirname(KEYCLOAK_CONFIGS_REPO_PATH), 'scripts', 'apply-organizations.sh')

# Ensure directories exist
os.makedirs(TENANTS_DIR, exist_ok=True)
os.makedirs(ORGS_DIR, exist_ok=True)

class KeycloakClient:
    """Keycloak Admin API client - limited to read-only operations for organizations mode"""
    
    def __init__(self):
        self.base_url = KEYCLOAK_URL
        self.admin_user = KEYCLOAK_ADMIN_USER
        self.admin_password = KEYCLOAK_ADMIN_PASSWORD
        self.token = None
        self.token_expires = None
    
    def get_admin_token(self):
        """Get admin access token"""
        try:
            token_url = f"{self.base_url}/realms/master/protocol/openid-connect/token"
            data = {
                'grant_type': 'password',
                'client_id': 'admin-cli',
                'username': self.admin_user,
                'password': self.admin_password
            }
            
            app.logger.debug(f"Getting token from: {token_url}")
            response = requests.post(token_url, data=data)
            response.raise_for_status()
            
            token_data = response.json()
            self.token = token_data['access_token']
            app.logger.debug("Successfully obtained admin token")
            return self.token
            
        except Exception as e:
            app.logger.error(f"Failed to get admin token: {e}")
            app.logger.error(f"Token URL: {token_url}")
            app.logger.error(f"Response status: {response.status_code if 'response' in locals() else 'No response'}")
            return None
    
    def get_headers(self):
        """Get authorization headers"""
        # Always get a fresh token to avoid expiration issues
        token = self.get_admin_token()
        if not token:
            raise Exception("Failed to get admin token")
        
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
    
    def list_organizations(self, realm_name):
        """List all organizations in a realm"""
        try:
            url = f"{self.base_url}/admin/realms/{realm_name}/organizations"
            
            response = requests.get(url, headers=self.get_headers())
            response.raise_for_status()
            
            return {'success': True, 'organizations': response.json()}
            
        except Exception as e:
            app.logger.error(f"Failed to list organizations: {e}")
            return {'success': False, 'error': str(e), 'organizations': []}

keycloak_client = KeycloakClient()

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
    alphabet = string.ascii_letters + string.digits + "l!@#$"
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
    org_config_path = os.path.join(ORGS_DIR, f"{tenant_id}.yaml")
    return os.path.exists(tenant_config_path) or os.path.exists(org_config_path)

def git_operations(entity_id, action="add"):
    """
    Performs git operations (add, commit, push) for a new config file.
    Action can be 'add' for tenants or 'add_org' for organizations.
    """
    if not GITHUB_TOKEN or not GITHUB_REPO:
        app.logger.warning("GITHUB_TOKEN or GITHUB_REPO not set. Skipping git operations.")
        return False, "Git credentials not configured."

    try:
        setup_git_credentials()

        repo_path = Path(KEYCLOAK_CONFIGS_REPO_PATH).parent
        
        if action == "add_org":
            file_path = f"keycloak-configs/organizations/{entity_id}.yaml"
            commit_message = f"feat: add organization {entity_id}"
        else: # Default to tenant
            file_path = f"keycloak-configs/tenants/{entity_id}.yaml"
            commit_message = f"feat: add tenant {entity_id}"

        # Git commands
        subprocess.run(["git", "config", "--global", "user.email", "kta-backend@example.com"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "--global", "user.name", "KTA Backend"], cwd=repo_path, check=True)
        subprocess.run(["git", "pull", "--rebase"], cwd=repo_path, check=True)
        subprocess.run(["git", "add", file_path], cwd=repo_path, check=True)
        
        # Check if there are changes to commit
        status_result = subprocess.run(["git", "status", "--porcelain"], cwd=repo_path, check=True, capture_output=True, text=True)
        if not status_result.stdout:
            app.logger.info("No changes to commit. Working tree clean.")
            return True, "No changes to commit."

        subprocess.run(["git", "commit", "-m", commit_message], cwd=repo_path, check=True)
        subprocess.run(["git", "push", f"https://{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"], cwd=repo_path, check=True)
        
        app.logger.info(f"Successfully committed and pushed {file_path}")
        return True, None
    except subprocess.CalledProcessError as e:
        app.logger.error(f"Git operation failed: {e}")
        app.logger.error(f"Stderr: {e.stderr}")
        app.logger.error(f"Stdout: {e.stdout}")
        return False, str(e)
    except Exception as e:
        app.logger.error(f"An unexpected error occurred during git operation: {e}")
        return False, str(e)

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

# Organizations Mode Endpoints

@app.route('/api/organizations/signup', methods=['POST'])
def signup_organization():
    """
    Handles organization signup by generating a declarative configuration file
    from a template and saving it to the organizations directory.
    """
    if KTA_MODE != 'organizations':
        return jsonify({
            "success": False,
            "error": "Backend not in organizations mode"
        }), 400

    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Invalid JSON"}), 400

    required_fields = ['org_name', 'org_alias', 'admin_email', 'admin_first_name', 'admin_last_name', 'domains']
    if not all(field in data for field in required_fields):
        return jsonify({"success": False, "error": f"Missing one or more required fields: {required_fields}"}), 400

    org_alias = data['org_alias']
    if not validate_tenant_id(org_alias):
        return jsonify({
            "success": False,
            "error": "Invalid organization alias. Use lowercase letters, numbers, and hyphens."
        }), 400

    org_config_path = Path(ORGS_DIR) / f"{org_alias}.yaml"
    if org_config_path.exists():
        return jsonify({"success": False, "error": "Organization already exists"}), 409

    try:
        with open(ORG_TEMPLATE_PATH) as f:
            template = Template(f.read())
        
        # Ensure domains is a list of objects
        domains = data.get('domains', [])
        if domains and isinstance(domains[0], str):
            data['domains'] = [{'name': d} for d in domains]

        rendered_config_str = template.render(data)

        # The 'domains' field is rendered as a string, so we need to parse it back
        # into the structure before saving the final YAML.
        rendered_config = yaml.safe_load(rendered_config_str)
        if 'domains' in rendered_config and isinstance(rendered_config['domains'], str):
             rendered_config['domains'] = yaml.safe_load(rendered_config['domains'])
        
        # Save the new organization file
        with open(org_config_path, 'w') as f:
            yaml.dump(rendered_config, f, sort_keys=False)
        
        app.logger.info(f"Successfully created organization config file: {org_config_path}")

        # Git operations to commit and push the new organization file
        git_success, git_error = git_operations(org_alias, "add_org")

        response_data = {
            "success": True,
            "message": f"Organization '{org_alias}' configuration created successfully.",
            "org_alias": org_alias,
            "git_committed": git_success
        }

        if not git_success:
            response_data["git_warning"] = f"Config file saved, but Git operation failed: {git_error}"
            # Still return a success because the file was created
            return jsonify(response_data), 201
            
    except Exception as e:
        app.logger.error(f"Failed to render or save organization template: {e}")
        return jsonify({"success": False, "error": "Failed to process organization template"}), 500
            
    return jsonify(response_data), 201

@app.route('/api/organizations', methods=['GET'])
def list_organizations():
    """List all organizations (from both local configs and Keycloak)"""
    try:
        organizations = []
        
        # Get organizations from local config files
        if os.path.exists(TENANTS_DIR):
            for filename in os.listdir(TENANTS_DIR):
                if filename.endswith('_org.yaml'):
                    tenant_id = filename[:-9]  # Remove _org.yaml extension
                    org_path = os.path.join(TENANTS_DIR, filename)
                    
                    try:
                        with open(org_path, 'r') as f:
                            config = yaml.safe_load(f)
                        
                        mtime = os.path.getmtime(org_path)
                        created_at = datetime.fromtimestamp(mtime).isoformat() + "Z"
                        
                        organizations.append({
                            "tenant_id": tenant_id,
                            "tenant_name": config.get('tenant_name'),
                            "mode": "organizations",
                            "realm": config.get('realm', ORGANIZATIONS_REALM),
                            "organization_id": config.get('keycloak_org_id'),
                            "admin_email": config.get('admin_email'),
                            "domain": config.get('tenant_domain'),
                            "config_file": f"tenants/{filename}",
                            "created_at": created_at
                        })
                    except Exception as e:
                        app.logger.warning(f"Failed to load organization config {filename}: {e}")
        
        # Optionally get live data from Keycloak
        if KTA_MODE == 'organizations':
            try:
                keycloak_orgs = keycloak_client.list_organizations(ORGANIZATIONS_REALM)
                if keycloak_orgs['success']:
                    # Here you could merge/compare with Keycloak data
                    pass
            except Exception as e:
                app.logger.warning(f"Failed to fetch organizations from Keycloak: {e}")
        
        return jsonify({
            "organizations": sorted(organizations, key=lambda x: x['created_at'], reverse=True),
            "total_count": len(organizations),
            "mode": KTA_MODE,
            "realm": ORGANIZATIONS_REALM if KTA_MODE == 'organizations' else None
        })
    
    except Exception as e:
        app.logger.error(f"Error listing organizations: {str(e)}")
        return jsonify({
            "error": "Failed to list organizations",
            "details": str(e) if app.debug else None
        }), 500

@app.route('/api/mode', methods=['GET'])
def get_mode():
    """Get current KTA mode and configuration"""
    return jsonify({
        "mode": KTA_MODE,
        "organizations_realm": ORGANIZATIONS_REALM if KTA_MODE == 'organizations' else None,
        "keycloak_url": KEYCLOAK_URL,
        "supports_realm_per_tenant": True,
        "supports_organizations": True,
        "current_config": {
            "realm_template_exists": os.path.exists(TENANT_TEMPLATE_PATH),
            "simple_template_exists": os.path.exists(SIMPLE_TEMPLATE_PATH),
            "org_template_exists": os.path.exists(ORG_TEMPLATE_PATH),
            "org_realm_template_exists": os.path.exists(ORG_REALM_TEMPLATE_PATH)
        }
    })

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "kta-backend",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "mode": KTA_MODE,
        "template_exists": os.path.exists(TENANT_TEMPLATE_PATH),
        "simple_template_exists": os.path.exists(SIMPLE_TEMPLATE_PATH),
        "org_template_exists": os.path.exists(ORG_TEMPLATE_PATH),
        "tenants_dir_exists": os.path.exists(TENANTS_DIR),
        "git_configured": bool(GITHUB_TOKEN and GITHUB_REPO),
        "keycloak_url": KEYCLOAK_URL,
        "environment": {
            "PORT": PORT,
            "KTA_MODE": KTA_MODE,
            "ORGANIZATIONS_REALM": ORGANIZATIONS_REALM,
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
