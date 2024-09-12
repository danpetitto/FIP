from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import Portfolio, db
from finance import (
    add_current_prices, calculate_portfolio_value, calculate_realized_profit, 
    calculate_unrealized_profit, calculate_invested_amount, calculate_dividend_cash, 
    calculate_fees
)
import pandas as pd
from io import BytesIO

portfolio_bp = Blueprint('portfolio', __name__)

# Route pro nahrávání nového portfolia
@portfolio_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        # Diagnostika: Výpis obsahu request.form a request.files
        print("Form Data: ", request.form)  # Zobrazí data formuláře
        print("File Data: ", request.files)  # Zobrazí data souborů

        # Získání souboru a názvu portfolia z formuláře
        file = request.files.get('file')  # Používáme get() pro bezpečné získání souboru
        portfolio_name = request.form.get('portfolio_name')  # Používáme get() pro volné získání názvu portfolia

        # Kontrola, zda byl soubor nahrán a portfolio má název
        if not file or not portfolio_name:
            flash('Musíte nahrát soubor a zadat název portfolia.', 'error')
            return redirect(url_for('portfolio.upload'))

        # Kontrola, zda nahraný soubor je CSV
        if not file.filename.endswith('.csv'):
            flash('Prosím, nahrajte soubor ve formátu CSV.', 'error')
            return redirect(url_for('portfolio.upload'))

        # Uložení nového portfolia do databáze
        new_portfolio = Portfolio(
            name=portfolio_name,  # Libovolně definovatelný název portfolia
            filename=file.filename,
            data=file.read(),
            user=current_user  # Oprava na 'user'
        )
        db.session.add(new_portfolio)
        db.session.commit()

        flash('Portfolio bylo úspěšně nahráno.', 'success')
        return redirect(url_for('portfolio.upload'))

    # Získání všech portfolií aktuálního uživatele
    user_portfolios = Portfolio.query.filter_by(user_id=current_user.id).all()
    return render_template('upload.html', portfolios=user_portfolios)

# Route pro zobrazení zpracovaného portfolia
@portfolio_bp.route('/select_portfolio/<int:portfolio_id>', methods=['GET'])
@login_required
def select_portfolio(portfolio_id):
    portfolio = Portfolio.query.get_or_404(portfolio_id)

    # Kontrola, zda portfolio patří přihlášenému uživateli
    if portfolio.user != current_user:  # Změna z 'owner' na 'user'
        flash('Nemáte oprávnění k zobrazení tohoto portfolia.', 'error')
        return redirect(url_for('portfolio.upload'))

    # Zpracování CSV dat portfolia
    csv_data = BytesIO(portfolio.data)
    try:
        data = pd.read_csv(csv_data, encoding='utf-8')
    except pd.errors.EmptyDataError:
        flash('Soubor je prázdný nebo neplatný.', 'error')
        return redirect(url_for('portfolio.upload'))

    # Přidání aktuálních cen a výpočet hodnoty portfolia
    data = add_current_prices(data)
    portfolio_value = calculate_portfolio_value(data)

    # Výpočet realizovaného a nerealizovaného zisku
    realized_profit = calculate_realized_profit(data)
    total_invested = calculate_invested_amount(data)
    unrealized_profit = calculate_unrealized_profit(portfolio_value, total_invested)

    # Výpočet dividend
    dividend_results = calculate_dividend_cash(data)
    total_dividends = dividend_results['total_dividends']
    dividend_yield = dividend_results['dividend_yield']
    dividend_prediction_10_years = dividend_results['dividend_prediction_10_years']
    tax_on_dividends = dividend_results['tax_on_dividends']

    # Výpočet poplatků
    total_fees = calculate_fees(data)

    # Zaokrouhlení výsledků a sestavení slovníku výsledků
    results = {
        'portfolio_value': f"{round(portfolio_value, 2)} €",
        'realized_profit': f"{round(realized_profit, 2)} €",
        'unrealized_profit': f"{round(unrealized_profit, 2)} €",
        'total_dividends': f"{round(total_dividends, 2)} €",
        'dividend_yield': f"{round(dividend_yield, 2)} %",
        'dividend_prediction_10_years': f"{round(dividend_prediction_10_years, 2)} €",
        'tax_on_dividends': f"{round(tax_on_dividends, 2)} €",
        'total_fees': f"{round(total_fees, 2)} €",
        'invested': f"{round(total_invested, 2)} €"
    }

    return render_template('process.html', results=results, portfolio=portfolio)

# Route pro smazání portfolia
@portfolio_bp.route('/delete_portfolio/<int:portfolio_id>', methods=['POST'])
@login_required
def delete_portfolio(portfolio_id):
    portfolio_to_delete = Portfolio.query.get_or_404(portfolio_id)

    # Kontrola, zda portfolio patří přihlášenému uživateli
    if portfolio_to_delete.owner != current_user:
        flash('Nemáte oprávnění smazat toto portfolio.', 'error')
        return redirect(url_for('portfolio.upload'))

    db.session.delete(portfolio_to_delete)
    db.session.commit()
    flash('Portfolio bylo úspěšně smazáno.', 'success')
    return redirect(url_for('portfolio.upload'))
