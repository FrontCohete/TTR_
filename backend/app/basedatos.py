"""Conexión única a PostgreSQL para toda la API.

Reutiliza get_engine() de backend/db.py, que lee las credenciales de .env.
El engine se crea una sola vez y todos los endpoints lo comparten.
"""
from db import get_engine

engine = get_engine()