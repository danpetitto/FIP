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

    return tickers_prices, portfolio_value, invested_amount, investment_duration, avg_monthly_investment, stock_info_list

# Funkce pro výpočet doby investování (v měsících)
def calculate_investment_duration(data):
    oldest_date_str = data['Datum'].min()
    try:
        oldest_date = parser.parse(oldest_date_str)
    except Exception as e:
        print(f"Chyba při parsování data: {e}")
        return 0

    current_date = datetime.now()
    duration_in_months = (current_date.year - oldest_date.year) * 12 + current_date.month - oldest_date.month

    return duration_in_months

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

    tickers_prices, portfolio_value, invested_amount, investment_duration, avg_monthly_investment, stock_info_list = calculate_portfolio_results(data)

    stock_labels = ['Technology', 'Healthcare', 'Finance']
    stock_percentages = [40, 30, 30]
    position_labels = ['TSLA', 'AAPL', 'AMZN']
    position_percentages = [50, 25, 25]

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
                           position_labels=position_labels,
                           position_percentages=position_percentages,
                           stock_info_list=stock_info_list,
                           investment_duration=investment_duration,
                           avg_monthly_investment=round(avg_monthly_investment, 2))

# Route pro zobrazení detailů investic
@portfolio_bp.route('/investment_details', methods=['GET'])
@login_required
def investment_details():
    invested_amount = session.get('invested_amount', 0)
    investment_duration = session.get('investment_duration', 0)

    if investment_duration > 0:
        avg_monthly_investment = invested_amount / investment_duration
    else:
        avg_monthly_investment = 0

    return render_template('investment_details.html', 
                           invested_amount=invested_amount,
                           investment_duration=investment_duration,
                           avg_monthly_investment=round(avg_monthly_investment, 2))

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
