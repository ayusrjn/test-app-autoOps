import random
import time
import redis
import requests
from fastapi import FastAPI
from sqlalchemy import text

# Import database engine and table
from db import engine, orders
from telemetry import tracer

# Setup Redis
r = redis.Redis(host="localhost", port=6379)

# Instruments
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

# Instrument redis and requests
RedisInstrumentor().instrument()
RequestsInstrumentor().instrument()

app = FastAPI()

# Instrument FastAPI app
FastAPIInstrumentor.instrument_app(app)

memory = []

@app.get("/")
def home():
    with tracer.start_as_current_span("home_endpoint"):
        time.sleep(random.uniform(0.05, 0.2))
        return {
            "status": "ok"
        }

@app.get("/slow")
def slow():
    time.sleep(5)
    return {"ok": True}

@app.get("/memory")
def leak():
    global memory
    memory.extend([0] * 1000000)
    return {"size": len(memory)}

@app.get("/error")
def error():
    if random.random() > 0.5:
        raise Exception("Database timeout")
    return {"ok": True}

@app.get("/cpu")
def cpu():
    x = 0
    for i in range(100000000):
        x += i
    return {"done": x}

@app.get("/db")
def db_endpoint():
    with engine.connect() as conn:
        # Insert a random order
        stmt = orders.insert().values(name=f"Order-{random.randint(1000, 9999)}")
        conn.execute(stmt)
        conn.commit()
        # Query orders
        result = conn.execute(orders.select()).fetchall()
        return {"orders": [{"id": row[0], "name": row[1]} for row in result]}

@app.get("/db-lock")
def db_lock():
    with engine.connect() as conn:
        time.sleep(3)
        conn.execute(text("SELECT 1"))
    return {"ok": True}

@app.get("/redis")
def redis_endpoint():
    r.set("foo", f"bar-{random.randint(100, 999)}")
    val = r.get("foo")
    return {"redis_val": val.decode("utf-8") if val else None}

@app.get("/redis-timeout")
def redis_timeout():
    time.sleep(2)
    val = r.get("abc")
    return {"val": val.decode("utf-8") if val else None}

@app.get("/external")
def external_api():
    requests.get("https://httpbin.org/get")
    return {"ok": True}

@app.get("/latency")
def random_latency():
    time.sleep(random.uniform(0.1, 4))
    return {"ok": True}
