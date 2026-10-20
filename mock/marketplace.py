"""Заглушка API маркетплейса для разработки и тестов.

    uvicorn marketplace:app --app-dir mock --port 8090

Авторизация: Authorization: Bearer <MOCK_TOKEN> (по умолчанию dev-token).
Методы /_test/* — только для тестов: наполнение и сброс состояния.
"""

import os
from datetime import datetime

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

TOKEN = os.environ.get("MOCK_TOKEN", "dev-token")
STATUSES = {"awaiting_packaging", "delivering", "delivered", "cancelled"}

app = FastAPI(title="Marketplace mock")

offers: set[str] = set()
stocks: dict[str, int] = {}
orders: dict[str, dict] = {}


def now():
    return datetime.now().isoformat(timespec="seconds")


def auth(authorization: str = Header(default="")):
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "invalid token")


class OrderItem(BaseModel):
    offer_id: str
    quantity: int
    price: float


class Order(BaseModel):
    order_id: str
    status: str = "awaiting_packaging"
    created_at: str | None = None
    updated_at: str | None = None
    items: list[OrderItem]


class StatusUpdate(BaseModel):
    status: str


class StockItem(BaseModel):
    offer_id: str
    stock: int


@app.get("/v1/orders", dependencies=[Depends(auth)])
def list_orders(since: str | None = None, status: str | None = None):
    # since — по дате изменения, включительно: повторно полученные заказы клиент должен пропускать
    result = [
        o for o in orders.values() if (not since or o["updated_at"] >= since) and (not status or o["status"] == status)
    ]
    return {"orders": sorted(result, key=lambda o: o["updated_at"])}


@app.patch("/v1/orders/{order_id}/status", dependencies=[Depends(auth)])
def set_status(order_id: str, body: StatusUpdate):
    if order_id not in orders:
        raise HTTPException(404, "order not found")
    if body.status not in STATUSES:
        raise HTTPException(400, f"unknown status {body.status}")
    orders[order_id]["status"] = body.status
    orders[order_id]["updated_at"] = now()
    return orders[order_id]


@app.post("/v1/stocks", dependencies=[Depends(auth)])
def update_stocks(items: list[StockItem]):
    errors = []
    for i in items:
        if i.offer_id in offers:
            stocks[i.offer_id] = i.stock
        else:
            errors.append({"offer_id": i.offer_id, "error": "offer not found"})
    return {"updated": len(items) - len(errors), "errors": errors}


@app.get("/v1/stocks", dependencies=[Depends(auth)])
def get_stocks():
    return stocks


@app.post("/_test/orders")
def add_orders(items: list[Order]):
    for o in items:
        data = o.model_dump()
        data["created_at"] = data["created_at"] or now()
        data["updated_at"] = now()
        orders[o.order_id] = data
        offers.update(i.offer_id for i in o.items)
    return {"total": len(orders)}


@app.post("/_test/offers")
def add_offers(ids: list[str]):
    offers.update(ids)
    return {"total": len(offers)}


@app.get("/_test/orders/{order_id}")
def get_order(order_id: str):
    if order_id not in orders:
        raise HTTPException(404, "order not found")
    return orders[order_id]


@app.post("/_test/reset")
def reset():
    offers.clear()
    stocks.clear()
    orders.clear()
    return {"ok": True}
