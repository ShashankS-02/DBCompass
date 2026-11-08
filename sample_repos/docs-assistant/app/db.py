"""Database engine and session."""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(os.environ["DATABASE_URL"], pool_size=20, max_overflow=10, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
