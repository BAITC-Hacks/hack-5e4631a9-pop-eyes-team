"""Shared PostgreSQL connection setup for synchronous FastAPI handlers."""

import os

import psycopg
from psycopg.rows import dict_row


def connect() -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ.get("DB_HOST", "db"),
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", "eventmatch"),
        user=os.environ.get("POSTGRES_USER", "eventmatch"),
        password=os.environ["POSTGRES_PASSWORD"],
        connect_timeout=3,
        options="-c statement_timeout=5000",
        row_factory=dict_row,
    )
