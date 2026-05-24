import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, make_response
import io, csv
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime

app = Flask(__name__)
# Secret key for session (change in production)
app.secret_key = 'dev_secret_change_me'
# Konfigurimi i Databazes SQLite
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///stoku.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

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
    password_hash = db.Column(db.String(128), nullable=False)
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


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.String(100), nullable=True)
    action = db.Column(db.String(20), nullable=False)  # CREATE, UPDATE, DELETE
    object_type = db.Column(db.String(50), nullable=False)
    object_id = db.Column(db.String(100), nullable=True)
    details = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


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
def login():
    next_url = request.args.get('next')
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = bool(user.is_admin)
            session['is_super'] = bool(getattr(user, 'is_super', False))
            flash('Hyrje e suksesshme.', 'success')
            return redirect(next_url or url_for('categories'))
        flash('Emri ose fjalëkalimi është i pasaktë.', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Doli nga sistemi.', 'info')
    return redirect(url_for('login'))


@app.route('/admin', methods=['GET', 'POST'])
@admin_required
def admin_panel():
    users = User.query.order_by(User.username).all()
    if request.method == 'POST':
        current_user = User.query.get(session.get('user_id'))
        # Create new user
        new_username = request.form.get('new_username')
        new_password = request.form.get('new_password_create')
        new_role = request.form.get('new_role')
        if new_username and new_password:
            if User.query.filter_by(username=new_username).first():
                flash('Përdoruesi ekziston.', 'danger')
            else:
                # only superadmin can create other admins
                if new_role == 'admin' and not getattr(current_user, 'is_super', False):
                    flash('Vetëm Superadmin mund të krijojë adminë.', 'danger')
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
                    flash('Përdoruesi u krijua.', 'success')
            return redirect(url_for('admin_panel'))

        # Change existing user's password
        user_id = request.form.get('user_id')
        new_pw = request.form.get('new_password')
        if user_id and new_pw:
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
                    flash('Fjalëkalimi u ndryshua.', 'success')
                else:
                    flash('Vetëm Superadmin mund të ndryshojë fjalëkalimin e përdoruesve të tjerë.', 'danger')
        return redirect(url_for('admin_panel'))
    return render_template('admin.html', users=users)

@app.route('/')
def index():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    return redirect(url_for('categories'))

@app.route('/categories', methods=['GET', 'POST'])
@login_required
def categories():
    if request.method == 'POST':
        if not session.get('is_admin'):
            flash('Vetëm admin mund të shtojë elemente.', 'danger')
            return redirect(url_for('categories'))

        # Shto klient te ri (nese formi i klientit u dergua)
        client_name = request.form.get('client_name')
        if client_name:
            client_category = request.form.get('client_category')
            if client_name.strip():
                new_client = Client(
                    name=client_name.strip(),
                    category=(client_category.strip() if client_category else None),
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

        # Shto material (nese formi i materialit u dergua)
        name = request.form.get('name')
        unit = request.form.get('unit')
        dept_id = request.form.get('department_id')
        
        if name and unit and dept_id:
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

    materials = Material.query.all()
    clients = Client.query.order_by(Client.name).all()
    return render_template('categories.html', materials=materials, clients=clients)

@app.route('/department/<int:dept_id>', methods=['GET', 'POST'])
@app.route('/department/<int:dept_id>', methods=['GET', 'POST'])
@login_required
def department(dept_id):
    dept = Department.query.get_or_404(dept_id)
    clients = Client.query.order_by(Client.name).all()

    if request.method == 'POST':
        if not session.get('is_admin'):
            flash('Vetëm admin mund të shtojë porosi.', 'danger')
            return redirect(url_for('department', dept_id=dept.id))

        client_id = request.form.get('client_id')
        client_name = None
        if client_id:
            sel = Client.query.get(client_id)
            if sel:
                client_name = sel.name

        # fallback: user typed a client name
        if not client_name:
            client_name = request.form.get('client_name')

        material_id = request.form.get('material_id')
        qty = request.form.get('quantity')
        note = request.form.get('note')

        if client_name and material_id and qty:
            new_item = PurchaseItem(
                client_name=client_name,
                note=(note.strip() if note else None),
                created_by=session.get('username'),
                created_at=datetime.utcnow(),
                material_id=material_id,
                quantity=float(qty),
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


@app.route('/audit')
@login_required
def audit():
    # Simple paginated view for audit events (visible to any logged-in user)
    try:
        page = int(request.args.get('page', 1))
    except Exception:
        page = 1
    try:
        per_page = int(request.args.get('per_page', 50))
    except Exception:
        per_page = 50
    total = AuditLog.query.count()
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).offset((page-1)*per_page).limit(per_page).all()
    has_next = (page * per_page) < total
    has_prev = page > 1
    return render_template('audit.html', logs=logs, page=page, per_page=per_page, total=total, has_next=has_next, has_prev=has_prev)


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
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
    except Exception:
        flash('Për eksport PDF duhet të instaloni `reportlab` (pip install reportlab).', 'danger')
        return redirect(request.referrer or url_for('department', dept_id=dept.id))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=30, bottomMargin=18)
    elements = []
    styles = getSampleStyleSheet()
    elements.append(Paragraph(f'Reparti: {dept.name}', styles['Title']))
    client_text = 'Të gjitha'
    if client_id:
        try:
            cobj = Client.query.get(int(client_id))
            if cobj:
                client_text = cobj.name
        except Exception:
            pass
    elements.append(Paragraph(f'Filtro klienti: {client_text}', styles['Normal']))
    elements.append(Spacer(1, 12))

    if mode == 'items':
        data = [['Client', 'Material', 'Note', 'Quantity', 'Unit']]
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
        data = [['Material', 'Note', 'Total Qty', 'Unit']]
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
        ('ALIGN',(0,0),(-1,-1),'LEFT'),
    ]))
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    try:
        return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')
    except TypeError:
        return send_file(buffer, as_attachment=True, attachment_filename=filename, mimetype='application/pdf')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
    