from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Order

app = FastAPI(title="Orders API")


@app.post("/orders")
def create_order(payload: dict) -> dict:
    with SessionLocal() as session:
        order = Order(customer_id=payload["customer_id"], total=payload["total"])
        session.add(order)
        session.commit()
        return {"id": order.id}


@app.get("/orders/{order_id}")
def get_order(order_id: int) -> dict:
    with SessionLocal() as session:
        order = session.get(Order, order_id)
        return {"id": order.id, "total": float(order.total)}


@app.get("/search")
def search(q: str) -> list:
    sql = text("SELECT id, name FROM products WHERE to_tsvector('english', name) @@ plainto_tsquery(:q) LIMIT 20")
    with SessionLocal() as session:
        return [dict(row._mapping) for row in session.execute(sql, {"q": q})]


@app.get("/products/{product_id}/similar")
def similar(product_id: int) -> list:
    sql = text("SELECT id FROM products ORDER BY embedding <-> (SELECT embedding FROM products WHERE id = :id) LIMIT 10")
    with SessionLocal() as session:
        return [row.id for row in session.execute(sql, {"id": product_id})]


@app.get("/reports/daily")
def daily_report(session: Session) -> list:
    sql = text("SELECT date_trunc('day', created_at) AS day, COUNT(*), SUM(total) FROM orders WHERE created_at BETWEEN :start AND :end GROUP BY 1")
    return [dict(row._mapping) for row in session.execute(sql)]
