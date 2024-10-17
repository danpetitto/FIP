import requests
import os
import pandas as pd
from polygon import RESTClient
from dotenv import load_dotenv
import time
import schedule
import datetime

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
def get_delayed_price_polygon(ticker, date=None):
    if not ticker:
        return None
    
    # Rozhodneme se, zda získat cenu pro konkrétní den nebo poslední dostupnou cenu
    if date:
        url = f"https://api.polygon.io/v1/open-close/{ticker}/{date}?adjusted=true&apiKey={POLYGON_API_KEY}"
    else:
        url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?adjusted=true&apiKey={POLYGON_API_KEY}"
    
    print(f"Fetching data for {ticker} on {date}: {url}")

    try:
        response = requests.get(url)
        if response.status_code == 200:
            if date:
                # Pro konkrétní den získáváme zavírací cenu
                result = response.json().get('close')
            else:
                # Získáváme poslední dostupnou cenu
                results = response.json().get('results', [])
                result = results[0].get('c') if results else None

            if result:
                print(f"Cena pro {ticker} k datu {date}: {result}")
                return result
            else:
                print(f"Žádná data pro {ticker} k datu {date}")
                return None
        else:
            print(f"Chyba při získávání dat pro {ticker}: {response.status_code}")
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

import requests

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
        ticker = get_ticker_from_isin(row['ISIN'])
        if ticker:
            dividends = get_dividend_data_polygon(ticker)
            if dividends:
                for dividend in dividends:
                    dividend_amount = dividend['amount']
                    total_dividends += dividend_amount * row.get('Počet_x', row.get('Počet', 0))
    return round(total_dividends, 2)

# Výpočet dividendového výnosu (dividend yield)
def calculate_dividend_yield(total_dividends, portfolio_value):
    if portfolio_value == 0:
        print("Portfolio value is zero, cannot calculate dividend yield.")
        return 0  # Abychom se vyhnuli dělení nulou
    return round((total_dividends / portfolio_value) * 100, 2)

# Predikce dividend na 10 let
def predict_dividends_for_10_years(total_dividends):
    return round(total_dividends * 10, 2)

# Výpočet daně z dividend (14 %)
def calculate_tax_on_dividends(total_dividends, tax_rate=14):
    if total_dividends == 0:
        print("No dividends, no tax.")
        return 0  # Pokud nejsou žádné dividendy, není žádná daň
    tax_amount = total_dividends * (tax_rate / 100)
    return round(tax_amount, 2)

# Hlavní funkce pro výpočet všech dividendových údajů a jejich souhrn
def calculate_dividend_cash(data):
    # Spočítáme celkové dividendy
    total_dividends = calculate_total_dividends(data)
    print(f"Celková výše dividend: {total_dividends}")  # Ladicí výstup

    # Spočítáme hodnotu portfolia
    portfolio_value = calculate_portfolio_value(data)
    print(f"Hodnota portfolia: {portfolio_value}")  # Ladicí výstup

    # Spočítáme dividendový výnos
    dividend_yield = calculate_dividend_yield(total_dividends, portfolio_value)
    print(f"Dividendový výnos: {dividend_yield}%")  # Ladicí výstup

    # Predikce dividend na 10 let
    dividend_prediction_10_years = predict_dividends_for_10_years(total_dividends)
    print(f"Predikce dividend na 10 let: {dividend_prediction_10_years} €")  # Ladicí výstup

    # Spočítáme daň z dividend (14 %)
    tax_on_dividends = calculate_tax_on_dividends(total_dividends)
    print(f"Daň z dividend: {tax_on_dividends} €")  # Ladicí výstup

    # Výsledky
    results = {
        "total_dividends": total_dividends,
        "dividend_yield": dividend_yield,
        "dividend_prediction_10_years": dividend_prediction_10_years,
        "tax_on_dividends": tax_on_dividends,
        "portfolio_value": portfolio_value
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
    
def calculate_unrealized_profit_percentage(unrealized_profit, portfolio_value):
    if portfolio_value == 0:
        return 0  # Vyhneme se dělení nulou
    return round((unrealized_profit / portfolio_value) * 100, 2)

def calculate_realized_profit_percentage(realized_profit, portfolio_value):
    if portfolio_value == 0:
        return 0  # Vyhneme se dělení nulou
    return round((realized_profit / portfolio_value) * 100, 2)

def calculate_fees_percentage(total_fees, portfolio_value):
    if portfolio_value == 0:
        return 0  # Vyhneme se dělení nulou
    return round((total_fees / portfolio_value) * 100, 2)

def calculate_forex_impact_percentage(forex_impact, portfolio_value):
    if portfolio_value == 0:
        return 0  # Vyhneme se dělení nulou
    return round((forex_impact / portfolio_value) * 100, 2)

# Funkce pro získání inflace pro rok 2024
def get_czech_inflation_2024():
    # Prozatím ručně zadáváme inflaci pro rok 2024, dokud není API spolehlivé
    inflation_rate = 2.8  # Roční míra inflace v České republice pro rok 2024
    print(f"Inflace za rok 2024: {inflation_rate}%")
    return inflation_rate

# Funkce pro výpočet hodnoty portfolia po započtení inflace
def calculate_portfolio_with_inflation(portfolio_value, inflation_rate):
    if inflation_rate is None:
        print("Inflace nebyla dostupná, vracíme původní hodnotu portfolia.")
        return portfolio_value  # Pokud nemáme inflaci, vrátíme původní hodnotu
    
    # Inflaci převedeme na procentuální vyjádření a upravíme hodnotu portfolia
    inflation_adjustment = portfolio_value * (inflation_rate / 100)
    portfolio_with_inflation = portfolio_value - inflation_adjustment
    
    print(f"Original Portfolio Value: {portfolio_value} €")
    print(f"Inflation Rate Applied: {inflation_rate} %")
    print(f"Portfolio Value after Inflation Adjustment: {portfolio_with_inflation} €")  # Debug výpis
    
    return portfolio_with_inflation

# Příklad použití
portfolio_value = 10000  # Příklad hodnoty portfolia
inflation_rate = get_czech_inflation_2024()  # Použijeme funkci pro inflaci 2024

if inflation_rate is not None:
    portfolio_with_inflation = calculate_portfolio_with_inflation(portfolio_value, inflation_rate)  # Spočítáme hodnotu portfolia po inflaci
    print(f"Final Portfolio Value (adjusted for inflation): {portfolio_with_inflation} €")
else:
    print("Nepodařilo se získat aktuální inflaci.")
