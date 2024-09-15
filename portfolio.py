from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import Portfolio, db
from finance import (
    add_current_prices, calculate_portfolio_value, calculate_realized_profit, 
    calculate_unrealized_profit, calculate_invested_amount, calculate_dividend_cash, 
    calculate_fees
)
from portfolio_analysis import (
    get_ticker_from_isin, get_delayed_price_polygon
)
import pandas as pd
from io import BytesIO
import time

portfolio_bp = Blueprint('portfolio', __name__)

# Route pro nahrávání nového portfolia
@portfolio_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        # Diagnostika: Výpis obsahu request.form a request.files
        print("Form Data: ", request.form)
        print("File Data: ", request.files)

        # Získání souboru a názvu portfolia z formuláře
        file = request.files.get('file')
        portfolio_name = request.form.get('portfolio_name')

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
            name=portfolio_name,
            filename=file.filename,
            data=file.read(),
            user=current_user
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
    if portfolio.user != current_user:
        flash('Nemáte oprávnění k zobrazení tohoto portfolia.', 'error')
        return redirect(url_for('portfolio.upload'))

    # Zpracování CSV dat portfolia
    csv_data = BytesIO(portfolio.data)
    try:
        data = pd.read_csv(csv_data, encoding='utf-8')
    except pd.errors.EmptyDataError:
        flash('Soubor je prázdný nebo neplatný.', 'error')
        return redirect(url_for('portfolio.upload'))

    # **Výpočty pro "Výsledky portfolia" pomocí funkcí z finance.py**
    # Přidání aktuálních cen
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

    # **Vytvoření slovníku s výsledky portfolia**
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

    # **Zpracování pro "Informace o akciích" pomocí funkcí z portfolio_analysis.py**
    # Filtrujeme pouze akcie, které mají kladný počet (otevřené pozice)
    open_positions = data[data['Počet'] > 0]

    # Získání informací o akciích (ticker, kupní hodnota, aktuální hodnota, profit)
    stock_info_list = []
    for _, row in open_positions.iterrows():
        stock_info = {
            'ticker': row['Ticker'],
            'kupni_hodnota': row['Cena'] * row['Počet'],
            'aktualni_hodnota': row['Aktuální Cena'] * row['Počet'],
            'profit': (row['Aktuální Cena'] * row['Počet']) - (row['Cena'] * row['Počet'])
        }
        stock_info_list.append(stock_info)

    # **Předání výsledků do šablony**
    return render_template('process.html', results=results, stock_info_list=stock_info_list, portfolio=portfolio)

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

