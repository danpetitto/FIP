import os
import requests
from flask import Blueprint, request, jsonify, render_template
import logging
import yfinance as yf  # Přidání yfinance pro získání P/E a EPS poměru
from datetime import datetime, timedelta

# Zde vložte přímo svůj API klíč pro Polygon API
POLYGON_API_KEY = os.getenv('POLYGON_API_KEY')

# API URL pro vyhledávání tickerů (dostupné pro bezplatné účty)
API_SEARCH_URL = 'https://api.polygon.io/v3/reference/tickers'
# API URL pro detaily o společnosti
API_DETAILS_URL = 'https://api.polygon.io/v3/reference/tickers/{ticker}'
# API URL pro cenová data (vyžaduje placený tarif)
API_PRICE_URL = 'https://api.polygon.io/v1/last/stocks/{ticker}'
# URL pro Moody's Aaa Corporate Bond Yield (použijeme makroekonomický indikátor)
MOODYS_AAA_YIELD_URL = 'https://api.example.com/moody-bond-yield'

# Funkce pro získání Moody's Seasoned Aaa Corporate Bond Yield
def get_moodys_aaa_yield():
    try:
        response = requests.get(MOODYS_AAA_YIELD_URL)
        response.raise_for_status()
        data = response.json()
        # Očekáváme, že API vrátí výnos v procentech (např. 3.5)
        return data.get('yield', 3.5)  # Použijeme výchozí hodnotu, pokud API selže
    except Exception as e:
        logging.error(f"Chyba při načítání Moody's Aaa Corporate Bond Yield: {e}")
        return 3.5  # Výchozí hodnota, pokud selže API

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

# Upravená funkce pro výpočet vnitřní hodnoty akcie podle Grahamova vzorce
def calculate_intrinsic_value(eps, estimated_growth_rate):
    """
    Výpočet vnitřní hodnoty akcie pomocí původního Grahamova vzorce:
    Intrinsic Value = EPS * (8.5 + 2 * odhadovaný růst v %)
    """
    try:
        if eps is not None and eps != 'Data nejsou dostupná':
            eps = float(eps)
            # Převod growth rate na procenta, pokud je zadán jako desetinná hodnota
            if estimated_growth_rate <= 1:  # Např. 0.1459 -> 14.59
                estimated_growth_rate *= 100
            intrinsic_value = eps * (8.5 + 2 * estimated_growth_rate)
            return round(intrinsic_value, 2)
        else:
            return 'Data nejsou dostupná'
    except (ValueError, TypeError, ZeroDivisionError) as e:
        logging.error(f"Error calculating intrinsic value: {e}")
        return 'Data nejsou dostupná'

# Získání Moody's Aaa Corporate Bond Yield
def get_moodys_aaa_yield():
    try:
        response = requests.get(MOODYS_AAA_YIELD_URL, timeout=5)
        response.raise_for_status()
        data = response.json()
        return data.get('yield', 3.5)
    except requests.RequestException as e:
        logging.error(f"Error fetching Moody's Aaa Corporate Bond Yield: {e}")
        return 3.5

# Funkce pro získání loga pomocí Clearbit
def get_logo_url(ticker):
    return f'https://logo.clearbit.com/{ticker.lower()}.com'

# Route pro získání dat o akciích
@stock_bp.route('/stocks/<ticker>', methods=['GET'])
def get_stock(ticker):
    params = {'apiKey': POLYGON_API_KEY}
    logging.debug(f"Requesting details for ticker: {ticker} with params: {params}")

    try:
        # Získání informací o tickeru
        response = requests.get(API_DETAILS_URL.format(ticker=ticker), params=params)
        response.raise_for_status()
        stock_data = response.json()

        # Získání dividendových dat a ceny
        dividend_data = get_polygon_dividend_data(ticker)
        delayed_price = get_polygon_delayed_price(ticker)

        # Načítání dat o akcii pomocí yfinance
        stock = yf.Ticker(ticker)
        pe_ratio = stock.info.get('trailingPE', 'Data nejsou dostupná')
        eps = stock.info.get('trailingEps', 'Data nejsou dostupná')
        ev_to_ebitda = stock.info.get('enterpriseToEbitda', 'Data nejsou dostupná')
        ebitda = stock.info.get('ebitda', 'Data nejsou dostupná')
        roe = stock.info.get('returnOnEquity', 'Data nejsou dostupná')

        gross_margin = stock.info.get('grossMargins', 'Data nejsou dostupná')
        operating_margin = stock.info.get('operatingMargins', 'Data nejsou dostupná')
        net_margin = stock.info.get('profitMargins', 'Data nejsou dostupná')
        estimated_growth_rate = stock.info.get('earningsGrowth', 0)

        # Formátování dat
        if gross_margin != 'Data nejsou dostupná':
            gross_margin = f"{gross_margin * 100:.2f} %"
        if operating_margin != 'Data nejsou dostupná':
            operating_margin = f"{operating_margin * 100:.2f} %"
        if net_margin != 'Data nejsou dostupná':
            net_margin = f"{net_margin * 100:.2f} %"
        if ev_to_ebitda != 'Data nejsou dostupná':
            ev_to_ebitda = f"{ev_to_ebitda:.2f}"
        if ebitda != 'Data nejsou dostupná':
            ebitda = f"{ebitda / 1e9:.2f} B USD"
        if roe != 'Data nejsou dostupná':
            roe = f"{roe * 100:.2f} %"

        # Výpočet vnitřní hodnoty
        intrinsic_value = calculate_intrinsic_value(eps, estimated_growth_rate)

        # Extrakce dalších informací
        stock_name = stock_data['results'].get('name', 'Název není dostupný')
        market_cap = stock_data['results'].get('market_cap', 'Data nejsou dostupná')
        payout_years = get_dividend_payout_years(ticker)

         # Získání loga
        logo_url = get_logo_url(ticker)

        # Kombinace a zobrazení dat
        return render_stock_data(
            stock_name, market_cap, delayed_price, pe_ratio, eps, gross_margin, operating_margin,
            net_margin, ev_to_ebitda, ebitda, roe, dividend_data, payout_years, intrinsic_value, ticker, logo_url
        )

    except requests.exceptions.HTTPError as err:
        if err.response.status_code == 403:
            logging.error("403 Forbidden: API klíč nemá přístup k požadovanému endpointu.")
            return render_template('stocks.html', error="API přístup zamítnut. Ověřte API klíč.", ticker=ticker), 403
        elif err.response.status_code == 404:
            logging.error("404 Not Found")
            return render_template('stocks.html', error="Akcie nebyla nalezena.", ticker=ticker), 404
        logging.error(f'HTTP error: {err}')
        return render_template('stocks.html', error=f'HTTP chyba: {err}', ticker=ticker)

    except Exception as err:
        logging.error(f'Něco se pokazilo: {err}')
        return render_template('stocks.html', error=f'Něco se pokazilo: {err}', ticker=ticker)


# Funkce pro kombinování dat a renderování šablony
def render_stock_data(stock_name, market_cap, delayed_price, pe_ratio, eps, gross_margin, operating_margin,
                      net_margin, ev_to_ebitda, ebitda, roe, dividend_data, payout_years, intrinsic_value, ticker, logo_url):
    stock_data_combined = {
        'name': stock_name,
        'market_cap': market_cap,
        'current_price': delayed_price,
        'pe_ratio': pe_ratio,
        'eps': eps,
        'gross_margin': gross_margin,
        'operating_margin': operating_margin,
        'net_margin': net_margin,
        'ev_to_ebitda': ev_to_ebitda,
        'ebitda': ebitda,
        'roe': roe,
        'annual_dividend_per_share': dividend_data.get('annual_dividend_per_share', 'Data nejsou dostupná'),
        'dividend_yield': dividend_data.get('dividend_yield', 'Data nejsou dostupná'),
        'dividend_payout_years': payout_years,
        'intrinsic_value': intrinsic_value,
        'logo': logo_url
    }
    return render_template('stocks.html', stock=stock_data_combined, ticker=ticker)

# Funkce pro zpracování chyb z API
def handle_api_error(err, ticker):
    if isinstance(err, requests.exceptions.HTTPError):
        if err.response.status_code == 403:
            logging.error("403 Forbidden: API klíč nemá přístup k požadovanému endpointu.")
            return render_template(
                'stocks.html',
                error="Přístup k API Polygon je zakázán. Ověřte, zda máte platný API klíč a odpovídající tarif.",
                ticker=ticker
            ), 403
        elif err.response.status_code == 404:
            logging.error(f"404 Not Found: {err}")
            return render_template('stocks.html', error="Akcie nebyla nalezena. Zkontrolujte symbol.", ticker=ticker), 404
    logging.error(f"HTTP chyba: {err}")
    return render_template('stocks.html', error=f"HTTP chyba: {err}", ticker=ticker)

def handle_generic_error(err, ticker):
    logging.error(f"Něco se pokazilo: {err}")
    return render_template('stocks.html', error=f"Něco se pokazilo: {err}", ticker=ticker)

import requests
import logging

FRED_API_KEY = 'bb0cd01f86e198c1762cf75669b8e861'  # Váš API klíč
FRED_API_URL = 'https://api.stlouisfed.org/fred/series/observations'

def get_moodys_aaa_yield():
    try:
        # Parametry pro volání API
        params = {
            'series_id': 'AAA',  # Moody's Aaa Corporate Bond Yield
            'api_key': FRED_API_KEY,
            'file_type': 'json'
        }
        # Volání FRED API
        response = requests.get(FRED_API_URL, params=params)
        response.raise_for_status()  # Ověření, zda API volání bylo úspěšné
        data = response.json()
        
        # Získání posledního pozorování výnosu
        latest_observation = data['observations'][-1]
        return float(latest_observation['value'])
    
    except Exception as e:
        logging.error(f"Chyba při načítání Moody's Aaa Corporate Bond Yield: {e}")
        return 3.5  # Výchozí hodnota v případě chyby

# Příklad použití funkce
moodys_aaa_yield = get_moodys_aaa_yield()
print(f"Moody's Aaa Corporate Bond Yield: {moodys_aaa_yield}%")

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
    
@stock_bp.route('/stock_chart/<ticker>', methods=['GET'])
def stock_chart_data(ticker):
    period = request.args.get('period', '1mo')  # Defaultně 1 měsíc
    try:
        stock = yf.Ticker(ticker)
        data = stock.history(period=period)
        
        dates = data.index.strftime('%Y-%m-%d').tolist()  # Datum jako seznam řetězců
        prices = data['Close'].tolist()  # Uzavírací ceny
        
        return jsonify({'dates': dates, 'prices': prices})
    
    except Exception as e:
        logging.error(f"Chyba při načítání dat pro graf: {e}")
        return jsonify({'error': 'Nepodařilo se načíst data pro graf'}), 500
    
    

import os
import logging
import openai
import yfinance as yf
from flask import render_template, Blueprint
from dotenv import load_dotenv

# Načtení .env souboru pro získání klíčů
load_dotenv()

# Získání API klíčů z prostředí
POLYGON_API_KEY = os.getenv('POLYGON_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Zkontrolujeme, jestli se OpenAI klíč správně načetl
if not OPENAI_API_KEY:
    raise ValueError("OpenAI API klíč nebyl nalezen v prostředí.")

# Nastavíme OpenAI API klíč pro knihovnu openai
openai.api_key = OPENAI_API_KEY

# Funkce pro výpočet předpokládané změny ceny na základě růstu
def calculate_price_change(current_price, growth_rate, eps):
    # Pokud není k dispozici růstový odhad nebo EPS, nelze vypočítat
    if growth_rate is None or eps is None:
        return None
    
    # Odhad ceny na základě růstu EPS (velmi zjednodušené, bez dalších faktorů)
    future_price = current_price * (1 + growth_rate)
    return future_price

# Funkce pro provedení AI analýzy
def ai_stock_analysis(ticker, historical_data, current_price, eps, growth_rate):
    try:
        # Základní výpočet procentuální změny
        future_price = calculate_price_change(current_price, growth_rate, eps)
        estimated_change = ((future_price - current_price) / current_price) * 100 if future_price else "nelze odhadnout"

        prompt = (
            f"Analyzuj historická data pro akcii {ticker} a odhadni budoucí vývoj ceny akcie na základě následujících údajů:\n"
            f"Historická data:\n{historical_data}\n"
            f"Současná cena: {current_price}\n"
            f"EPS (Zisk na akcii): {eps}\n"
            f"Odhadovaný růst: {growth_rate}\n"
            f"Odhadovaný budoucí vývoj ceny: {future_price}\n"
            f"Jaká je očekávaná procentuální změna ceny této akcie ({estimated_change}%) a kdy k tomu může dojít? "
            "Odhadni časový rámec, kdy by tato změna mohla nastat."
        )
        
        # Volání OpenAI API s použitím modelu gpt-3.5-turbo
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # Nahraď modelem, ke kterému máš přístup
            messages=[
                {"role": "system", "content": "Jsi asistent pro analýzu akcií."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300  # Zvýšíme limit pro lepší odpovědi
        )
        ai_analysis = response['choices'][0]['message']['content'].strip()

        if not ai_analysis:
            logging.error("OpenAI API vrátilo prázdnou odpověď.")
            return "AI analýzu nebylo možné provést."

        return ai_analysis
    except Exception as e:
        logging.error(f"Chyba při volání OpenAI API: {e}")
        return "AI analýzu nebylo možné provést."

# Trasa pro zobrazení AI analýzy
@stock_bp.route('/ai_analysis/<ticker>', methods=['GET'])
def get_ai_analysis(ticker):
    try:
        # Získání historických dat
        stock = yf.Ticker(ticker)
        historical_data = stock.history(period='5y')
        eps = stock.info.get('trailingEps', None)
        estimated_growth_rate = stock.info.get('earningsGrowth', None)

        # Aktuální cena akcie
        current_price = stock.history(period='1d')['Close'].iloc[-1]

        # AI analýza
        ai_analysis = ai_stock_analysis(ticker, historical_data, current_price, eps, estimated_growth_rate)

        # Debugging informace
        logging.info(f"AI analýza pro {ticker}: {ai_analysis}")

        # Renderování šablony s AI analýzou
        return render_template('ai_analysis.html', 
                               ticker=ticker, 
                               ai_analysis=ai_analysis, 
                               current_price=current_price, 
                               eps=eps, 
                               growth_rate=estimated_growth_rate)

    except Exception as err:
        logging.error(f"Něco se pokazilo: {err}")
        return render_template('ai_analysis.html', error=f"Něco se pokazilo: {err}", ticker=ticker)


from flask import Blueprint, render_template
import yfinance as yf
import openai
import logging

@stock_bp.route('/financials/<ticker>', methods=['GET'])
def get_financials(ticker):
    try:
        # Získání finančních výkazů z yFinance
        stock = yf.Ticker(ticker)
        financials = stock.financials
        balance_sheet = stock.balance_sheet
        cashflow = stock.cashflow

        # Debug: Výpis finančních dat pro kontrolu
        print(f"Financials: {financials}")
        print(f"Balance Sheet: {balance_sheet}")
        print(f"Cashflow: {cashflow}")

        # Převedeme finanční data do formátu pro šablonu (řetězce pro lepší čitelnost)
        financials_str = financials.to_string() if not financials.empty else "Data nejsou k dispozici"
        balance_sheet_str = balance_sheet.to_string() if not balance_sheet.empty else "Data nejsou k dispozici"
        cashflow_str = cashflow.to_string() if not cashflow.empty else "Data nejsou k dispozici"

        # Vytvoříme prompt pro OpenAI pro analýzu výkazů
        prompt = (
            f"Analyzuj následující finanční výkazy pro společnost {ticker} a shrň jejich obsah:\n\n"
            f"Finanční výkaz:\n{financials_str}\n\n"
            f"Rozvaha:\n{balance_sheet_str}\n\n"
            f"Přehled cash flow:\n{cashflow_str}\n\n"
            "Shrň hlavní závěry a stav společnosti. Zmiň se o růstu, ziscích, dluhu a vyhlídkách do budoucna."
        )

        # Volání OpenAI API pro analýzu
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Jsi finanční analytik."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300
        )
        ai_analysis = response['choices'][0]['message']['content'].strip()

        # Další finanční informace (mock data, pokud nejsou dostupná z yFinance)
        stock_info = stock.info
        current_price = stock_info.get('currentPrice', "N/A")
        eps = stock_info.get('eps', "N/A")
        growth_rate = stock_info.get('growthRate', "N/A")
        ai_analysis_contains_growth = "růst" in ai_analysis.lower()

        # Mock data pro očekávanou změnu ceny
        expected_price_change = "10 %"  # Nebo získat z OpenAI odpovědi
        expected_time_frame = "6 měsíců"  # Nebo získat z OpenAI odpovědi

        # Renderování šablony s finančními výkazy a analýzou
        return render_template(
            'financials.html', 
            ticker=ticker,
            financials=financials_str,
            balance_sheet=balance_sheet_str,
            cashflow=cashflow_str,
            ai_analysis=ai_analysis,
            current_price=current_price,
            eps=eps,
            growth_rate=growth_rate,
            ai_analysis_contains_growth=ai_analysis_contains_growth,
            expected_price_change=expected_price_change,
            expected_time_frame=expected_time_frame
        )

    except Exception as err:
        logging.error(f"Něco se pokazilo při načítání finančních výkazů: {err}")
        return render_template('financials.html', error=f"Něco se pokazilo: {err}", ticker=ticker)
