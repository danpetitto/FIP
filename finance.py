import requests
import os
import pandas as pd
from polygon import RESTClient
from dotenv import load_dotenv
import time

# Načtení proměnných z .env souboru
load_dotenv()

# API klíče z .env souboru
OPENFIGI_API_KEY = os.getenv('OPENFIGI_API_KEY')
POLYGON_API_KEY = os.getenv('POLYGON_API_KEY')

# Polygon.io REST Client
client = RESTClient(POLYGON_API_KEY)

#test 
# Funkce pro získání měnového kurzu pomocí Polygon API
def get_fx_rate_polygon(from_currency, to_currency):
    url = f"https://api.polygon.io/v1/conversion/{from_currency}/{to_currency}?amount=1&precision=2&apiKey={POLYGON_API_KEY}"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        if 'converted' in data:
            return data['converted']  # Získání konvertovaného kurzu
        else:
            print("Chyba: kurz nebyl nalezen.")
            return None
    else:
        print(f"Chyba při získávání měnového kurzu: {response.status_code}")
        return None

# Jednoduchá cache pro uložení ISIN a tickerů
ticker_cache = {}

# Funkce pro získání tickeru z OpenFIGI API na základě ISIN s cachingem
def get_ticker_from_isin(isin):
    if isin in ticker_cache:
        return ticker_cache[isin]
    
    headers = {
        'Content-Type': 'application/json',
        'X-OPENFIGI-APIKEY': OPENFIGI_API_KEY
    }
    data = [{"idType": "ID_ISIN", "idValue": isin}]
    
    try:
        response = requests.post('https://api.openfigi.com/v3/mapping', json=data, headers=headers)
        if response.status_code == 200:
            figi_data = response.json()
            if figi_data and len(figi_data[0]['data']) > 0:
                ticker = figi_data[0]['data'][0].get('ticker')
                ticker_cache[isin] = ticker
                return ticker
        else:
            print(f"Chyba při získávání tickeru pro ISIN {isin}: {response.text}")
    except Exception as e:
        print(f"Výjimka při získávání tickeru pro ISIN {isin}: {str(e)}")
    
    return None

# Funkce pro získání zpožděné ceny z Polygon.io pomocí RESTClient
def get_delayed_price_polygon(ticker):
    if not ticker:
        return None
    try:
        # Získáme agregovaná data (OHLCV), kde close představuje nejaktuálnější cenu
        url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?adjusted=true&apiKey={POLYGON_API_KEY}"
        response = requests.get(url)
        
        if response.status_code == 200:
            results = response.json().get('results', [])
            if len(results) > 0:
                return results[0].get('c', None)  # 'c' je uzavírací cena pro poslední den
        else:
            print(f"Chyba při získávání zpožděných dat pro {ticker}: {response.status_code}")
            return None
    except Exception as e:
        print(f"Chyba při získávání dat pro {ticker}: {str(e)}")
        return None

# Funkce pro přidání zpožděných cen do dat pomocí ISIN
def add_current_prices(data):
    data['Ticker'] = data['ISIN'].apply(get_ticker_from_isin)
    time.sleep(1)  # Pauza mezi voláními API
    data['Aktuální Cena'] = data['Ticker'].apply(get_delayed_price_polygon)  # Získání zpožděné ceny
    return data

#testování investovaná částka

# Výpočet investované částky - pouze pro otevřené (neprodané) pozice
def calculate_invested_amount(data):
    # Skupinujeme podle ISIN a sečteme počet akcií (kladné = nákup, záporné = prodej)
    position_summary = data.groupby('ISIN')['Počet'].sum().reset_index()

    # Filtrujeme pouze ISINy, které mají kladný součet (pozice stále otevřené)
    open_positions_filtered = position_summary[position_summary['Počet'] > 0]

    # Připojíme zpět k původnímu datasetu, abychom získali další informace (např. pořizovací cena, měna)
    open_positions = pd.merge(open_positions_filtered, data, on='ISIN', how='left')

    # Inicializujeme celkovou investovanou částku
    total_invested = 0

    # Výpočet investované částky
    for _, row in open_positions.iterrows():
        if row['Počet_x'] > 0:  # Pouze kladné pozice
            currency = row['Unnamed: 8']  # Zde je měna (např. USD, CZK)
            amount = row['Cena'] * row['Počet_x']  # Cena * Počet akcií

            if currency != 'EUR':
                fx_rate = row['Směnný kurz']  # Použijeme směnný kurz z CSV
                if fx_rate:
                    amount_in_eur = amount / fx_rate  # Převod na EUR
                else:
                    continue  # Přeskočíme tuto pozici, pokud není dostupný směnný kurz
            else:
                amount_in_eur = amount  # Pokud je měna EUR, nepřevádíme

            # Přičítáme investovanou částku
            total_invested += amount_in_eur

    # Vrátíme celkovou investovanou částku naformátovanou v EUR
    return round(total_invested, 2)

# Výpočet hodnoty portfolia - pouze pro otevřené (neprodané) pozice
def calculate_portfolio_value(data):
    # Skupinujeme podle ISIN a sečteme počet akcií (kladné = nákup, záporné = prodej)
    position_summary = data.groupby('ISIN')['Počet'].sum().reset_index()

    # Filtrujeme pouze ISINy, které mají kladný součet (znamená to, že pozice jsou stále otevřené)
    open_positions_filtered = position_summary[position_summary['Počet'] > 0]

    # Připojíme zpět k původnímu datasetu, abychom získali další informace (např. ticker)
    open_positions = pd.merge(open_positions_filtered, data, on='ISIN', how='left')

    # Získání tickeru pro každou neprodanou pozici
    open_positions['Ticker'] = open_positions['ISIN'].apply(get_ticker_from_isin)

    # Získání aktuální ceny pro každou neprodanou pozici pomocí Polygon API
    open_positions['Aktuální Cena'] = open_positions['Ticker'].apply(get_delayed_price_polygon)

    # Výpočet hodnoty pozice (Počet akcií * Aktuální cena)
    open_positions['Hodnota pozice'] = open_positions['Počet_x'] * open_positions['Aktuální Cena']

    # Výpočet celkové hodnoty portfolia - součet hodnot všech neprodaných pozic
    total_portfolio_value = open_positions['Hodnota pozice'].sum()

    return total_portfolio_value

# Výpočet realizovaného zisku/ztráty
def calculate_realized_profit(data):
    # Najdeme uzavřené (prodané) pozice
    closed_positions = data[data['Počet'] < 0].copy()

    # Pro každou uzavřenou pozici musíme najít odpovídající nákupní pozici
    realized_profits = []

    for index, sale in closed_positions.iterrows():
        # Najdeme odpovídající nákupní pozici pro daný ISIN
        matching_purchase = data[(data['ISIN'] == sale['ISIN']) & (data['Počet'] > 0)].copy()

        if not matching_purchase.empty:
            # Pro jednoduchost vezmeme první nalezený nákup
            purchase = matching_purchase.iloc[0]
            
            # Výpočet realizovaného zisku/ztráty: (Prodejní cena - Nákupní cena) * Počet prodaných akcií
            realized_profit = (sale['Cena'] - purchase['Cena']) * abs(sale['Počet'])
            realized_profits.append(realized_profit)

    # Sečteme všechny realizované zisky/ztráty
    return sum(realized_profits)

def calculate_unrealized_profit(total_portfolio_value, total_invested):
    # Nerealizovaný zisk je rozdíl mezi hodnotou portfolia a investovanou částkou
    unrealized_profit = total_portfolio_value - total_invested
    return round(unrealized_profit, 2)

# Získání tickeru z OpenFIGI API na základě ISIN
def get_ticker_from_isin(isin):
    if isin in ticker_cache:
        return ticker_cache[isin]
    
    headers = {
        'Content-Type': 'application/json',
        'X-OPENFIGI-APIKEY': OPENFIGI_API_KEY
    }
    data = [{"idType": "ID_ISIN", "idValue": isin}]
    
    try:
        response = requests.post('https://api.openfigi.com/v3/mapping', json=data, headers=headers)
        if response.status_code == 200:
            figi_data = response.json()
            if figi_data and len(figi_data[0]['data']) > 0:
                ticker = figi_data[0]['data'][0].get('ticker')
                ticker_cache[isin] = ticker
                return ticker
        else:
            print(f"Chyba při získávání tickeru pro ISIN {isin}: {response.text}")
    except Exception as e:
        print(f"Výjimka při získávání tickeru pro ISIN {isin}: {str(e)}")
    
    return None

# Funkce pro získání dividendových dat z Polygon.io

def get_dividend_data_polygon(ticker):
    if not ticker:
        return None
    try:
        # Získáme dividendová data pro daný ticker
        url = f"https://api.polygon.io/v2/reference/dividends/{ticker}?apiKey={POLYGON_API_KEY}"
        response = requests.get(url)
        
        if response.status_code == 200:
            dividend_data = response.json().get('results', [])
            return dividend_data  # Vracíme seznam dividendových dat
        else:
            print(f"Chyba při získávání dividend pro {ticker}: {response.status_code}")
            return None
    except Exception as e:
        print(f"Chyba při získávání dividend pro {ticker}: {str(e)}")
        return None
    
    # Výpočet celkových dividend na základě tickeru a dat o dividendách
def calculate_total_dividends(data):
    total_dividends = 0
    for _, row in data.iterrows():
        # Získání tickeru na základě ISIN
        ticker = get_ticker_from_isin(row['ISIN'])
        dividends = get_dividend_data_polygon(ticker)
        
        if dividends:
            # Spočítáme dividendy pro každou akcii, kterou vlastníme
            for dividend in dividends:
                dividend_amount = dividend['amount']
                # Pokud není sloupec 'Počet_x', zkusíme použít 'Počet'
                total_dividends += dividend_amount * row.get('Počet_x', row['Počet'])
    return round(total_dividends, 2)

# Výpočet dividendového výnosu
def calculate_dividend_yield(total_dividends, portfolio_value):
    if portfolio_value == 0:
        return 0
    return round((total_dividends / portfolio_value) * 100, 2)

# Predikce dividend na 10 let
def predict_dividends_for_10_years(total_dividends):
    return round(total_dividends * 10, 2)

# Výpočet daně z dividend
def calculate_tax_on_dividends(total_dividends, tax_rate=15):
    tax_amount = total_dividends * (tax_rate / 100)
    return round(tax_amount, 2)

def calculate_dividend_cash(data):
    # Spočítáme celkové dividendy
    total_dividends = calculate_total_dividends(data)
    
    # Spočítáme hodnotu portfolia
    portfolio_value = calculate_portfolio_value(data)
    
    # Spočítáme dividendový výnos
    dividend_yield = calculate_dividend_yield(total_dividends, portfolio_value)
    
    # Predikce dividend na 10 let
    dividend_prediction_10_years = predict_dividends_for_10_years(total_dividends)
    
    # Spočítáme daň z dividend
    tax_on_dividends = calculate_tax_on_dividends(total_dividends)
    
    # Výsledky
    results = {
        "total_dividends": total_dividends,
        "dividend_yield": dividend_yield,
        "dividend_prediction_10_years": dividend_prediction_10_years,
        "tax_on_dividends": tax_on_dividends
    }
    
    return results

def calculate_fees(data):
    # Najdeme všechny sloupce, které obsahují text "Transaction and/or third"
    fee_columns = [col for col in data.columns if 'Transaction and/or third' in col]

    # Pokud takové sloupce existují, sečteme všechny hodnoty z těchto sloupců
    if fee_columns:
        total_fees = data[fee_columns].sum().sum()  # První sum() sečte řádky, druhá sum() sečte všechny sloupce
        return total_fees
    else:
        return 0




