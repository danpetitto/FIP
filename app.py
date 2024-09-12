from flask import Flask, render_template
from models import db, User
from auth import auth_bp
from portfolio import portfolio_bp
from flask_login import LoginManager
from flask_migrate import Migrate
from config import Config  # Načteme konfiguraci z config.py

app = Flask(__name__)

# Aplikujeme konfiguraci z config.py
app.config.from_object(Config)

# Inicializace SQLAlchemy s aplikací
db.init_app(app)

# Flask-Migrate inicializace
migrate = Migrate(app, db)

# Flask-Login konfigurace
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.init_app(app)

# Načítání uživatele podle ID pro Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Registrace blueprintů
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(portfolio_bp, url_prefix='/portfolio')

# Hlavní stránka
@app.route('/')
def index():
    return render_template('index.html')

# Spuštění aplikace
if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Vytvoření databázových tabulek, pokud ještě neexistují
    app.run(debug=True)
