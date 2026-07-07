from sqlalchemy import *
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

engine = create_engine("sqlite:///orders.db")

metadata = MetaData()

orders = Table(
    "orders",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String),
)

metadata.create_all(engine)

# Instrument SQLAlchemy
SQLAlchemyInstrumentor().instrument(
    engine=engine
)
