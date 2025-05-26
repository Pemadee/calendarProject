from typing import Optional
from sqlalchemy import Column, String, DateTime, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
from pydantic import BaseModel


Base = declarative_base()

class Token(Base):
    __tablename__ = 'tokens'

    email = Column(String, primary_key=True, index=True)
    access_token = Column(String, nullable=False)
    refresh_token = Column(String, nullable=False)
    expiry = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)

class TokenResponse(BaseModel):
    email: str
    access_token: str
    refresh_token: str
    expiry: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        orm_mode = True


class EmailResponse(BaseModel):
    email: str
    
    class Config:
        orm_mode = True
# DB Setup
DATABASE_URL = "sqlite:///./tokens.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

