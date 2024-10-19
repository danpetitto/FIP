from flask import Blueprint, render_template, request
from models import Portfolio, Trade
from datetime import datetime, timedelta
from collections import defaultdict
from flask_login import current_user
import logging

# Nastavení loggeru
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

tax_bp = Blueprint('tax', __name__)

# Limit pro osvobození od daní
VALUE_LIMIT = 100000

# Výpočet prodejů podle let
def calculate_sales_by_year(trades_data):
    sales_by_year = defaultdict(float)
    processed_trades = set()  # Sledování unikátních transakcí (založené na datu a tickeru)

    for trade in trades_data:
        trade_key = (trade['date'], trade['ticker'])  # Kombinace data a tickeru jako unikátní klíč
        if trade['type'] == 'prodej' and trade_key not in processed_trades:
            year = trade['date'].year
            sales_by_year[year] += trade['hodnota']  # Přičítáme hodnotu prodeje
            processed_trades.add(trade_key)  # Označíme transakci jako zpracovanou

            # Výpis pro každou transakci
            logger.info(f"Transakce: rok {year}, hodnota: {trade['hodnota']}, celkem za rok: {sales_by_year[year]}")
    
    # Výpis součtu pro jednotlivé roky
    logger.info(f"Součty pro jednotlivé roky: {dict(sales_by_year)}")
    
    return sales_by_year

# Route pro výběr portfolia (tax.html)
@tax_bp.route('/', methods=['GET'])
def tax_select():
    user_id = current_user.id
    portfolios = Portfolio.query.filter_by(user_id=user_id).all()
    return render_template('tax.html', portfolios=portfolios)

# Route pro výsledky (tax_results.html)
@tax_bp.route('/results', methods=['GET'])
def tax_results():
    user_id = current_user.id
    portfolios = Portfolio.query.filter_by(user_id=user_id).all()

    selected_portfolio_id = request.args.get('portfolio_id')
    if selected_portfolio_id:
        portfolio = Portfolio.query.filter_by(id=selected_portfolio_id, user_id=user_id).first()
        if not portfolio:
            return render_template('tax_results.html', portfolios=portfolios, trades={}, current_year_sales=0, remaining_limit=VALUE_LIMIT, sales_status={})
    else:
        return render_template('tax_results.html', portfolios=portfolios, trades={}, current_year_sales=0, remaining_limit=VALUE_LIMIT, sales_status={})

    trades = Trade.query.filter_by(portfolio_id=portfolio.id).all()

    if not trades:
        return render_template('tax_results.html', portfolios=portfolios, trades={}, current_year_sales=0, remaining_limit=VALUE_LIMIT, sales_status={})

    # Data z obchodů
    trades_data = [{
        'date': trade.datum,
        'type': trade.typ_obchodu,
        'ticker': trade.ticker,
        'hodnota': trade.hodnota  # Použijeme hodnotu prodeje
    } for trade in trades]

    # Výpočet prodejů za jednotlivé roky
    sales_by_year = calculate_sales_by_year(trades_data)

    # Sestavení statusů pro jednotlivé roky
    sales_status = {}
    for year, sales in sales_by_year.items():
        sales_status[year] = f"Součet prodejů: {sales:.2f} €"

    return render_template(
        'tax_results.html',
        portfolios=portfolios,
        sales_status=sales_status,
        current_year_sales=sales_by_year.get(datetime.now().year, 0),
        remaining_limit=VALUE_LIMIT - sales_by_year.get(datetime.now().year, 0)
    )
