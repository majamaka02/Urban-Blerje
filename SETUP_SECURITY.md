# Quick Setup Guide - Security Fixed Version

## 🚀 First Time Setup

### 1. Generate Secret Key
```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```
Copy the output (this will be your SECRET_KEY)

### 2. Create .env File
Create a file named `.env` in the project root with:

```env
SECRET_KEY=<paste-your-generated-key-here>
DEBUG=False
FLASK_ENV=development
PORT=5000
DATABASE_URL=sqlite:///stoku.db
SESSION_COOKIE_SECURE=False
SESSION_COOKIE_SAMESITE=Lax
BACKUP_ENABLED=True
BACKUP_DIR=./backups
```

### 3. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 4. Run the App
```powershell
python app.py
```

App will start at `http://localhost:5000`

### 5. Login & Change Passwords
- Default username: `admin`
- Default password: `123` (CHANGE THIS IMMEDIATELY!)
- Go to Admin Panel and set a strong password

---

## 🔐 Before Going to Production

### Critical Steps:
1. Generate a new strong SECRET_KEY
2. Set DEBUG=False
3. Set SESSION_COOKIE_SECURE=True (if using HTTPS)
4. Change all default passwords
5. Test CSRF protection (forms should have hidden token field)

### Production .env Example:
```env
SECRET_KEY=<very-long-random-key>
DEBUG=False
FLASK_ENV=production
PORT=5000
DATABASE_URL=sqlite:///stoku.db
SESSION_COOKIE_SECURE=True
SESSION_COOKIE_SAMESITE=Strict
BACKUP_ENABLED=True
BACKUP_DIR=./backups
```

### Deploy with Gunicorn:
```powershell
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

---

## ✅ What's New

- ✅ CSRF protection on all forms
- ✅ Environment-based configuration (.env)
- ✅ Input validation for all user data
- ✅ Strong password requirements
- ✅ Automatic database backups
- ✅ Security headers
- ✅ Rate limiting on login

---

## 🆘 Common Issues

**"ModuleNotFoundError: No module named 'flask_wtf'"**
```powershell
pip install Flask-WTF
```

**".env not found" warning**
Create `.env` file with the configuration shown above.

**CSRF token validation errors**
- All forms now require CSRF tokens
- If errors occur, clear browser cookies and try again

---

## 📝 Important Files

- `app.py` - Main application (fixed security issues)
- `.env` - Configuration (create this, never commit)
- `requirements.txt` - Python dependencies (updated)
- `SECURITY_FIXES.md` - Detailed security documentation
- `templates/` - HTML templates (CSRF tokens added)
- `backups/` - Auto-created database backups

See `SECURITY_FIXES.md` for detailed information about all security fixes.
