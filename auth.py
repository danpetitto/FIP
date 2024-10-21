from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer
from models import User, db
from extensions import mail  # Importujeme mail z extensions.py
from werkzeug.utils import secure_filename
import os


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


#PROFIL UŽIVATELE
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
import os
from werkzeug.utils import secure_filename
from datetime import datetime

@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = current_user  # Získáme aktuálního uživatele

    if request.method == 'POST':
        username = request.form.get('username')
        about = request.form.get('about')
        profile_image = request.files.get('profile_image')
        investor_type = request.form.get('investor_type')
        investor_since = request.form.get('investor_since')
        location = request.form.get('location')  # Nové pole pro místo bydliště
        website = request.form.get('website')  # Nové pole pro webovou stránku
        social_links = request.form.get('social_links')  # Nové pole pro sociální sítě

        if username:
            user.username = username
        if about:
            user.about = about
        if investor_type:
            user.investor_type = investor_type
        if investor_since:
            try:
                user.investor_since = datetime.strptime(investor_since, '%Y').date()
            except ValueError:
                flash('Neplatný formát data pro "Investor od roku". Zadejte rok ve formátu YYYY.', 'error')
        if location:
            user.location = location
        if website:
            user.website = website
        if social_links:
            user.social_links = social_links

        # Zpracování profilového obrázku
        if profile_image and allowed_file(profile_image.filename):
            filename = secure_filename(profile_image.filename)
            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)

            file_path = os.path.join(upload_folder, filename)
            profile_image.save(file_path)
            user.profile_image = filename

        # Uložíme změny do databáze
        try:
            db.session.commit()
            flash('Profil byl úspěšně aktualizován!', 'success')
        except Exception as e:
            flash(f'Chyba při ukládání změn: {e}', 'error')
            db.session.rollback()

        return redirect(url_for('auth.profile'))

    edit_mode = request.args.get('edit', 'false') == 'true'

    # Sledování uživatele
    follow_action = request.args.get('action')
    if follow_action == 'follow':
        current_user.follow(user)
        db.session.commit()
    elif follow_action == 'unfollow':
        current_user.unfollow(user)
        db.session.commit()

    return render_template('profile.html', user=user, edit_mode=edit_mode)
