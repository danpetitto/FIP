import requests
import pandas as pd
from finance import get_ticker_from_isin  # Z finance.py

# Funkce pro získání zpožděné ceny z Polygon API
def get_delayed_price_polygon(ticker):
    api_key = "your_polygon_api_key"  # Musíš mít platný Polygon API klíč
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?adjusted=true&apiKey={api_key}"
    
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        if data.get('results'):
            return data['results'][0]['c']  # 'c' je cena uzavření
    return None

# Funkce pro získání informací o akciích podle ISIN
def get_stock_info(isin):
    ticker = get_ticker_from_isin(isin)
    if not ticker:
        return {
            'Symbol': 'Neznámý',
            'Kupní hodnota': 'Neznámá',
            'Aktuální hodnota': 'Neznámá',
            'Počet akcií': 'Neznámé',
            'Profit': 'Neznámý'
        }

    # Najdeme odpovídající řádek v datasetu
    stock_data = data[data['ISIN'] == isin]
    if stock_data.empty:
        return {
            'Symbol': ticker,
            'Kupní hodnota': 'Neznámá',
            'Aktuální hodnota': 'Neznámá',
            'Počet akcií': 'Neznámé',
            'Profit': 'Neznámý'
        }

    # Výpočet hodnot
    pocet_akcii = stock_data['Počet'].values[0]
    kupni_cena = stock_data['Cena'].values[0]
    aktualni_cena = get_delayed_price_polygon(ticker)

    if not aktualni_cena:
        return {
            'Symbol': ticker,
            'Kupní hodnota': kupni_cena,
            'Aktuální hodnota': 'Neznámá',
            'Počet akcií': pocet_akcii,
            'Profit': 'Neznámý'
        }

    aktualni_hodnota = aktualni_cena * pocet_akcii
    profit = aktualni_hodnota - (kupni_cena * pocet_akcii)

    return {
        'Symbol': ticker,
        'Kupní hodnota': round(kupni_cena * pocet_akcii, 2),
        'Aktuální hodnota': round(aktualni_hodnota, 2),
        'Počet akcií': pocet_akcii,
        'Profit': round(profit, 2)
    }
