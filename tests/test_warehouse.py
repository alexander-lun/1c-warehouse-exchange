"""Адресное хранение: ячейки, размещение, отбор по заказу, лист отбора, оборачиваемость."""

import datetime
import io
from concurrent.futures import ThreadPoolExecutor

import pdfplumber
import pytest

from conftest import order

RECEPTION = "ПРИЕМКА"


@pytest.fixture
def cells(api, uid):
    """Создает ячейки с уникальными адресами: cells(("A", 10), ...) -> {"A": "A-<uid>"}."""

    def _cells(*items):
        addresses = {name: f"{name}-{uid}" for name, _ in items}
        payload = [{"address": addresses[name], "route_order": route} for name, route in items]
        r = api.post("/cells", json={"cells": payload})
        assert r.status_code == 200, r.text
        return addresses

    return _cells


@pytest.fixture
def place(api):
    def _place(*items):
        payload = [{"sku": sku, "from": src, "to": dst, "quantity": qty} for sku, src, dst, qty in items]
        return api.post("/placements", json={"items": payload})

    return _place


def cells_of(api, sku):
    return {c["cell"]: c["quantity"] for c in api.get(f"/stock/{sku}").json()["cells"]}


def test_cells_are_upserted_by_address(api, cells):
    addr = cells(("A", 10))["A"]
    r = api.post("/cells", json={"cells": [{"address": addr, "route_order": 20}]})
    assert r.json() == {"created": 0, "updated": 1}
    assert api.post("/cells", json={"cells": []}).status_code == 400


def test_placement_moves_goods_from_reception(api, uid, cells, receive, place):
    sku = f"T-{uid}"
    a = cells(("A", 10))["A"]
    receive(sku, 10, name="Товар")

    r = place((sku, RECEPTION, a, 7))
    assert r.status_code == 201, r.text
    assert r.json()["items"] == [{"sku": sku, "from": RECEPTION, "to": a, "quantity": 7}]
    assert cells_of(api, sku) == {RECEPTION: 3, a: 7}


def test_placement_cannot_take_more_than_in_cell(api, uid, cells, receive, place):
    sku = f"T-{uid}"
    a = cells(("A", 10))["A"]
    receive(sku, 2, name="Товар")

    r = place((sku, RECEPTION, a, 5))
    assert r.status_code == 422
    assert "не хватает" in r.json()["error"]
    assert cells_of(api, sku) == {RECEPTION: 2}

    assert place((sku, RECEPTION, f"NONE-{uid}", 1)).status_code == 400


def test_auto_placement_puts_goods_where_item_is_stored(api, uid, cells, receive, place):
    sku = f"T-{uid}"
    a = cells(("A", 10))["A"]
    receive(sku, 4, name="Товар")
    assert place((sku, RECEPTION, a, 4)).status_code == 201

    receive(sku, 6)
    r = api.post("/placements")
    assert r.status_code == 201, r.text
    assert {"sku": sku, "from": RECEPTION, "to": a, "quantity": 6} in r.json()["items"]
    assert cells_of(api, sku) == {a: 10}


def test_pick_walks_cells_in_route_order(api, mock, uid, cells, receive, place, pull):
    sku1, sku2, order_id = f"T1-{uid}", f"T2-{uid}", f"MP-{uid}"
    c = cells(("A", 10), ("B", 20), ("C", 30))
    receive(sku1, 7, name="Товар 1")
    receive(sku2, 3, name="Товар 2")
    assert (
        place((sku1, RECEPTION, c["C"], 5), (sku1, RECEPTION, c["A"], 2), (sku2, RECEPTION, c["B"], 3)).status_code
        == 201
    )

    mock.post("/_test/orders", json=[order(order_id, (sku1, 4, 100), (sku2, 1, 50))])
    assert pull()["errors"] == []

    r = api.post(f"/orders/{order_id}/pick")
    assert r.status_code == 201, r.text
    items = [(i["cell"], i["sku"], i["quantity"]) for i in r.json()["items"]]
    # Сначала вся ячейка A (2 шт.), остаток - из C; по пути - B.
    assert items == [(c["A"], sku1, 2), (c["B"], sku2, 1), (c["C"], sku1, 2)]
    assert cells_of(api, sku1) == {c["C"]: 3}
    assert cells_of(api, sku2) == {c["B"]: 2}

    assert api.post(f"/orders/{order_id}/pick").status_code == 409
    assert api.get(f"/orders/{order_id}/pick-list", params={"format": "json"}).json()["items"] == r.json()["items"]


def test_pick_list_pdf(api, mock, uid, cells, receive, place, pull):
    sku, order_id = f"T-{uid}", f"MP-{uid}"
    a = cells(("A", 10))["A"]
    receive(sku, 3, name="Товар для листа отбора")
    assert place((sku, RECEPTION, a, 3)).status_code == 201
    mock.post("/_test/orders", json=[order(order_id, (sku, 2, 10))])
    pull()

    assert api.get(f"/orders/{order_id}/pick-list").status_code == 404
    assert api.post(f"/orders/{order_id}/pick").status_code == 201

    r = api.get(f"/orders/{order_id}/pick-list")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    assert "Лист отбора" in text
    assert order_id in text
    assert a in text and sku in text


def test_goods_in_reception_cannot_be_picked(api, mock, uid, receive, pull):
    sku, order_id = f"T-{uid}", f"MP-{uid}"
    receive(sku, 5, name="Товар")
    mock.post("/_test/orders", json=[order(order_id, (sku, 1, 10))])
    pull()

    r = api.post(f"/orders/{order_id}/pick")
    assert r.status_code == 422
    assert "не хватает" in r.json()["error"]


def test_cancelled_order_cannot_be_picked(api, mock, uid, cells, receive, place, pull):
    sku, order_id = f"T-{uid}", f"MP-{uid}"
    a = cells(("A", 10))["A"]
    receive(sku, 5, name="Товар")
    place((sku, RECEPTION, a, 5))
    mock.post("/_test/orders", json=[order(order_id, (sku, 1, 10))])
    pull()
    assert api.put(f"/orders/{order_id}/status", json={"status": "cancelled"}).status_code == 200

    r = api.post(f"/orders/{order_id}/pick")
    assert r.status_code == 422
    assert "Ожидает сборки" in r.json()["error"]
    assert cells_of(api, sku) == {a: 5}


def test_parallel_picks_of_one_order(api, mock, uid, cells, receive, place, pull):
    sku, order_id = f"T-{uid}", f"MP-{uid}"
    a = cells(("A", 10))["A"]
    receive(sku, 10, name="Товар")
    place((sku, RECEPTION, a, 10))
    mock.post("/_test/orders", json=[order(order_id, (sku, 2, 10))])
    pull()

    with ThreadPoolExecutor(4) as pool:
        codes = sorted(pool.map(lambda _: api.post(f"/orders/{order_id}/pick").status_code, range(4)))

    assert codes.count(201) == 1
    assert cells_of(api, sku) == {a: 8}


def test_turnover(api, mock, uid, receive, pull):
    sku, order_id = f"T-{uid}", f"MP-{uid}"
    receive(sku, 10, name="Товар")
    mock.post("/_test/orders", json=[order(order_id, (sku, 4, 10))])
    pull()

    today = datetime.date.today().isoformat()
    r = api.get("/reports/turnover", params={"from": today, "to": today})
    assert r.status_code == 200, r.text
    item = next(i for i in r.json()["items"] if i["sku"] == sku)
    # Средний остаток (0 + 6) / 2 = 3, продано 4 за 1 день: оборачиваемость 3 * 1 / 4 = 0.75 -> 0.8 дня,
    # остатка 6 хватит на 6 / 4 = 1.5 дня.
    assert item == {
        "sku": sku,
        "name": "Товар",
        "opening": 0,
        "sold": 4,
        "closing": 6,
        "average": 3,
        "turnover_days": 0.8,
        "cover_days": 1.5,
    }

    assert api.get("/reports/turnover", params={"from": "2026-13-01"}).status_code == 400
    assert api.get("/reports/turnover", params={"from": today, "to": "2020-01-01"}).status_code == 400
