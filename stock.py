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

# Funkce pro získání dat z Yahoo Finance API
def get_yahoo_finance_data(ticker):
    yahoo_url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}?modules=summaryDetail,financialData"
    try:
        yahoo_response = requests.get(yahoo_url)
        yahoo_response.raise_for_status()
        yahoo_data = yahoo_response.json()
        
        # Logování celé odpovědi pro kontrolu struktury
        logging.debug(f'Odpověď z Yahoo Finance pro {ticker}: {yahoo_data}')
        
        if "quoteSummary" in yahoo_data and "result" in yahoo_data["quoteSummary"]:
            result = yahoo_data["quoteSummary"]["result"][0]
            
            # Ověření, zda je správně načtena aktuální cena
            current_price = result['financialData'].get('currentPrice', {}).get('raw', 'Data nejsou dostupná')
            market_cap = result['summaryDetail'].get('marketCap', {}).get('raw', 'Data nejsou dostupná')
            dividend_yield = result['summaryDetail'].get('dividendYield', {}).get('raw', 'Data nejsou dostupná')

            stock_data_combined = {
                'name': ticker.upper(),
                'market_cap': market_cap,
                'current_price': current_price,
                'dividend_yield': dividend_yield
            }

            logging.debug(f"Aktuální cena pro {ticker}: {current_price}")
            return stock_data_combined
        else:
            logging.debug(f"Yahoo Finance neposkytuje data pro {ticker}")
            return None

    except requests.exceptions.HTTPError as err:
        logging.error(f'HTTP chyba z Yahoo Finance: {err}')
        return None
    except Exception as err:
        logging.error(f'Něco se pokazilo při volání Yahoo Finance API: {err}')
        return None

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

        # Uložíme pouze relevantní data: Tržní kapitalizace, aktuální cena a dividendový výnos
        stock_data_combined = {
            'name': stock_data['results'].get('name', 'Název není dostupný'),
            'market_cap': stock_data['results'].get('market_cap', 'Data nejsou dostupná'),
            # Ověření, že aktuální cena je ve správném formátu
            'current_price': stock_data['results'].get('current_price', 'Data nejsou dostupná'),
            # Ověření, že dividendový výnos je ve správném formátu
            'dividend_yield': stock_data['results'].get('dividend_yield', 'Data nejsou dostupná')
        }

        # Pokud jsou všechna data "N/A", zkusíme Yahoo Finance
        if all(value == 'Data nejsou dostupná' for value in stock_data_combined.values()):
            logging.debug(f"Polygon API neposkytuje data, přecházím na Yahoo Finance pro {ticker}")
            stock_data_combined = get_yahoo_finance_data(ticker)

            if stock_data_combined is None:
                return render_template('stocks.html', error="Data nejsou dostupná ani z Yahoo Finance.", ticker=ticker)
        
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
