import requests
import pandas as pd
from finance import get_ticker_from_isin  # Z finance.py

# Funkce pro získání zpožděné ceny z Polygon API
def get_delayed_price_polygon(ticker):
    api_key = "your_polygon_api_key"  # Musíš mít platný Polygon API klíč
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?adjusted=true&apiKey={api_key}"
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data.get('results'):
                return data['results'][0]['c']  # 'c' je cena uzavření
    except Exception as e:
        print(f"Chyba při získávání ceny pro {ticker}: {e}")
    return None

# Funkce pro získání informací o akciích podle ISIN
def get_stock_info(data, isin):  
    # Získání tickeru na základě ISIN
    ticker = get_ticker_from_isin(isin)
    if not ticker:
        return {
            'Symbol': 'Neznámý',
            'Kupní hodnota': 'Neznámá',
            'Aktuální hodnota': 'Neznámá',
            'Počet akcií': 'Neznámé',
            'Profit': 'Neznámý'
        }

    # Vyfiltrování dat pro konkrétní ISIN
    stock_data = data[data['ISIN'] == isin]
    if stock_data.empty:
        return {
            'Symbol': ticker,
            'Kupní hodnota': 'Neznámá',
            'Aktuální hodnota': 'Neznámá',
            'Počet akcií': 'Neznámé',
            'Profit': 'Neznámý'
        }

    # Výpočet počtu akcií a kupní ceny
    pocet_akcii = stock_data['Počet'].sum()  # Sčítáme počet akcií pro všechny řádky daného ISIN
    kupni_cena = stock_data['Cena'].mean()  # Průměrná kupní cena

    # Získání aktuální ceny akcie
    aktualni_cena = get_delayed_price_polygon(ticker)
    if aktualni_cena is None:
        return {
            'Symbol': ticker,
            'Kupní hodnota': round(kupni_cena * pocet_akcii, 2),
            'Aktuální hodnota': 'Neznámá',
            'Počet akcií': pocet_akcii,
            'Profit': 'Neznámý'
        }

    # Výpočet hodnoty pozice a profitu
    aktualni_hodnota = aktualni_cena * pocet_akcii
    profit = aktualni_hodnota - (kupni_cena * pocet_akcii)

    # Návrat strukturovaných dat o akcii
    return {
        'Symbol': ticker,
        'Kupní hodnota': round(kupni_cena * pocet_akcii, 2),
        'Aktuální hodnota': round(aktualni_hodnota, 2),
        'Počet akcií': pocet_akcii,
        'Profit': round(profit, 2)
    }
