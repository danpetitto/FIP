import os
from dotenv import load_dotenv

# Načti proměnné z .env souboru
load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'default_secret_key')
    SQLALCHEMY_DATABASE_URI = os.getenv('SQLALCHEMY_DATABASE_URI')
    SQLALCHEMY_TRACK_MODIFICATIONS = os.getenv('SQLALCHEMY_TRACK_MODIFICATIONS', False)

    # Flask-Mail konfigurace
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.seznam.cz')
    MAIL_PORT = os.getenv('MAIL_PORT', 465)
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'False').lower() in ['true', '1', 't']
    MAIL_USE_SSL = os.getenv('MAIL_USE_SSL', 'True').lower() in ['true', '1', 't']
    MAIL_USERNAME = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER', MAIL_USERNAME)
    
    # Další konfigurace
    API_KEY = os.getenv('API_KEY')
    POLYGON_API_KEY = os.getenv('POLYGON_API_KEY')
