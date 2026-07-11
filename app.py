import random
import time
import json
import redis
import requests
import datetime
import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, update, insert, text

# Import database schema
from db import engine, products, orders, order_items
from telemetry import tracer, logger

# Setup Redis
redis_host = os.environ.get("REDIS_HOST", "localhost")
redis_port = int(os.environ.get("REDIS_PORT", 6379))
r = redis.Redis(host=redis_host, port=redis_port)

# Instruments
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from prometheus_fastapi_instrumentator import Instrumentator

# Instrument redis and requests
RedisInstrumentor().instrument()
RequestsInstrumentor().instrument()

app = FastAPI(title="Chronos Watch Shop API")

# Instrument FastAPI app for OpenTelemetry tracing
FastAPIInstrumentor.instrument_app(app)

# Helper function to serialize SQL Row
def row_to_dict(row, keys):
    return {keys[i]: row[i] for i in range(len(keys))}

# Define Cart requests
class AddToCartRequest(BaseModel):
    product_id: int
    quantity: int

class RemoveFromCartRequest(BaseModel):
    product_id: int

# Memory leak storage
memory_leak_list = []

# --- E-Commerce API Endpoints ---

@app.get("/api/products")
def get_products():
    logger.info("GET /api/products - Fetching all products")
    # Attempt to retrieve from Redis cache
    cached_products = r.get("products_cache")
    if cached_products:
        with tracer.start_as_current_span("cache_hit"):
            logger.info("Products cache hit")
            return json.loads(cached_products)
            
    # Cache miss - query SQL database
    with tracer.start_as_current_span("cache_miss_db_query"):
        logger.info("Products cache miss - querying database")
        with engine.connect() as conn:
            stmt = select(products)
            result = conn.execute(stmt).fetchall()
            
            # Serialize
            keys = ["id", "name", "brand", "price", "description", "image_url", "stock"]
            product_list = [row_to_dict(row, keys) for row in result]
            
            # Save to Redis cache for 60 seconds
            r.setex("products_cache", 60, json.dumps(product_list))
            logger.info("Fetched %d products from DB and cached them", len(product_list))
            return product_list

@app.get("/api/products/{product_id}")
def get_product(product_id: int):
    logger.info("GET /api/products/%d - Fetching product", product_id)
    # Try fetching from cache or database
    with engine.connect() as conn:
        stmt = select(products).where(products.c.id == product_id)
        row = conn.execute(stmt).first()
        if not row:
            logger.warning("Product ID %d not found", product_id)
            raise HTTPException(status_code=404, detail="Product not found")
        keys = ["id", "name", "brand", "price", "description", "image_url", "stock"]
        product_data = row_to_dict(row, keys)
        logger.info("Successfully fetched product: %s", product_data["name"])
        return product_data

@app.get("/api/cart")
def get_cart():
    logger.info("GET /api/cart - Fetching cart items")
    # Cart is stored in Redis as a hash map under key "cart"
    # Fields are product_id, values are quantities
    cart_raw = r.hgetall("cart")
    cart_items = []
    total_price = 0.0
    
    with engine.connect() as conn:
        for p_id_bytes, qty_bytes in cart_raw.items():
            product_id = int(p_id_bytes.decode("utf-8"))
            quantity = int(qty_bytes.decode("utf-8"))
            
            # Fetch product details
            stmt = select(products).where(products.c.id == product_id)
            row = conn.execute(stmt).first()
            if row:
                keys = ["id", "name", "brand", "price", "description", "image_url", "stock"]
                product_data = row_to_dict(row, keys)
                subtotal = product_data["price"] * quantity
                total_price += subtotal
                
                cart_items.append({
                    "product": product_data,
                    "quantity": quantity,
                    "subtotal": subtotal
                })
                
    logger.info("Cart retrieved with %d unique items, total price: $%s", len(cart_items), total_price)
    return {
        "items": cart_items,
        "total_price": total_price
    }

@app.post("/api/cart/add")
def add_to_cart(req: AddToCartRequest):
    logger.info("POST /api/cart/add - Adding product ID %d (qty: %d) to cart", req.product_id, req.quantity)
    if req.quantity <= 0:
        logger.warning("Invalid quantity: %d", req.quantity)
        raise HTTPException(status_code=400, detail="Quantity must be greater than 0")
        
    # Check if product exists and check stock
    with engine.connect() as conn:
        stmt = select(products.c.stock).where(products.c.id == req.product_id)
        stock = conn.execute(stmt).scalar()
        if stock is None:
            logger.warning("Product ID %d not found for add to cart", req.product_id)
            raise HTTPException(status_code=404, detail="Product not found")
        if stock < req.quantity:
            logger.warning("Insufficient stock for product ID %d (requested %d, stock %d)", req.product_id, req.quantity, stock)
            raise HTTPException(status_code=400, detail=f"Insufficient stock. Only {stock} available.")
            
    # Add/Update quantity in Redis
    r.hincrby("cart", req.product_id, req.quantity)
    logger.info("Product ID %d successfully added to cart", req.product_id)
    return {"status": "success", "message": "Product added to cart"}

@app.post("/api/cart/remove")
def remove_from_cart(req: RemoveFromCartRequest):
    logger.info("POST /api/cart/remove - Removing product ID %d from cart", req.product_id)
    # Remove key from Redis hash
    r.hdel("cart", req.product_id)
    logger.info("Product ID %d removed from cart", req.product_id)
    return {"status": "success", "message": "Product removed from cart"}

@app.post("/api/cart/clear")
def clear_cart():
    logger.info("POST /api/cart/clear - Clearing all items from cart")
    r.delete("cart")
    return {"status": "success", "message": "Cart cleared"}

@app.post("/api/checkout")
def checkout():
    logger.info("POST /api/checkout - Starting checkout pipeline")
    # Run checkout pipeline inside custom span
    with tracer.start_as_current_span("checkout_pipeline") as checkout_span:
        cart_raw = r.hgetall("cart")
        if not cart_raw:
            raise HTTPException(status_code=400, detail="Cart is empty")
            
        with engine.connect() as conn:
            # Start database transaction
            trans = conn.begin()
            try:
                total_price = 0.0
                items_to_purchase = []
                
                # Verify and collect all items first
                for p_id_bytes, qty_bytes in cart_raw.items():
                    product_id = int(p_id_bytes.decode("utf-8"))
                    quantity = int(qty_bytes.decode("utf-8"))
                    
                    stmt = select(products).where(products.c.id == product_id)
                    row = conn.execute(stmt).first()
                    if not row:
                        raise HTTPException(status_code=404, detail=f"Product ID {product_id} not found")
                    
                    keys = ["id", "name", "brand", "price", "description", "image_url", "stock"]
                    product = row_to_dict(row, keys)
                    
                    if product["stock"] < quantity:
                        checkout_span.set_attribute("error", True)
                        checkout_span.record_exception(Exception(f"Out of stock for product: {product['name']}"))
                        raise HTTPException(
                            status_code=400, 
                            detail=f"Out of stock for {product['name']}. Available: {product['stock']}, Requested: {quantity}"
                        )
                    
                    total_price += product["price"] * quantity
                    items_to_purchase.append({
                        "product_id": product_id,
                        "quantity": quantity,
                        "price": product["price"],
                        "current_stock": product["stock"]
                    })
                
                # Insert order
                order_stmt = insert(orders).values(
                    total_price=total_price,
                    status="Processing",
                    created_at=datetime.datetime.utcnow().isoformat()
                )
                order_result = conn.execute(order_stmt)
                order_id = order_result.lastrowid
                
                # Insert order items and deduct stock
                for item in items_to_purchase:
                    # Insert item
                    item_stmt = insert(order_items).values(
                        order_id=order_id,
                        product_id=item["product_id"],
                        quantity=item["quantity"],
                        price=item["price"]
                    )
                    conn.execute(item_stmt)
                    
                    # Deduct stock
                    new_stock = item["current_stock"] - item["quantity"]
                    update_stmt = update(products).where(products.c.id == item["product_id"]).values(stock=new_stock)
                    conn.execute(update_stmt)
                
                # External Payment Gateway Call (Simulated via RequestsInstrumentor)
                with tracer.start_as_current_span("payment_gateway_call") as pay_span:
                    # Let's request httpbin to simulate an external gateway integration
                    resp = requests.get("https://httpbin.org/get?amount=" + str(total_price))
                    if resp.status_code != 200:
                        raise Exception("Payment Gateway failed")
                    pay_span.set_attribute("payment.status", "authorized")
                
                # Update order status to Completed
                update_order_stmt = update(orders).where(orders.c.id == order_id).values(status="Completed")
                conn.execute(update_order_stmt)
                
                # Commit database changes
                trans.commit()
                
                # Clear cart and product list cache
                r.delete("cart")
                r.delete("products_cache")
                
                return {
                    "status": "success",
                    "order_id": order_id,
                    "total_price": total_price,
                    "message": "Checkout completed successfully"
                }
                
            except Exception as e:
                trans.rollback()
                if isinstance(e, HTTPException):
                    raise e
                raise HTTPException(status_code=500, detail=f"Checkout failed: {str(e)}")

@app.get("/api/orders")
def get_orders():
    logger.info("GET /api/orders - Fetching order history")
    with engine.connect() as conn:
        stmt = select(orders).order_by(orders.c.id.desc())
        result = conn.execute(stmt).fetchall()
        keys = ["id", "total_price", "status", "created_at"]
        return [row_to_dict(row, keys) for row in result]

# --- Telemetry Simulation Endpoints (For AutoOps Testing) ---

@app.get("/api/simulate/slow-checkout")
def simulate_slow_checkout():
    logger.info("GET /api/simulate/slow-checkout - Simulating slow checkout")
    # Simulates a slow database lock or slow payment response
    with tracer.start_as_current_span("slow_checkout_simulation"):
        time.sleep(5)
        return {"status": "ok", "message": "Slow process simulated (5 seconds)"}

@app.get("/api/simulate/memory-leak")
def simulate_memory_leak():
    logger.info("GET /api/simulate/memory-leak - Simulating memory leak")
    # Appends large list of zeros to global list to leak memory
    global memory_leak_list
    with tracer.start_as_current_span("memory_leak_simulation"):
        memory_leak_list.extend([0] * 1000000)
        return {"status": "ok", "memory_list_size": len(memory_leak_list)}

@app.get("/api/simulate/payment-error")
def simulate_payment_error():
    logger.info("GET /api/simulate/payment-error - Simulating payment gateway error")
    # Simulates a payment processor timeout/exception
    with tracer.start_as_current_span("payment_error_simulation") as span:
        if random.random() > 0.3:
            err_msg = "Payment Gateway connection timed out"
            span.set_attribute("error", True)
            span.record_exception(Exception(err_msg))
            raise HTTPException(status_code=503, detail=err_msg)
        return {"status": "ok", "message": "Simulated payment succeeded"}

@app.get("/api/simulate/cpu-load")
def simulate_cpu_load():
    logger.info("GET /api/simulate/cpu-load - Simulating heavy CPU load")
    # Simulates heavy CPU load
    with tracer.start_as_current_span("cpu_load_simulation"):
        x = 0
        for i in range(50000000):
            x += i
        return {"status": "ok", "result": x}

@app.get("/api/simulate/db-lock")
def simulate_db_lock():
    logger.info("GET /api/simulate/db-lock - Simulating database lock")
    # Emulates db transaction lock wait
    with engine.connect() as conn:
        with tracer.start_as_current_span("db_lock_simulation"):
            time.sleep(3)
            conn.execute(text("SELECT 1"))
            return {"status": "ok", "message": "DB lock simulated (3 seconds)"}

@app.get("/api/simulate/external")
def simulate_external():
    logger.info("GET /api/simulate/external - Simulating external API call")
    # Simulates an external API call
    with tracer.start_as_current_span("external_api_simulation"):
        resp = requests.get("https://httpbin.org/get")
        return {"status": "ok", "external_status": resp.status_code}

# --- Serve Frontend ---

# Mount the static directory
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_index():
    return FileResponse("static/index.html")

@app.get("/health")
def health_check():
    return {"status": "ok"}

# Instrument FastAPI app for Prometheus metrics and expose /metrics
Instrumentator().instrument(app).expose(app)
