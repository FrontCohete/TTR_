"""Configuración general del backend.

Los valores se pueden cambiar desde backend/.env sin tocar el código.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Carpeta backend (este archivo está en backend/app/config.py)
BACKEND = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND / ".env")

# Donde se guardan los archivos subidos mientras esperan a ser procesados
CARPETA_CARGAS = Path(os.getenv("CARPETA_CARGAS", BACKEND / "cargas"))
CARPETA_CARGAS.mkdir(parents=True, exist_ok=True)