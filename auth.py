from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required
from models import User, db

# Definice blueprintu pro autentizaci
auth_bp = Blueprint('auth', __name__)

# Route pro přihlášení
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Získání e-mailu a hesla
        email = request.form.get('email')  # Změna z username na email
        password = request.form.get('password')

        if not email or not password:
            flash('Musíte zadat e-mail a heslo.')
            return redirect(url_for('auth.login'))

        # Hledání uživatele v databázi podle e-mailu
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            print(f"User {email} logged in successfully")  # Diagnostika
            return redirect(url_for('portfolio.upload'))  # Přesměrování na stránku pro nahrávání portfolia
        else:
            print("Login failed: incorrect email or password")  # Diagnostika
            flash('Špatný e-mail nebo heslo.')
            return redirect(url_for('auth.login'))

    return render_template('login.html')

# Route pro registraci
@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        # Získání dat z formuláře
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        # Diagnostický výpis
        print(f"Form data received - Username: {username}, Email: {email}")

        # Kontrola, zda jsou všechna pole vyplněna
        if not username or not email or not password:
            flash('Musíte vyplnit všechna pole.')
            return redirect(url_for('auth.signup'))

        # Kontrola, zda uživatel s tímto e-mailem již existuje
        if User.query.filter_by(email=email).first():
            flash('E-mail již existuje.')
            print("Email already exists")  # Diagnostika
            return redirect(url_for('auth.signup'))

        # Kontrola, zda uživatel s tímto uživatelským jménem již existuje
        if User.query.filter_by(username=username).first():
            flash('Uživatel již existuje.')
            print("Username already exists")  # Diagnostika
            return redirect(url_for('auth.signup'))

        # Vytvoření nového uživatele a uložení do databáze
        new_user = User(username=username, email=email)
        new_user.set_password(password)  # Nastavení hashovaného hesla

        # Diagnostika před uložením
        print(f"Creating user: {username}, Email: {email}, Hashed password: {new_user.password_hash}")

        db.session.add(new_user)
        db.session.commit()

        # Diagnostika po úspěšném uložení
        print(f"User {username} created successfully")

        # Automatické přihlášení nového uživatele
        login_user(new_user)
        print(f"User {username} logged in successfully")

        return redirect(url_for('portfolio.upload'))  # Přesměrování na stránku pro nahrávání portfolia

    return render_template('signup.html')

# Route pro odhlášení
@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Byli jste úspěšně odhlášeni.')
    return redirect(url_for('auth.login'))
