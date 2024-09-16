from flask import Blueprint, render_template, request, redirect, url_for, flash
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

portfolio_bp = Blueprint('portfolio', __name__)

# Funkce pro výpočet výsledků portfolia (včetně načtení tickerů, cen a sektorů)
def calculate_portfolio_results(data):
    tickers_prices = {
        'ticker': {},
        'current_price': {},
        'sector': {}
    }

    # Získání tickerů, cen a odvětví pro každou jedinečnou ISIN
    unique_isins = data['ISIN'].unique()
    for isin in unique_isins:
        ticker = get_ticker_from_isin(isin)
        current_price = get_delayed_price_polygon(ticker)
        sector = get_sector_from_ticker(ticker)

        # Uložení do slovníku
        tickers_prices['ticker'][isin] = ticker
        tickers_prices['current_price'][isin] = current_price
        tickers_prices['sector'][isin] = sector

    # Výpočet hodnoty portfolia
    portfolio_value = calculate_portfolio_value(data)

    return tickers_prices, portfolio_value

# Route pro nahrávání nového portfolia
@portfolio_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
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

    # Získání tickerů, aktuálních cen a odvětví pro ISINy
    tickers_prices, portfolio_value = calculate_portfolio_results(data)

    # Agregace transakcí podle ISIN
    aggregated_data = data.groupby('ISIN')['Počet'].sum().reset_index()

    # Filtrování pouze otevřených pozic (kladný počet)
    open_positions = aggregated_data[aggregated_data['Počet'] > 0]

    # Seskupení podle odvětví a výpočet investovaných částek
    sector_investments = {}
    stock_info_list = []  # Pro zobrazení informací o jednotlivých akciích

    for _, row in open_positions.iterrows():
        isin = row['ISIN']
        ticker = tickers_prices['ticker'].get(isin)
        current_price = tickers_prices['current_price'].get(isin)
        sector = tickers_prices['sector'].get(isin)

        # Zobrazit akcie i v případě, že nemají cenu nebo ticker
        kupni_hodnota = data[data['ISIN'] == isin]['Cena'].mean() * row['Počet']
        aktualni_hodnota = current_price * row['Počet'] if current_price else 0  # Pokud chybí cena, nastavíme ji na 0
        profit = aktualni_hodnota - kupni_hodnota

        stock_info = {
            'ticker': ticker if ticker else 'Neznámý',  # Pokud není ticker, použije se 'Neznámý'
            'kupni_hodnota': kupni_hodnota,
            'aktualni_hodnota': aktualni_hodnota,
            'profit': profit,
            'sector': sector if sector else 'Neznámý'  # Pokud není sektor, použije se 'Neznámý'
        }
        stock_info_list.append(stock_info)

        # Přidání investice k příslušnému odvětví
        if sector in sector_investments:
            sector_investments[sector] += kupni_hodnota
        else:
            sector_investments[sector] = kupni_hodnota

    # Převedení investic podle odvětví do seznamu pro graf
    sector_labels = list(sector_investments.keys())
    sector_percentages = list(sector_investments.values())
    total_invested = sum(sector_percentages)
    
    if total_invested > 0:
        sector_percentages = [(x / total_invested) * 100 for x in sector_percentages]
    else:
        sector_percentages = [0 for _ in sector_percentages]

    # Ověření, že sektory a investice jsou platné (žádné None hodnoty)
    sector_labels = [label if label is not None else 'Neznámé' for label in sector_labels]
    sector_percentages = [percentage if percentage is not None else 0 for percentage in sector_percentages]

    # Předání výsledků do šablony
    results = {
        'portfolio_value': f"{round(portfolio_value, 2)} €",
        'realized_profit': f"{round(calculate_realized_profit(data), 2)} €",
        'unrealized_profit': f"{round(calculate_unrealized_profit(portfolio_value, calculate_invested_amount(data)), 2)} €",
        'total_dividends': f"{round(calculate_dividend_cash(data)['total_dividends'], 2)} €",
        'total_fees': f"{round(calculate_fees(data), 2)} €",
        'invested': f"{round(calculate_invested_amount(data), 2)} €"
    }

    return render_template('process.html',
                           results=results,
                           stock_info_list=stock_info_list,
                           stock_labels=sector_labels or [],  # Prázdný seznam pokud je None
                           stock_percentages=sector_percentages or [],  # Prázdný seznam pokud je None
                           portfolio=portfolio)

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

