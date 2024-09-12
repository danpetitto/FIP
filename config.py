import os
from dotenv import load_dotenv

# Načti proměnné z .env souboru
load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'default_secret_key')  # Záložní hodnota
    SQLALCHEMY_DATABASE_URI = os.getenv('SQLALCHEMY_DATABASE_URI')
    MAIL_USERNAME = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER')
    API_KEY = os.getenv('API_KEY')
    POLYGON_API_KEY = os.getenv('POLYGON_API_KEY')
