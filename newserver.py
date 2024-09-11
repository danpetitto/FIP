import os
import uuid
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import pandas as pd
from finance import add_current_prices, calculate_portfolio_value, calculate_realized_profit, calculate_unrealized_profit, calculate_dividend_cash, calculate_fees, calculate_invested_amount
from werkzeug.security import check_password_hash, generate_password_hash
from models import db, User, Portfolio
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_cors import CORS
from flask_mail import Mail, Message
from io import BytesIO
from dotenv import load_dotenv
from flask_migrate import Migrate

# Načtení environment proměnných
load_dotenv()

app = Flask(__name__)
CORS(app)

# Tajný klíč aplikace
app.config['SECRET_KEY'] = 'tajny_klic'

# Připojení k MySQL databázi (vyplň si vlastní údaje pro MySQL)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:D200426p?@localhost/sakila'

# Inicializace databáze a migrace
db.init_app(app)
migrate = Migrate(app, db)

# Flask-Mail konfigurace (musíš si nastavit proměnné v .env souboru)
app.config['MAIL_SERVER'] = 'smtp.seznam.cz'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')  # Tvůj Seznam.cz e-mail z .env
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')  # Heslo k tvému Seznam.cz e-mailu z .env
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')  # Tvůj Seznam.cz e-mail z .env

mail = Mail(app)

# Flask-Login setup
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Ručně vytvoříme tabulky při spuštění aplikace
with app.app_context():
    db.create_all()
#registrace uživatele
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']  # Získání e-mailu z formuláře
        password = request.form['password']

        # Kontrola, jestli uživatel již existuje
        if User.query.filter_by(username=username).first():
            flash('Uživatel již existuje.')
            return redirect(url_for('signup'))

        # Kontrola, zda e-mail není prázdný
        if not email:
            flash('E-mail je povinný.')
            return redirect(url_for('signup'))

        # Kontrola, jestli e-mail již existuje
        if User.query.filter_by(email=email).first():
            flash('E-mail již existuje.')
            return redirect(url_for('signup'))

        # Vytvoření nového uživatele
        new_user = User(username=username, email=email)  # Uložení e-mailu
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        # Automatické přihlášení po registraci
        login_user(new_user)
        return redirect(url_for('upload'))

    return render_template('upload.html')

# Přihlášení a zpracování špatného hesla 
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('upload'))
        else:
            flash('Špatné uživatelské jméno nebo heslo. <a href="/reset_password">Zapomněli jste své heslo?</a>', 'danger')
            return render_template('login.html')

    return render_template('upload.html')

# Odhlášení uživatele
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# Hlavní stránka po přihlášení
@app.route('/')
@login_required
def index():
    return redirect(url_for('upload'))
#nahrání csv
@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        # Získání nahraného souboru a názvu portfolia
        file = request.files['file']
        portfolio_name = request.form['portfolio_name']
        
        # Kontrola, jestli soubor a název portfolia jsou platné
        if file and portfolio_name:
            # Uložení souboru a portfolia
            new_portfolio = Portfolio(
                name=portfolio_name,
                filename=file.filename,
                data=file.read(),
                owner=current_user
            )
            db.session.add(new_portfolio)
            db.session.commit()

            flash('Portfolio bylo úspěšně nahráno.')
            return redirect(url_for('upload'))  # Přesměrování zpět na stránku nahrávání
        else:
            flash('Název portfolia a soubor jsou povinné!', 'danger')

    user_portfolios = Portfolio.query.filter_by(user_id=current_user.id).all()
    return render_template('upload.html', portfolios=user_portfolios)

# Výběr portfolia k zobrazení a zpracování

@app.route('/select_portfolio/<int:portfolio_id>', methods=['GET', 'POST'])
@login_required
def select_portfolio(portfolio_id):
    portfolio = Portfolio.query.get_or_404(portfolio_id)

    # Ověření, zda portfolio patří aktuálnímu uživateli
    if portfolio.owner != current_user:
        flash('Nemáte oprávnění k zobrazení tohoto portfolia.', 'danger')
        return redirect(url_for('upload'))

    try:
        # Zpracování CSV dat
        csv_data = BytesIO(portfolio.data)
        try:
            data = pd.read_csv(csv_data, encoding='utf-8')
        except UnicodeDecodeError:
            csv_data.seek(0)
            data = pd.read_csv(csv_data, encoding='ISO-8859-1')

        # Přidání aktuálních cen a zpracování
        data = add_current_prices(data)

        # Výpočty výsledků portfolia
        portfolio_value = calculate_portfolio_value(data)
        realized_profit = calculate_realized_profit(data)
        total_invested = calculate_invested_amount(data)
        unrealized_profit = calculate_unrealized_profit(portfolio_value, total_invested)
        dividend_results = calculate_dividend_cash(data)
        total_fees = calculate_fees(data)

        results = {
            'portfolio_value': f"{round(portfolio_value, 2)} €",
            'realized_profit': f"{round(realized_profit, 2)} €",
            'unrealized_profit': f"{round(unrealized_profit, 2)} €",
            'total_dividends': f"{round(dividend_results['total_dividends'], 2)} €",
            'dividend_yield': f"{round(dividend_results['dividend_yield'], 2)} %",
            'dividend_prediction_10_years': f"{round(dividend_results['dividend_prediction_10_years'], 2)} €",
            'tax_on_dividends': f"{round(dividend_results['tax_on_dividends'], 2)} €",
            'total_fees': f"{round(total_fees, 2)} €",
            'invested': total_invested
        }

        return render_template('process.html', results=results, portfolio=portfolio)
    
    except Exception as e:
        flash(f"Chyba při zpracování souboru: {str(e)}", 'danger')
        return redirect(url_for('upload'))

# Smazání portfolia
@app.route('/delete_portfolio/<int:portfolio_id>', methods=['POST'])
@login_required
def delete_portfolio(portfolio_id):
    portfolio_to_delete = Portfolio.query.get_or_404(portfolio_id)

    if portfolio_to_delete.owner != current_user:
        flash('Nemáte oprávnění smazat toto portfolio.')
        return redirect(url_for('upload'))

    db.session.delete(portfolio_to_delete)
    db.session.commit()
    flash('Portfolio bylo úspěšně smazáno.')
    return redirect(url_for('upload'))

# Stránka pro zadání e-mailu k obnovení hesla
@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(username=email).first()

        if user:
            token = str(uuid.uuid4())
            user.reset_token = token  # Uložíme token do databáze (můžeš upravit model User a přidat reset_token)
            db.session.commit()

            reset_url = url_for('reset_password_token', token=token, _external=True)
            msg = Message('Obnovení hesla', sender='noreply@yourapp.com', recipients=[email])
            msg.body = f'Klikněte na následující odkaz pro obnovení hesla: {reset_url}'
            mail.send(msg)

            flash('Pokyny k obnovení hesla byly odeslány na váš e-mail.', 'info')
            return redirect(url_for('login'))
        else:
            flash('Tento e-mail není zaregistrován.', 'danger')
            return redirect(url_for('reset_password'))

    return render_template('reset_password.html')

# Stránka pro zadání nového hesla na základě tokenu

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password_token(token):
    user = User.query.filter_by(reset_token=token).first()

    if not user:
        flash('Neplatný nebo vypršelý token.', 'danger')
        return redirect(url_for('reset_password'))

    if request.method == 'POST':
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        if new_password != confirm_password:
            flash('Hesla se neshodují.', 'danger')
            return redirect(url_for('reset_password_token', token=token))

        # Nastavení nového hesla a vymazání tokenu
        user.set_password(new_password)
        user.reset_token = None
        db.session.commit()

        flash('Heslo bylo úspěšně změněno. Můžete se nyní přihlásit.', 'success')
        return redirect(url_for('login'))

    return render_template('new_password.html')

if __name__ == '__main__':
    app.run(debug=True)

