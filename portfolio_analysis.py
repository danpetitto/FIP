import requests
import os
import time
import pandas as pd
from dotenv import load_dotenv
from cachetools import TTLCache
import matplotlib.pyplot as plt
from tkinter import Tk
from tkinter.filedialog import askopenfilename

# Načtení API klíčů z .env souboru
load_dotenv()
OPENFIGI_API_KEY = os.getenv('OPENFIGI_API_KEY')
POLYGON_API_KEY = os.getenv('POLYGON_API_KEY')

# Cache s časovým omezením (TTLCache) pro ISINy a tickery a sektory
ticker_cache = TTLCache(maxsize=100, ttl=3600)  # Cache platí 1 hodinu
sector_cache = TTLCache(maxsize=100, ttl=3600)  # Cache pro sektory

# Funkce pro získání tickeru z OpenFIGI API na základě ISIN
def get_ticker_from_isin(isin):
    if isin in ticker_cache:
        return ticker_cache[isin]
    
    time.sleep(2)  # Pauza 2 sekundy mezi voláními API
    headers = {
        'Content-Type': 'application/json',
        'X-OPENFIGI-APIKEY': OPENFIGI_API_KEY
    }
    data = [{"idType": "ID_ISIN", "idValue": isin}]
    response = requests.post('https://api.openfigi.com/v3/mapping', json=data, headers=headers)
    
    if response.status_code == 200:
        figi_data = response.json()
        if figi_data and len(figi_data[0]['data']) > 0:
            ticker = figi_data[0]['data'][0].get('ticker')
            ticker_cache[isin] = ticker  # Uložení tickeru do cache
            return ticker
    else:
        print(f"Chyba při získávání tickeru pro ISIN {isin}: {response.text}")
    return None

# Funkce pro získání zpožděné ceny z Polygon.io API na základě tickeru
def get_delayed_price_polygon(ticker):
    if not ticker:
        return None
    try:
        time.sleep(1)
        url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?adjusted=true&apiKey={POLYGON_API_KEY}"
        response = requests.get(url)
        if response.status_code == 200:
            results = response.json().get('results', [])
            if len(results) > 0:
                return results[0].get('c')  # Uzavírací cena (closing price)
    except Exception as e:
        print(f"Chyba při načítání ceny pro {ticker}: {str(e)}")
    return None

# Funkce pro získání odvětví na základě ticker symbolu (Polygon.io)
def get_sector_from_ticker(ticker):
    if ticker in sector_cache:
        return sector_cache[ticker]

    try:
        url = f"https://api.polygon.io/v3/reference/tickers/{ticker}?apiKey={POLYGON_API_KEY}"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            sector = data.get('results', {}).get('sic_description')  # Načtení odvětví
            if sector:
                sector_cache[ticker] = sector  # Uložení sektoru do cache
            return sector
        else:
            print(f"Chyba při načítání odvětví pro {ticker}: {response.text}")
    except Exception as e:
        print(f"Chyba při načítání odvětví pro {ticker}: {str(e)}")
    
    return None

# Funkce pro analýzu otevřených pozic
def analyze_open_positions(data, tickers_prices):
    position_summary = data.groupby('ISIN')['Počet'].sum().reset_index()
    open_positions_filtered = position_summary[position_summary['Počet'] > 0]
    open_positions_filtered = open_positions_filtered.drop_duplicates(subset=['ISIN'])
    open_positions_filtered['Ticker'] = open_positions_filtered['ISIN'].map(tickers_prices['ticker'])
    open_positions_filtered['Aktuální Cena'] = open_positions_filtered['ISIN'].map(tickers_prices['current_price'])
    open_positions_filtered = open_positions_filtered.dropna(subset=['Ticker', 'Aktuální Cena'])
    open_positions_filtered = pd.merge(open_positions_filtered, data[['ISIN', 'Cena']].drop_duplicates(subset=['ISIN']), on='ISIN', how='left')
    open_positions_filtered = open_positions_filtered[open_positions_filtered['Cena'] > 0]
    open_positions_filtered['Nákupní Hodnota'] = open_positions_filtered['Cena'] * open_positions_filtered['Počet']
    open_positions_filtered['Aktuální Hodnota'] = open_positions_filtered['Aktuální Cena'] * open_positions_filtered['Počet']
    open_positions_filtered['Profit'] = open_positions_filtered['Aktuální Hodnota'] - open_positions_filtered['Nákupní Hodnota']
    return open_positions_filtered[['ISIN', 'Ticker', 'Počet', 'Cena', 'Nákupní Hodnota', 'Aktuální Hodnota', 'Profit']]

# Funkce pro vykreslení grafu rozložení investic
def plot_investment_distribution(open_positions):
    total_invested = open_positions['Nákupní Hodnota'].sum()
    open_positions['Percent Invested'] = (open_positions['Nákupní Hodnota'] / total_invested) * 100
    open_positions_sorted = open_positions.sort_values('Percent Invested', ascending=False)

    plt.figure(figsize=(10, 6))
    plt.bar(open_positions_sorted['Ticker'], open_positions_sorted['Percent Invested'], color='lightblue')
    plt.xlabel('Akcie')
    plt.ylabel('Procento zainvestováno')
    plt.title('Rozložení investic do akcií')
    plt.show()

# Funkce pro načtení dat z CSV souboru
def load_data_from_csv():
    Tk().withdraw()  # Skryje hlavní okno Tkinter
    file_path = askopenfilename(filetypes=[("CSV files", "*.csv")])  # Otevře dialogové okno pro výběr souboru
    if not file_path:
        print("Nebyl vybrán žádný soubor.")
        return None
    try:
        data = pd.read_csv(file_path)
        return data
    except Exception as e:
        print(f"Chyba při načítání souboru: {str(e)}")
        return None

# Hlavní funkce programu
def main():
    # Načti data z CSV souboru (uživatel nahrává CSV)
    data = load_data_from_csv()
    
    if data is not None:
        tickers_prices = {
            'ticker': {
                'US88160R1014': 'TSLA', 
                'US0231351067': 'AMZN', 
                'GB00BLFHRK18': 'CEZ',
                'GB00BF3ZNS54': 'VEN'
            },
            'current_price': {
                'US88160R1014': 230.29, 
                'US0231351067': 186.49, 
                'GB00BLFHRK18': 27.615,
                'GB00BF3ZNS54': 5.00
            }
        }

        # Spuštění analýzy otevřených pozic
        open_positions = analyze_open_positions(data, tickers_prices)

        # Zobrazit graf rozložení investic
        plot_investment_distribution(open_positions)
    else:
        print("Nepodařilo se načíst data z CSV.")

if __name__ == "__main__":
    main()


