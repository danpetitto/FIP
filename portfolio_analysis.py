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

# Funkce pro zpracování otevřených pozic, které nebyly prodány
def analyze_open_positions(data):
    # Krok 1: Skupinování podle ISIN a sečtení všech nákupů a prodejů (kladné = nákup, záporné = prodej)
    position_summary = data.groupby('ISIN')['Počet'].sum().reset_index()

    # Krok 2: Filtrování pouze těch ISINů, kde zůstává kladný počet akcií (pozice stále otevřené)
    open_positions_filtered = position_summary[position_summary['Počet'] > 0]

    # Krok 3: Spojení s původními daty pro získání dalších informací (pořizovací cena, transakční data)
    open_positions = pd.merge(open_positions_filtered, data, on='ISIN', how='left')

    # Krok 4: Získání tickeru pro každou otevřenou pozici
    open_positions['Ticker'] = open_positions['ISIN'].apply(get_ticker_from_isin)

    # Krok 5: Získání aktuální (zpožděné) ceny pro každou otevřenou pozici
    open_positions['Aktuální Cena'] = open_positions['Ticker'].apply(get_delayed_price_polygon)

    # Krok 6: Výpočet nákupní hodnoty (Cena * Počet z původních dat)
    open_positions['Nákupní Hodnota'] = open_positions['Cena'] * open_positions['Počet_y']

    # Krok 7: Výpočet aktuální hodnoty (Aktuální cena * Počet z původních dat)
    open_positions['Aktuální Hodnota'] = open_positions['Aktuální Cena'] * open_positions['Počet_y']

    # Krok 8: Výpočet profitu (Aktuální hodnota - Nákupní hodnota)
    open_positions['Profit'] = open_positions['Aktuální Hodnota'] - open_positions['Nákupní Hodnota']

    # Zobrazit pouze otevřené pozice (neprodány)
    print("\nOtevřené pozice:")
    print(open_positions[['ISIN', 'Ticker', 'Počet_y', 'Cena', 'Nákupní Hodnota', 'Aktuální Hodnota', 'Profit']])

    # Vrátit výsledný dataframe s rozebranými pozicemi
    return open_positions[['ISIN', 'Ticker', 'Počet_y', 'Cena', 'Nákupní Hodnota', 'Aktuální Hodnota', 'Profit']]

# Testovací funkce (příklad použití)
def main():
    # Příklad dat (můžeš nahradit skutečnými daty)
    data = {
        'ISIN': ['US88160R1014', 'US0231351067', 'GB00BLFHRK18'],
        'Počet': [10, 15, 0],  # 0 znamená prodané, > 0 znamená otevřené pozice
        'Cena': [200, 150, 5]  # Nákupní cena
    }
    data = pd.DataFrame(data)

    # Analyzovat otevřené pozice
    open_positions = analyze_open_positions(data)
    print(open_positions)

if __name__ == "__main__":
    main()
