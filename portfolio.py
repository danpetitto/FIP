from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_required, current_user
from models import Portfolio, db, Trade
from io import StringIO
from finance import (
    add_current_prices, calculate_portfolio_value, calculate_realized_profit,
    calculate_unrealized_profit, calculate_invested_amount, calculate_dividend_cash,
    calculate_fees, get_czech_inflation_2024, calculate_portfolio_with_inflation
)
from portfolio_analysis import (
    get_ticker_from_isin, get_delayed_price_polygon, get_sector_from_ticker
)
import pandas as pd
from io import BytesIO
from datetime import datetime
from dateutil import parser
from investment_history import calculate_investment_history  # Importuje funkce z investment_history.py
from datetime import timedelta
from finance import calculate_unrealized_profit_percentage, calculate_realized_profit_percentage, calculate_fees_percentage, calculate_forex_impact_percentage

portfolio_bp = Blueprint('portfolio', __name__)

# Funkce pro výpočet výsledků portfolia (včetně načtení tickerů, cen a sektorů)
def calculate_calculate_dividend_cash(data):
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

from io import StringIO  # Import StringIO z modulu io

from datetime import datetime

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

        # Přiřazení správného zdroje na základě souboru
        if 'XTB' in file.filename.upper():
            source = 'XTB'
        elif 'DEGIRO' in file.filename.upper():
            source = 'DEGIRO'
        else:
            source = 'UNKNOWN'

        # Načtení obsahu souboru jako bytes
        try:
            file_data = file.read()  # Zůstává jako bytes
            data = pd.read_csv(BytesIO(file_data), encoding='utf-8')

            # Nastavení hodnoty 'date' na základě dat z CSV
            if 'Datum' in data.columns:
                date = pd.to_datetime(data['Datum'], dayfirst=True, errors='coerce').min()
            else:
                date = datetime.utcnow().date()  # Výchozí na aktuální datum, pokud není 'Datum' ve sloupci

            if pd.isnull(date):
                date = datetime.utcnow().date()  # Výchozí na aktuální datum, pokud převod selže

        except Exception as e:
            flash(f'Chyba při čtení souboru: {str(e)}', 'error')
            return redirect(url_for('portfolio.upload'))

        # Vytvoření nového portfolia s načtenými daty
        new_portfolio = Portfolio(
            name=portfolio_name,
            filename=file.filename,
            source=source,
            data=file_data,  
            user_id=current_user.id,
            date=date  # Nastavuje hodnotu date
        )
        db.session.add(new_portfolio)
        db.session.commit()

        flash('Portfolio bylo úspěšně nahráno.', 'success')
        return redirect(url_for('portfolio.upload'))

    # Načtení uživatelových portfolií pro zobrazení
    user_portfolios = Portfolio.query.filter_by(user_id=current_user.id).all()
    return render_template('upload.html', portfolios=user_portfolios)

import re

# Funkce pro získání ISIN pomocí OpenFIGI na základě symbolu
def get_isin_from_symbol(symbol):
    headers = {
        'Content-Type': 'application/json',
        'X-OPENFIGI-APIKEY': os.getenv('OPENFIGI_API_KEY')  # Použití klíče z prostředí
    }
    payload = [{
        "idType": "TICKER",
        "idValue": symbol,
        "exchCode": "US"  # Specifikace burzy (volitelná)
    }]
    
    try:
        response = requests.post('https://api.openfigi.com/v3/mapping', headers=headers, json=payload)
        if response.status_code == 200:
            figi_data = response.json()
            
            # Ověření, zda odpověď obsahuje potřebné informace
            if isinstance(figi_data, list) and len(figi_data) > 0:
                if 'data' in figi_data[0] and len(figi_data[0]['data']) > 0:
                    return figi_data[0]['data'][0].get('figi')  # Vrácení ISIN, pokud existuje
                
            # Pokud odpověď neobsahuje data
            print(f"OpenFIGI API nevrátila žádná data pro symbol {symbol}. Odpověď: {figi_data}")
        else:
            print(f"Chyba při volání OpenFIGI API pro symbol {symbol}: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Chyba při volání OpenFIGI API pro symbol {symbol}: {str(e)}")
    
    return None

# Funkce pro transformaci XTB dat na formát DEGIRO
def transform_xtb_to_degiro_structure(xtb_df):
    # Vytvoření nové tabulky s požadovanými sloupci DEGIRO
    transformed_data = pd.DataFrame()

    # Rozdělení sloupce "Time" na "Datum" a "Čas"
    if 'Time' in xtb_df.columns:
        transformed_data['Datum'] = pd.to_datetime(xtb_df['Time']).dt.date
        transformed_data['Čas'] = pd.to_datetime(xtb_df['Time']).dt.time
    else:
        raise KeyError("Sloupec 'Time' nebyl nalezen v XTB souboru.")

    # Sloupec "Produkt" odpovídá sloupci "Symbol" z XTB
    if 'Symbol' in xtb_df.columns:
        transformed_data['Produkt'] = xtb_df['Symbol']
    else:
        raise KeyError("Sloupec 'Symbol' nebyl nalezen v XTB souboru.")

    # Získání ISIN pomocí OpenFIGI API
    transformed_data['ISIN'] = xtb_df['Symbol'].apply(get_isin_from_symbol)

    # Přidáme prázdné sloupce "Reference", "Venue", protože tyto informace nejsou v XTB souboru
    transformed_data['Reference'] = None
    transformed_data['Venue'] = None

    # Extrahujeme "Počet" a "Cena" z "Comment"
    if 'Comment' in xtb_df.columns:
        def extract_count_and_price(comment):
            match = re.search(r'BUY ([\d.]+) @ ([\d.]+)', comment)
            if match:
                return float(match.group(1)), float(match.group(2))
            return None, None

        transformed_data[['Počet', 'Cena']] = xtb_df['Comment'].apply(lambda x: pd.Series(extract_count_and_price(x)))
    else:
        raise KeyError("Sloupec 'Comment' nebyl nalezen v XTB souboru.")

    # Sloupec "Hodnota v domácí měně" odpovídá sloupci "Amount" z XTB
    if 'Amount' in xtb_df.columns:
        transformed_data['Hodnota v domácí měně'] = xtb_df['Amount']
    else:
        raise KeyError("Sloupec 'Amount' nebyl nalezen v XTB souboru.")

    # Sloupec "Hodnota" nastavíme na stejný jako "Amount"
    transformed_data['Hodnota'] = transformed_data['Hodnota v domácí měně']

    # Přidáme prázdné sloupce pro "Směnný kurz", "Transaction and/or third"
    transformed_data['Směnný kurz'] = None
    transformed_data['Transaction and/or third'] = None

    # Sloupec "Celkem" bude mít stejnou hodnotu jako "Hodnota"
    transformed_data['Celkem'] = transformed_data['Hodnota']

    return transformed_data

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from datetime import timedelta

from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from io import BytesIO
import pandas as pd
from datetime import datetime
from stock_info import get_stock_info  # Import funkce get_stock_info ze stock_info.py
from finance import get_ticker_from_isin  # Z finance.py

@portfolio_bp.route('/select_portfolio/<int:portfolio_id>', methods=['GET'])
@login_required
def select_portfolio(portfolio_id):
    portfolio = Portfolio.query.get_or_404(portfolio_id)

    if portfolio.user != current_user:
        flash('Nemáte oprávnění k zobrazení tohoto portfolia.', 'error')
        return redirect(url_for('portfolio.upload'))
    
     # Inicializace proměnných s výchozími hodnotami
    country_labels = []
    country_percentages = []
    sector_labels = []
    sector_percentages = []

    # Pokud nejsou výsledky zastaralé a jsou již vypočítány, použij uložené hodnoty
    if not portfolio.needs_recalculation() and portfolio.calculated_results:
        results = portfolio.calculated_results
        stock_info_list = results.get("stock_info_list", [])
        position_labels = results.get("position_labels", [])
        position_percentages = results.get("position_percentages", [])
        portfolio_dates = results.get("portfolio_dates", [])
        portfolio_values = results.get("portfolio_values", [])
        investment_duration = results.get("investment_duration")
        country_labels = results.get("country_labels", [])
        country_percentages = results.get("country_percentages", [])
        sector_labels = results.get("sector_labels", [])
        sector_percentages = results.get("sector_percentages", [])
    else:
        # Čtení a zpracování dat z CSV
        csv_data = BytesIO(portfolio.data)
        try:
            data = pd.read_csv(csv_data, encoding='utf-8')
        except pd.errors.EmptyDataError:
            flash('Soubor je prázdný nebo neplatný.', 'error')
            return redirect(url_for('portfolio.upload'))

        # Transformace formátu pro XTB, pokud je potřeba
        if 'Time' in data.columns:
            data = transform_xtb_to_degiro_structure(data)
        elif 'Datum' not in data.columns:
            flash("Neplatný formát souboru. Očekáván je sloupec 'Datum' nebo 'Time'.", 'error')
            return redirect(url_for('portfolio.upload'))
        
        # Převod a čištění datumu
        data['Datum'] = pd.to_datetime(data['Datum'], format='%d-%m-%Y', errors='coerce')
        data = data.dropna(subset=['Datum'])

        # Výpočet hodnoty portfolia v čase
        data = data.sort_values(by='Datum')
        open_positions = data[data['Počet'] > 0]
        open_positions['Hodnota pozice'] = open_positions['Počet'] * open_positions['Cena']

        # Kumulativní součet hodnoty portfolia v čase
        portfolio_value_over_time = open_positions.groupby('Datum')['Hodnota pozice'].sum().cumsum().reset_index()

        # Převod na seznamy pro JavaScript grafy
        portfolio_dates = portfolio_value_over_time['Datum'].dt.strftime('%Y-%m-%d').tolist()
        portfolio_values = portfolio_value_over_time['Hodnota pozice'].tolist()

        # Výpočty pro portfolio (včetně dividend a měnových efektů)
        tickers_prices, portfolio_value, invested_amount, investment_duration, avg_monthly_investment, stock_info_list, position_percentages, position_labels = calculate_calculate_dividend_cash(data)
        forex_results, total_forex_impact_czk = calculate_forex_profit_loss(data)
        dividend_results = calculate_dividend_cash(data)
        realized_profit = calculate_realized_profit(data)
        unrealized_profit = calculate_unrealized_profit(portfolio_value, invested_amount)
        total_fees = calculate_fees(data)

        # Výpočty procentuálních hodnot
        unrealized_profit_percentage = calculate_unrealized_profit_percentage(unrealized_profit, portfolio_value)
        realized_profit_percentage = calculate_realized_profit_percentage(realized_profit, portfolio_value)
        fees_percentage = calculate_fees_percentage(total_fees, portfolio_value)
        forex_impact_percentage = calculate_forex_impact_percentage(total_forex_impact_czk, portfolio_value)

        # Výpočet inflace
        inflation_rate = get_czech_inflation_2024()
        portfolio_with_inflation = calculate_portfolio_with_inflation(portfolio_value, inflation_rate)

        # Přidání sektoru pro každou otevřenou pozici
        open_positions['Sektor'] = open_positions['ISIN'].apply(lambda isin: get_sector_from_isin(isin))

        # Skupinování podle sektorů a výpočet celkové hodnoty každého sektoru
        sector_allocation = open_positions.groupby('Sektor')['Hodnota pozice'].sum().reset_index()

        # Výpočet alokace podle akcií
        stock_labels, stock_percentages = calculate_stock_allocation(data)

       # Výpočet alokace podle zemí
        country_labels, country_percentages = calculate_country_allocation(data)

        # Výběr top investic podle profitu
        top_investments = get_top_investments(stock_info_list)

         # Výpočet procentuálního podílu každého sektoru
        total_value = open_positions['Hodnota pozice'].sum()
        if total_value > 0:
            sector_allocation['Procentuální podíl'] = (sector_allocation['Hodnota pozice'] / total_value) * 100
        else:
            sector_allocation['Procentuální podíl'] = 0

        # Převod na seznamy pro použití v grafu
        sector_labels = sector_allocation['Sektor'].tolist()
        sector_percentages = sector_allocation['Procentuální podíl'].tolist()

        # Debug výpis pro kontrolu dat pro sektorový graf
        print(f"DEBUG: sector_labels: {sector_labels}")
        print(f"DEBUG: sector_percentages: {sector_percentages}")

        # Uložení výsledků
        results = {
            'portfolio_value': f"{round(portfolio_value, 2)} €",
            'portfolio_with_inflation': f"{round(portfolio_with_inflation, 2)} €",
            'inflation_rate': f"{inflation_rate if inflation_rate else 'Neznámá'} %",
            'realized_profit': f"{round(realized_profit, 2)} €",
            'realized_profit_percentage': f"{realized_profit_percentage} %",
            'unrealized_profit': f"{round(unrealized_profit, 2)} €",
            'unrealized_profit_percentage': f"{unrealized_profit_percentage} %",
            'total_dividends': f"{round(dividend_results['total_dividends'], 2)} €",
            'dividend_yield': f"{round(dividend_results['dividend_yield'], 2)} %",
            'investment_duration': investment_duration,
            'dividend_prediction_10_years': f"{round(dividend_results['dividend_prediction_10_years'], 2)} €",
            'tax_on_dividends': f"{round(dividend_results['tax_on_dividends'], 2)} €",
            'invested': f"{round(invested_amount, 2)} €",
            'total_fees': f"{round(total_fees, 2)} €",
            'fees_percentage': f"{fees_percentage} %",
            'forex_impact_czk': f"{round(total_forex_impact_czk, 2)} CZK",
            'forex_impact_percentage': f"{forex_impact_percentage} %",
            'forex_impact_eur': f"{round(total_forex_impact_czk / get_current_fx_rate('CZK'), 2)} €",
            # Uložení grafových a seznamových dat
            'stock_info_list': stock_info_list,
            'position_labels': position_labels,
            'position_percentages': position_percentages,
            'portfolio_dates': portfolio_dates,
            'portfolio_values': portfolio_values,
            'top_investments': top_investments,
            'stock_labels': stock_labels,
            'stock_percentages': stock_percentages,
            'country_labels': country_labels,
            'country_percentages': country_percentages,
            'sector_labels': sector_labels,
            'sector_percentages': sector_percentages
        }

        # Uložení do databáze
        portfolio.calculated_results = results
        portfolio.last_calculated_at = datetime.utcnow()
        db.session.commit()

    ai_commentary = generate_ai_commentary(results, stock_info_list)

    return render_template(
        'process.html',
        results=results,
        portfolio=portfolio,
        stock_labels=position_labels,
        stock_percentages=position_percentages,
        stock_info_list=stock_info_list,
        investment_duration=investment_duration,
        ai_commentary=ai_commentary,
        portfolio_dates=portfolio_dates,
        portfolio_values=portfolio_values,
        country_labels=country_labels,  # Přidáno
        country_percentages=country_percentages,
        sector_labels=sector_labels,
        sector_percentages=sector_percentages
    )

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

from flask import session, request, redirect, flash, url_for, render_template
from flask_login import login_required, current_user
from models import db, Portfolio, Trade
from datetime import datetime
from manual import store_manual_trade  # Importujeme funkci z manual.py

from datetime import datetime
import math

@portfolio_bp.route('/trades/add/<int:portfolio_id>', methods=['POST'])
@login_required
def add_trade(portfolio_id):
    portfolio = Portfolio.query.get_or_404(portfolio_id)

    if portfolio.user != current_user:
        flash('Nemáte oprávnění k zobrazení tohoto portfolia.', 'error')
        return redirect(url_for('portfolio.upload'))

    # Načtení dat z formuláře
    datum = request.form.get('datum')
    typ_obchodu = request.form.get('typ')
    ticker = request.form.get('ticker')
    cena = float(request.form.get('cena', 0)) or 0.0  # Pokud cena je NaN, nastavíme ji na 0
    pocet = int(request.form.get('pocet', 1)) or 0  # Pokud pocet je NaN, nastavíme jej na 0
    poplatky = float(request.form.get('poplatky', 0)) or 0.0  # Pokud poplatky jsou NaN, nastavíme je na 0

    # Vypočítáme hodnotu
    hodnota = cena * pocet

    # Ošetření případných hodnot NaN před uložením
    if math.isnan(cena):
        cena = 0.0
    if math.isnan(pocet):
        pocet = 0
    if math.isnan(hodnota):
        hodnota = 0.0
    if math.isnan(poplatky):
        poplatky = 0.0

    # Ošetření formátu data
    try:
        # Nejprve zkusíme formát '%d-%m-%Y'
        datum_obj = datetime.strptime(datum, '%d-%m-%Y')
    except ValueError:
        try:
            # Pokud to selže, zkusíme '%Y-%m-%d'
            datum_obj = datetime.strptime(datum, '%Y-%m-%d')
        except ValueError:
            # Pokud ani to nefunguje, vyhodíme chybu
            flash('Datum má neplatný formát.', 'error')
            return redirect(url_for('portfolio.upload'))

    # Vytvoření nové transakce a uložení do databáze
    novy_obchod = Trade(
        portfolio_id=portfolio_id,
        datum=datum_obj,
        typ_obchodu=typ_obchodu,
        ticker=ticker,
        cena=cena,
        pocet=pocet,
        hodnota=hodnota,
        poplatky=poplatky
    )
    
    db.session.add(novy_obchod)
    db.session.commit()

    # Předání nové transakce do manual.py pro další zpracování
    store_manual_trade(portfolio_id, ticker, datum, typ_obchodu, cena, pocet, hodnota, poplatky)

    flash('Obchod byl úspěšně přidán.', 'success')
    return redirect(url_for('portfolio.trades', portfolio_id=portfolio_id))

# Route pro zobrazení obchodů
@portfolio_bp.route('/trades/<int:portfolio_id>', methods=['GET'])
@login_required
def trades(portfolio_id):
    portfolio = Portfolio.query.get_or_404(portfolio_id)

    if portfolio.user != current_user:
        flash('Nemáte oprávnění k zobrazení tohoto portfolia.', 'error')
        return redirect(url_for('portfolio.upload'))

    # Načtení obchodů z databáze
    trades_data_from_db = Trade.query.filter_by(portfolio_id=portfolio_id).order_by(Trade.datum.desc()).all()

    # Načtení dat z CSV souboru v portfoliu (pokud existuje)
    csv_data = BytesIO(portfolio.data)
    try:
        data = pd.read_csv(csv_data, encoding='utf-8')
    except pd.errors.EmptyDataError:
        flash('Soubor je prázdný nebo neplatný.', 'error')
        return redirect(url_for('portfolio.upload'))

    if 'ISIN' in data.columns:
        data['Ticker'] = data['ISIN'].apply(get_ticker_from_isin)
    else:
        flash('Soubor neobsahuje sloupec "ISIN".', 'error')
        return redirect(url_for('portfolio.upload'))

    # Převod CSV na seznam obchodů
    if 'Počet' in data.columns and 'Cena' in data.columns:
        data['Typ obchodu'] = data['Počet'].apply(lambda x: 'nákup' if x > 0 else 'prodej')
        data['Hodnota'] = data['Cena'] * abs(data['Počet'])

        if 'Transaction and/or third' not in data.columns:
            data['Transaction and/or third'] = 0

        # Přidáme počet do slovníků
        trades_data_from_csv = data[['Datum', 'Typ obchodu', 'Ticker', 'Cena', 'Počet', 'Hodnota', 'Transaction and/or third']].to_dict(orient='records')

        # Uložení každého obchodu z CSV do databáze
        for trade in trades_data_from_csv:
            # Ošetření hodnot NaN z CSV
            cena = float(trade['Cena']) if not math.isnan(trade['Cena']) else 0.0
            pocet = int(trade['Počet']) if not math.isnan(trade['Počet']) else 0
            hodnota = float(trade['Hodnota']) if not math.isnan(trade['Hodnota']) else 0.0
            poplatky = float(trade['Transaction and/or third']) if not math.isnan(trade['Transaction and/or third']) else 0.0

            # Vytvoření nové transakce
            novy_obchod = Trade(
                portfolio_id=portfolio_id,
                datum=datetime.strptime(trade['Datum'], '%d-%m-%Y'),  # Parsování datumu
                typ_obchodu=trade['Typ obchodu'],
                ticker=trade['Ticker'],
                cena=cena,
                pocet=pocet,
                hodnota=hodnota,
                poplatky=poplatky
            )
            db.session.add(novy_obchod)
        
        # Uložíme všechny nové transakce do databáze
        db.session.commit()

    else:
        flash('Soubor neobsahuje potřebné sloupce "Počet" nebo "Cena".', 'error')
        trades_data_from_csv = []

    # Spojení obchodů z CSV a z databáze
    trades_data_combined = trades_data_from_csv + [{
        'Datum': trade.datum.strftime('%d-%m-%Y'),
        'Typ obchodu': trade.typ_obchodu,
        'Ticker': trade.ticker,
        'Cena': trade.cena,
        'Počet': trade.pocet,
        'Hodnota': trade.hodnota,
        'Transaction and/or third': trade.poplatky
    } for trade in trades_data_from_db]

    # Zobrazení obchodů ve šabloně
    return render_template('trades.html', trades=trades_data_combined, portfolio_id=portfolio_id)

@portfolio_bp.route('/trades/delete/<int:trade_id>/<int:portfolio_id>', methods=['POST'])
@login_required
def delete_trade(trade_id, portfolio_id):
    # Najdeme transakci podle ID
    trade_to_delete = Trade.query.get_or_404(trade_id)
    
    # Ověříme, zda uživatel má oprávnění k portfoliu, ke kterému transakce patří
    portfolio = Portfolio.query.get_or_404(portfolio_id)
    
    if portfolio.user != current_user:
        flash('Nemáte oprávnění smazat tento obchod.', 'error')
        return redirect(url_for('portfolio.trades', portfolio_id=portfolio_id))

    # Ověříme, zda transakce patří k portfoliu
    if trade_to_delete.portfolio_id != portfolio_id:
        flash('Transakce nepatří k tomuto portfoliu.', 'error')
        return redirect(url_for('portfolio.trades', portfolio_id=portfolio_id))

    # Smazání transakce
    db.session.delete(trade_to_delete)
    db.session.commit()

    flash('Obchod byl úspěšně smazán.', 'success')
    return redirect(url_for('portfolio.trades', portfolio_id=portfolio_id))

import requests
from dotenv import load_dotenv
import os

# Načtení proměnných z .env souboru
load_dotenv()

# Definice API klíče
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")

from datetime import datetime

from datetime import datetime
import requests
import pandas as pd
from flask import render_template, flash, redirect, url_for
from flask_login import current_user, login_required
from io import BytesIO
from collections import defaultdict

def get_filtered_dividend_calendar(data):
    dividend_calendar = defaultdict(lambda: defaultdict(float))

    portfolio_start_date = data['Datum'].min()
    unique_isins = data['ISIN'].unique()
    
    for isin in unique_isins:
        ticker = get_ticker_from_isin(isin)
        if not ticker:
            continue
        
        stock_transactions = data[data['ISIN'] == isin].sort_values(by='Datum')
        holding = 0
        start_date = portfolio_start_date
        end_date = None
        
        for _, transaction in stock_transactions.iterrows():
            date = transaction['Datum']
            quantity = transaction['Počet']

            if quantity > 0:
                if holding == 0:
                    start_date = max(portfolio_start_date, date)
                holding += quantity
            elif quantity < 0:
                holding += quantity
                if holding == 0:
                    end_date = date
                    add_dividends_to_calendar(dividend_calendar, ticker, isin, start_date, end_date, portfolio_start_date, data)
                    start_date = None
        
        if holding > 0:
            add_dividends_to_calendar(dividend_calendar, ticker, isin, start_date, None, portfolio_start_date, data)
    
    return dict(dividend_calendar)

def add_dividends_to_calendar(dividend_calendar, ticker, isin, start_date, end_date, portfolio_start_date, data):
    dividends = get_dividend_data_polygon(ticker, portfolio_start_date)
    if dividends:
        for dividend in dividends:
            ex_date = dividend.get('exDate')
            amount_per_share = dividend.get('amount')
            
            if start_date and (ex_date >= start_date) and (not end_date or ex_date <= end_date):
                relevant_transactions = data[(data['ISIN'] == isin) & (data['Datum'] <= ex_date)]
                shares_held = relevant_transactions['Počet'].sum()
                total_amount = amount_per_share * shares_held

                ex_date_obj = datetime.strptime(ex_date, "%Y-%m-%d")
                year = ex_date_obj.year
                month = ex_date_obj.strftime('%B')  # Get the month as string (e.g., 'January')
                
                dividend_calendar[year][month] += total_amount

# Funkce pro získání dividendových dat s omezením od data zahájení portfolia
def get_dividend_data_polygon(ticker, start_date):
    if not ticker:
        return None
    try:
        # Format the start_date correctly for API compatibility
        start_year = datetime.strptime(start_date, "%Y-%m-%d").year
        url = f"https://api.polygon.io/v2/reference/dividends/{ticker}?apiKey={POLYGON_API_KEY}&start_date={start_year}-01-01"
        
        response = requests.get(url)
        if response.status_code == 200:
            dividend_data = response.json().get('results', [])
            
            # Parse dates and filter based on `start_date`
            filtered_dividends = []
            for dividend in dividend_data:
                ex_date_str = dividend.get('exDate')
                ex_date = datetime.strptime(ex_date_str, "%Y-%m-%d").date()
                
                if ex_date >= datetime.strptime(start_date, "%Y-%m-%d").date():
                    filtered_dividends.append({
                        'exDate': ex_date_str,
                        'amount': dividend.get('amount')
                    })
                    
            print(f"Dividends for {ticker}: {filtered_dividends}")  # Debugging output
            return filtered_dividends
        else:
            print(f"Error fetching dividends for {ticker}: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error fetching dividends for {ticker}: {str(e)}")
        return None
    
# Route pro dividendový kalendář
@portfolio_bp.route('/portfolio/dividend_calendar/<int:portfolio_id>', methods=['GET'])
@login_required
def dividend_calendar(portfolio_id):
    portfolio = Portfolio.query.get_or_404(portfolio_id)

    if portfolio.user != current_user:
        flash('Nemáte oprávnění k zobrazení tohoto portfolia.', 'error')
        return redirect(url_for('portfolio.upload'))

    csv_data = BytesIO(portfolio.data)
    try:
        # Načteme CSV data portfolia
        data = pd.read_csv(csv_data, encoding='utf-8')
        data['Datum'] = pd.to_datetime(data['Datum'], format='%d-%m-%Y', errors='coerce').dt.strftime('%Y-%m-%d')
    except pd.errors.EmptyDataError:
        flash('Soubor je prázdný nebo neplatný.', 'error')
        return redirect(url_for('portfolio.upload'))

    # Získání historických dividend
    dividend_calendar = get_filtered_dividend_calendar(data)

    # Získání nadcházejících dividend pro portfolio
    upcoming_dividends = get_upcoming_dividends_for_portfolio(data)

    # Debugging: Vypíše, co se předává šabloně
    print(f"Nadcházející dividendy: {upcoming_dividends}")

    return render_template('dividend_calendar.html',
                           portfolio=portfolio,
                           dividend_calendar=dividend_calendar,
                           upcoming_dividends=upcoming_dividends)

#NADCCHÁZEJÍCÍ DIVIDENDY

def get_upcoming_dividend(ticker):
    """
    Zjistí nadcházející nebo poslední známé datum výplaty dividend pro konkrétní ticker pomocí Polygon API.
    """
    try:
        # Voláme API Polygon pro nadcházející dividendy
        url = f"https://api.polygon.io/v3/reference/dividends?ticker={ticker}&order=desc&limit=1&apiKey={POLYGON_API_KEY}"
        response = requests.get(url)
        
        # Debugging API odpovědi
        print(f"API Response for {ticker}: {response.status_code} - {response.json()}")
        
        if response.status_code == 200:
            data = response.json().get('results', [])
            
            # Debug: vypište celý obsah odpovědi API
            print(f"Výsledek API pro {ticker}: {data}")
            
            if data:
                # Použijeme první dividendu, ať je historická nebo nadcházející
                dividend = data[0]
                ex_date = dividend.get('ex_dividend_date')
                amount = dividend.get('cash_amount')

                # Ověření, zda je datum ex-dividendy v budoucnosti
                today = datetime.now().date()
                ex_date_dt = datetime.strptime(ex_date, '%Y-%m-%d').date()
                
                # Pokud je v budoucnosti, vrátíme jako nadcházející
                if ex_date_dt > today:
                    print(f"Nadcházející dividenda: {amount} USD pro {ticker}, Ex-date: {ex_date}")
                    return ex_date, amount
                else:
                    # Pokud je datum v minulosti, vrátíme poslední známou dividendu
                    print(f"Poslední známá dividenda: {amount} USD pro {ticker}, Ex-date: {ex_date}")
                    return ex_date, amount
            else:
                print(f"Žádné dividendy vrácené API pro {ticker}.")
                return None, None
        else:
            print(f"Chyba při volání API Polygon pro {ticker}: {response.status_code}")
            return None, None
    except Exception as e:
        print(f"Chyba při zpracování API pro {ticker}: {str(e)}")
        return None, None
    
# Funkce, která zpracuje celé portfolio a zjistí nadcházející dividendy
def get_upcoming_dividends_for_portfolio(data):
    unique_isins = data['ISIN'].unique()
    upcoming_dividends = []

    for isin in unique_isins:
        ticker = get_ticker_from_isin(isin)
        if not ticker:
            print(f"Ticker pro ISIN {isin} nebyl nalezen.")
            continue

        print(f"Zpracovávám ticker: {ticker}")
        ex_date, amount = get_upcoming_dividend(ticker)
        if ex_date and amount:
            print(f"Nalezená nadcházející dividenda: {ex_date}, {amount}")
            upcoming_dividends.append({
                'ticker': ticker,
                'ex_date': ex_date,
                'amount': amount
            })
        else:
            print(f"Žádné nadcházející dividendy pro {ticker}.")

    print(f"Nadcházející dividendy pro portfolio: {upcoming_dividends}")
    return upcoming_dividends

@portfolio_bp.route('/portfolio/upcoming_dividends/<int:portfolio_id>', methods=['GET'])
@login_required
def upcoming_dividends(portfolio_id):
    portfolio = Portfolio.query.get_or_404(portfolio_id)

    if portfolio.user != current_user:
        flash('Nemáte oprávnění k zobrazení tohoto portfolia.', 'error')
        return redirect(url_for('portfolio.upload'))

    csv_data = BytesIO(portfolio.data)
    try:
        # Načteme CSV data portfolia
        data = pd.read_csv(csv_data, encoding='utf-8')
        data['Datum'] = pd.to_datetime(data['Datum'], format='%d-%m-%Y', errors='coerce').dt.strftime('%Y-%m-%d')
    except pd.errors.EmptyDataError:
        flash('Soubor je prázdný nebo neplatný.', 'error')
        return redirect(url_for('portfolio.upload'))

    # Získání nadcházejících dividend pro portfolio
    upcoming_dividends = get_upcoming_dividends_for_portfolio(data)

    # Debug: Vypíše nadcházející dividendy, které jsou předávány šabloně
    print(f"Nadcházející dividendy předané šabloně: {upcoming_dividends}")

    return render_template('upcoming_dividends.html', portfolio=portfolio, upcoming_dividends=upcoming_dividends)

import requests
import xml.etree.ElementTree as ET
import pandas as pd

# Funkce pro získání aktuálního směnného kurzu pomocí ECB API
def get_current_fx_rate(from_currency):
    # ECB API poskytuje směnné kurzy pouze proti EUR
    if from_currency == 'EUR':
        return 1.0  # Pokud je měna EUR, vrátíme kurz 1:1
    
    # API ECB vrací XML s denními směnnými kurzy proti EUR
    url = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
    response = requests.get(url)
    
    if response.status_code == 200:
        tree = ET.ElementTree(ET.fromstring(response.content))
        root = tree.getroot()

        # Hledáme směnný kurz k euru pro danou měnu
        namespaces = {'ns': 'http://www.ecb.int/vocabulary/2002-08-01/eurofxref'}
        for cube in root.findall(".//ns:Cube[@currency]", namespaces):
            if cube.attrib['currency'] == from_currency:
                return float(cube.attrib['rate'])
        print(f"Chyba: Nenalezen směnný kurz pro {from_currency}.")
        return None
    else:
        print(f"Chyba při získávání měnového kurzu: {response.status_code}")
        return None


# Výpočet profitu/ztráty na základě původní a aktuální hodnoty transakce (v CZK)
def calculate_forex_profit_loss(data):
    forex_results = []
    total_forex_impact = 0  # Celkový měnový dopad v CZK

    # Získání směnného kurzu EUR/CZK pro přepočet výsledků do CZK
    eur_to_czk_rate = get_current_fx_rate('CZK')
    if eur_to_czk_rate is None:
        print("Chyba: Nelze získat směnný kurz EUR/CZK.")
        return forex_results, total_forex_impact

    # Filtrujeme pozice, které nejsou uzavřené (které mají stále nějaký počet akcií)
    open_positions = data[data['Počet'] > 0]

    for _, row in open_positions.iterrows():
        domestic_value = abs(row.get('Hodnota v domácí měně', 0))  # Hodnota v domácí měně
        original_fx_rate = row.get('Směnný kurz', None)  # Původní směnný kurz
        currency = row.get('Unnamed: 8', 'EUR')  # Měna z Unnamed: 8 (v případě chybějícího sloupce defaultně EUR)

        if pd.isna(domestic_value) or pd.isna(original_fx_rate):
            print(f"Skipping row due to missing data: {row}")
            continue

        if currency == 'EUR':
            # Pro měny v EUR není potřeba výpočet forex dopadu
            print(f"Skipping row as currency is EUR: {row}")
            continue

        # Získání aktuálního směnného kurzu pro měnu do EUR
        current_fx_rate = get_current_fx_rate(currency)

        # Přidáme ladicí výpis pro zobrazení směnných kurzů
        print(f"Currency: {currency}, Original FX Rate: {original_fx_rate}, Current FX Rate: {current_fx_rate}")

        if current_fx_rate:
            # Původní hodnota v EUR
            original_eur_value = domestic_value / original_fx_rate

            # Přepočet původní hodnoty v domácí měně na EUR pomocí aktuálního kurzu
            current_value_in_domestic = original_eur_value * current_fx_rate

            # Rozdíl mezi aktuální a původní hodnotou v domácí měně (profit/ztráta) v EUR
            profit_or_loss_eur = current_value_in_domestic - domestic_value

            # Přepočet profitu nebo ztráty z EUR do CZK pomocí aktuálního kurzu EUR/CZK
            profit_or_loss_czk = profit_or_loss_eur * eur_to_czk_rate
            total_forex_impact += profit_or_loss_czk

            # Uložení výsledků pro každou transakci v CZK
            forex_results.append({
                'Datum': row['Datum'],
                'Měna': currency,
                'Původní hodnota': domestic_value,
                'Původní kurz': original_fx_rate,
                'Aktuální kurz': current_fx_rate,
                'Původní hodnota v EUR': original_eur_value,
                'Aktuální hodnota v domácí měně': current_value_in_domestic,
                'Profit/Ztráta (CZK)': round(profit_or_loss_czk, 2)
            })

            # Přidáme ladicí výpis pro zobrazení zisku/ztráty v CZK
            print(f"Transaction profit/loss for {currency} (CZK): {round(profit_or_loss_czk, 2)}")

    # Výpis celkového forex dopadu v CZK
    print(f"Total Forex Impact (CZK): {round(total_forex_impact, 2)}")

    return forex_results, round(total_forex_impact, 2)

@portfolio_bp.route('/delete_portfolio/<int:portfolio_id>', methods=['POST'])
@login_required
def delete_portfolio(portfolio_id):
    print(f"Request to delete portfolio {portfolio_id}")
    portfolio_to_delete = Portfolio.query.get_or_404(portfolio_id)

    # Změna owner na user (ověřte, že `user` je správný atribut)
    if portfolio_to_delete.user != current_user:
        flash('Nemáte oprávnění smazat toto portfolio.', 'error')
        return redirect(url_for('portfolio.upload'))

    try:
        db.session.delete(portfolio_to_delete)
        db.session.commit()
        flash('Portfolio bylo úspěšně smazáno.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Chyba při mazání portfolia: {str(e)}', 'error')

    return redirect(url_for('portfolio.upload'))


import openai  # Ujistěte se, že je importováno pro OpenAI API

# Funkce pro vytvoření AI komentáře
def generate_ai_commentary(results, stock_info_list):
    prompt = """
    Imagine you are Warren Buffett analyzing a portfolio with the following metrics. 
    Provide constructive criticism and advice. Discuss what could be improved, 
    suggest diversification, and evaluate if any positions might be worth selling or holding.

    Key Metrics:
    Portfolio Value: {portfolio_value}
    Realized Profit: {realized_profit} ({realized_profit_percentage})
    Unrealized Profit: {unrealized_profit} ({unrealized_profit_percentage})
    Total Dividends: {total_dividends}
    Dividend Yield: {dividend_yield}
    Investment Duration: {investment_duration} months
    Fees: {total_fees} ({fees_percentage})
    Forex Impact: {forex_impact_czk} (in CZK), {forex_impact_eur} (in EUR)

    Portfolio Positions:
    {positions}
    """
    # Formátování pozic do textu
    positions = "\n".join(
        f"{stock['ticker']}: Purchase Value - {stock['kupni_hodnota']} €, "
        f"Current Value - {stock['aktualni_hodnota']} €, Profit - {stock['profit']} €"
        for stock in stock_info_list
    )

    # Doplnění dat z výsledků portfolia
    prompt = prompt.format(
        portfolio_value=results['portfolio_value'],
        realized_profit=results['realized_profit'],
        realized_profit_percentage=results['realized_profit_percentage'],
        unrealized_profit=results['unrealized_profit'],
        unrealized_profit_percentage=results['unrealized_profit_percentage'],
        total_dividends=results['total_dividends'],
        dividend_yield=results['dividend_yield'],
        investment_duration=results['investment_duration'],
        total_fees=results['total_fees'],
        fees_percentage=results['fees_percentage'],
        forex_impact_czk=results['forex_impact_czk'],
        forex_impact_eur=results['forex_impact_eur'],
        positions=positions
    )

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.7
        )
        return response['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"Error generating AI commentary: {e}")
        return "Unable to generate AI commentary at this time."

    

import pandas as pd
import logging


# Funkce pro výpočet hodnoty portfolia ke konci každého měsíce - pouze pro otevřené pozice
def calculate_monthly_portfolio_values(data):
    # Převod datumu na datetime formát
    logging.debug("Převádím datumy na datetime formát")
    data['Datum'] = pd.to_datetime(data['Datum'], format='%d-%m-%Y', errors='coerce')

    # Ověříme, že sloupec 'Datum' neobsahuje neplatná data
    if data['Datum'].isnull().any():
        logging.error("Některá data ve sloupci 'Datum' nejsou validní")
        raise ValueError("Některá data ve sloupci 'Datum' nejsou validní.")

    # Setřídíme data podle datumu
    data = data.sort_values(by='Datum')
    logging.debug(f"Data po seřazení podle datumu: \n{data.head()}")

    # Přidáme sloupec 'Month' pro identifikaci měsíce a roku
    data['Month'] = data['Datum'].dt.to_period('M')

    # Inicializace seznamů pro uchování dat a hodnot portfolia
    dates = []
    values = []

    # Iterace přes jednotlivé měsíce v datech
    for month, monthly_data in data.groupby('Month'):
        # Skupinujeme podle ISIN a sečteme počet akcií (kladné = nákup, záporné = prodej)
        position_summary = monthly_data.groupby('ISIN')['Počet'].sum().reset_index()

        # Filtrujeme pouze ISINy, které mají kladný součet (znamená to, že pozice jsou stále otevřené)
        open_positions_filtered = position_summary[position_summary['Počet'] > 0]

        # Připojíme zpět k původnímu datasetu, abychom získali další informace (např. ticker)
        open_positions = pd.merge(open_positions_filtered, data, on='ISIN', how='left')

        # Filtrujeme pouze transakce, které se vztahují k aktuálnímu měsíci nebo dříve
        open_positions = open_positions[open_positions['Month'] <= month]

        # Odstraníme duplicity, abychom měli pouze poslední záznam pro každý ISIN
        open_positions = open_positions.drop_duplicates(subset='ISIN', keep='last')

        # Získání tickeru pro každou neprodanou pozici
        open_positions['Ticker'] = open_positions['ISIN'].apply(get_ticker_from_isin)

        # Získání aktuální ceny pro každou neprodanou pozici pomocí Polygon API
        open_positions['Aktuální Cena'] = open_positions['Ticker'].apply(get_delayed_price_polygon)

        # Výpočet hodnoty pozice (Počet akcií * Aktuální cena)
        open_positions['Hodnota pozice'] = open_positions['Počet_x'] * open_positions['Aktuální Cena']

        # Výpočet celkové hodnoty portfolia za daný měsíc - součet hodnot všech neprodaných pozic
        total_portfolio_value = open_positions['Hodnota pozice'].sum()

        # Uložení výsledků do seznamů
        dates.append(month.to_timestamp().strftime('%Y-%m-%d'))
        values.append(total_portfolio_value)

        logging.debug(f"Hodnota portfolia za měsíc {month}: {total_portfolio_value}")

    return dates, values

@portfolio_bp.route('/view/<int:portfolio_id>', methods=['GET'])
@login_required
def view_portfolio(portfolio_id):
    portfolio = Portfolio.query.get(portfolio_id)

    if not portfolio or portfolio.user_id != current_user.id:
        flash('Portfolio nebylo nalezeno nebo k němu nemáte přístup.', 'error')
        return redirect(url_for('portfolio.upload'))

    # Načti data portfolia ze stringu (z databáze) do DataFrame
    try:
        data = pd.read_csv(pd.compat.StringIO(portfolio.data))
        # Vypočítej hodnotu portfolia v čase
        portfolio_dates, portfolio_values = calculate_monthly_portfolio_values(data)
    except Exception as e:
        flash(f'Chyba při zpracování dat portfolia: {str(e)}', 'error')
        return redirect(url_for('portfolio.upload'))

    # Debug výpisy pro kontrolu dat, která budou odeslána do JavaScriptu
    logging.debug(f"Portfolio Dates pro JS: {portfolio_dates}")
    logging.debug(f"Portfolio Values pro JS: {portfolio_values}")

    return render_template('process.html', portfolio_dates=portfolio_dates, portfolio_values=portfolio_values)


def get_country_from_isin(isin):
    """
    Získá zemi na základě prvních dvou písmen ISIN.
    Prvních dvou písmen ISIN představuje kód země.
    """
    country_code = isin[:2].upper()
    country_mapping = {
        'US': 'United States',
        'GB': 'United Kingdom',
        'FR': 'France',
        'DE': 'Germany',
        'JP': 'Japan',
        'CN': 'China',
        'CA': 'Canada',
        'AU': 'Australia',
        'NL': 'Netherlands',
        'IT': 'Italy',
        'SE': 'Sweden',
        'ES': 'Spain',
        'CZ': 'Czech Republic',
    }

    country = country_mapping.get(country_code, 'Unknown Country')
    print(f"ISIN: {isin}, Country Code: {country_code}, Country: {country}")
    return country

def calculate_country_allocation(data):
    """
    Funkce, která vypočítá procentuální rozložení investic do různých zemí.

    Parameters:
    data (DataFrame): DataFrame obsahující transakce portfolia.

    Returns:
    tuple: Seznam zemí a jejich odpovídajících procentuálních podílů v portfoliu.
    """
    # Vybereme otevřené pozice (počet > 0)
    open_positions = data[data['Počet'] > 0].copy()
    print("Open Positions (Country Allocation):")
    print(open_positions)

    # Přidáme sloupec s hodnotou každé pozice (počet akcií * cena)
    open_positions['Hodnota pozice'] = open_positions['Počet'] * open_positions['Cena']
    print("Open Positions with Position Value:")
    print(open_positions)

    # Přidáme sloupec se zemí na základě ISIN
    open_positions['Země'] = open_positions['ISIN'].apply(lambda isin: get_country_from_isin(isin))
    print("Open Positions with Country:")
    print(open_positions)

    # Součet hodnot všech pozic
    total_value = open_positions['Hodnota pozice'].sum()
    print(f"Total Portfolio Value: {total_value}")

    # Pokud je hodnota portfolia nulová, vrátíme prázdné seznamy
    if total_value == 0:
        return [], []

    # Skupinujeme podle země a vypočítáme celkovou hodnotu každé země
    country_allocation = open_positions.groupby('Země')['Hodnota pozice'].sum().reset_index()
    print("Country Allocation:")
    print(country_allocation)

    # Přidáme sloupec s procentuálním podílem na celkovém portfoliu
    country_allocation['Procentuální podíl'] = (country_allocation['Hodnota pozice'] / total_value) * 100
    print("Country Allocation with Percentages:")
    print(country_allocation)

    # Vrátíme seznam zemí a jejich odpovídající podíly
    countries = country_allocation['Země'].tolist()
    percentages = country_allocation['Procentuální podíl'].tolist()

    return countries, percentages

def calculate_stock_allocation(data):
    """
    Funkce, která vypočítá procentuální rozložení investic do jednotlivých akcií.

    Parameters:
    data (DataFrame): DataFrame obsahující transakce portfolia.

    Returns:
    tuple: Seznam tickerů a jejich odpovídajících procentuálních podílů v portfoliu.
    """
    # Vybereme otevřené pozice (počet > 0)
    open_positions = data[data['Počet'] > 0].copy()
    print("Open Positions (Stock Allocation):")
    print(open_positions)

    # Zkontrolujeme, jestli sloupec 'Ticker' existuje, pokud ne, přidáme ho pomocí převodu z ISIN
    if 'Ticker' not in open_positions.columns:
        open_positions['Ticker'] = open_positions['ISIN'].apply(get_ticker_from_isin)
        open_positions['Ticker'].fillna('Unknown', inplace=True)  # Nahrazení chybějících tickerů hodnotou 'Unknown'
    print("Open Positions with Ticker:")
    print(open_positions)

    # Přidáme sloupec s hodnotou každé pozice (počet akcií * cena)
    open_positions['Hodnota pozice'] = open_positions['Počet'] * open_positions['Cena']
    print("Open Positions with Position Value:")
    print(open_positions)

    # Součet hodnot všech pozic
    total_value = open_positions['Hodnota pozice'].sum()
    print(f"Total Portfolio Value: {total_value}")

    # Pokud je hodnota portfolia nulová, vrátíme prázdné seznamy
    if total_value == 0:
        return [], []

    # Skupinujeme podle tickeru a vypočítáme celkovou hodnotu každé akcie
    allocation = open_positions.groupby('Ticker')['Hodnota pozice'].sum().reset_index()
    print("Stock Allocation:")
    print(allocation)

    # Přidáme sloupec s procentuálním podílem na celkovém portfoliu
    allocation['Procentuální podíl'] = (allocation['Hodnota pozice'] / total_value) * 100
    print("Stock Allocation with Percentages:")
    print(allocation)

    # Vrátíme seznam tickerů a jejich odpovídající podíly
    tickers = allocation['Ticker'].tolist()
    percentages = allocation['Procentuální podíl'].tolist()

    return tickers, percentages


def get_top_investments(stock_info_list, top_n=5):
    """
    Vrací seznam top N investic seřazených podle profitu.

    Args:
        stock_info_list (list): Seznam slovníků s informacemi o akciích (ticker, kupní hodnota, aktuální hodnota, profit).
        top_n (int): Počet nejlepších investic, které vrátíme.

    Returns:
        list: Seznam nejlepších investic podle profitu.
    """
    # Seřadíme podle profitu sestupně
    sorted_investments = sorted(stock_info_list, key=lambda x: x['profit'], reverse=True)
    # Vrátíme top N investic
    return sorted_investments[:top_n]

import requests
import json
import os
import pandas as pd
import yfinance as yf

def get_ticker_from_isin(isin):
    """
    Získá ticker na základě ISIN pomocí OpenFIGI API.
    """
    # Načtení API klíče z proměnného prostředí
    api_key = os.getenv('OPENFIGI_API_KEY')
    if not api_key:
        print("Chyba: OPENFIGI_API_KEY není nastaven v prostředí.")
        return None

    headers = {
        'Content-Type': 'application/json',
        'X-OPENFIGI-APIKEY': api_key  # Použití klíče z prostředí
    }

    # Připravíme payload s ISIN
    payload = [{"idType": "ID_ISIN", "idValue": isin}]
    
    try:
        # Pošleme POST request na OpenFIGI API
        response = requests.post("https://api.openfigi.com/v3/mapping", headers=headers, data=json.dumps(payload))
        response.raise_for_status()  # Pokud dojde k chybě, raise error
        
        data = response.json()

        # Debug výpis pro kontrolu odpovědi API
        print(f"DEBUG: OpenFIGI API response: {data}")

        # Kontrola, zda jsme dostali data
        if data and 'data' in data[0] and data[0]['data']:
            ticker = data[0]['data'][0].get('ticker', None)
            return ticker
        else:
            return None

    except requests.exceptions.RequestException as e:
        print(f"Chyba při komunikaci s OpenFIGI API: {e}")
        return None

def get_sector_from_isin(isin):
    """
    Získá sektor na základě ISIN tím, že nejdříve získá ticker a poté použije Yahoo Finance.
    """
    ticker = get_ticker_from_isin(isin)
    if not ticker:
        return 'Unknown Sector'

    return get_sector_from_ticker(ticker)

def get_sector_from_ticker(ticker):
    """
    Získá sektor na základě tickeru pomocí Yahoo Finance.
    """
    try:
        # Použití knihovny yfinance k získání dat o společnosti
        stock = yf.Ticker(ticker)
        info = stock.info

        # Debug výpis pro kontrolu informací o společnosti
        print(f"DEBUG: Informace o společnosti pro ticker {ticker}: {info}")

        # Získání sektoru, pokud je dostupný
        sector = info.get('sector', 'Unknown Sector')
        print(f"DEBUG: Sektor pro ticker {ticker}: {sector}")
        return sector
    except Exception as e:
        print(f"Chyba při získávání sektoru z Yahoo Finance pro ticker {ticker}: {e}")
        return 'Unknown Sector'

def calculate_sector_allocation(data):
    """
    Funkce, která vypočítá procentuální rozložení investic do různých sektorů.

    Parameters:
    data (DataFrame): DataFrame obsahující transakce portfolia.

    Returns:
    tuple: Seznam sektorů a jejich odpovídajících procentuálních podílů v portfoliu.
    """
    # Vybereme otevřené pozice (počet > 0)
    open_positions = data[data['Počet'] > 0].copy()
    open_positions['Hodnota pozice'] = open_positions['Počet'] * open_positions['Cena']

    # Debug výpis pro kontrolu otevřených pozic
    print("DEBUG: Otevřené pozice:")
    print(open_positions)

    # Přidáme sloupec se sektorem na základě ISIN
    open_positions['Sektor'] = open_positions['ISIN'].apply(lambda isin: get_sector_from_isin(isin))

    # Debug výpis pro kontrolu pozic se sektory
    print("DEBUG: Otevřené pozice se sektory:")
    print(open_positions)

    # Součet hodnot všech pozic
    total_value = open_positions['Hodnota pozice'].sum()
    print(f"DEBUG: Celková hodnota portfolia: {total_value}")

    # Pokud je hodnota portfolia nulová, vrátíme prázdné seznamy
    if total_value == 0:
        return [], []

    # Skupinujeme podle sektoru a vypočítáme celkovou hodnotu každého sektoru
    sector_allocation = open_positions.groupby('Sektor')['Hodnota pozice'].sum().reset_index()

    # Debug výpis pro kontrolu alokace sektorů
    print("DEBUG: Alokace sektorů:")
    print(sector_allocation)

    # Přidáme sloupec s procentuálním podílem na celkovém portfoliu
    sector_allocation['Procentuální podíl'] = (sector_allocation['Hodnota pozice'] / total_value) * 100

    # Debug výpis pro kontrolu alokace sektorů s procenty
    print("DEBUG: Alokace sektorů s procentuálními podíly:")
    print(sector_allocation)

    # Vrátíme seznam sektorů a jejich odpovídající podíly
    sectors = sector_allocation['Sektor'].tolist()
    percentages = sector_allocation['Procentuální podíl'].tolist()

    return sectors, percentages
