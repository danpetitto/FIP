from flask import Flask, render_template
from flask import Flask, render_template
from models import db, User  # SQLAlchemy modely, včetně uživatele
from auth import auth_bp  # Blueprint pro autentizaci
from portfolio import portfolio_bp  # Blueprint pro portfolio
from stock import stock_bp  # Blueprint pro akcie (pokud ho máte)
from flask_login import LoginManager
from flask_migrate import Migrate
from config import Config  # Konfigurace z config.py
from extensions import mail  # Flask-Mail

app = Flask(__name__)

# Načteme konfiguraci z config.py
app.config.from_object(Config)

# Inicializace SQLAlchemy
db.init_app(app)

# Inicializace Flask-Mail
mail.init_app(app)

# Inicializace Flask-Migrate
migrate = Migrate(app, db)

# Flask-Login konfigurace
login_manager = LoginManager()
login_manager.login_view = 'auth.login'  # Login page pro neautentizované uživatele
login_manager.init_app(app)

# Načítání uživatele podle ID pro Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Registrace blueprintů
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(portfolio_bp, url_prefix='/portfolio')

# Pokud máte stock_bp pro akcie, zaregistrujte jej
app.register_blueprint(stock_bp, url_prefix='/stock')

# Hlavní stránka
@app.route('/')
def index():
    return render_template('index.html')

# Spuštění aplikace
if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Vytvoření databázových tabulek, pokud ještě neexistují
    app.run(debug=True)
