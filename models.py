from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
from datetime import datetime

# Inicializace SQLAlchemy
db = SQLAlchemy()

# Model pro uživatele
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False, unique=True)
    email = db.Column(db.String(150), nullable=False, unique=True)
    password_hash = db.Column(db.String(128))

    portfolios = relationship('Portfolio', back_populates='user')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Model pro portfolio
class Portfolio(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    filename = db.Column(db.String(150), nullable=False)
    data = db.Column(db.LargeBinary, nullable=False)
    
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = relationship('User', back_populates='portfolios')

# Model pro obchod (Trade)
class Trade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey('portfolio.id'), nullable=False)
    datum = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    typ_obchodu = db.Column(db.String(10), nullable=False)  # nákup/prodej
    ticker = db.Column(db.String(10), nullable=False)
    cena = db.Column(db.Float, nullable=False)
    pocet = db.Column(db.Integer, nullable=False)  # nový sloupec pro počet
    hodnota = db.Column(db.Float, nullable=False)
    poplatky = db.Column(db.Float, nullable=False, default=0.0)
