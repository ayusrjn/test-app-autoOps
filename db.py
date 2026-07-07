from sqlalchemy import *
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

import os
database_url = os.environ.get("DATABASE_URL", "sqlite:///orders.db")
engine = create_engine(database_url)
metadata = MetaData()

products = Table(
    "products",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String, nullable=False),
    Column("brand", String, nullable=False),
    Column("price", Float, nullable=False),
    Column("description", String),
    Column("image_url", String),
    Column("stock", Integer, default=5)
)

orders = Table(
    "orders",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("total_price", Float, nullable=False),
    Column("status", String, default="Pending"),
    Column("created_at", String)  # Stored as ISO string
)

order_items = Table(
    "order_items",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("order_id", Integer, ForeignKey("orders.id")),
    Column("product_id", Integer, ForeignKey("products.id")),
    Column("quantity", Integer, nullable=False),
    Column("price", Float, nullable=False)
)

metadata.create_all(engine)

# Seed database with premium watches if empty
with engine.connect() as conn:
    # Check if products exist
    count = conn.execute(select(func.count()).select_from(products)).scalar()
    if count == 0:
        seed_data = [
            {
                "id": 1,
                "name": "Submariner Date",
                "brand": "Rolex",
                "price": 14500.0,
                "description": "The quintessential divers watch, featuring a rotatable bezel and robust Oyster bracelet.",
                "image_url": "https://images.unsplash.com/photo-1547996160-81dfa63595aa?w=500&auto=format&fit=crop&q=60",
                "stock": 5
            },
            {
                "id": 2,
                "name": "Speedmaster Moonwatch",
                "brand": "Omega",
                "price": 7600.0,
                "description": "One of the world's most iconic timepieces, worn on all six lunar missions.",
                "image_url": "https://images.unsplash.com/photo-1522312346375-d1a52e2b99b3?w=500&auto=format&fit=crop&q=60",
                "stock": 8
            },
            {
                "id": 3,
                "name": "Alpinist Green Dial",
                "brand": "Seiko",
                "price": 750.0,
                "description": "A classic sports watch designed for mountaineering, featuring an inner rotating compass ring.",
                "image_url": "https://images.unsplash.com/photo-1614162692292-7ac56d7f7f1e?w=500&auto=format&fit=crop&q=60",
                "stock": 15
            },
            {
                "id": 4,
                "name": "G-Shock CasiOak",
                "brand": "Casio",
                "price": 150.0,
                "description": "Stealthy, rugged, and functional. Offers 200m water resistance in a sleek octagonal design.",
                "image_url": "https://images.unsplash.com/photo-1508685096489-7aacd43bd3b1?w=500&auto=format&fit=crop&q=60",
                "stock": 25
            },
            {
                "id": 5,
                "name": "Nautilus 5711",
                "brand": "Patek Philippe",
                "price": 115000.0,
                "description": "With the rounded octagonal shape of its bezel and its horizontally embossed dial, the epitome of elegant sports watches.",
                "image_url": "https://images.unsplash.com/photo-1619134778706-7015533a6150?w=500&auto=format&fit=crop&q=60",
                "stock": 2
            },
            {
                "id": 6,
                "name": "Royal Oak Selfwinding",
                "brand": "Audemars Piguet",
                "price": 48000.0,
                "description": "The pioneer of luxury steel sports watches, recognizable by its octagonal bezel with hexagonal screws.",
                "image_url": "https://images.unsplash.com/photo-1539874754764-5a96559165b0?w=500&auto=format&fit=crop&q=60",
                "stock": 3
            },
            {
                "id": 7,
                "name": "Apple Watch Ultra 2",
                "brand": "Apple",
                "price": 799.0,
                "description": "The most rugged and capable Apple Watch, engineered for outdoor adventures and endurance sports.",
                "image_url": "https://images.unsplash.com/photo-1434056886845-dac89ffee9b5?w=500&auto=format&fit=crop&q=60",
                "stock": 10
            },
            {
                "id": 8,
                "name": "PRX Powermatic 80",
                "brand": "Tissot",
                "price": 675.0,
                "description": "Thin, smooth, and authentic. Features an integrated case and bracelet design with an automatic Swiss movement.",
                "image_url": "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=500&auto=format&fit=crop&q=60",
                "stock": 12
            }
        ]
        conn.execute(products.insert(), seed_data)
        conn.commit()

# Instrument SQLAlchemy
SQLAlchemyInstrumentor().instrument(
    engine=engine
)
