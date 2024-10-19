from flask import Blueprint, render_template, request
from models import Portfolio, Trade
from datetime import datetime, timedelta
from collections import defaultdict
from flask_login import current_user
from flask_sqlalchemy import SQLAlchemy

tax_bp = Blueprint('tax', __name__)

# Limit pro osvobození od daní
VALUE_LIMIT = 100000
TIME_LIMIT = timedelta(days=365 * 3)

def calculate_sales_by_year(trades_data):
    sales_by_year = defaultdict(float)
    for trade in trades_data:
        if trade['type'] == 'prodej':
            year = trade['date'].year
            sales_by_year[year] += trade['price'] * abs(trade['quantity'])
    return sales_by_year

def passes_time_test(purchase_date, sale_date):
    return (sale_date - purchase_date) >= TIME_LIMIT

def calculate_taxable_amount(trades):
    taxable_trades = defaultdict(list)
    total_taxable_profit = 0
    for trade in trades:
        if trade['type'] == 'prodej':
            purchase_trade = find_purchase(trade['ticker'], trade['date'], trades)
            if purchase_trade:
                profit = calculate_profit(purchase_trade, trade)
                if not passes_time_test(purchase_trade['date'], trade['date']):
                    year = trade['date'].year
                    taxable_trades[year].append({
                        'ticker': trade['ticker'],
                        'purchase_date': purchase_trade['date'],
                        'sale_date': trade['date'],
                        'profit': profit
                    })
                    total_taxable_profit += profit
    return taxable_trades, total_taxable_profit

def find_purchase(ticker, sale_date, trades):
    purchases = [t for t in trades if t['ticker'] == ticker and t['type'] == 'nákup' and t['date'] < sale_date]
    if purchases:
        return purchases[0]
    return None

def calculate_profit(purchase_trade, sale_trade):
    return (sale_trade['price'] - purchase_trade['price']) * abs(sale_trade['quantity'])

# Route pro výběr portfolia (tax.html)
@tax_bp.route('/', methods=['GET'])
def tax_select():
    user_id = current_user.id
    portfolios = Portfolio.query.filter_by(user_id=user_id).all()
    return render_template('tax.html', portfolios=portfolios)

@tax_bp.route('/results', methods=['GET'])
def tax_results():
    user_id = current_user.id
    portfolios = Portfolio.query.filter_by(user_id=user_id).all()

    selected_portfolio_id = request.args.get('portfolio_id')
    print(f"Selected portfolio ID: {selected_portfolio_id}")  # Debug výpis
    
    if selected_portfolio_id:
        portfolio = Portfolio.query.filter_by(id=selected_portfolio_id, user_id=user_id).first()
        print(f"Selected portfolio: {portfolio}")  # Debug výpis
        if not portfolio:
            return render_template('tax_results.html', portfolios=portfolios, trades={}, total_taxable_profit=0, current_year_sales=0, remaining_limit=VALUE_LIMIT, sales_status={})
    else:
        print("No portfolio selected.")  # Debug výpis
        return render_template('tax_results.html', portfolios=portfolios, trades={}, total_taxable_profit=0, current_year_sales=0, remaining_limit=VALUE_LIMIT, sales_status={})

    trades = Trade.query.filter_by(portfolio_id=portfolio.id).all()
    print(f"Trades found: {trades}")  # Debug výpis

    if not trades:
        return render_template('tax_results.html', portfolios=portfolios, trades={}, total_taxable_profit=0, current_year_sales=0, remaining_limit=VALUE_LIMIT, sales_status={})

    trades_data = [{
        'date': trade.datum,
        'type': trade.typ_obchodu,
        'ticker': trade.ticker,
        'price': trade.cena,
        'quantity': trade.pocet
    } for trade in trades]
    
    print(f"Trades data: {trades_data}")  # Debug výpis
    
    taxable_trades, total_taxable_profit = calculate_taxable_amount(trades_data)
    sales_by_year = calculate_sales_by_year(trades_data)

    sales_status = {}
    for year, sales in sales_by_year.items():
        if sales > VALUE_LIMIT:
            sales_status[year] = f"Daňová povinnost: {sales} CZK"
        else:
            sales_status[year] = f"Součet prodejů: {sales} CZK"

    print(f"Sales status: {sales_status}")  # Debug výpis

    return render_template(
        'tax_results.html',
        portfolios=portfolios,
        trades=taxable_trades,
        total_taxable_profit=total_taxable_profit,
        sales_status=sales_status,
        current_year_sales=sales_by_year.get(datetime.now().year, 0),
        remaining_limit=VALUE_LIMIT - sales_by_year.get(datetime.now().year, 0)
    )
