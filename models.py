from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
from datetime import datetime

# Inicializace SQLAlchemy
db = SQLAlchemy()

# Model pro sledování (follow)
class Follow(db.Model):
    follower_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    followed_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# Model pro uživatele
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False, unique=True)
    email = db.Column(db.String(150), nullable=False, unique=True)
    password_hash = db.Column(db.String(255))
    location = db.Column(db.String(150), default="Není k dispozici")
    website = db.Column(db.String(150), default="Není k dispozici")
    social_links = db.Column(db.String(300), default="Není k dispozici")
    investor_since = db.Column(db.Date)
    profile_image = db.Column(db.String(300), default="default.png")
    investor_type = db.Column(db.String(50), nullable=True, default="Není k dispozici")
    
    # Definice vztahu follow a followed
    followed = db.relationship('Follow',
                               foreign_keys=[Follow.follower_id],
                               backref=db.backref('follower', lazy='joined'),
                               lazy='dynamic',
                               cascade='all, delete-orphan')

    followers = db.relationship('Follow',
                                foreign_keys=[Follow.followed_id],
                                backref=db.backref('followed', lazy='joined'),
                                lazy='dynamic',
                                cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def follow(self, user):
        if not self.is_following(user):
            follow = Follow(follower_id=self.id, followed_id=user.id)
            db.session.add(follow)

    def unfollow(self, user):
        follow = self.followed.filter_by(followed_id=user.id).first()
        if follow:
            db.session.delete(follow)

    def is_following(self, user):
        return self.followed.filter_by(followed_id=user.id).count() > 0

    # Zpětná vazba pro portfolio
    portfolios = relationship('Portfolio', back_populates='user')


# Model pro portfolio
class Portfolio(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    filename = db.Column(db.String(150), nullable=False)
    data = db.Column(db.LargeBinary, nullable=False)
    total_value = db.Column(db.Float, default=0)
    total_trades = db.Column(db.Integer, default=0)
    total_fees = db.Column(db.Float, default=0)
    stocks = db.Column(db.JSON, default=[])
    date = db.Column(db.Date, nullable=False)  # Sloupec `date` je správně definován
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


    # Přidání vztahu k modelu User
    user = relationship('User', back_populates='portfolios')


# Model pro obchod (trade)
class Trade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey('portfolio.id'), nullable=False)
    datum = db.Column(db.DateTime, nullable=False)
    typ_obchodu = db.Column(db.String(10), nullable=False)
    ticker = db.Column(db.String(10), nullable=False)
    cena = db.Column(db.Float, nullable=False)
    pocet = db.Column(db.Integer, nullable=False)
    hodnota = db.Column(db.Float, nullable=False)
    poplatky = db.Column(db.Float, nullable=True)

    # Definice vztahu k portfoliu
    portfolio = db.relationship('Portfolio', backref=db.backref('trades', lazy=True))

