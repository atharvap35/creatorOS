import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import BASE_DIR, DATABASE_URL

DEFAULT_DB_PATH = os.path.join(str(BASE_DIR), "creator_os.db")

SQLALCHEMY_DATABASE_URL = DATABASE_URL or f"sqlite:///{DEFAULT_DB_PATH}"

connect_args = {"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

Base = declarative_base()


def _apply_sqlite_migrations() -> None:
    """Additive column migrations so existing dev databases keep working.

    SQLite cannot add a foreign key with ALTER TABLE, so user_id is added as a
    plain integer; the ORM still enforces ownership on every query.
    """
    if not SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as connection:
        for table_name, table in Base.metadata.tables.items():
            if table_name not in existing_tables:
                continue

            actual = {col["name"] for col in inspector.get_columns(table_name)}
            for column in table.columns:
                if column.name in actual:
                    continue

                if column.name == "user_id":
                    connection.execute(
                        text(
                            f"ALTER TABLE {table_name} ADD COLUMN user_id INTEGER "
                            "REFERENCES users(id) ON DELETE CASCADE"
                        )
                    )
                    continue

                ddl_type = column.type.compile(dialect=engine.dialect)
                connection.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN {column.name} {ddl_type}")
                )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
