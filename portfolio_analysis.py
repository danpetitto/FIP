import requests
import os
import time
import pandas as pd
from dotenv import load_dotenv
from cachetools import TTLCache

# Načtení API klíčů z .env souboru
load_dotenv()
OPENFIGI_API_KEY = os.getenv('OPENFIGI_API_KEY')
POLYGON_API_KEY = os.getenv('POLYGON_API_KEY')

# Cache s časovým omezením (TTLCache) pro ISINy a tickery
ticker_cache = TTLCache(maxsize=100, ttl=3600)  # Cache platí 1 hodinu

# Funkce pro získání tickeru z OpenFIGI API na základě ISIN
def get_ticker_from_isin(isin):
    # Zkontrolujeme, zda je ISIN v cache
    if isin in ticker_cache:
        return ticker_cache[isin]

    # Pauza mezi voláními API (zabraňuje překročení limitu požadavků)
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
        # Pauza mezi voláními API (pro Polygon.io)
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

import pandas as pd

def analyze_open_positions(data, tickers_prices):
    # Opatření 1: Součet všech transakcí pro každý ISIN
    position_summary = data.groupby('ISIN')['Počet'].sum().reset_index()
    
    # Opatření 2: Filtrování pouze kladných počtů (otevřené pozice)
    open_positions_filtered = position_summary[position_summary['Počet'] > 0]
    
    # Opatření 3: Odstranění duplicitních ISIN
    open_positions_filtered = open_positions_filtered.drop_duplicates(subset=['ISIN'])

    # Opatření 4: Mapování tickerů na ISIN
    open_positions_filtered['Ticker'] = open_positions_filtered['ISIN'].map(tickers_prices['ticker'])
    
    # Opatření 5: Mapování aktuální ceny na ISIN
    open_positions_filtered['Aktuální Cena'] = open_positions_filtered['ISIN'].map(tickers_prices['current_price'])
    
    # Opatření 6: Odstranění řádků, kde chybí ticker nebo aktuální cena
    open_positions_filtered = open_positions_filtered.dropna(subset=['Ticker', 'Aktuální Cena'])

    # Opatření 7: Spojení s původními daty pro získání nákupní ceny (unikátní ISINy)
    open_positions_filtered = pd.merge(open_positions_filtered, data[['ISIN', 'Cena']].drop_duplicates(subset=['ISIN']), on='ISIN', how='left')
    
    # Opatření 8: Zajištění, že nejsou žádné nulové nebo neplatné ceny
    open_positions_filtered = open_positions_filtered[open_positions_filtered['Cena'] > 0]

    # Opatření 9: Výpočet nákupní hodnoty (Cena * Počet)
    open_positions_filtered['Nákupní Hodnota'] = open_positions_filtered['Cena'] * open_positions_filtered['Počet']

    # Opatření 10: Výpočet aktuální hodnoty (Aktuální cena * Počet)
    open_positions_filtered['Aktuální Hodnota'] = open_positions_filtered['Aktuální Cena'] * open_positions_filtered['Počet']

    # Výpočet profitu
    open_positions_filtered['Profit'] = open_positions_filtered['Aktuální Hodnota'] - open_positions_filtered['Nákupní Hodnota']

    # Zobrazení finálních výsledků po všech opatřeních
    print("\nFinální otevřené pozice po aplikaci všech opatření:")
    print(open_positions_filtered[['ISIN', 'Ticker', 'Počet', 'Cena', 'Nákupní Hodnota', 'Aktuální Hodnota', 'Profit']])

    # Návrat výsledného dataframe
    return open_positions_filtered[['ISIN', 'Ticker', 'Počet', 'Cena', 'Nákupní Hodnota', 'Aktuální Hodnota', 'Profit']]

# Testovací funkce (příklad použití)
def main():
    # Příklad slovníku s tickers_prices (nahraď skutečnými daty)
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

    # Příklad testovacích dat (představuje transakce)
    data = pd.DataFrame({
        'ISIN': ['US88160R1014', 'US0231351067', 'GB00BLFHRK18', 'US88160R1014', 'GB00BF3ZNS54'],
        'Počet': [2, -2, 5, 1, 10],
        'Cena': [200, 150, 5, 190, 0]
    })

    # Spuštění analýzy otevřených pozic s 10 opatřeními
    open_positions = analyze_open_positions(data, tickers_prices)
    print("\nVýsledné otevřené pozice:")
    print(open_positions)

if __name__ == "__main__":
    main()


