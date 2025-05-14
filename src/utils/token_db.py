from models.token_model import SessionLocal, Token
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

def get_all_emails():
    db = SessionLocal()
    try:
        result = db.query(Token.email).all()
        emails = [item.email for item in result]
        return emails
    finally:
        db.close()

def delete_token(email: str) -> bool:
    """
    ลบข้อมูล token ตาม email
    """
    db = SessionLocal()
    try:
        # ค้นหา token ตาม email
        token = db.query(Token).filter(Token.email == email).first()
        
        if token is None:
            return False
        
        # ลบข้อมูล
        db.delete(token)
        db.commit()
        return True
    except Exception as e:
        db.rollback()# กรณีเกิดข้อผิดพลาดกับฐานข้อมูล ให้ rollback
        raise Exception(f"เกิดข้อผิดพลาดในการลบข้อมูลจากฐานข้อมูล: {str(e)}")
    finally:
        db.close()


