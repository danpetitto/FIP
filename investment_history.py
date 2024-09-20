import pandas as pd
from dateutil.relativedelta import relativedelta
from finance import get_ticker_from_isin, get_delayed_price_polygon
from datetime import datetime, timedelta

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
    monthly_summaries = {}  # Pro uložení celkových součtů za všechny ISINy pro každý měsíc

    for isin, group in grouped_data:
        print(f"Zpracovávám ISIN: {isin}")

        # Získáme ticker pro ISIN pomocí funkce z finance.py
        ticker = get_ticker_from_isin(isin)

        if not ticker:
            print(f"Ticker nenalezen pro ISIN: {isin}")
            continue

        # Inicializujeme proměnné pro sledování portfolia
        current_date = group['Datum'].min().replace(day=1)
        end_date = datetime.now()
        shares_held = 0  # Počet aktuálně držených akcií
        total_invested = 0  # Celková investovaná částka
        average_purchase_price = 0  # Průměrná nákupní cena
        last_month_profit = 0  # Zisk minulého měsíce

        while current_date <= end_date:
            # Transakce do aktuálního měsíce
            transactions_up_to_date = group[group['Datum'] <= current_date]

            if transactions_up_to_date.empty:
                current_date += relativedelta(months=1)
                continue

            # Nové nákupy a prodeje během měsíce
            monthly_transactions = group[(group['Datum'] > current_date - relativedelta(months=1)) & (group['Datum'] <= current_date)]

            # Zpracujeme nákupy a prodeje
            for _, row in monthly_transactions.iterrows():
                if row['Počet'] > 0:  # Nákup
                    total_invested += row['Počet'] * row['Cena']
                    shares_held += row['Počet']
                    average_purchase_price = total_invested / shares_held  # Aktualizujeme průměrnou cenu
                elif row['Počet'] < 0:  # Prodej
                    shares_held += row['Počet']  # Prodeje jsou záporné, proto sčítáme
                    if shares_held == 0:
                        total_invested = 0  # Pokud jsou všechny akcie prodány
                    else:
                        total_invested = shares_held * average_purchase_price  # Zůstávající investice

            if shares_held > 0:
                # Získáme cenu ke konci měsíce
                next_date = (current_date + relativedelta(months=1)).replace(day=1) - pd.Timedelta(days=1)
                price_at_end_of_month = get_price_for_month(ticker, next_date)

                if price_at_end_of_month:
                    # Hodnota portfolia na konci měsíce
                    portfolio_value = shares_held * price_at_end_of_month

                    # Nerealizovaný zisk = hodnota portfolia - investovaná částka
                    current_profit = portfolio_value - total_invested

                    # Výkonnost: zisk tento měsíc - zisk minulý měsíc
                    monthly_performance = current_profit - last_month_profit

                    # Procentuální výkonnost
                    percentage_performance = (monthly_performance / portfolio_value) * 100 if portfolio_value > 0 else 0

                    # Uložíme výsledky pro daný měsíc, kumulujeme výsledky za všechny ISINy
                    if current_date.year not in monthly_summaries:
                        monthly_summaries[current_date.year] = {}

                    if current_date.strftime('%B') not in monthly_summaries[current_date.year]:
                        monthly_summaries[current_date.year][current_date.strftime('%B')] = {
                            'cash_change': 0,
                            'percentage_change': 0
                        }

                    # Zaokrouhlíme na 2 desetinná místa a naformátujeme
                    monthly_summaries[current_date.year][current_date.strftime('%B')]['cash_change'] += round(monthly_performance, 2)
                    monthly_summaries[current_date.year][current_date.strftime('%B')]['percentage_change'] += round(percentage_performance, 2)

                    # Uložíme zisk pro příští měsíc
                    last_month_profit = current_profit

            # Posuneme se o měsíc dále
            current_date += relativedelta(months=1)

    # Výpočet součtu za každý rok a formátování výsledků
    yearly_totals = {
        year: {
            'cash_change': "{:.2f} €".format(round(sum(months['cash_change'] for months in year_data.values()), 2)),
            'percentage_change': "{:.2f} %".format(round(sum(months['percentage_change'] for months in year_data.values()) / len(year_data), 2))
        }
        for year, year_data in monthly_summaries.items()
    }

    # Formátujeme výstupy pro měsíce
    formatted_monthly_summaries = {
        year: {
            month: "{:.2f} € ({:.2f} %)".format(month_data['cash_change'], month_data['percentage_change'])
            for month, month_data in months.items()
        }
        for year, months in monthly_summaries.items()
    }

    return formatted_monthly_summaries, yearly_totals

def get_price_for_month(ticker, date):
    """Získání ceny ke konci měsíce, pokusí se vrátit cenu z předchozího obchodního dne, pokud je 404."""
    price = get_delayed_price_polygon(ticker, date.strftime('%Y-%m-%d'))

    if price is None:
        # Pokud se zobrazí chyba 404, zkusíme předchozí den
        attempts = 5  # Zkusíme získat cenu z 5 předchozích dní
        while attempts > 0:
            date -= timedelta(days=1)
            price = get_delayed_price_polygon(ticker, date.strftime('%Y-%m-%d'))
            if price is not None:
                break
            attempts -= 1
    return price

