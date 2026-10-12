import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine

load_dotenv(Path(__file__).with_name(".env"))


def get_engine(echo: bool = False):
    """Devuelve un engine de SQLAlchemy conectado a ttr_clusteragent."""
    url = URL.create(
        drivername="postgresql+psycopg",
        username=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.environ["DB_NAME"],
    )
    return create_engine(url, echo=echo)