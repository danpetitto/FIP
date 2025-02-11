import requests
import xml.etree.ElementTree as ET
from flask import Blueprint, render_template, request
from models import Portfolio, Trade
from datetime import datetime, timedelta
import requests
from collections import defaultdict  # Nebo jiný potřebný modul z collections
import xml.etree.ElementTree as ET
import logging
import io
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict
from flask import Blueprint, render_template, request, jsonify, send_file, url_for, flash, redirect
from flask_login import current_user
from auth import subscription_required, login_required
import openai
from models import Portfolio, Trade

# Pro práci s časovými pásmy a relativními rozdíly mezi daty
import pytz
from dateutil.relativedelta import relativedelta
import numpy as np
from decimal import Decimal
import os
from dotenv import load_dotenv
import openai

# Načtení proměnných prostředí z .env souboru
load_dotenv()

# Načtení OpenAI API klíče z prostředí
openai.api_key = os.getenv('OPENAI_API_KEY')


# Definice Blueprintu pro daňovou sekci
tax_bp = Blueprint('tax', __name__)

# Limit pro osvobození od daní v CZK
VALUE_LIMIT = 100000

# URL pro stažení XML kurzu z ECB
ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"

def get_eur_to_czk_rate():
    """Funkce pro získání aktuálního kurzu EUR/CZK z ECB."""
    try:
        response = requests.get(ECB_URL)
        if response.status_code == 200:
            xml_tree = ET.ElementTree(ET.fromstring(response.content))
            root = xml_tree.getroot()
            namespace = {'ns': 'http://www.ecb.int/vocabulary/2002-08-01/eurofxref'}
            for cube in root.findall('.//ns:Cube/ns:Cube/ns:Cube', namespace):
                if cube.attrib.get('currency') == 'CZK':
                    return float(cube.attrib.get('rate'))
        return None
    except Exception as e:
        logging.error(f"Chyba při získávání kurzu: {e}")
        return None

def calculate_yearly_stats(trades_data):
    """
    Vypočítá detailní statistiku prodejů (transakce typu 'prodej' nebo 'sell') za jednotlivé roky.
    Vrací slovník, kde klíčem je rok a hodnotou je slovník s:
      - totalSales: celková hodnota prodejů (EUR)
      - soldCount: počet prodaných akcií
      - profit: součet zisků (EUR)
      - loss: součet ztrát (EUR)
    """
    stats = {}
    for trade in trades_data:
        if trade['type'].lower() not in ['prodej', 'sell']:
            continue
        trade_date = trade['date'] if isinstance(trade['date'], datetime) else datetime.strptime(trade['date'], '%Y-%m-%d')
        year = trade_date.year
        if year not in stats:
            stats[year] = {'totalSales': 0, 'soldCount': 0, 'profit': 0, 'loss': 0}
        stats[year]['totalSales'] += trade['hodnota']
        stats[year]['soldCount'] += abs(trade['pocet'])
        poplatky = trade.get('poplatky') or 0.0
        net = trade['hodnota'] - poplatky
        if net >= 0:
            stats[year]['profit'] += net
        else:
            stats[year]['loss'] += abs(net)
    logging.info(f"Yearly stats: {stats}")
    return stats

def sum_sales_by_year(trades_data):
    """
    Vrací slovník, kde klíčem je rok a hodnotou je celková hodnota prodejů
    (zahrnuje pouze transakce typu 'prodej' nebo 'sell').
    """
    sales_by_year = {}
    for trade in trades_data:
        if trade['type'].lower() in ['prodej', 'sell']:
            trade_date = trade['date'] if isinstance(trade['date'], datetime) else datetime.strptime(trade['date'], '%Y-%m-%d')
            year = trade_date.year
            sales_by_year[year] = sales_by_year.get(year, 0) + trade['hodnota']
    return sales_by_year

def convert_to_serializable(data):
    """
    Rekurzivně konvertuje hodnoty v datech na typy, které lze serializovat do JSON.
    """
    if isinstance(data, dict):
        return {k: convert_to_serializable(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_to_serializable(v) for v in data]
    elif isinstance(data, (np.int64, np.int32, int)):
        return int(data)
    elif isinstance(data, (np.float64, np.float32, float, Decimal)):
        return float(data)
    elif isinstance(data, datetime):
        return data.strftime('%Y-%m-%d %H:%M:%S')
    elif data is None:
        return None
    else:
        return str(data)

def analyze_open_positions(data, tickers_prices):
    """
    Analyzuje předaná data obchodů a vrací seznam otevřených pozic.
    Pro každou nákupní transakci (buy/nákup) odečítá odpovídající prodeje (sell/prodej) – FIFO metoda.
    U každého zbývajícího nákupního lotu vypočítá datum expirace (nákup + 3 roky) a počet zbývajících dní.
    Pokud je dostupná aktuální cena, přidá ji také.
    """
    from dateutil.relativedelta import relativedelta

    # Ujistíme se, že všechny záznamy mají datum jako datetime objekt
    for trade in data:
        if not isinstance(trade['date'], datetime):
            trade['date'] = datetime.strptime(trade['date'], '%Y-%m-%d')
    
    sorted_trades = sorted(data, key=lambda t: t['date'])
    positions = {}
    for trade in sorted_trades:
        trade_type = trade['type'].lower()
        ticker = trade['ticker']
        quantity = trade['pocet']
        trade_date = trade['date']
        if trade_type in ['nákup', 'buy']:
            positions.setdefault(ticker, []).append({
                'quantity': quantity,
                'purchase_date': trade_date
            })
        elif trade_type in ['prodej', 'sell']:
            if ticker in positions:
                qty_to_sell = quantity
                for lot in positions[ticker]:
                    if qty_to_sell <= 0:
                        break
                    if lot['quantity'] <= qty_to_sell:
                        qty_to_sell -= lot['quantity']
                        lot['quantity'] = 0
                    else:
                        lot['quantity'] -= qty_to_sell
                        qty_to_sell = 0
                positions[ticker] = [lot for lot in positions[ticker] if lot['quantity'] > 0]
                if not positions[ticker]:
                    del positions[ticker]
    
    prague_tz = pytz.timezone('Europe/Prague')
    now_prague = datetime.now(prague_tz)
    
    open_positions = []
    for ticker, lots in positions.items():
        current_price = tickers_prices.get(ticker)
        for lot in lots:
            purchase_date = lot['purchase_date']
            if purchase_date.tzinfo is None:
                purchase_date = prague_tz.localize(purchase_date)
            else:
                purchase_date = purchase_date.astimezone(prague_tz)
            expiration_date = purchase_date + relativedelta(years=3)
            days_remaining = (expiration_date - now_prague).days
            position = {
                'ticker': ticker,
                'quantity': lot['quantity'],
                'purchase_date': purchase_date.strftime('%Y-%m-%d'),
                'expiration_date': expiration_date.strftime('%Y-%m-%d'),
                'days_remaining': days_remaining
            }
            if current_price is not None:
                position['current_price'] = current_price
                position['current_value'] = round(current_price * lot['quantity'], 2)
            open_positions.append(position)
    
    return open_positions


@tax_bp.route('/api/sales_by_year', methods=['GET'])
@login_required
def api_sales_by_year():
    """
    Endpoint, který vrací součet prodejů (hodnota transakcí typu 'prodej'/'sell') za každý rok.
    """
    user_id = current_user.id
    selected_portfolio_id = request.args.get('portfolio_id')
    if not selected_portfolio_id:
        return jsonify({'error': 'Portfolio ID chybí'}), 400
    portfolio = Portfolio.query.filter_by(id=selected_portfolio_id, user_id=user_id).first()
    if not portfolio:
        return jsonify({'error': 'Portfolio nenalezeno'}), 404
    trades = Trade.query.filter_by(portfolio_id=portfolio.id).all()
    logging.info(f"Total trades for portfolio {selected_portfolio_id}: {len(trades)}")
    trades_data = []
    for trade in trades:
        trades_data.append({
            'date': trade.datum,
            'type': trade.typ_obchodu,
            'ticker': trade.ticker,
            'cena': trade.cena,
            'pocet': trade.pocet,
            'hodnota': trade.hodnota,
            'poplatky': trade.poplatky
        })
    sales_by_year = sum_sales_by_year(trades_data)
    return jsonify(sales_by_year)


@tax_bp.route('/api/trades', methods=['GET'])
@login_required
def api_trades():
    """
    Endpoint, který vrací všechny transakce portfolia, případně filtrované podle roku.
    """
    user_id = current_user.id
    selected_portfolio_id = request.args.get('portfolio_id')
    year = request.args.get('year', type=int)
    if not selected_portfolio_id:
        return jsonify({'error': 'Portfolio ID chybí'}), 400
    portfolio = Portfolio.query.filter_by(id=selected_portfolio_id, user_id=user_id).first()
    if not portfolio:
        return jsonify({'error': 'Portfolio nenalezeno'}), 404
    trades = Trade.query.filter_by(portfolio_id=portfolio.id).all()
    if year:
        trades = [trade for trade in trades if trade.datum.year == year]
    trades_data = []
    for trade in trades:
        trades_data.append({
            'date': trade.datum.strftime('%Y-%m-%d'),
            'type': trade.typ_obchodu,
            'ticker': trade.ticker,
            'cena': trade.cena,
            'pocet': trade.pocet,
            'hodnota': trade.hodnota,
            'poplatky': trade.poplatky
        })
    return jsonify(trades_data)


@tax_bp.route('/api/holdings', methods=['GET'])
@login_required
def api_holdings():
    """
    Endpoint pro získání aktuálně držených akcií.
    Pokud jsou výsledky již uloženy v portfolio.calculated_results (pod klíčem 'open_positions'),
    vrátí je. Jinak spočítá otevřené pozice pomocí funkce analyze_open_positions.
    """
    user_id = current_user.id
    selected_portfolio_id = request.args.get('portfolio_id')
    if not selected_portfolio_id:
        return jsonify({'error': 'Portfolio ID chybí'}), 400

    portfolio = Portfolio.query.filter_by(id=selected_portfolio_id, user_id=user_id).first()
    if not portfolio:
        return jsonify({'error': 'Portfolio nenalezeno'}), 404

    if portfolio.calculated_results:
        stored_results = portfolio.calculated_results
        open_positions = stored_results.get('open_positions', [])
        if open_positions:
            return jsonify(open_positions)

    trades = Trade.query.filter_by(portfolio_id=portfolio.id).all()
    trades_data = [
        {
            'ticker': trade.ticker,
            'type': trade.typ_obchodu,
            'pocet': trade.pocet,
            'date': trade.datum.strftime('%Y-%m-%d') if isinstance(trade.datum, datetime) else trade.datum
        }
        for trade in trades
    ]
    tickers_prices = {}  # Zde lze implementovat volání API pro aktuální ceny
    open_positions = analyze_open_positions(trades_data, tickers_prices)

    existing_results = portfolio.calculated_results if portfolio.calculated_results else {}
    existing_results['open_positions'] = open_positions
    portfolio.calculated_results = convert_to_serializable(existing_results)
    portfolio.last_calculated_at = datetime.utcnow()
    db.session.commit()

    return jsonify(open_positions)


def tax_optimization_advice(trades_data, current_year_sales, current_year_sales_czk, remaining_limit_czk):
    """
    Vytvoří prompt z transakcí aktuálního roku a zavolá OpenAI API, aby získal doporučení.
    """
    current_year = datetime.now().year
    current_year_trades = [
        trade for trade in trades_data
        if (trade['date'] if isinstance(trade['date'], datetime) else datetime.strptime(trade['date'], '%Y-%m-%d')).year == current_year
           and trade['type'].lower() in ['prodej', 'sell']
    ]
    prompt = (
        f"Uživatel má prodeje v hodnotě {current_year_sales:.2f} EUR, což je přibližně {current_year_sales_czk:.2f} CZK. "
        f"Zbývající limit pro osvobození od daní je {remaining_limit_czk:.2f} CZK. "
        "Následující transakce byly provedeny v aktuálním roce:\n"
    )
    for trade in current_year_trades:
        poplatky = trade.get('poplatky') if trade.get('poplatky') is not None else 0.0
        trade_date = trade['date'] if isinstance(trade['date'], datetime) else datetime.strptime(trade['date'], '%Y-%m-%d')
        prompt += (
            f"Ticker: {trade['ticker']}, Typ: {trade['type']}, Datum: {trade_date.strftime('%d-%m-%Y')}, "
            f"Cena: {trade['cena']:.2f} EUR, Počet: {abs(trade['pocet'])}, Hodnota: {trade['hodnota']:.2f} EUR, Poplatky: {abs(poplatky):.2f} EUR\n"
        )
    prompt += (
        "Na základě těchto údajů, jaké jsou nejlepší legální možnosti pro optimalizaci daní pro příští rok? "
        "Navrhni doporučení pro investice a prodeje akcií."
    )
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Jsi asistent, který poskytuje doporučení pro daňovou optimalizaci."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=200
        )
        advice = response.choices[0].message['content'].strip()
        return advice
    except Exception as e:
        logging.error(f"Chyba při získávání doporučení od OpenAI: {e}")
        return "Nepodařilo se získat doporučení pro daňovou optimalizaci."


@tax_bp.route('/', methods=['GET'])
def tax_select():
    user_id = current_user.id
    portfolios = Portfolio.query.filter_by(user_id=user_id).all()
    return render_template('tax.html', portfolios=portfolios)


@tax_bp.route('/results', methods=['GET'])
@login_required
@subscription_required
def tax_results():
    user_id = current_user.id
    portfolios = Portfolio.query.filter_by(user_id=user_id).all()
    selected_portfolio_id = request.args.get('portfolio_id')
    if not selected_portfolio_id:
        return render_template('tax_results.html', portfolios=portfolios, trades=[], results={}, current_year_sales="0 €",
                               current_year_sales_czk="0 CZK", remaining_limit=f"{VALUE_LIMIT} CZK", sales_status={}, advice="",
                               current_year=datetime.now().year, sales_by_year={})
    portfolio = Portfolio.query.filter_by(id=selected_portfolio_id, user_id=user_id).first()
    if not portfolio:
        return render_template('tax_results.html', portfolios=portfolios, trades=[], results={}, current_year_sales="0 €",
                               current_year_sales_czk="0 CZK", remaining_limit=f"{VALUE_LIMIT} CZK", sales_status={}, advice="",
                               current_year=datetime.now().year, sales_by_year={})
    trades = Trade.query.filter_by(portfolio_id=portfolio.id).all()
    if not trades:
        return render_template('tax_results.html', portfolios=portfolios, trades=[], results={}, current_year_sales="0 €",
                               current_year_sales_czk="0 CZK", remaining_limit=f"{VALUE_LIMIT} CZK", sales_status={}, advice="",
                               current_year=datetime.now().year, sales_by_year={})
    trades_data = []
    for trade in trades:
        trades_data.append({
            'date': trade.datum,
            'type': trade.typ_obchodu,
            'ticker': trade.ticker,
            'cena': trade.cena,
            'pocet': trade.pocet,
            'hodnota': trade.hodnota,
            'poplatky': trade.poplatky
        })
    yearly_stats = calculate_yearly_stats(trades_data)
    eur_to_czk_rate = get_eur_to_czk_rate() or 24.0
    current_year = datetime.now().year
    current_year_sales = yearly_stats.get(current_year, {}).get('totalSales', 0)
    current_year_sales_czk = current_year_sales * eur_to_czk_rate
    remaining_limit_czk = VALUE_LIMIT - current_year_sales_czk
    sales_status = {year: f"Celkové prodeje: {data['totalSales']:.2f} €" for year, data in yearly_stats.items()}
    advice = tax_optimization_advice(trades_data, current_year_sales, current_year_sales_czk, remaining_limit_czk)
    
    if portfolio.calculated_results:
        results = portfolio.calculated_results
    else:
        results = {}  # Pokud neexistují žádné uložené výsledky
    
    return render_template(
        'tax_results.html',
        portfolios=portfolios,
        trades=trades,
        results=results,
        current_year_sales=f"{current_year_sales:.2f} €",
        current_year_sales_czk=f"{current_year_sales_czk:.2f} CZK",
        remaining_limit=f"{remaining_limit_czk:.2f} CZK",
        sales_status=sales_status,
        advice=advice,
        current_year=current_year,
        sales_by_year=yearly_stats,
        selected_portfolio_id=selected_portfolio_id
    )


@tax_bp.route('/export_excel', methods=['GET'])
@login_required
def export_excel():
    user_id = current_user.id
    selected_portfolio_id = request.args.get('portfolio_id')
    if not selected_portfolio_id:
        return "Portfolio ID chybí", 400
    portfolio = Portfolio.query.filter_by(id=selected_portfolio_id, user_id=user_id).first()
    if not portfolio:
        return "Portfolio nenalezeno", 404
    trades = Trade.query.filter_by(portfolio_id=portfolio.id).all()
    if not trades:
        return "Žádné transakce k exportu", 404
    export_data = []
    for trade in trades:
        export_data.append({
            'Ticker': trade.ticker,
            'Nákup': trade.purchase_date.strftime('%d.%m.%Y') if hasattr(trade, 'purchase_date') and trade.purchase_date else trade.datum.strftime('%d.%m.%Y'),
            'Prodej': trade.sale_date.strftime('%d.%m.%Y') if hasattr(trade, 'sale_date') and trade.sale_date else (trade.datum.strftime('%d.%m.%Y') if trade.typ_obchodu.lower() in ['prodej', 'sell'] else ''),
            'Cena': trade.cena,
            'Počet': trade.pocet,
            'Hodnota': trade.hodnota,
            'Poplatky': trade.poplatky if trade.poplatky else 0,
            'Čistá hodnota': trade.hodnota - (trade.poplatky if trade.poplatky else 0)
        })
    df = pd.DataFrame(export_data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Transakce')
    output.seek(0)
    filename = f"transakce_{selected_portfolio_id}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return send_file(output,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True,
                     download_name=filename)

logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

from flask_login import current_user
import openai
from auth import subscription_required,login_required
from flask import Blueprint, render_template, request, jsonify


# Nastavení OpenAI API klíče
openai.api_key = 'YOUR_OPENAI_API_KEY'

# Blueprint pro daňovou sekci
tax_bp = Blueprint('tax', __name__)

# Limit pro osvobození od daní
VALUE_LIMIT = 100000

# URL pro stažení XML z ECB
ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"

def get_eur_to_czk_rate():
    try:
        response = requests.get(ECB_URL)
        if response.status_code == 200:
            xml_tree = ET.ElementTree(ET.fromstring(response.content))
            root = xml_tree.getroot()

            # Projít XML a najít kurz EUR/CZK
            namespace = {'ns': 'http://www.ecb.int/vocabulary/2002-08-01/eurofxref'}
            for cube in root.findall('.//ns:Cube/ns:Cube/ns:Cube', namespace):
                if cube.attrib['currency'] == 'CZK':
                    return float(cube.attrib['rate'])
        return None
    except Exception as e:
        print(f"Chyba při získávání kurzu: {e}")
        return None

# Výpočet prodejů podle let
def calculate_sales_by_year(trades_data):
    sales_by_year = defaultdict(float)
    processed_trades = set()  # Sledování unikátních transakcí (založené na datu a tickeru)

    for trade in trades_data:
        trade_key = (trade['date'], trade['ticker'])  # Kombinace data a tickeru jako unikátní klíč
        if trade['type'] == 'prodej' and trade_key not in processed_trades:
            year = trade['date'].year
            sales_by_year[year] += trade['hodnota']  # Přičítáme hodnotu prodeje
            processed_trades.add(trade_key)  # Označíme transakci jako zpracovanou
    return sales_by_year


@tax_bp.route('/api/sales_by_year', methods=['GET'])
@login_required
def api_sales_by_year():
    user_id = current_user.id

    # Získání portfolio_id z query parametru
    selected_portfolio_id = request.args.get('portfolio_id')
    if not selected_portfolio_id:
        return jsonify({'error': 'Portfolio ID missing'}), 400

    # Načtení portfolia
    portfolio = Portfolio.query.filter_by(id=selected_portfolio_id, user_id=user_id).first()
    if not portfolio:
        return jsonify({'error': 'Portfolio not found'}), 404

    # Načtení obchodů
    trades = Trade.query.filter_by(portfolio_id=portfolio.id).all()
    trades_data = [{
        'date': trade.datum,
        'type': trade.typ_obchodu,
        'ticker': trade.ticker,
        'hodnota': trade.hodnota
    } for trade in trades]

    # Výpočet součtu prodejů podle let
    sales_by_year = calculate_sales_by_year(trades_data)
    return jsonify(sales_by_year)


# Doporučení pro daňovou optimalizaci
def tax_optimization_advice(trades_data, current_year_sales, current_year_sales_czk, remaining_limit_czk):
    # Filtrace pro aktuální rok
    current_year = datetime.now().year
    current_year_trades = [trade for trade in trades_data if trade['date'].year == current_year]

    prompt = (
        f"Uživatel má prodeje v hodnotě {current_year_sales:.2f} EUR, což je přibližně {current_year_sales_czk:.2f} CZK. "
        f"Zbývající limit pro osvobození od daní je {remaining_limit_czk:.2f} CZK. "
        "Následující transakce byly provedeny v aktuálním roce:\n"
    )
    for trade in current_year_trades:
        poplatky = trade['poplatky'] if trade['poplatky'] is not None else 0.0
        prompt += (
            f"Ticker: {trade['ticker']}, Typ: {trade['type']}, Datum: {trade['date'].strftime('%d-%m-%Y')}, "
            f"Cena: {trade['cena']:.2f} EUR, Počet: {abs(trade['pocet'])}, Hodnota: {trade['hodnota']:.2f} EUR, Poplatky: {abs(poplatky):.2f} EUR\n"
        )
    prompt += (
        "Na základě těchto údajů, jaké jsou nejlepší legální možnosti pro optimalizaci daní pro příští rok? "
        "Navrhni doporučení pro investice a prodeje akcií."
    )

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Jsi asistent, který poskytuje doporučení pro daňovou optimalizaci."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=200
        )
        advice = response.choices[0].message['content'].strip()
        return advice
    except Exception as e:
        print(f"Chyba při získávání doporučení od OpenAI: {e}")
        return "Nepodařilo se získat doporučení pro daňovou optimalizaci."

# Route pro výběr portfolia (tax.html)
@tax_bp.route('/', methods=['GET'])
def tax_select():
    user_id = current_user.id
    portfolios = Portfolio.query.filter_by(user_id=user_id).all()
    return render_template('tax.html', portfolios=portfolios)

# Route pro výsledky (tax_results.html)
@tax_bp.route('/results', methods=['GET'])
@login_required
@subscription_required
def tax_results():
    user_id = current_user.id
    portfolios = Portfolio.query.filter_by(user_id=user_id).all()

    selected_portfolio_id = request.args.get('portfolio_id')
    if selected_portfolio_id:
        portfolio = Portfolio.query.filter_by(id=selected_portfolio_id, user_id=user_id).first()
        if not portfolio:
            return render_template('tax_results.html', portfolios=portfolios, trades={}, current_year_sales=0, remaining_limit=VALUE_LIMIT, sales_status={}, advice="")
    else:
        return render_template('tax_results.html', portfolios=portfolios, trades={}, current_year_sales=0, remaining_limit=VALUE_LIMIT, sales_status={}, advice="")

    trades = Trade.query.filter_by(portfolio_id=portfolio.id).all()

    if not trades:
        return render_template('tax_results.html', portfolios=portfolios, trades={}, current_year_sales=0, remaining_limit=VALUE_LIMIT, sales_status={}, advice="")

    # Data z obchodů
    trades_data = [{
        'date': trade.datum,
        'type': trade.typ_obchodu,
        'ticker': trade.ticker,
        'cena': trade.cena,
        'pocet': trade.pocet,
        'hodnota': trade.hodnota,
        'poplatky': trade.poplatky
    } for trade in trades]

    # Výpočet prodejů za jednotlivé roky
    sales_by_year = calculate_sales_by_year(trades_data)

    # Získání aktuálního kurzu EUR/CZK z ECB
    eur_to_czk_rate = get_eur_to_czk_rate()
    if eur_to_czk_rate is None:
        eur_to_czk_rate = 24.0  # Záložní kurz, pokud selže načtení XML

    # Sestavení statusů pro jednotlivé roky
    sales_status = {}
    for year, sales in sales_by_year.items():
        sales_status[year] = f"Součet prodejů: {sales:.2f} €"

    current_year_sales = sales_by_year.get(datetime.now().year, 0)
    current_year_sales_czk = current_year_sales * eur_to_czk_rate
    remaining_limit_czk = VALUE_LIMIT - current_year_sales_czk

    # Získání doporučení pro daňovou optimalizaci
    advice = tax_optimization_advice(trades_data, current_year_sales, current_year_sales_czk, remaining_limit_czk)

    return render_template(
        'tax_results.html',
        portfolios=portfolios,
        sales_status=sales_status,
        current_year_sales=f"{current_year_sales:.2f} €",
        current_year_sales_czk=f"{current_year_sales_czk:.2f} CZK",
        remaining_limit=f"{remaining_limit_czk:.2f} CZK",
        advice=advice,
        sales_by_year=sales_by_year
    )

# Odstranit hned jak to bude hotové
import logging

logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
