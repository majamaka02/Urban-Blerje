import os
import re
import shutil
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, make_response, jsonify
import io, csv
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import inspect, text
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timedelta
import time
from collections import defaultdict
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# Ensure Flask finds templates/static regardless of working directory
app = Flask(
    __name__,
    template_folder=str(BASE_DIR / 'templates'),
    static_folder=str(BASE_DIR / 'static'),
    static_url_path='/static'
)

# Debug: print template/static paths and list templates at startup (appears in Render logs)
try:
    print('BASE_DIR =', str(BASE_DIR))
    print('app.template_folder =', app.template_folder)
    jpaths = getattr(app.jinja_loader, 'searchpath', None)
    print('jinja_loader.searchpath =', jpaths)
    tpl_dir = BASE_DIR / 'templates'
    if tpl_dir.exists():
        files = sorted([p.name for p in tpl_dir.iterdir() if p.is_file()])
        print('templates files:', files[:200])
    else:
        print('templates directory does not exist at', str(tpl_dir))
except Exception as _e:
    print('Error while listing templates:', _e)


@app.route('/_debug_templates')
def debug_templates():
    """Return JSON with template folder info and file list for runtime debugging."""
    try:
        tpl_dir = BASE_DIR / 'templates'
        exists = tpl_dir.exists()
        files = []
        if exists:
            files = sorted([p.name for p in tpl_dir.iterdir() if p.is_file()])
        return jsonify({'base_dir': str(BASE_DIR), 'template_folder': app.template_folder, 'exists': exists, 'files': files})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ===== SECURITY CONFIGURATION =====
# Use environment variables for sensitive config
app.secret_key = os.getenv('SECRET_KEY', 'dev_secret_change_me_in_production')
DEBUG_MODE = os.getenv('DEBUG', 'False').lower() == 'true'
FLASK_ENV = os.getenv('FLASK_ENV', 'production')

# CSRF Protection
csrf = CSRFProtect(app)

# Konfigurimi i Databazes - normalize DATABASE_URL to avoid SQLAlchemy parse errors
# Read DATABASE_URL and provide a safe fallback to SQLite for development
db_url = os.getenv('DATABASE_URL', '').strip()
if not db_url:
    # optional secondary env var used in some setups
    db_url = os.getenv('SQLITE_URL', '') or 'sqlite:///stoku.db'

# Normalize older provider scheme
if db_url.startswith('postgres://'):
    db_url = db_url.replace('postgres://', 'postgresql://', 1)

# Detect obvious placeholder values and fall back to sqlite (to avoid import-time crash)
if '<' in db_url or '>' in db_url or 'your_password' in db_url:
    print('WARNING: DATABASE_URL contains placeholder values; falling back to SQLite. Set a valid DATABASE_URL in your environment.')
    db_url = 'sqlite:///stoku.db'

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# SESSION SECURITY - Adjust for development vs production
secure_cookies = FLASK_ENV == 'production'
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', str(secure_cookies)).lower() == 'true'
app.config['SESSION_COOKIE_HTTPONLY'] = True  # No JS access
app.config['SESSION_COOKIE_SAMESITE'] = os.getenv('SESSION_COOKIE_SAMESITE', 'Strict')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

# Request size limit (prevent DoS)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

db = SQLAlchemy(app)

# ===== INPUT VALIDATION =====
def validate_input(value, field_name, max_length=255, allow_special=False):
    """Validate user input for security"""
    if value is None:
        return None
    
    # Convert to string and strip
    value = str(value).strip()
    
    # Check length
    if len(value) > max_length:
        raise ValueError(f'{field_name} is too long (max {max_length} characters)')
    
    # Check for empty strings
    if not value:
        raise ValueError(f'{field_name} cannot be empty')
    
    # Prevent SQL injection patterns
    dangerous_patterns = [';', '--', '/*', '*/', 'DROP', 'DELETE', 'INSERT', 'UPDATE', 'UNION']
    if any(pattern.lower() in value.lower() for pattern in dangerous_patterns):
        raise ValueError(f'{field_name} contains invalid characters')
    
    # Optional: restrict special characters
    if not allow_special:
        if not re.match(r'^[a-zA-Z0-9\s\-\.\/\(\)\,ë\s]+$', value):  # Allow Albanian chars
            raise ValueError(f'{field_name} contains invalid characters')
    
    return value

def validate_password(password):
    """Validate password: require minimum 6 characters (no complexity required)."""
    if not password or len(password) < 6:
        raise ValueError('Password must be at least 6 characters long')
    if len(password) > 256:
        raise ValueError('Password is too long')
    return password


# ===== DATABASE BACKUP =====
def create_backup():
    """Create a backup of the database"""
    try:
        backup_dir = Path(os.getenv('BACKUP_DIR', './backups'))
        backup_dir.mkdir(exist_ok=True)
        
        source_db = Path('stoku.db')
        if source_db.exists():
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            backup_file = backup_dir / f'stoku_backup_{timestamp}.db'
            shutil.copy2(source_db, backup_file)
            # Keep only last 10 backups
            backups = sorted(backup_dir.glob('stoku_backup_*.db'))
            if len(backups) > 10:
                for old_backup in backups[:-10]:
                    old_backup.unlink()
            return str(backup_file)
    except Exception as e:
        print(f'Backup failed: {e}')
    return None
# Dictionary për të ruajtur login attempts: {ip_or_username: [timestamps...]}
login_attempts = defaultdict(list)
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_TIME_SECONDS = 60

def check_login_attempts(identifier):
    """Check if user is locked out due to too many attempts"""
    now = time.time()
    # Clean old attempts (older than lockout time)
    login_attempts[identifier] = [t for t in login_attempts[identifier] if now - t < LOCKOUT_TIME_SECONDS]
    
    if len(login_attempts[identifier]) >= MAX_LOGIN_ATTEMPTS:
        # User is locked out
        oldest_attempt = login_attempts[identifier][0]
        lockout_end = oldest_attempt + LOCKOUT_TIME_SECONDS
        remaining_seconds = int(lockout_end - now)
        return False, remaining_seconds
    return True, 0

def record_login_attempt(identifier):
    """Record a failed login attempt"""
    now = time.time()
    login_attempts[identifier].append(now)
    # Keep only last 10 attempts
    login_attempts[identifier] = login_attempts[identifier][-10:]

def reset_login_attempts(identifier):
    """Reset login attempts after successful login"""
    if identifier in login_attempts:
        del login_attempts[identifier]

# ===== SECURITY HEADERS =====
@app.after_request
def set_security_headers(response):
    """Add security headers to all responses"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'self' https:; script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; img-src 'self' data: https:;"
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    # Prevent caching of protected pages - always validate session on reload
    if request.path not in ['/', '/login', '/static/style.css', '/static/manifest.json', '/static/sw.js']:
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    
    return response

# --- MODELET E DATABAZES ---

class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    materials = db.relationship('Material', backref='department', lazy=True)
    items = db.relationship('PurchaseItem', backref='department', lazy=True)

class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    unit = db.Column(db.String(20), nullable=False) # psh. copë, m2, litër
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)
    created_by = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, nullable=True)
    updated_by = db.Column(db.String(100), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=True)


class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(100), nullable=True)
    created_by = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, nullable=True)
    updated_by = db.Column(db.String(100), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=True)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_super = db.Column(db.Boolean, default=False)

class PurchaseItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_name = db.Column(db.String(100), nullable=False)
    note = db.Column(db.String(200), nullable=True)
    created_by = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, nullable=True)
    updated_by = db.Column(db.String(100), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=True)
    quantity = db.Column(db.Float, nullable=False)
    is_bought = db.Column(db.Boolean, default=False)
    material_id = db.Column(db.Integer, db.ForeignKey('material.id'), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)
    material = db.relationship('Material')
    # Note: we keep `client_name` as a simple string for compatibility.
    # New `Client` model stores clients; when a client is selected, we save its name here.


class CompletedClient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(100), nullable=True)
    completed_by = db.Column(db.String(100), nullable=True)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('CompletedPurchaseItem', backref='completed_client', lazy=True)


class CompletedPurchaseItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    completed_client_id = db.Column(db.Integer, db.ForeignKey('completed_client.id'), nullable=False)
    material_name = db.Column(db.String(200), nullable=True)
    quantity = db.Column(db.Float, nullable=True)
    unit = db.Column(db.String(50), nullable=True)
    department_id = db.Column(db.Integer, nullable=True)
    note = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.String(100), nullable=True)
    action = db.Column(db.String(20), nullable=False)  # CREATE, UPDATE, DELETE
    object_type = db.Column(db.String(50), nullable=False)
    object_id = db.Column(db.String(100), nullable=True)
    details = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class LoginAttempt(db.Model):
    """Track login attempts for security purposes"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)  # IPv4 or IPv6
    success = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_agent = db.Column(db.String(500), nullable=True)


def log_event(user, action, object_type, object_id=None, details=None):
    """Helper to record an audit event. Commits immediately."""
    try:
        ev = AuditLog(
            user=(user or 'anonymous'),
            action=action,
            object_type=object_type,
            object_id=(str(object_id) if object_id is not None else None),
            details=(details if details is not None else None),
            timestamp=datetime.utcnow()
        )
        db.session.add(ev)
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass

# Krijo databazen dhe repartet default
with app.app_context():
    db.create_all()
    if not Department.query.first():
        default_depts = ['Iverica', 'Ngjyra', 'Druri', 'Shtofi']
        for d in default_depts:
            db.session.add(Department(name=d))
        db.session.commit()

    # Ensure audit columns exist in tables (for existing DBs)
    try:
        inspector = inspect(db.engine)
        table_columns = {}
        table_columns[Material.__table__.name] = [
            ('created_by', 'VARCHAR(100)'), ('created_at', 'DATETIME'), ('updated_by', 'VARCHAR(100)'), ('updated_at', 'DATETIME')
        ]
        table_columns[Client.__table__.name] = [
            ('created_by', 'VARCHAR(100)'), ('created_at', 'DATETIME'), ('updated_by', 'VARCHAR(100)'), ('updated_at', 'DATETIME')
        ]
        table_columns[PurchaseItem.__table__.name] = [
            ('note', 'VARCHAR(200)'), ('created_by', 'VARCHAR(100)'), ('created_at', 'DATETIME'), ('updated_by', 'VARCHAR(100)'), ('updated_at', 'DATETIME')
        ]

        for table_name, cols in table_columns.items():
            existing = [c['name'] for c in inspector.get_columns(table_name)]
            for col_name, col_type in cols:
                if col_name not in existing:
                    try:
                        with db.engine.begin() as conn:
                            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"))
                    except Exception:
                        # ignore failures to alter (SQLite older versions, permissions)
                        pass
    except Exception:
        pass

    # Ensure `is_super` exists on user table
    try:
        inspector = inspect(db.engine)
        user_cols = [c['name'] for c in inspector.get_columns(User.__table__.name)]
        if 'is_super' not in user_cols:
            with db.engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {User.__table__.name} ADD COLUMN is_super BOOLEAN DEFAULT 0"))
    except Exception:
        pass

    # Werkzeug's default password hashes are longer than 128 chars.
    # Older deployments may have created this as VARCHAR(128), which breaks logins/resets on Postgres.
    try:
        if db.engine.url.get_backend_name().startswith('postgresql'):
            with db.engine.begin() as conn:
                conn.execute(text('ALTER TABLE "user" ALTER COLUMN password_hash TYPE TEXT'))
    except Exception:
        pass

    # Create default users if missing
    try:
        if not User.query.filter_by(username='admin').first():
            admin_pw = generate_password_hash('123')
            db.session.add(User(username='admin', password_hash=admin_pw, is_admin=True, is_super=True))
        if not User.query.filter_by(username='Altin').first():
            viewer_pw = generate_password_hash('123')
            db.session.add(User(username='Altin', password_hash=viewer_pw, is_admin=False, is_super=False))
        db.session.commit()
        # Ensure existing 'admin' user is marked as super
        admin_user = User.query.filter_by(username='admin').first()
        if admin_user and not getattr(admin_user, 'is_super', False):
            admin_user.is_super = True
            admin_user.is_admin = True
            db.session.commit()
    except Exception:
        pass

# Initialize Flask-Migrate (used for schema migrations; run `flask db ...`)
migrate = Migrate(app, db)

# --- RRUGET (ROUTES) ---

# Rruga globale per te marre repartet ne side panel
@app.context_processor
def inject_departments():
    return dict(departments=Department.query.all(), current_user=session.get('username'), current_user_id=session.get('user_id'), is_admin=session.get('is_admin'), is_super=session.get('is_super'))


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            flash('Nuk keni leje për këtë veprim.', 'danger')
            return redirect(url_for('categories'))
        return f(*args, **kwargs)
    return decorated


def super_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_super'):
            flash('Veprim i paautorizuar.', 'danger')
            return redirect(url_for('categories'))
        return f(*args, **kwargs)
    return decorated


@app.route('/login', methods=['GET', 'POST'])
@csrf.exempt  # Login form doesn't need CSRF since no session yet
def login():
    next_url = request.args.get('next')
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        ip_address = request.remote_addr
        user_agent = request.headers.get('User-Agent', '')
        
        # Validate input
        try:
            username = validate_input(username, 'Username', max_length=80)
        except ValueError as e:
            flash(f'Invalid username: {str(e)}', 'danger')
            return render_template('login.html')
        
        if not password or len(password) > 256:
            flash('Invalid password.', 'danger')
            return render_template('login.html')
        
        # Check rate limiting
        is_allowed, remaining_time = check_login_attempts(username)
        if not is_allowed:
            # Log the lockout attempt
            try:
                attempt = LoginAttempt(
                    username=username,
                    ip_address=ip_address,
                    success=False,
                    user_agent=user_agent
                )
                db.session.add(attempt)
                db.session.commit()
            except Exception:
                pass
            
            flash(f'Too many failed attempts. Please wait {remaining_time} seconds before trying again.', 'danger')
            return render_template('login.html')
        
        # Try authentication
        user = User.query.filter_by(username=username).first()
        
        # Log attempt
        try:
            attempt = LoginAttempt(
                username=username,
                ip_address=ip_address,
                success=bool(user and check_password_hash(user.password_hash, password)),
                user_agent=user_agent
            )
            db.session.add(attempt)
            db.session.commit()
        except Exception:
            pass
        
        if user and check_password_hash(user.password_hash, password):
            # Reset login attempts on successful login
            reset_login_attempts(username)
            
            # Set session
            session.permanent = True
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = bool(user.is_admin)
            session['is_super'] = bool(getattr(user, 'is_super', False))
            
            flash('Login successful.', 'success')
            return redirect(next_url or url_for('categories'))
        
        # Failed login
        record_login_attempt(username)
        remaining_attempts = MAX_LOGIN_ATTEMPTS - len(login_attempts[username])
        
        flash(f'Invalid username or password. {remaining_attempts} attempts remaining.', 'danger')
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    username = session.get('username')
    session.clear()
    # For PWA: Ensure session is completely cleared
    response = make_response(redirect(url_for('login')))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    flash('Doli nga sistemi.', 'info')
    return response


@app.route('/check-session')
def check_session():
    """API endpoint for PWA to check if session is still valid"""
    if session.get('user_id'):
        return jsonify({'valid': True, 'username': session.get('username')})
    return jsonify({'valid': False}), 401


@app.route('/security-logs')
@admin_required
def security_logs():
    """View login attempts and security logs"""
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))

    # Filters
    username_filter = request.args.get('username', '').strip()
    result_filter = request.args.get('result', 'all')  # all | failed | success

    query = LoginAttempt.query
    if username_filter:
        query = query.filter(LoginAttempt.username.contains(username_filter))
    if result_filter == 'failed':
        query = query.filter(LoginAttempt.success == False)
    elif result_filter == 'success':
        query = query.filter(LoginAttempt.success == True)

    attempts = query.order_by(LoginAttempt.timestamp.desc()).paginate(page=page, per_page=per_page)

    # Summary statistics
    last_24h = datetime.utcnow() - timedelta(hours=24)
    total_attempts = LoginAttempt.query.count()
    failed_today = LoginAttempt.query.filter(LoginAttempt.success == False, LoginAttempt.timestamp > last_24h).count()
    success_today = LoginAttempt.query.filter(LoginAttempt.success == True, LoginAttempt.timestamp > last_24h).count()

    return render_template('security_logs.html', 
                         attempts=attempts,
                         total_attempts=total_attempts,
                         failed_today=failed_today,
                         success_today=success_today,
                         username_filter=username_filter,
                         result_filter=result_filter)


@app.route('/admin', methods=['GET', 'POST'])
@admin_required
def admin_panel():
    users = User.query.order_by(User.username).all()
    if request.method == 'POST':
        current_user = User.query.get(session.get('user_id'))

        # --- Delete user (super only) ---
        delete_user_id = request.form.get('delete_user_id')
        if delete_user_id:
            if not getattr(current_user, 'is_super', False):
                flash('Only Superadmin can delete users.', 'danger')
            else:
                try:
                    uid = int(delete_user_id)
                    if uid == current_user.id:
                        flash('You cannot delete your own account.', 'danger')
                    else:
                        target = User.query.get(uid)
                        if target:
                            name = target.username
                            db.session.delete(target)
                            db.session.commit()
                            try:
                                log_event(current_user.username, 'DELETE', 'User', name, 'Deleted by superadmin')
                            except Exception:
                                pass
                            flash('User deleted successfully.', 'success')
                except Exception:
                    flash('Invalid user id.', 'danger')
            return redirect(url_for('admin_panel'))

        # --- Change role (super only) ---
        change_role_user_id = request.form.get('change_role_user_id')
        if change_role_user_id:
            if not getattr(current_user, 'is_super', False):
                flash('Only Superadmin can change roles.', 'danger')
            else:
                try:
                    uid = int(change_role_user_id)
                    new_role = request.form.get('new_role_for_user', 'viewer')
                    u = User.query.get(uid)
                    if u:
                        if uid == current_user.id:
                            flash('Cannot change your own role here.', 'danger')
                        else:
                            is_super_flag = True if new_role == 'super' else False
                            is_admin_flag = True if new_role == 'admin' or is_super_flag else False
                            u.is_super = is_super_flag
                            u.is_admin = is_admin_flag
                            db.session.commit()
                            try:
                                log_event(current_user.username, 'UPDATE', 'User', u.username, f'Role set to {new_role}')
                            except Exception:
                                pass
                            flash('User role updated.', 'success')
                except Exception:
                    flash('Invalid user id.', 'danger')
            return redirect(url_for('admin_panel'))

        # --- Create new user ---
        new_username = request.form.get('new_username', '').strip()
        new_password = request.form.get('new_password_create', '')
        new_role = request.form.get('new_role', '')
        
        if new_username and new_password:
            try:
                # Validate inputs
                new_username = validate_input(new_username, 'Username', max_length=80)
                validate_password(new_password)
                
                if User.query.filter_by(username=new_username).first():
                    flash('User already exists.', 'danger')
                else:
                    # only superadmin can create other admins
                    if new_role == 'admin' and not getattr(current_user, 'is_super', False):
                        flash('Only Superadmin can create admin users.', 'danger')
                    else:
                        is_admin_flag = True if new_role == 'admin' else False
                        is_super_flag = True if new_role == 'super' else False
                        db.session.add(User(username=new_username, password_hash=generate_password_hash(new_password), is_admin=is_admin_flag, is_super=is_super_flag))
                        db.session.commit()
                        # Audit
                        try:
                            log_event(current_user.username, 'CREATE', 'User', new_username, f'Role: {new_role}')
                        except Exception:
                            pass
                        flash('User created successfully.', 'success')
            except ValueError as e:
                flash(f'Error: {str(e)}', 'danger')
            return redirect(url_for('admin_panel'))

        # --- Change existing user's password ---
        user_id = request.form.get('user_id')
        new_pw = request.form.get('new_password', '')
        if user_id and new_pw:
            try:
                validate_password(new_pw)
                u = User.query.get(user_id)
                if u:
                    # allow if current is superadmin or changing own password
                    if getattr(current_user, 'is_super', False) or current_user.id == u.id:
                        u.password_hash = generate_password_hash(new_pw)
                        db.session.commit()
                        # Audit
                        try:
                            log_event(current_user.username, 'UPDATE', 'User', u.username, 'Password changed')
                        except Exception:
                            pass
                        flash('Password changed successfully.', 'success')
                    else:
                        flash('Only Superadmin can change other users passwords.', 'danger')
            except ValueError as e:
                flash(f'Password error: {str(e)}', 'danger')
        return redirect(url_for('admin_panel'))
    return render_template('admin.html', users=users)

@app.route('/')
def index():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    return redirect(url_for('categories'))

@app.route('/manifest.json')
def manifest():
    """Serve PWA manifest"""
    return send_file('static/manifest.json', mimetype='application/manifest+json')

@app.route('/sw.js')
def service_worker():
    """Serve service worker"""
    response = make_response(send_file('static/sw.js'))
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

@app.route('/categories', methods=['GET', 'POST'])
@login_required
def categories():
    if request.method == 'POST':
        if not session.get('is_admin'):
            flash('Only admins can add items.', 'danger')
            return redirect(url_for('categories'))

        # Shto klient te ri (nese formi i klientit u dergua)
        client_name = request.form.get('client_name', '').strip()
        if client_name:
            try:
                client_name = validate_input(client_name, 'Client name', max_length=100)
                client_category = request.form.get('client_category', '').strip()
                if client_category:
                    client_category = validate_input(client_category, 'Category', max_length=100, allow_special=True)
                
                new_client = Client(
                    name=client_name,
                    category=(client_category if client_category else None),
                    created_by=session.get('username'),
                    created_at=datetime.utcnow()
                )
                db.session.add(new_client)
                db.session.commit()
                # Audit
                try:
                    log_event(session.get('username'), 'CREATE', 'Client', new_client.id, f'Name: {new_client.name}; Category: {new_client.category or "-"}')
                except Exception:
                    pass
                return redirect(url_for('categories'))
            except ValueError as e:
                flash(f'Error: {str(e)}', 'danger')
                return redirect(url_for('categories'))

        # Shto material (nese formi i materialit u dergua)
        name = request.form.get('name', '').strip()
        unit = request.form.get('unit', '').strip()
        dept_id = request.form.get('department_id', '')
        
        if name and unit and dept_id:
            try:
                name = validate_input(name, 'Material name', max_length=100)
                unit = validate_input(unit, 'Unit', max_length=20)
                
                new_material = Material(
                    name=name,
                    unit=unit,
                    department_id=dept_id,
                    created_by=session.get('username'),
                    created_at=datetime.utcnow()
                )
                db.session.add(new_material)
                db.session.commit()
                # Audit
                try:
                    dept_name = Department.query.get(int(dept_id)).name if dept_id else ''
                except Exception:
                    dept_name = ''
                try:
                    log_event(session.get('username'), 'CREATE', 'Material', new_material.id, f'Name: {name}; Unit: {unit}; Dept: {dept_name}')
                except Exception:
                    pass
                return redirect(url_for('categories'))
            except ValueError as e:
                flash(f'Error: {str(e)}', 'danger')
                return redirect(url_for('categories'))

    materials = Material.query.all()
    clients = Client.query.order_by(Client.name).all()
    return render_template('categories.html', materials=materials, clients=clients)

@app.route('/department/<int:dept_id>', methods=['GET', 'POST'])
@login_required
def department(dept_id):
    dept = Department.query.get_or_404(dept_id)
    clients = Client.query.order_by(Client.name).all()

    if request.method == 'POST':
        if not session.get('is_admin'):
            flash('Only admins can add purchase orders.', 'danger')
            return redirect(url_for('department', dept_id=dept.id))

        client_id = request.form.get('client_id')
        client_name = None
        if client_id:
            sel = Client.query.get(client_id)
            if sel:
                client_name = sel.name

        # fallback: user typed a client name
        if not client_name:
            client_name = request.form.get('client_name', '').strip()

        material_id = request.form.get('material_id')
        qty = request.form.get('quantity', '').strip()
        note = request.form.get('note', '').strip()

        if client_name and material_id and qty:
            try:
                client_name = validate_input(client_name, 'Client name', max_length=100)
                qty_float = float(qty)
                if qty_float <= 0:
                    raise ValueError('Quantity must be greater than 0')
                
                note_validated = None
                if note:
                    note_validated = validate_input(note, 'Note', max_length=200, allow_special=True)
                
                new_item = PurchaseItem(
                    client_name=client_name,
                    note=note_validated,
                    created_by=session.get('username'),
                    created_at=datetime.utcnow(),
                    material_id=material_id,
                    quantity=qty_float,
                    department_id=dept.id
                )
                db.session.add(new_item)
                db.session.commit()
                # Audit
                try:
                    mat = new_item.material.name if new_item.material else str(new_item.material_id)
                except Exception:
                    mat = str(new_item.material_id)
                try:
                    log_event(session.get('username'), 'CREATE', 'PurchaseItem', new_item.id, f'Material: {mat}; Qty: {new_item.quantity}; Client: {new_item.client_name}; Note: {new_item.note or "-"}')
                except Exception:
                    pass
                return redirect(url_for('department', dept_id=dept.id))
            except ValueError as e:
                flash(f'Error: {str(e)}', 'danger')
                return redirect(url_for('department', dept_id=dept.id))

    # Filtrim sipas klientit (përmes GET param `client_id`)
    filter_client_id = request.args.get('client_id')
    if filter_client_id:
        sel = Client.query.get(filter_client_id)
        if sel:
            items = PurchaseItem.query.filter_by(department_id=dept.id, client_name=sel.name).order_by(PurchaseItem.is_bought, PurchaseItem.id.desc()).all()
        else:
            items = PurchaseItem.query.filter_by(department_id=dept.id).order_by(PurchaseItem.is_bought, PurchaseItem.id.desc()).all()
    else:
        items = PurchaseItem.query.filter_by(department_id=dept.id).order_by(PurchaseItem.is_bought, PurchaseItem.id.desc()).all()
    
    # Llogaritja e totalit per gjerat qe duhen blere (pa blere ende)
    summary = {}
    for item in items:
        if not item.is_bought:
            mat_name = item.material.name
            note_text = (item.note or '').strip()
            key = (mat_name, note_text)
            if key in summary:
                summary[key]['qty'] += item.quantity
            else:
                summary[key] = {'qty': item.quantity, 'unit': item.material.unit, 'mat_name': mat_name, 'note': note_text}

    summary_list = list(summary.values())

    return render_template('department.html', department=dept, items=items, summary=summary_list, clients=clients, selected_client_id=filter_client_id)

@app.route('/toggle/<int:item_id>')
@admin_required
def toggle_item(item_id):
    item = PurchaseItem.query.get_or_404(item_id)
    prev = bool(item.is_bought)
    item.is_bought = not prev
    item.updated_by = session.get('username')
    item.updated_at = datetime.utcnow()
    db.session.commit()
    # Audit
    try:
        log_event(session.get('username'), 'UPDATE', 'PurchaseItem', item.id, f'is_bought: {prev} -> {item.is_bought}; Qty: {item.quantity}; Client: {item.client_name}')
    except Exception:
        pass
    return redirect(request.referrer)

@app.route('/delete/<int:item_id>')
@admin_required
def delete_item(item_id):
    item = PurchaseItem.query.get_or_404(item_id)
    try:
        details = f'Material: {item.material.name if item.material else item.material_id}; Qty: {item.quantity}; Client: {item.client_name}; Note: {item.note or "-"}'
    except Exception:
        details = f'PurchaseItem id {item_id}'
    db.session.delete(item)
    db.session.commit()
    # Audit
    try:
        log_event(session.get('username'), 'DELETE', 'PurchaseItem', item.id, details)
    except Exception:
        pass
    return redirect(request.referrer)


@app.route('/delete_material/<int:mat_id>')
@login_required
def delete_material(mat_id):
    # Only Superadmin may delete materials
    if not session.get('is_super'):
        flash('Nuk keni leje për këtë veprim.', 'danger')
        return redirect(url_for('categories'))
    mat = Material.query.get_or_404(mat_id)
    # Prevent deletion if there are linked purchase items
    linked = PurchaseItem.query.filter_by(material_id=mat.id).first()
    if linked:
        flash('Nuk mund ta fshini sepse ka porosi të lidhura për këtë material.', 'danger')
        return redirect(url_for('categories'))
    name = mat.name
    db.session.delete(mat)
    db.session.commit()
    # Audit
    try:
        log_event(session.get('username'), 'DELETE', 'Material', mat.id, f'Name: {name}; Dept: {mat.department.name if mat.department else "-"}; Unit: {mat.unit}')
    except Exception:
        pass
    flash(f'Materiali "{name}" u fshi.', 'success')
    return redirect(request.referrer or url_for('categories'))


@app.route('/delete_client/<int:client_id>')
@login_required
def delete_client(client_id):
    # Only Superadmin may delete clients
    if not session.get('is_super'):
        flash('Nuk keni leje për këtë veprim.', 'danger')
        return redirect(url_for('categories'))
    client = Client.query.get_or_404(client_id)
    # Prevent deletion if there are purchase items linked by name
    linked = PurchaseItem.query.filter_by(client_name=client.name).first()
    if linked:
        flash('Nuk mund ta fshini sepse ka porosi të lidhura për këtë klient.', 'danger')
        return redirect(url_for('categories'))
    name = client.name
    db.session.delete(client)
    db.session.commit()
    # Audit
    try:
        log_event(session.get('username'), 'DELETE', 'Client', client.id, f'Name: {name}; Category: {client.category or "-"}')
    except Exception:
        pass
    flash(f'Klienti "{name}" u fshi.', 'success')
    return redirect(request.referrer or url_for('categories'))


@app.route('/complete_client/<int:client_id>')
@admin_required
def complete_client(client_id):
    """Archive a client's purchased materials into CompletedClient and remove them from active tables."""
    client = Client.query.get_or_404(client_id)
    # Gather all purchase items for this client (by name)
    items = PurchaseItem.query.filter_by(client_name=client.name).all()
    if not items:
        flash('Nuk ka të dhëna blerjeje për këtë klient.', 'warning')
        return redirect(request.referrer or url_for('categories'))

    try:
        completed = CompletedClient(name=client.name, category=client.category, completed_by=session.get('username'), completed_at=datetime.utcnow())
        db.session.add(completed)
        db.session.flush()

        for it in items:
            mat_name = it.material.name if it.material else (str(it.material_id) if it.material_id else '-')
            cp = CompletedPurchaseItem(
                completed_client_id=completed.id,
                material_name=mat_name,
                quantity=it.quantity,
                unit=(it.material.unit if it.material else None),
                department_id=it.department_id,
                note=it.note
            )
            db.session.add(cp)
            db.session.delete(it)

        # remove the client from active clients
        db.session.delete(client)
        db.session.commit()
        try:
            log_event(session.get('username'), 'CREATE', 'CompletedClient', completed.id, f'Archived {completed.name} with {len(items)} items')
        except Exception:
            pass
        flash('Klienti u përfundua dhe u arkivua te `Klientet e perfunduar`.', 'success')
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        flash(f'Ndodhi një gabim gjatë arkivimit: {e}', 'danger')

    return redirect(request.referrer or url_for('categories'))


@app.route('/completed_clients')
@login_required
def completed_clients():
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    name_filter = request.args.get('name', '').strip()

    query = CompletedClient.query
    if name_filter:
        query = query.filter(CompletedClient.name.contains(name_filter))

    total = query.count()
    clients = query.order_by(CompletedClient.completed_at.desc()).offset((page-1)*per_page).limit(per_page).all()
    has_next = (page * per_page) < total
    has_prev = page > 1
    return render_template('completed_clients.html', clients=clients, page=page, per_page=per_page, total=total, has_next=has_next, has_prev=has_prev, name_filter=name_filter)


@app.route('/completed_client/<int:comp_id>')
@login_required
def completed_client_detail(comp_id):
    comp = CompletedClient.query.get_or_404(comp_id)
    items = CompletedPurchaseItem.query.filter_by(completed_client_id=comp.id).order_by(CompletedPurchaseItem.created_at.desc()).all()
    return render_template('completed_client_detail.html', client=comp, items=items)


@app.route('/audit')
@login_required
def audit():
    # Paginated and filterable audit events
    try:
        page = int(request.args.get('page', 1))
    except Exception:
        page = 1
    try:
        per_page = int(request.args.get('per_page', 50))
    except Exception:
        per_page = 50

    user_filter = request.args.get('user', '').strip()
    action_filter = request.args.get('action', '').strip()

    query = AuditLog.query
    if user_filter:
        query = query.filter(AuditLog.user == user_filter)
    if action_filter:
        query = query.filter(AuditLog.action == action_filter)

    total = query.count()
    logs = query.order_by(AuditLog.timestamp.desc()).offset((page-1)*per_page).limit(per_page).all()
    has_next = (page * per_page) < total
    has_prev = page > 1

    # Provide a list of users present in audit for quick filtering
    try:
        distinct_users = [row[0] for row in db.session.query(AuditLog.user).distinct().order_by(AuditLog.user).all() if row[0]]
    except Exception:
        distinct_users = []

    return render_template('audit.html', logs=logs, page=page, per_page=per_page, total=total, has_next=has_next, has_prev=has_prev, distinct_users=distinct_users, user_filter=user_filter, action_filter=action_filter)


@app.route('/export/department/<int:dept_id>/csv')
@login_required
def export_department_csv(dept_id):
    mode = request.args.get('mode', 'items')
    client_id = request.args.get('client_id') or None
    dept = Department.query.get_or_404(dept_id)

    # select items based on client filter
    if client_id:
        try:
            sel = Client.query.get(int(client_id))
        except Exception:
            sel = None
        if sel:
            items = PurchaseItem.query.filter_by(department_id=dept.id, client_name=sel.name).order_by(PurchaseItem.is_bought, PurchaseItem.id.desc()).all()
        else:
            items = PurchaseItem.query.filter_by(department_id=dept.id).order_by(PurchaseItem.is_bought, PurchaseItem.id.desc()).all()
    else:
        items = PurchaseItem.query.filter_by(department_id=dept.id).order_by(PurchaseItem.is_bought, PurchaseItem.id.desc()).all()

    filename = f"{dept.name}_export_{mode}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"

    if mode == 'summary':
        # compute summary
        summary = {}
        for item in items:
            if not item.is_bought:
                mat_name = item.material.name
                note_text = (item.note or '').strip()
                key = (mat_name, note_text)
                if key in summary:
                    summary[key]['qty'] += item.quantity
                else:
                    summary[key] = {'qty': item.quantity, 'unit': item.material.unit, 'mat_name': mat_name, 'note': note_text}
        rows = []
        for v in summary.values():
            rows.append([v['mat_name'], v['note'] or '-', v['qty'], v['unit']])
        headers = ['Materiali', 'Shënim', 'Sasia Totale', 'Njësia']
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        data = output.getvalue().encode('utf-8-sig')
        # Audit
        try:
            log_event(session.get('username'), 'EXPORT', 'DepartmentSummary', dept.id, f'mode=summary; client_id={client_id or "all"}')
        except Exception:
            pass
        response = make_response(data)
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        return response

    # default: items list
    headers = ['Client', 'Material', 'Note', 'Quantity', 'Unit', 'CreatedBy', 'CreatedAt', 'UpdatedBy', 'UpdatedAt']
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for item in items:
        writer.writerow([
            item.client_name,
            item.material.name if item.material else item.material_id,
            item.note or '-',
            item.quantity,
            item.material.unit if item.material else '-',
            item.created_by or '-',
            item.created_at.strftime('%Y-%m-%d %H:%M') if item.created_at else '-',
            item.updated_by or '-',
            item.updated_at.strftime('%Y-%m-%d %H:%M') if item.updated_at else '-'
        ])
    data = output.getvalue().encode('utf-8-sig')
    try:
        log_event(session.get('username'), 'EXPORT', 'DepartmentItems', dept.id, f'mode=items; client_id={client_id or "all"}')
    except Exception:
        pass
    response = make_response(data)
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    return response


@app.route('/export/department/<int:dept_id>/xlsx')
@login_required
def export_department_xlsx(dept_id):
    mode = request.args.get('mode', 'items')
    client_id = request.args.get('client_id') or None
    dept = Department.query.get_or_404(dept_id)

    # select items
    if client_id:
        try:
            sel = Client.query.get(int(client_id))
        except Exception:
            sel = None
        if sel:
            items = PurchaseItem.query.filter_by(department_id=dept.id, client_name=sel.name).order_by(PurchaseItem.is_bought, PurchaseItem.id.desc()).all()
        else:
            items = PurchaseItem.query.filter_by(department_id=dept.id).order_by(PurchaseItem.is_bought, PurchaseItem.id.desc()).all()
    else:
        items = PurchaseItem.query.filter_by(department_id=dept.id).order_by(PurchaseItem.is_bought, PurchaseItem.id.desc()).all()

    filename = f"{dept.name}_export_{mode}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"

    try:
        from openpyxl import Workbook
    except Exception:
        flash('Për eksport Excel duhet të instaloni bibliotekën `openpyxl` (pip install openpyxl).', 'danger')
        return redirect(request.referrer or url_for('department', dept_id=dept.id))

    wb = Workbook()
    ws = wb.active
    ws.title = f"{dept.name}"

    if mode == 'summary':
        summary = {}
        for item in items:
            if not item.is_bought:
                mat_name = item.material.name
                note_text = (item.note or '').strip()
                key = (mat_name, note_text)
                if key in summary:
                    summary[key]['qty'] += item.quantity
                else:
                    summary[key] = {'qty': item.quantity, 'unit': item.material.unit, 'mat_name': mat_name, 'note': note_text}
        ws.append(['Materiali', 'Shënim', 'Sasia Totale', 'Njësia'])
        for v in summary.values():
            ws.append([v['mat_name'], v['note'] or '-', v['qty'], v['unit']])
        try:
            log_event(session.get('username'), 'EXPORT', 'DepartmentSummary', dept.id, f'mode=summary; client_id={client_id or "all"}')
        except Exception:
            pass
    else:
        ws.append(['Client', 'Material', 'Note', 'Quantity', 'Unit', 'CreatedBy', 'CreatedAt', 'UpdatedBy', 'UpdatedAt'])
        for item in items:
            ws.append([
                item.client_name,
                item.material.name if item.material else item.material_id,
                item.note or '-',
                item.quantity,
                item.material.unit if item.material else '-',
                item.created_by or '-',
                item.created_at.strftime('%Y-%m-%d %H:%M') if item.created_at else '-',
                item.updated_by or '-',
                item.updated_at.strftime('%Y-%m-%d %H:%M') if item.updated_at else '-'
            ])
        try:
            log_event(session.get('username'), 'EXPORT', 'DepartmentItems', dept.id, f'mode=items; client_id={client_id or "all"}')
        except Exception:
            pass

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    try:
        return send_file(output, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except TypeError:
        return send_file(output, as_attachment=True, attachment_filename=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@app.route('/export/department/<int:dept_id>/pdf')
@login_required
def export_department_pdf(dept_id):
    mode = request.args.get('mode', 'summary')
    client_id = request.args.get('client_id') or None
    dept = Department.query.get_or_404(dept_id)

    # select items
    if client_id:
        try:
            sel = Client.query.get(int(client_id))
        except Exception:
            sel = None
        if sel:
            items = PurchaseItem.query.filter_by(department_id=dept.id, client_name=sel.name).order_by(PurchaseItem.is_bought, PurchaseItem.id.desc()).all()
        else:
            items = PurchaseItem.query.filter_by(department_id=dept.id).order_by(PurchaseItem.is_bought, PurchaseItem.id.desc()).all()
    else:
        items = PurchaseItem.query.filter_by(department_id=dept.id).order_by(PurchaseItem.is_bought, PurchaseItem.id.desc()).all()

    filename = f"{dept.name}_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
    except Exception:
        flash('Për eksport PDF duhet të instaloni `reportlab` (pip install reportlab).', 'danger')
        return redirect(request.referrer or url_for('department', dept_id=dept.id))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=30, bottomMargin=18)
    elements = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontSize=18,
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=12,
        alignment=1
    )
    
    header_style = ParagraphStyle(
        'HeaderStyle',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#475569'),
        spaceAfter=6
    )

    # HEADER SECTION
    elements.append(Paragraph(f'RAPORTI I POROSITEVE - {dept.name}', title_style))
    elements.append(Paragraph(f'Data: {datetime.utcnow().strftime("%d/%m/%Y %H:%M")}', header_style))
    elements.append(Spacer(1, 12))

    client_text = 'Të gjitha klientet'
    selected_client_obj = None
    if client_id:
        try:
            cobj = Client.query.get(int(client_id))
            if cobj:
                client_text = cobj.name
                selected_client_obj = cobj
        except Exception:
            pass
    
    elements.append(Paragraph(f'<b>Filtro klienti:</b> {client_text}', header_style))
    elements.append(Spacer(1, 12))

    # CLIENT INFORMATION SECTION (if filtered by client)
    if selected_client_obj:
        elements.append(Paragraph('<b>INFORMACIONI I KLIENTIT</b>', styles['Heading2']))
        client_info_data = [
            ['Emri', selected_client_obj.name],
            ['Kategoria', selected_client_obj.category or '-'],
            ['Regjistruar nga', selected_client_obj.created_by or '-'],
            ['Data regjistrimi', selected_client_obj.created_at.strftime('%d/%m/%Y') if selected_client_obj.created_at else '-']
        ]
        client_info_table = Table(client_info_data, colWidths=[2*inch, 4*inch])
        client_info_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#f8fafc')),
            ('TEXTCOLOR', (0,0), (-1,-1), colors.black),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
            ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 10),
            ('ROWBACKGROUNDS', (0,0), (-1,-1), [colors.white, colors.HexColor('#f9fafb')])
        ]))
        elements.append(client_info_table)
        elements.append(Spacer(1, 15))

    # MATERIALS SECTION - List of materials for each client or filtered client
    elements.append(Paragraph('<b>MATERIALET QE DUHEN BLERE</b>', styles['Heading2']))
    
    # Group items by client to show materials for each client
    client_materials = {}
    for item in items:
        if not item.is_bought:  # Only unbought items
            if item.client_name not in client_materials:
                client_materials[item.client_name] = []
            client_materials[item.client_name].append(item)
    
    if client_materials:
        for client_name in sorted(client_materials.keys()):
            elements.append(Paragraph(f'<b>Klienti: {client_name}</b>', header_style))
            mat_data = [['Materiali', 'Sasia', 'Njësia', 'Shënim']]
            for mat_item in client_materials[client_name]:
                mat_data.append([
                    mat_item.material.name if mat_item.material else str(mat_item.material_id),
                    str(mat_item.quantity),
                    mat_item.material.unit if mat_item.material else '-',
                    mat_item.note or '-'
                ])
            mat_table = Table(mat_data, colWidths=[2.5*inch, 0.8*inch, 0.8*inch, 1.9*inch])
            mat_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#dbeafe')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#0c4a6e')),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,-1), 9),
                ('ALIGN', (1,0), (-1,-1), 'LEFT'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f9fafb')])
            ]))
            elements.append(mat_table)
            elements.append(Spacer(1, 8))
    else:
        elements.append(Paragraph('Nuk ka materiale për të blerë.', header_style))
    
    elements.append(Spacer(1, 15))

    # MAIN DATA TABLE SECTION
    if mode == 'items':
        elements.append(Paragraph('<b>LISTA E PLOTE E POROSITEVE</b>', styles['Heading2']))
        data = [['Klienti', 'Materiali', 'Shënim', 'Sasia', 'Njësia']]
        for it in items:
            data.append([
                it.client_name,
                it.material.name if it.material else str(it.material_id),
                it.note or '-',
                str(it.quantity),
                it.material.unit if it.material else '-'
            ])
        try:
            log_event(session.get('username'), 'EXPORT', 'DepartmentItemsPDF', dept.id, f'client_id={client_id or "all"}')
        except Exception:
            pass
    else:
        # summary
        elements.append(Paragraph('<b>PERMBLEDHJE E MATERIALEVE</b>', styles['Heading2']))
        summary = {}
        for item in items:
            if not item.is_bought:
                mat_name = item.material.name
                note_text = (item.note or '').strip()
                key = (mat_name, note_text)
                if key in summary:
                    summary[key]['qty'] += item.quantity
                else:
                    summary[key] = {'qty': item.quantity, 'unit': item.material.unit, 'mat_name': mat_name, 'note': note_text}
        data = [['Materiali', 'Shënim', 'Sasia Totale', 'Njësia']]
        for v in summary.values():
            data.append([v['mat_name'], v['note'] or '-', str(v['qty']), v['unit']])
        try:
            log_event(session.get('username'), 'EXPORT', 'DepartmentSummaryPDF', dept.id, f'client_id={client_id or "all"}')
        except Exception:
            pass

    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f8fafc')),
        ('TEXTCOLOR',(0,0),(-1,0),colors.black),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('ALIGN',(0,0),(-1,-1),'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f9fafb')])
    ]))
    elements.append(table)
    
    # Footer
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(f'Eksportuar: {datetime.utcnow().strftime("%d/%m/%Y %H:%M:%S")} | Nga: {session.get("username")}', 
                             ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#94a3b8'))))
    
    doc.build(elements)
    buffer.seek(0)
    try:
        return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')
    except TypeError:
        return send_file(buffer, as_attachment=True, attachment_filename=filename, mimetype='application/pdf')

if __name__ == '__main__':
    # Create a backup when starting the application
    try:
        if os.getenv('BACKUP_ENABLED', 'True').lower() == 'true':
            create_backup()
    except Exception as e:
        print(f'Backup on startup failed: {e}')
    
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'False').lower() == 'true'
    
    # Warn if running in debug mode
    if debug:
        print("⚠️  WARNING: Running in DEBUG mode - DO NOT USE IN PRODUCTION!")
    
    app.run(debug=debug, host='0.0.0.0', port=port)
    
