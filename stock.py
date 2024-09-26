import os 
import requests
from flask import Blueprint, request, jsonify, render_template
import logging

# Zde vložte přímo svůj API klíč pro Polygon API
POLYGON_API_KEY = 'NlFMCIQRvxPJtgoAmzek9jGpJxbpnpyf'

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
    

  # URL pro získání dividend z Polygon API - správný endpoint
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
            dividend_per_share = result.get('cash_amount', 'Data nejsou dostupná')
            
            # Získání aktuální ceny akcie pro výpočet
            current_price = get_polygon_delayed_price(ticker)

            # Výpočet čtvrtletního výnosu (%)
            if current_price != 'Data nejsou dostupná' and dividend_per_share != 'Data nejsou dostupná':
                quarterly_yield = (float(dividend_per_share) / float(current_price)) * 100
                quarterly_yield = round(quarterly_yield, 2)  # Zaokrouhlení na 2 desetinná místa
            else:
                quarterly_yield = 'Data nejsou dostupná'

            return {
                'quarterly_dividend_per_share': f'{dividend_per_share} USD',  # Zobrazení čtvrtletní dividendy
                'quarterly_yield': f'{quarterly_yield} %' if quarterly_yield != 'Data nejsou dostupná' else 'Data nejsou dostupná',
                'dividend_yield': f'{(quarterly_yield * 4):.2f} %' if quarterly_yield != 'Data nejsou dostupná' else 'Data nejsou dostupná'  # Roční dividendový výnos (pokud nejsou dostupná data z API)
            }
        else:
            return {
                'quarterly_dividend_per_share': 'Data nejsou dostupná',
                'quarterly_yield': 'Data nejsou dostupná',
                'dividend_yield': 'Data nejsou dostupná'
            }

    except Exception as err:
        logging.error(f"Chyba při získávání dividend z Polygon API: {err}")
        return {
            'quarterly_dividend_per_share': 'Data nejsou dostupná',
            'quarterly_yield': 'Data nejsou dostupná',
            'dividend_yield': 'Data nejsou dostupná'
        }

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

        # Kontrola a extrakce dat z API odpovědi
        stock_name = stock_data['results'].get('name', 'Název není dostupný')
        market_cap = stock_data['results'].get('market_cap', 'Data nejsou dostupná')

        # Pokud data nejsou dostupná, záznam o tom
        if market_cap == 'Data nejsou dostupná':
            logging.debug(f"Tržní kapitalizace pro {ticker} není dostupná.")

        # Kombinování všech získaných dat
        stock_data_combined = {
            'name': stock_name,
            'market_cap': market_cap,
            'current_price': delayed_price,
            'dividend_yield': dividend_data.get('dividend_yield', 'Data nejsou dostupná'),
            'dividend_per_share': dividend_data.get('dividend_per_share', 'Data nejsou dostupná')
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
