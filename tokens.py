from itsdangerous import URLSafeTimedSerializer
from flask import current_app as app
from models import User

# Funkce pro generování a ověření tokenu
def generate_reset_token(user, expires_sec=1800):
    s = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return s.dumps(user.email, salt='password-reset-salt')

def verify_reset_token(token, expires_sec=1800):
    s = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    try:
        email = s.loads(token, salt='password-reset-salt', max_age=expires_sec)
    except:
        return None
    return User.query.filter_by(email=email).first()
