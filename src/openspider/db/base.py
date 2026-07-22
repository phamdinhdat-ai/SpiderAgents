# -*- coding: utf-8 -*-
"""SQLAlchemy declarative base for all PostgreSQL models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
