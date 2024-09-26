from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_required, current_user
from models import Portfolio, db
from finance import (
    add_current_prices, calculate_portfolio_value, calculate_realized_profit,
    calculate_unrealized_profit, calculate_invested_amount, calculate_dividend_cash,
    calculate_fees
)
from portfolio_analysis import (
    get_ticker_from_isin, get_delayed_price_polygon, get_sector_from_ticker
)
import pandas as pd
from io import BytesIO
from datetime import datetime
from dateutil import parser
from investment_history import calculate_investment_history  # Importuje funkce z investment_history.py

portfolio_bp = Blueprint('portfolio', __name__)

# Funkce pro výpočet výsledků portfolia (včetně načtení tickerů, cen a sektorů)
def calculate_portfolio_results(data):
    tickers_prices = {
        'ticker': {},
        'current_price': {},
        'sector': {}
    }

    stock_info_list = []

    # Získání tickerů, cen a odvětví pro každou jedinečnou ISIN
    unique_isins = data['ISIN'].unique()
    for isin in unique_isins:
        ticker = get_ticker_from_isin(isin)
        current_price = get_delayed_price_polygon(ticker)
        sector = get_sector_from_ticker(ticker)

        tickers_prices['ticker'][isin] = ticker
        tickers_prices['current_price'][isin] = current_price
        tickers_prices['sector'][isin] = sector

        # Výpočet kupní hodnoty, aktuální hodnoty a profitu pro každou akcii
        total_shares = data.loc[data['ISIN'] == isin, 'Počet'].sum()
        purchase_price = data.loc[data['ISIN'] == isin, 'Cena'].mean()
        purchase_value = total_shares * purchase_price
        current_value = total_shares * current_price if current_price else 0
        profit = current_value - purchase_value

        if ticker and current_value > 0:
            stock_info_list.append({
                'ticker': ticker,
                'kupni_hodnota': round(purchase_value, 2),
                'aktualni_hodnota': round(current_value, 2),
                'profit': round(profit, 2)
            })

    portfolio_value = calculate_portfolio_value(data)
    invested_amount = calculate_invested_amount(data)
    investment_duration = calculate_investment_duration(data)

    if investment_duration > 0:
        avg_monthly_investment = invested_amount / investment_duration
    else:
        avg_monthly_investment = 0

    # Převod investic podle jednotlivých pozic na procenta pro graf jednotlivých akcií
    total_invested_positions = sum([info['kupni_hodnota'] for info in stock_info_list])
    if total_invested_positions > 0:
        position_percentages = [(info['kupni_hodnota'] / total_invested_positions) * 100 for info in stock_info_list]
        position_labels = [info['ticker'] for info in stock_info_list]  # Přidáme tickery pro graf
    else:
        position_percentages = []
        position_labels = []

    # Návratové hodnoty včetně přidaných názvů akcií pro graf
    return tickers_prices, portfolio_value, invested_amount, investment_duration, avg_monthly_investment, stock_info_list, position_percentages, position_labels

# Funkce pro výpočet doby investování (v měsících) na základě prvního záznamu investice
def calculate_investment_duration(data):
    # Převod sloupce Datum na datetime, pokud ještě nebyl převeden
    data['Datum'] = pd.to_datetime(data['Datum'], dayfirst=True, errors='coerce')

    # Validace dat
    if data['Datum'].isnull().any():
        raise ValueError("Některá data ve sloupci 'Datum' nejsou validní.")

    # Najdeme nejstarší datum v datech - začátek investice
    oldest_date = data['Datum'].min()

    # Získáme aktuální datum
    current_date = datetime.now()

    # Výpočet délky investice v měsících
    # Pokud je aktuální den větší nebo roven dni nejstarší transakce, přidáme plný měsíc navíc
    duration_in_months = (current_date.year - oldest_date.year) * 12 + current_date.month - oldest_date.month
    if current_date.day >= oldest_date.day:
        duration_in_months += 1  # Přičteme 1, pokud je aktuální den větší nebo stejný jako den investice

    return duration_in_months

# Příklad použití s testovacími daty
data = pd.DataFrame({
    'Datum': ['2022-09-15', '2022-10-10', '2023-08-25', '2024-07-05']  # Testovací data
})

# Volání funkce pro výpočet délky investování
duration = calculate_investment_duration(data)
print(f"Délka investování: {duration} měsíců")

def get_price_for_month(ticker, date):
    """Získání ceny ke konci měsíce, pokusí se vrátit cenu z předchozího obchodního dne, pokud je 404."""
    price = get_delayed_price_polygon(ticker, date.strftime('%Y-%m-%d'))

    if price is None:
        # Pokud se zobrazí chyba 404, zkusíme předchozí den
        attempts = 5  # Zkusíme získat cenu z 5 předchozích dní
        while attempts > 0:
            date -= timedelta(days=1)
            price = get_delayed_price_polygon(ticker, date.strftime('%Y-%m-%d'))
            if price is not None:
                break
            attempts -= 1
    return price

def get_price_for_month(ticker, date):
    """Získání ceny ke konci měsíce, pokusí se vrátit cenu z předchozího obchodního dne, pokud je 404."""
    price = get_delayed_price_polygon(ticker, date.strftime('%Y-%m-%d'))

    if price is None:
        # Pokud se zobrazí chyba 404, zkusíme předchozí den
        attempts = 5  # Zkusíme získat cenu z 5 předchozích dní
        while attempts > 0:
            date -= timedelta(days=1)
            price = get_delayed_price_polygon(ticker, date.strftime('%Y-%m-%d'))
            if price is not None:
                break
            attempts -= 1
    return price

# Route pro nahrávání nového portfolia
@portfolio_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        file = request.files.get('file')
        portfolio_name = request.form.get('portfolio_name')

        if not file or not portfolio_name:
            flash('Musíte nahrát soubor a zadat název portfolia.', 'error')
            return redirect(url_for('portfolio.upload'))

        if not file.filename.endswith('.csv'):
            flash('Prosím, nahrajte soubor ve formátu CSV.', 'error')
            return redirect(url_for('portfolio.upload'))

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

    user_portfolios = Portfolio.query.filter_by(user_id=current_user.id).all()
    return render_template('upload.html', portfolios=user_portfolios)

# Route pro výběr portfolia
@portfolio_bp.route('/select_portfolio/<int:portfolio_id>', methods=['GET'])
@login_required
def select_portfolio(portfolio_id):
    portfolio = Portfolio.query.get_or_404(portfolio_id)

    if portfolio.user != current_user:
        flash('Nemáte oprávnění k zobrazení tohoto portfolia.', 'error')
        return redirect(url_for('portfolio.upload'))

    csv_data = BytesIO(portfolio.data)
    try:
        data = pd.read_csv(csv_data, encoding='utf-8')
    except pd.errors.EmptyDataError:
        flash('Soubor je prázdný nebo neplatný.', 'error')
        return redirect(url_for('portfolio.upload'))

    tickers_prices, portfolio_value, invested_amount, investment_duration, avg_monthly_investment, stock_info_list, position_percentages, position_labels = calculate_portfolio_results(data)

    stock_labels = ['Technology', 'Healthcare', 'Finance']
    stock_percentages = [40, 30, 30]

    results = {
        'portfolio_value': f"{round(portfolio_value, 2)} €",
        'realized_profit': f"{round(calculate_realized_profit(data), 2)} €",
        'unrealized_profit': f"{round(calculate_unrealized_profit(portfolio_value, invested_amount), 2)} €",
        'total_dividends': f"{round(calculate_dividend_cash(data)['total_dividends'], 2)} €",
        'total_fees': f"{round(calculate_fees(data), 2)} €",
        'invested': f"{round(invested_amount, 2)} €"
    }

    session['invested_amount'] = invested_amount
    session['investment_duration'] = investment_duration

    return render_template('process.html',
                           results=results,
                           stock_labels=stock_labels,
                           stock_percentages=stock_percentages,
                           position_labels=position_labels,  # Předání názvů akcií pro graf
                           position_percentages=position_percentages,  # Předání procent pro graf
                           stock_info_list=stock_info_list,
                           investment_duration=investment_duration,
                           avg_monthly_investment=round(avg_monthly_investment, 2))

# Route pro zobrazení detailů investic
@portfolio_bp.route('/investment_details', methods=['GET'])
@login_required
def investment_details():
    # Získání investované částky a doby investování ze session nebo vypočítané hodnoty
    invested_amount = session.get('invested_amount', 1519.96)  # Příkladová hodnota
    investment_duration = session.get('investment_duration', 19)  # Příkladová hodnota

    if investment_duration > 0:
        avg_monthly_investment = invested_amount / investment_duration
    else:
        avg_monthly_investment = 0

    # Získáme portfolia a jejich data
    portfolio = Portfolio.query.filter_by(user_id=current_user.id).first()
    csv_data = BytesIO(portfolio.data)
    data = pd.read_csv(csv_data, encoding='utf-8')

    # Použijeme funkci pro výpočet historie investic
    investment_history, yearly_totals = calculate_investment_history(data)

    return render_template('investment_details.html', 
                           invested_amount=round(invested_amount, 2),
                           investment_duration=investment_duration,
                           avg_monthly_investment=round(avg_monthly_investment, 2),
                           investment_history=investment_history,
                           yearly_totals=yearly_totals)

# Route pro smazání portfolia
@portfolio_bp.route('/delete_portfolio/<int:portfolio_id>', methods=['POST'])
@login_required
def delete_portfolio(portfolio_id):
    portfolio_to_delete = Portfolio.query.get_or_404(portfolio_id)

    if portfolio_to_delete.owner != current_user:
        flash('Nemáte oprávnění smazat toto portfolio.', 'error')
        return redirect(url_for('portfolio.upload'))

    db.session.delete(portfolio_to_delete)
    db.session.commit()
    flash('Portfolio bylo úspěšně smazáno.', 'success')
    return redirect(url_for('portfolio.upload'))
