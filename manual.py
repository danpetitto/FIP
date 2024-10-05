import os
import requests
from dotenv import load_dotenv
from models import db, Portfolio

# Načtení klíče z .env souboru
load_dotenv()
POLYGON_API_KEY = os.getenv('POLYGON_API_KEY')

def get_current_price(ticker):
    """
    Získá aktuální cenu akcie pomocí Polygon API.
    """
    url = f"https://api.polygon.io/v1/last/stocks/{ticker}?apiKey={POLYGON_API_KEY}"
    
    try:
        response = requests.get(url)
        response.raise_for_status()

        data = response.json()
        return data['last']['price']  # Získání poslední ceny

    except requests.exceptions.RequestException as e:
        print(f"Chyba při volání Polygon API: {e}")
        return None


def store_manual_trade(portfolio_id, ticker, datum, typ_obchodu, cena, pocet, hodnota, poplatky):
    portfolio = Portfolio.query.get(portfolio_id)

    if not portfolio:
        raise ValueError("Portfolio not found")

    if cena == 0:
        current_price = get_current_price(ticker)
        if current_price:
            cena = current_price
            hodnota = cena * pocet
        else:
            raise ValueError("Nelze získat aktuální cenu pro ticker.")

    portfolio.total_value += hodnota  # Aktualizace celkové hodnoty
    portfolio.total_trades += 1       # Zvýšení počtu obchodů
    portfolio.total_fees += poplatky  # Aktualizace celkových poplatků

    # Logika pro aktualizaci akcií v portfoliu
    stock = next((stock for stock in portfolio.stocks if stock['ticker'] == ticker), None)
    if stock:
        stock['value'] += hodnota
        stock['total_shares'] += pocet
    else:
        portfolio.stocks.append({
            'ticker': ticker,
            'value': hodnota,
            'total_shares': pocet
        })

    db.session.commit()
