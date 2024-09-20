import pandas as pd
from dateutil.relativedelta import relativedelta
from finance import get_ticker_from_isin, get_delayed_price_polygon
from datetime import datetime

def calculate_investment_history(data):
    # Převod sloupce Datum na datetime
    data['Datum'] = pd.to_datetime(data['Datum'], dayfirst=True, errors='coerce')

    # Validace dat
    if data['Datum'].isnull().any():
        raise ValueError("Některá data ve sloupci 'Datum' nejsou validní.")

    # Seřazení podle data
    data = data.sort_values('Datum')

    # Skupinování podle ISIN
    grouped_data = data.groupby('ISIN')

    investment_history = {}

    for isin, group in grouped_data:
        print(f"Zpracovávám ISIN: {isin}")

        # Získáme ticker pro ISIN pomocí funkce z finance.py
        ticker = get_ticker_from_isin(isin)

        if not ticker:
            print(f"Ticker nenalezen pro ISIN: {isin}")
            continue

        start_date = group['Datum'].min()
        end_date = datetime.now()

        current_date = start_date.replace(day=1)

        while current_date <= end_date:
            next_date = (current_date + relativedelta(months=1)).replace(day=1) - pd.Timedelta(days=1)

            # Získáme cenu pomocí funkce z finance.py vždy pro konkrétní konec měsíce
            price_at_end_of_month = get_delayed_price_polygon(ticker, next_date.strftime('%Y-%m-%d'))

            if price_at_end_of_month:
                shares = group[group['Datum'] <= next_date]['Počet'].sum()

                if shares == 0:
                    current_date += relativedelta(months=1)
                    continue

                # Průměrná cena za akcie do daného měsíce
                purchase_price = group[group['Datum'] <= next_date]['Cena'].mean()

                # Hodnota investice na konci měsíce
                investment_value = shares * price_at_end_of_month
                invested_value = shares * purchase_price
                monthly_profit = investment_value - invested_value
                profit_percentage = (monthly_profit / invested_value) * 100 if invested_value > 0 else 0

                if current_date.year not in investment_history:
                    investment_history[current_date.year] = {}

                investment_history[current_date.year][current_date.strftime('%B')] = {
                    'cash_change': round(monthly_profit, 2),
                    'percentage_change': round(profit_percentage, 2)
                }

            # Posuneme se o měsíc dále
            current_date += relativedelta(months=1)

    # Výpočet součtu za každý rok
    yearly_totals = {
        year: {
            'cash_change': sum(months['cash_change'] for months in year_data.values()),
            'percentage_change': round(sum(months['percentage_change'] for months in year_data.values()) / len(year_data), 2)
        }
        for year, year_data in investment_history.items()
    }

    return investment_history, yearly_totals  # Funkce nyní vrací dvě hodnoty
