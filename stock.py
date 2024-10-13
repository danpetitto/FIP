import os
import requests
from flask import Blueprint, request, jsonify, render_template
import logging
import yfinance as yf  # Přidání yfinance pro získání P/E a EPS poměru

# Zde vložte přímo svůj API klíč pro Polygon API
POLYGON_API_KEY = os.getenv('POLYGON_API_KEY')

# API URL pro vyhledávání tickerů (dostupné pro bezplatné účty)
API_SEARCH_URL = 'https://api.polygon.io/v3/reference/tickers'
# API URL pro detaily o společnosti
API_DETAILS_URL = 'https://api.polygon.io/v3/reference/tickers/{ticker}'
# API URL pro cenová data (vyžaduje placený tarif)
API_PRICE_URL = 'https://api.polygon.io/v1/last/stocks/{ticker}'

# Definuj Blueprint pro stock API
stock_bp = Blueprint('stock', __name__)

# Přidáme logování pro debugování
logging.basicConfig(level=logging.DEBUG)

# Trasa pro zobrazení formuláře
@stock_bp.route('/search_stocks_form', methods=['GET'])
def search_stocks_form():
    return render_template('stock_search.html')

# Trasa pro skutečné vyhledávání akcií
@stock_bp.route('/search_stocks', methods=['GET'])
def search_stocks():
    query = request.args.get('query')

    logging.debug(f'Přijatý query parametr: {query}')
    
    if not query:
        return jsonify({'error': 'Je třeba zadat parametr query'}), 400
    
    # Parametry pro volání API
    params = {
        'search': query,
        'apiKey': POLYGON_API_KEY
    }

    try:
        # Volání Polygon API
        response = requests.get(API_SEARCH_URL, params=params)
        response.raise_for_status()
        stock_data = response.json().get('results', [])
        
        if not stock_data:
            logging.debug('Žádné výsledky nebyly nalezeny.')
            return jsonify({'error': 'Nebyly nalezeny žádné výsledky.'}), 404
        
        logging.debug(f'Nalezené výsledky: {stock_data}')
        return jsonify(stock_data)
    
    except requests.exceptions.HTTPError as err:
        if err.response.status_code == 401:
            logging.error("401 Unauthorized: API klíč není oprávněn pro tento endpoint.")
            return jsonify({'error': 'API klíč není oprávněn pro toto volání. Ověřte, zda je správný a že máte odpovídající tarif.'}), 401
        logging.error(f'HTTP chyba: {err}')
        return jsonify({'error': f'HTTP chyba: {err}'}), 500
    except Exception as err:
        logging.error(f'Něco se pokazilo: {err}')
        return jsonify({'error': f'Něco se pokazilo: {err}'}), 500

# Trasa pro zobrazení detailů akcie
@stock_bp.route('/stocks/<ticker>', methods=['GET'])
def get_stock(ticker):
    params = {'apiKey': POLYGON_API_KEY}
    logging.debug(f"Requesting details for ticker: {ticker} with params: {params}")

    try:
        # Získání informací o tickeru přes Polygon API
        response = requests.get(API_DETAILS_URL.format(ticker=ticker), params=params)
        response.raise_for_status()
        stock_data = response.json()

        # Získání dividendových dat
        dividend_data = get_polygon_dividend_data(ticker)

        # Získání zpožděné ceny
        delayed_price = get_polygon_delayed_price(ticker)

        # Získání P/E poměru, EPS, marží, EV/EBITDA, EBITDA a ROE pomocí yfinance
        stock = yf.Ticker(ticker)
        pe_ratio = stock.info.get('trailingPE', 'Data nejsou dostupná')
        eps = stock.info.get('trailingEps', 'Data nejsou dostupná')
        ev_to_ebitda = stock.info.get('enterpriseToEbitda', 'Data nejsou dostupná')
        ebitda = stock.info.get('ebitda', 'Data nejsou dostupná')
        roe = stock.info.get('returnOnEquity', 'Data nejsou dostupná')

        # Získání marží
        gross_margin = stock.info.get('grossMargins', 'Data nejsou dostupná')
        operating_margin = stock.info.get('operatingMargins', 'Data nejsou dostupná')
        net_margin = stock.info.get('profitMargins', 'Data nejsou dostupná')

        # Formátování marží a dalších ukazatelů (pokud jsou dostupné)
        if gross_margin != 'Data nejsou dostupná':
            gross_margin = f"{gross_margin * 100:.2f} %"
        if operating_margin != 'Data nejsou dostupná':
            operating_margin = f"{operating_margin * 100:.2f} %"
        if net_margin != 'Data nejsou dostupná':
            net_margin = f"{net_margin * 100:.2f} %"
        if ev_to_ebitda != 'Data nejsou dostupná':
            ev_to_ebitda = f"{ev_to_ebitda:.2f}"
        if ebitda != 'Data nejsou dostupná':
            ebitda = f"{ebitda / 1e9:.2f} B USD"  # Převedení EBITDA na miliardy USD
        if roe != 'Data nejsou dostupná':
            roe = f"{roe * 100:.2f} %"

        # Získání počtu let vyplácení dividend pomocí yfinance
        payout_years = get_dividend_payout_years(ticker)

        # Kontrola a extrakce dat z API odpovědi
        stock_name = stock_data['results'].get('name', 'Název není dostupný')
        market_cap = stock_data['results'].get('market_cap', 'Data nejsou dostupná')

        # Pokud data nejsou dostupná, záznam o tom
        if market_cap == 'Data nejsou dostupná':
            logging.debug(f"Tržní kapitalizace pro {ticker} není dostupná.")

        # Kombinování všech získaných dat, včetně P/E poměru, EPS, a dalších finančních ukazatelů
        stock_data_combined = {
            'name': stock_name,
            'market_cap': market_cap,
            'current_price': delayed_price,
            'pe_ratio': pe_ratio,  # P/E poměr
            'eps': eps,  # EPS
            'gross_margin': gross_margin,  # Hrubá marže
            'operating_margin': operating_margin,  # Provozní marže
            'net_margin': net_margin,  # Čistá marže
            'ev_to_ebitda': ev_to_ebitda,  # EV/EBITDA
            'ebitda': ebitda,  # EBITDA
            'roe': roe,  # ROE
            'annual_dividend_per_share': dividend_data.get('annual_dividend_per_share', 'Data nejsou dostupná'),  # Roční dividenda
            'dividend_yield': dividend_data.get('dividend_yield', 'Data nejsou dostupná'),  # Roční dividendový výnos
            'dividend_payout_years': payout_years  # Počet let vyplácení dividend
        }

        # Renderování šablony s daty
        return render_template('stocks.html', stock=stock_data_combined, ticker=ticker)

    except requests.exceptions.HTTPError as err:
        if err.response.status_code == 403:
            logging.error(f"403 Forbidden: API klíč nemá přístup k požadovanému endpointu. Ověřte, zda máte správný tarif.")
            return render_template('stocks.html', error="Přístup k API Polygon je zakázán. Ověřte, zda máte platný API klíč a odpovídající tarif.", ticker=ticker), 403
        elif err.response.status_code == 404:
            logging.error(f"404 Not Found: {err}")
            return render_template('stocks.html', error="Akcie nebyla nalezena. Zkontrolujte symbol.", ticker=ticker), 404
        logging.error(f'HTTP chyba: {err}')
        return render_template('stocks.html', error=f'HTTP chyba: {err}', ticker=ticker)

    except Exception as err:
        logging.error(f'Něco se pokazilo: {err}')
        return render_template('stocks.html', error=f'Něco se pokazilo: {err}', ticker=ticker)

# Funkce pro získání počtu let výplaty dividend z yfinance
def get_dividend_payout_years(ticker):
    try:
        stock = yf.Ticker(ticker)

        # Získání historických dividend
        dividend_history = stock.dividends

        # Kontrola, zda jsou dostupná data o dividendách
        if dividend_history.empty:
            return 'Data nejsou dostupná'

        # Získání prvního a posledního data výplaty dividendy
        first_dividend_date = dividend_history.index.min()
        last_dividend_date = dividend_history.index.max()

        # Výpočet rozdílu v letech mezi první a poslední dividendou
        payout_years = (last_dividend_date - first_dividend_date).days // 365

        return f"{payout_years} let" if payout_years > 0 else "Méně než 1 rok"
    except Exception as e:
        logging.error(f"Chyba při získávání počtu let výplaty dividend z yfinance pro {ticker}: {e}")
        return 'Data nejsou dostupná'

# URL pro získání zpožděné ceny z Polygon API
API_DELAYED_PRICE_URL = 'https://api.polygon.io/v2/aggs/ticker/{ticker}/prev'

# Funkce pro získání zpožděné ceny akcie z Polygon API
def get_polygon_delayed_price(ticker):
    url = API_DELAYED_PRICE_URL.format(ticker=ticker)
    params = {'apiKey': POLYGON_API_KEY}
    
    try:
        # Volání Polygon API
        response = requests.get(url, params=params)
        response.raise_for_status()
        price_data = response.json()

        # Ověření, zda máme správná data
        if 'results' in price_data and len(price_data['results']) > 0:
            result = price_data['results'][0]
            # Získání uzavírací ceny (close price) z výsledku
            delayed_price = result.get('c', 'Data nejsou dostupná')
            logging.debug(f"Zpožděná cena pro {ticker}: {delayed_price}")
            return delayed_price
        else:
            logging.debug(f"Polygon API neposkytuje data pro {ticker}.")
            return 'Data nejsou dostupná'

    except requests.exceptions.HTTPError as err:
        logging.error(f"HTTP chyba z Polygon API: {err}")
        return 'Data nejsou dostupná'
    except Exception as err:
        logging.error(f"Něco se pokazilo při volání Polygon API: {err}")
        return 'Data nejsou dostupná'

# URL pro získání dividend z Polygon API
API_DIVIDEND_URL = 'https://api.polygon.io/v3/reference/dividends?ticker={ticker}'

# Funkce pro získání dividend z Polygon API
def get_polygon_dividend_data(ticker):
    url = API_DIVIDEND_URL.format(ticker=ticker)
    params = {'apiKey': POLYGON_API_KEY}
    
    try:
        # Volání Polygon API pro získání dat o dividendách
        response = requests.get(url, params=params)

        # Zpracování odpovědi, pokud nejsou žádné chyby
        response.raise_for_status()
        dividend_data = response.json()

        if 'results' in dividend_data and len(dividend_data['results']) > 0:
            result = dividend_data['results'][0]
            
            # Získání čtvrtletní dividendy na akcii (cash_amount)
            quarterly_dividend_per_share = result.get('cash_amount', 'Data nejsou dostupná')

            # Získání aktuální ceny akcie pro výpočet
            current_price = get_polygon_delayed_price(ticker)

            # Výpočet roční dividendy (čtvrtletní dividenda x 4)
            if quarterly_dividend_per_share != 'Data nejsou dostupná':
                annual_dividend_per_share = round(float(quarterly_dividend_per_share) * 4, 2)
            else:
                annual_dividend_per_share = 'Data nejsou dostupná'

            # Výpočet ročního dividendového výnosu v procentech
            if current_price != 'Data nejsou dostupná' and annual_dividend_per_share != 'Data nejsou dostupná':
                try:
                    dividend_yield = (float(annual_dividend_per_share) / float(current_price)) * 100
                    dividend_yield = round(dividend_yield, 2)
                except (ValueError, TypeError):
                    dividend_yield = 'Data nejsou dostupná'
            else:
                dividend_yield = 'Data nejsou dostupná'

            return {
                'annual_dividend_per_share': f'{annual_dividend_per_share} USD' if annual_dividend_per_share != 'Data nejsou dostupná' else 'Data nejsou dostupná',
                'dividend_yield': f'{dividend_yield} %' if dividend_yield != 'Data nejsou dostupná' else 'Data nejsou dostupná'
            }
        else:
            return {
                'annual_dividend_per_share': 'Data nejsou dostupná',
                'dividend_yield': 'Data nejsou dostupná'
            }

    except Exception as err:
        logging.error(f"Chyba při získávání dividend z Polygon API: {err}")
        return {
            'annual_dividend_per_share': 'Data nejsou dostupná',
            'dividend_yield': 'Data nejsou dostupná'
        }
