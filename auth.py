from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer
from models import User, db
from extensions import mail  # Importujeme mail z extensions.py

# Definice blueprintu pro autentizaci
auth_bp = Blueprint('auth', __name__)

# Route pro přihlášení
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        if not email or not password:
            flash('Musíte zadat e-mail a heslo.', 'error')
            return redirect(url_for('auth.login'))

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('portfolio.upload'))
        else:
            flash('Špatný e-mail nebo heslo. Zapomněli jste své heslo?', 'error')
            return redirect(url_for('auth.login'))

    return render_template('login.html')

# Route pro registraci
@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        print(f"Form data received - Username: {username}, Email: {email}")

        if not username or not email or not password:
            flash('Musíte vyplnit všechna pole.')
            return redirect(url_for('auth.signup'))

        if User.query.filter_by(email=email).first():
            flash('E-mail již existuje.')
            print("Email already exists")
            return redirect(url_for('auth.signup'))

        if User.query.filter_by(username=username).first():
            flash('Uživatel již existuje.')
            print("Username already exists")
            return redirect(url_for('auth.signup'))

        new_user = User(username=username, email=email)
        new_user.set_password(password)

        print(f"Creating user: {username}, Email: {email}, Hashed password: {new_user.password_hash}")

        db.session.add(new_user)
        db.session.commit()

        print(f"User {username} created successfully")

        login_user(new_user)
        print(f"User {username} logged in successfully")

        return redirect(url_for('portfolio.upload'))

    return render_template('signup.html')

# Route pro zapomenuté heslo
@auth_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        if user:
            # Použití current_app pro přístup ke konfiguraci
            token = generate_reset_token(user)

            msg = Message('Resetování hesla',
                          sender=current_app.config['MAIL_DEFAULT_SENDER'],
                          recipients=[email])
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            msg.body = f'Pro resetování hesla klikněte na následující odkaz: {reset_url}'
            mail.send(msg)

            flash('Byl vám odeslán e-mail s instrukcemi pro resetování hesla.', 'info')
        else:
            flash('E-mail nebyl nalezen.', 'error')
        return redirect(url_for('auth.forgot_password'))

    return render_template('forgot_password.html')

# Route pro reset hesla
@auth_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = verify_reset_token(token)
    if not user:
        flash('Token pro resetování hesla je neplatný nebo vypršel.', 'error')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')

        if password != password_confirm:
            flash('Hesla se neshodují.', 'error')
            return redirect(url_for('auth.reset_password', token=token))

        # Nastavení nového hesla
        user.set_password(password)
        db.session.commit()

        # Zobrazení zprávy o úspěšném resetu hesla
        flash('Heslo bylo úspěšně změněno.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('reset_password.html', token=token)

# Route pro odhlášení
@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Byli jste úspěšně odhlášeni.')
    return redirect(url_for('auth.login'))

# Funkce pro generování a ověřování resetovacích tokenů
def generate_reset_token(user, expires_sec=1800):
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])  # Použití current_app místo app
    return s.dumps(user.email, salt='password-reset-salt')

def verify_reset_token(token, expires_sec=1800):
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])  # Použití current_app místo app
    try:
        email = s.loads(token, salt='password-reset-salt', max_age=expires_sec)
    except:
        return None
    return User.query.filter_by(email=email).first()
