import httpx

from conftest import API_URL


def test_without_key_is_unauthorized():
    assert httpx.get(f"{API_URL}/stock").status_code == 401
    assert httpx.get(f"{API_URL}/stock", headers={"X-Api-Key": "wrong"}).status_code == 401


def test_receipt_creates_item_and_stock(api, uid, receive, stock):
    sku = f"T-{uid}"
    receive(sku, 10, name=f"Тестовый товар {uid}")
    receive(sku, 2.5)

    r = api.get(f"/stock/{sku}")
    assert r.json() == {
        "sku": sku,
        "name": f"Тестовый товар {uid}",
        "quantity": 12.5,
        "cells": [{"cell": "ПРИЕМКА", "quantity": 12.5}],
    }
    assert any(i["sku"] == sku for i in api.get("/stock").json()["items"])


def test_receipt_validation(api, uid):
    assert api.post("/receipts", json={"items": []}).status_code == 400
    assert api.post("/receipts", content="not json").status_code == 400

    r = api.post("/receipts", json={"items": [{"sku": f"T-{uid}", "quantity": -1, "name": "x"}]})
    assert r.status_code == 400
    assert "quantity" in r.json()["error"]

    # новый товар без наименования создать нельзя, и поступление не создается целиком
    r = api.post(
        "/receipts",
        json={"items": [{"sku": f"A-{uid}", "quantity": 1, "name": "Есть имя"}, {"sku": f"B-{uid}", "quantity": 1}]},
    )
    assert r.status_code == 422
    assert api.get(f"/stock/A-{uid}").status_code == 404


def test_unknown_sku_returns_404(api, uid):
    assert api.get(f"/stock/NONE-{uid}").status_code == 404
    assert api.get(f"/orders/NONE-{uid}").status_code == 404


def test_orders_list_validation(api):
    assert api.get("/orders", params={"limit": 0}).status_code == 400
    assert api.get("/orders", params={"status": "lost"}).status_code == 400
    assert api.get("/orders", params={"limit": 5}).status_code == 200


def test_unknown_exchange_operation(api):
    assert api.post("/exchange/nothing").status_code == 404
