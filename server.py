import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import pandas as pd
from finance import add_current_prices, calculate_portfolio_value, calculate_realized_profit, calculate_unrealized_profit, calculate_dividend_cash, calculate_fees, calculate_invested_amount
from werkzeug.security import check_password_hash
from models import db, User, Portfolio
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from io import BytesIO

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'tajny_klic'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'

db.init_app(app)

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

# Stránka pro registraci
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if User.query.filter_by(username=username).first():
            flash('Uživatel již existuje.')
            return redirect(url_for('signup'))

        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        login_user(new_user)
        return redirect(url_for('upload'))

    return render_template('signup.html')

# Stránka pro přihlášení
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
            flash('Špatné uživatelské jméno nebo heslo.')
            return redirect(url_for('login'))

    return render_template('login.html')

# Stránka pro odhlášení
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

# Route pro nahrávání CSV souboru a správu portfolií
@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        file = request.files['file']
        portfolio_name = request.form['portfolio_name']
        if file and portfolio_name:
            new_portfolio = Portfolio(
                name=portfolio_name,
                filename=file.filename,
                data=file.read(),
                owner=current_user
            )
            db.session.add(new_portfolio)
            db.session.commit()
            flash('Portfolio bylo nahráno.')
            return redirect(url_for('upload'))

    # Načtení všech portfolií uživatelem
    user_portfolios = Portfolio.query.filter_by(user_id=current_user.id).all()
    return render_template('upload.html', portfolios=user_portfolios)

# Výběr portfolia k zobrazení a zpracování
@app.route('/select_portfolio/<int:portfolio_id>', methods=['GET', 'POST'])
@login_required
def select_portfolio(portfolio_id):
    portfolio = Portfolio.query.get_or_404(portfolio_id)

    if portfolio.owner != current_user:
        flash('Nemáte oprávnění k zobrazení tohoto portfolia.')
        return redirect(url_for('upload'))

    # Načtení dat z portfolia s ošetřením kódování
    try:
        csv_data = BytesIO(portfolio.data)
        try:
            data = pd.read_csv(csv_data, encoding='utf-8')
        except UnicodeDecodeError:
            flash("Chyba při načítání souboru v UTF-8. Zkouším jiné kódování.")
            csv_data.seek(0)
            data = pd.read_csv(csv_data, encoding='ISO-8859-1')
    except Exception as e:
        return f"Chyba při zpracování souboru: {str(e)}", 400

    # Přidáme aktuální ceny k datům na základě ISIN pomocí OpenFIGI a Polygon.io
    try:
        data = add_current_prices(data)
    except Exception as e:
        flash(f"Chyba při získávání aktuálních cen: {str(e)}")
        return redirect(url_for('upload'))

    # Výpočty pro portfolio
    portfolio_value = calculate_portfolio_value(data)  # Spočítáme hodnotu portfolia
    realized_profit = calculate_realized_profit(data)  # Spočítáme realizovaný zisk
    total_invested = calculate_invested_amount(data)  # Spočítáme investovanou částku

    # Výpočet nerealizovaného zisku
    unrealized_profit = calculate_unrealized_profit(portfolio_value, total_invested)

    # Výpočty pro dividendy
    dividend_results = calculate_dividend_cash(data)  # Spočítáme dividendy, yield, predikci a daň

    # Výpočet dalších částek
    total_dividends = dividend_results['total_dividends']
    dividend_yield = dividend_results['dividend_yield']
    dividend_prediction_10_years = dividend_results['dividend_prediction_10_years']
    tax_on_dividends = dividend_results['tax_on_dividends']

    # Výpočet dalších částek
    total_fees = calculate_fees(data)

    # Zaokrouhlení výsledků
    results = {
        'portfolio_value': f"{round(portfolio_value, 2)} €",
        'realized_profit': f"{round(realized_profit, 2)} €",
        'unrealized_profit': f"{round(unrealized_profit, 2)} €",
        'total_dividends': f"{round(total_dividends, 2)} €",
        'dividend_yield': f"{round(dividend_yield, 2)} %",
        'dividend_prediction_10_years': f"{round(dividend_prediction_10_years, 2)} €",
        'tax_on_dividends': f"{round(tax_on_dividends, 2)} €",
        'total_fees': f"{round(total_fees, 2)} €",
        'invested': total_invested  # Přidáme investovanou částku do výsledků
    }

    # Zobrazíme výsledky portfolia
    return render_template('process.html', results=results, portfolio=portfolio)

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

if __name__ == '__main__':
    app.run(debug=True)




