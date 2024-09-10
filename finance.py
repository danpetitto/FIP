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

#testování

def simple_debug_calculate_invested(data):
    total_invested = 0

    # Použijeme pouze kladné hodnoty ve sloupci 'Počet'
    for _, row in data.iterrows():
        if row['Počet'] > 0:
            amount = row['Cena'] * row['Počet']
            print(f"ISIN: {row['ISIN']}, Počet: {row['Počet']}, Cena: {row['Cena']}, Investovaná částka: {amount}")
            total_invested += amount

    return f"Investováno: {round(total_invested, 2)} €"

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

# Výpočet nerealizovaného zisku (otevřené pozice: počet > 0)
def calculate_unrealized_profit(data):
    data['Nerealizovaný zisk'] = (data['Aktuální Cena'] - data['Cena']) * data['Počet']
    open_positions = data[data['Počet'] > 0]
    return open_positions['Nerealizovaný zisk'].sum()

def calculate_dividend_cash(data):
    return 0  # Zatím placeholder pro dividendy

def calculate_fees(data):
    if 'Transaction and/or third-party fees' in data.columns:
        total_fees = data['Transaction and/or third-party fees'].sum()
        return total_fees
    else:
        return 0
