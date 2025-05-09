from src.models.token_model import SessionLocal, Token
from datetime import datetime

def get_token(email):
    db = SessionLocal()
    try:
        return db.query(Token).filter(Token.email == email).first()
    finally:
        db.close()

def get_all_tokens():
    db = SessionLocal()
    try:
        return db.query(Token).all()
    finally:
        db.close()


def update_token(email, access_token, refresh_token, expiry):
    db = SessionLocal()
    try:
        token = db.query(Token).filter(Token.email == email).first()
        if token:
            token.access_token = access_token
            token.refresh_token = refresh_token
            token.expiry = expiry
            token.updated_at = datetime.utcnow()
        else:
            token = Token(
                email=email,
                access_token=access_token,
                refresh_token=refresh_token,
                expiry=expiry
            )
            db.add(token)
        db.commit()
    finally:
        db.close()