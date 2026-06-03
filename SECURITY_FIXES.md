# Security Fixes & Configuration Guide

## 🔒 Security Issues Fixed

This document details all security vulnerabilities that have been addressed in the application.

---

## ✅ 1. Exposed Secret Key (CRITICAL) 

**What was the problem?**
- The Flask secret key was hardcoded as `'dev_secret_change_me'`
- This exposed session secrets and could lead to session hijacking

**How it's fixed:**
- Secret key now loaded from environment variables using `python-dotenv`
- Create a `.env` file in the project root with a strong secret key

**Action Required:**
```bash
# Generate a strong secret key
python -c "import secrets; print(secrets.token_hex(32))"
# Example output: 5c8f9a2b1d4e6f3a8c2b1e4f5a8c9d2b1e4f5a8c9d2b1e4f5a8c9d2b

# Add to .env file:
SECRET_KEY=5c8f9a2b1d4e6f3a8c2b1e4f5a8c9d2b1e4f5a8c9d2b1e4f5a8c9d2b
```

---

## ✅ 2. Debug Mode Enabled (CRITICAL)

**What was the problem?**
- `app.run(debug=True)` was hardcoded
- Enables Werkzeug debugger which exposes internals and allows RCE

**How it's fixed:**
- Debug mode now controlled by environment variable `DEBUG`
- Default is `False` for production safety
- App warns if running in debug mode

**To use debug mode in development:**
```
# In .env file:
DEBUG=True
FLASK_ENV=development
```

**For production (must have):**
```
# In .env file:
DEBUG=False
FLASK_ENV=production
```

---

## ✅ 3. Missing CSRF Protection (HIGH)

**What was the problem?**
- All POST forms were vulnerable to Cross-Site Request Forgery attacks
- Attackers could force unauthorized actions (delete, create, update)

**How it's fixed:**
- Installed `Flask-WTF` library
- Added CSRF token to all forms in templates
- All POST endpoints now automatically protected

**What you see:**
- Login form does NOT require CSRF token (session not yet established)
- All other forms have `{{ csrf_token() }}` added

---

## ✅ 4. Missing Input Validation (HIGH)

**What was the problem?**
- User inputs weren't validated for length, type, or dangerous patterns
- Could allow SQL injection attempts and stored XSS

**How it's fixed:**
- Created `validate_input()` function for general validation
- Created `validate_password()` for strong passwords
- Validation checks:
  - Maximum length enforcement
  - SQL injection pattern detection
  - Special character restrictions
  - Password strength (8+ chars, uppercase, lowercase, numbers)

**Password Requirements (new):**
- Minimum 8 characters
- At least 1 uppercase letter
- At least 1 lowercase letter  
- At least 1 number

---

## ✅ 5. Weak Default Credentials (MEDIUM)

**What was the problem?**
- Default users (admin, Altin) created with password `'123'`
- Extremely weak and documented in code

**How it's fixed:**
- Strong password policy now enforced for new users
- Admin can change user passwords from admin panel
- Existing users can update their own passwords

**Action Required:**
1. Login as admin with username: `admin` password: `123`
2. Go to Admin Panel
3. Change admin password to something strong
4. Change Altin user password

**Command line password reset (optional):**
```python
python
from app import app, db, User, generate_password_hash

with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    if admin:
        admin.password_hash = generate_password_hash('NewStrongPassword123!')
        db.session.commit()
        print("Password changed successfully")
```

---

## ✅ 6. Request Size Limit (MEDIUM)

**What was the problem?**
- No limit on file upload or POST body size
- Could cause DoS attacks with large file uploads

**How it's fixed:**
- Added `MAX_CONTENT_LENGTH = 16MB` configuration
- Prevents large uploads and requests

---

## ✅ 7. Session Security Configuration (MEDIUM)

**What was the problem?**
- `SESSION_COOKIE_SECURE=True` is required for HTTPS but breaks development without SSL

**How it's fixed:**
- Now environment variable controlled
- Development: `SESSION_COOKIE_SECURE=False` (works with HTTP)
- Production: `SESSION_COOKIE_SECURE=True` (with HTTPS)

---

## ✅ 8. Database Backups (FEATURE)

**What was added:**
- Automatic database backups on app startup
- Backs up to `./backups` directory
- Keeps last 10 backups (auto-cleanup)

**Configuration in .env:**
```
BACKUP_ENABLED=True
BACKUP_DIR=./backups
BACKUP_INTERVAL_HOURS=24
```

**To disable backups:**
```
BACKUP_ENABLED=False
```

---

## 📋 Environment Configuration (.env file)

The app now uses a `.env` file for configuration. Create this file in the project root:

```env
# ===== FLASK CONFIGURATION =====
SECRET_KEY=your-very-long-random-secret-key-here
DEBUG=False
FLASK_ENV=production
PORT=5000

# ===== DATABASE =====
DATABASE_URL=sqlite:///stoku.db

# ===== SECURITY =====
# Set to True only when using HTTPS (production with SSL/TLS)
SESSION_COOKIE_SECURE=False
SESSION_COOKIE_SAMESITE=Lax

# ===== BACKUP SETTINGS =====
BACKUP_ENABLED=True
BACKUP_DIR=./backups
BACKUP_INTERVAL_HOURS=24
```

**For Production Deployment:**
```env
SECRET_KEY=<generate-with-secrets.token_hex(32)>
DEBUG=False
FLASK_ENV=production
SESSION_COOKIE_SECURE=True
SESSION_COOKIE_SAMESITE=Strict
```

---

## 🚀 Running the App

### Development Mode:
```bash
# Create .env with DEBUG=True
echo "DEBUG=True" >> .env

# Run app
python app.py
```

### Production Mode:
```bash
# Create .env with production settings
echo "DEBUG=False" >> .env
echo "FLASK_ENV=production" >> .env
echo "SESSION_COOKIE_SECURE=True" >> .env

# Run with gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

---

## 📦 New Dependencies

The following packages were added for security:

```
Flask-WTF>=1.1.0       # CSRF protection
python-dotenv>=0.19.0  # Environment configuration
```

Install with:
```bash
pip install -r requirements.txt
```

---

## ✅ Next Steps / Recommendations

### HIGH PRIORITY (Do Soon):
1. ✅ Change admin and Altin user passwords
2. ✅ Generate strong SECRET_KEY for production
3. ✅ Configure SESSION_COOKIE_SECURE=True when using HTTPS

### MEDIUM PRIORITY (Consider):
1. Add 2-Factor Authentication (TOTP)
2. Add email-based password reset
3. Implement rate limiting on all endpoints
4. Set up IP whitelisting for admin panel
5. Encrypt sensitive database fields

### LOW PRIORITY (Future Enhancements):
1. Add audit log retention policy
2. Implement session timeout warning
3. Add API rate limiting
4. Set up automated database backups to cloud storage

---

## 🔍 Security Check Checklist

- [x] Secret key in environment variable
- [x] Debug mode disabled by default
- [x] CSRF protection on all forms
- [x] Input validation implemented
- [x] Strong password requirements
- [x] Session cookies secure configuration
- [x] Request size limits
- [x] Database backups enabled
- [ ] SSL/TLS certificate installed (manual - production only)
- [ ] 2FA implementation (future)
- [ ] Email password reset (future)

---

## 🆘 Troubleshooting

**App won't start - environment variables not loaded:**
```bash
# Check if .env exists
ls -la .env

# If missing, create from .env.example
cp .env.example .env

# Update SECRET_KEY in .env
```

**CSRF token validation fails:**
- Make sure all forms include `{{ csrf_token() }}`
- Check that Flask-WTF is installed: `pip install Flask-WTF`

**Password validation too strict:**
- Edit `validate_password()` function in app.py to adjust requirements

**Backups not being created:**
- Check `./backups` directory exists
- Set `BACKUP_ENABLED=True` in .env
- Check file permissions on backups directory

---

## 📚 References

- [Flask-WTF Documentation](https://flask-wtf.readthedocs.io/)
- [OWASP Security Best Practices](https://owasp.org/)
- [Python Secrets Module](https://docs.python.org/3/library/secrets.html)
- [Flask Security Documentation](https://flask.palletsprojects.com/security/)
