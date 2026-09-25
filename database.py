from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()

# Global listener on all SQLAlchemy Engine connections
# Runs outside application context, making it extremely thread-safe
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    # Enable WAL mode and pool tuning ONLY for SQLite connections
    dbapi_type = type(dbapi_connection).__module__
    if 'sqlite' not in dbapi_type.lower():
        return
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-128000")  # 128MB Cache
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.execute("PRAGMA mmap_size=268435456") # 256MB mmap
        cursor.execute("PRAGMA busy_timeout=15000")  # 15s busy timeout
        cursor.close()
    except Exception:
        if hasattr(dbapi_connection, 'rollback'):
            try:
                dbapi_connection.rollback()
            except Exception:
                pass

import sqlalchemy as sa

def _get_db_columns(inspector, table_name):
    """Return the set of existing column names for a database table."""
    try:
        columns = inspector.get_columns(table_name)
        return {col['name'] for col in columns}
    except Exception:
        return set()

def _get_sql_type(column, dialect):
    """Map a SQLAlchemy column type to its dialect-specific equivalent."""
    if dialect.name == 'sqlite':
        col_type = column.type
        if isinstance(col_type, (sa.Integer, sa.SmallInteger, sa.BigInteger)):
            return "INTEGER"
        elif isinstance(col_type, (sa.Float, sa.Numeric)):
            return "REAL"
        elif isinstance(col_type, sa.Boolean):
            return "INTEGER"
        elif isinstance(col_type, sa.DateTime):
            return "DATETIME"
        else:
            return "TEXT"
    else:
        # Natively compile type to dialect (e.g. VARCHAR(80), TIMESTAMP, etc.)
        return str(column.type.compile(dialect=dialect))

def _get_default_sql(column, dialect):
    """Generate a SQL DEFAULT fragment for a column, or None if not applicable."""
    if column.default is not None and hasattr(column.default, 'arg'):
        val = column.default.arg
        if callable(val):
            return None  # Callable defaults (e.g., datetime.utcnow) cannot be expressed in SQL
        if isinstance(val, bool):
            if dialect.name == 'sqlite':
                return "1" if val else "0"
            else:
                return "true" if val else "false"
        if isinstance(val, (int, float)):
            return str(val)
        if isinstance(val, str):
            return f"'{val}'"
    if column.nullable:
        return "NULL"
    return None

def run_adaptive_migrations(app):
    """
    Inspect every SQLAlchemy model and ensure all of its columns exist
    in the physical database. Adds any missing columns with the
    correct type and default. Never drops columns or tables. Never erases data.
    """
    import logging
    logger = logging.getLogger('migrations')

    with app.app_context():
        engine = db.engine
        dialect = engine.dialect
        
        # Step 1: Create any entirely missing tables
        try:
            db.create_all()
        except Exception as e:
            db.session.rollback()
            logger.error(f"[MIGRATE] db.create_all() failed: {e}")
            raise
        
        # Step 2: Get tables that actually exist in the database
        try:
            inspector = sa.inspect(engine)
            existing_tables = set(inspector.get_table_names())
        except Exception as e:
            logger.error(f"[MIGRATE] Failed to inspect database table schema: {e}")
            return

        added = 0
        errors = 0

        for model in db.Model.__subclasses__():
            table_name = getattr(model, '__tablename__', None)
            if not table_name or table_name not in existing_tables:
                continue

            db_cols = _get_db_columns(inspector, table_name)

            for col_name, column in model.__table__.columns.items():
                if col_name in db_cols:
                    continue  # Already present — nothing to do

                sql_type = _get_sql_type(column, dialect)
                default_sql = _get_default_sql(column, dialect)

                if default_sql is not None:
                    alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {sql_type} DEFAULT {default_sql}"
                else:
                    alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {sql_type}"

                try:
                    with engine.connect() as conn:
                        conn.execute(sa.text(alter_sql))
                        conn.commit()
                    logger.info(f"[MIGRATE] Added column: {table_name}.{col_name} ({sql_type})")
                    added += 1
                except Exception as e:
                    logger.warning(f"[MIGRATE] Could not add {table_name}.{col_name} via '{alter_sql}': {e}")
                    errors += 1

        if added > 0:
            logger.info(f"[MIGRATE] Adaptive migration complete: {added} column(s) added, {errors} error(s).")

def init_db(app):
    import logging
    logger = logging.getLogger('database')

    db.init_app(app)
    with app.app_context():
        dialect_name = db.engine.dialect.name
        driver_name = db.engine.dialect.driver
        has_db_uri = bool(app.config.get('SQLALCHEMY_DATABASE_URI'))

        logger.info(f"[DB INIT] Initializing database (Dialect: {dialect_name}, Driver: {driver_name}, URI Configured: {has_db_uri})")

        # Step 0: Test connectivity and clean initial transaction state
        try:
            db.session.execute(sa.text("SELECT 1"))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"[DB INIT] Connectivity check failed for {dialect_name} ({driver_name}): {e}")
            raise RuntimeError(f"Database connection check failed for {dialect_name} driver {driver_name}: {e}") from e

        # Step 1: Adaptive schema migration — adds any new columns without data loss
        try:
            run_adaptive_migrations(app)
        except Exception as e:
            db.session.rollback()
            logger.error(f"[DB INIT] Adaptive schema migration failed: {e}")
            raise

        # Step 2: Explicit one-time migrations for legacy columns (kept for safety)
        try:
            db.session.execute(db.text("ALTER TABLE brands ADD COLUMN category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL;"))
            db.session.commit()
        except Exception as e:
            db.session.rollback()

        try:
            timestamp_type = "DATETIME" if dialect_name == 'sqlite' else "TIMESTAMP"
            db.session.execute(db.text(f"ALTER TABLE banners ADD COLUMN expires_at {timestamp_type};"))
            db.session.commit()
        except Exception as e:
            db.session.rollback()

        # Step 3: Fast physical database performance indexes
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_products_active_cat ON products(is_active, category_id);",
            "CREATE INDEX IF NOT EXISTS idx_products_active_created ON products(is_active, created_at);",
            "CREATE INDEX IF NOT EXISTS idx_products_seller ON products(seller_id);",
            "CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand_id);",
            "CREATE INDEX IF NOT EXISTS idx_orders_user_status ON orders(user_id, status);",
            "CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);",
            "CREATE INDEX IF NOT EXISTS idx_cart_user ON cart(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_wishlist_user ON wishlist(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_reviews_product ON reviews(product_id);",
            "CREATE INDEX IF NOT EXISTS idx_recently_viewed_user ON recently_viewed(user_id, viewed_at);",
            "CREATE INDEX IF NOT EXISTS idx_banners_active ON banners(is_active, order_seq);",
            "CREATE INDEX IF NOT EXISTS idx_users_role_active ON users(role, is_active);",
            "CREATE INDEX IF NOT EXISTS idx_store_profiles_status ON store_profiles(status);"
        ]
        for idx_sql in indexes:
            try:
                db.session.execute(db.text(idx_sql))
                db.session.commit()
            except Exception:
                db.session.rollback()





