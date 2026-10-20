from concurrent.futures import ThreadPoolExecutor

from conftest import order

MOCK_AUTH = {"Authorization": "Bearer dev-token"}


def test_pull_creates_order_and_reserves_stock(api, mock, uid, receive, stock, pull):
    sku, order_id = f"T-{uid}", f"MP-{uid}"
    receive(sku, 5, name="Товар")
    mock.post("/_test/orders", json=[order(order_id, (sku, 2, 100))])

    result = pull()
    assert result["created"] == 1
    assert result["errors"] == []

    data = api.get(f"/orders/{order_id}").json()
    assert data["status"] == "awaiting_packaging"
    assert data["posted"] is True
    assert data["amount"] == 200
    assert data["items"] == [{"sku": sku, "name": "Товар", "quantity": 2, "price": 100, "amount": 200}]
    assert stock(sku) == 3


def test_pull_is_idempotent(api, mock, uid, receive, stock, pull):
    sku, order_id = f"T-{uid}", f"MP-{uid}"
    receive(sku, 5, name="Товар")
    mock.post("/_test/orders", json=[order(order_id, (sku, 1, 10))])

    assert pull()["created"] == 1
    assert pull()["created"] == 0
    assert stock(sku) == 4
    ids = [o["id"] for o in api.get("/orders", params={"limit": 1000}).json()["orders"]]
    assert ids.count(order_id) == 1


def test_order_without_stock_is_saved_unposted_and_posted_later(api, mock, uid, receive, stock, pull):
    sku, order_id = f"T-{uid}", f"MP-{uid}"
    receive(sku, 1, name="Товар")
    mock.post("/_test/orders", json=[order(order_id, (sku, 3, 50))])

    result = pull()
    assert result["created"] == 0
    assert len(result["errors"]) == 1
    assert "не хватает 2" in result["errors"][0]
    assert api.get(f"/orders/{order_id}").json()["posted"] is False
    assert stock(sku) == 1

    receive(sku, 5)
    result = pull()
    assert result["updated"] == 1
    assert result["errors"] == []
    assert api.get(f"/orders/{order_id}").json()["posted"] is True
    assert stock(sku) == 3


def test_order_with_unknown_sku_is_not_created(api, mock, uid, pull):
    order_id = f"MP-{uid}"
    mock.post("/_test/orders", json=[order(order_id, (f"NONE-{uid}", 1, 1))])

    result = pull()
    assert any(f"NONE-{uid}" in e for e in result["errors"])
    assert api.get(f"/orders/{order_id}").status_code == 404


def test_status_from_marketplace_is_applied(api, mock, uid, receive, stock, pull):
    sku, order_id = f"T-{uid}", f"MP-{uid}"
    receive(sku, 5, name="Товар")
    mock.post("/_test/orders", json=[order(order_id, (sku, 2, 10))])
    pull()

    # маркетплейс отменил заказ — загрузка должна снять резерв
    mock.post("/_test/orders", json=[order(order_id, (sku, 2, 10), status="cancelled")])
    result = pull()
    assert result["updated"] == 1
    assert api.get(f"/orders/{order_id}").json()["status"] == "cancelled"
    assert stock(sku) == 5


def test_status_change_is_sent_to_marketplace(api, mock, uid, receive, pull):
    sku, order_id = f"T-{uid}", f"MP-{uid}"
    receive(sku, 5, name="Товар")
    mock.post("/_test/orders", json=[order(order_id, (sku, 1, 10))])
    pull()

    r = api.put(f"/orders/{order_id}/status", json={"status": "delivering"})
    assert r.status_code == 200, r.text
    assert r.json()["marketplace_errors"] == []
    assert mock.get(f"/_test/orders/{order_id}").json()["status"] == "delivering"

    assert api.put(f"/orders/{order_id}/status", json={"status": "delivered"}).status_code == 200
    r = api.put(f"/orders/{order_id}/status", json={"status": "cancelled"})
    assert r.status_code == 409


def test_cancel_releases_stock(api, mock, uid, receive, stock, pull):
    sku, order_id = f"T-{uid}", f"MP-{uid}"
    receive(sku, 5, name="Товар")
    mock.post("/_test/orders", json=[order(order_id, (sku, 4, 10))])
    pull()
    assert stock(sku) == 1

    assert api.put(f"/orders/{order_id}/status", json={"status": "cancelled"}).status_code == 200
    assert stock(sku) == 5
    cancelled = [o["id"] for o in api.get("/orders", params={"status": "cancelled", "limit": 1000}).json()["orders"]]
    assert order_id in cancelled


def test_status_validation(api, mock, uid, receive, pull):
    sku, order_id = f"T-{uid}", f"MP-{uid}"
    receive(sku, 1, name="Товар")
    mock.post("/_test/orders", json=[order(order_id, (sku, 1, 10))])
    pull()

    assert api.put(f"/orders/{order_id}/status", json={"status": "lost"}).status_code == 400
    assert api.put(f"/orders/{order_id}/status", content="[]").status_code == 400
    assert api.put(f"/orders/NONE-{uid}/status", json={"status": "delivering"}).status_code == 404


def test_push_stock(api, mock, uid, receive):
    sku = f"T-{uid}"
    receive(sku, 7, name="Товар")
    mock.post("/_test/offers", json=[sku])

    r = api.post("/exchange/push-stock")
    assert r.status_code == 200
    assert r.json()["processed"] >= 1
    assert mock.get("/v1/stocks", headers=MOCK_AUTH).json()[sku] == 7


def test_status_change_posts_order_that_waited_for_stock(api, mock, uid, receive, stock, pull):
    sku, order_id = f"T-{uid}", f"MP-{uid}"
    receive(sku, 1, name="Товар")
    mock.post("/_test/orders", json=[order(order_id, (sku, 2, 10))])
    pull()
    assert api.get(f"/orders/{order_id}").json()["posted"] is False

    # без товара заказ провести нельзя
    r = api.put(f"/orders/{order_id}/status", json={"status": "delivering"})
    assert r.status_code == 422
    assert "не хватает 1" in r.json()["error"]

    receive(sku, 1)
    r = api.put(f"/orders/{order_id}/status", json={"status": "delivering"})
    assert r.status_code == 200, r.text
    assert r.json()["posted"] is True
    assert stock(sku) == 0


def test_status_is_resent_after_marketplace_outage(api, mock, uid, receive, pull):
    sku, order_id = f"T-{uid}", f"MP-{uid}"
    receive(sku, 5, name="Товар")
    mock.post("/_test/orders", json=[order(order_id, (sku, 1, 10))])
    pull()

    mock.post("/_test/fail", params={"status_updates": True})
    r = api.put(f"/orders/{order_id}/status", json={"status": "delivering"})
    assert r.status_code == 200
    assert r.json()["status"] == "delivering"
    assert len(r.json()["marketplace_errors"]) == 1
    assert mock.get(f"/_test/orders/{order_id}").json()["status"] == "awaiting_packaging"

    # пока маркетплейс недоступен, статус остается в очереди
    r = api.post("/exchange/push-statuses")
    assert any(order_id in e for e in r.json()["errors"])

    mock.post("/_test/fail", params={"status_updates": False})
    r = api.post("/exchange/push-statuses")
    assert r.json()["errors"] == []
    assert r.json()["processed"] >= 1
    assert mock.get(f"/_test/orders/{order_id}").json()["status"] == "delivering"


def test_parallel_orders_do_not_oversell(api, mock, uid, receive, stock, pull):
    sku = f"T-{uid}"
    ids = [f"A-{uid}", f"B-{uid}"]
    receive(sku, 1, name="Товар")
    mock.post("/_test/orders", json=[order(i, (sku, 3, 10)) for i in ids])
    pull()
    receive(sku, 4)  # остаток 5: хватает только на один заказ

    def deliver(order_id):
        return api.put(f"/orders/{order_id}/status", json={"status": "delivering"}).status_code

    with ThreadPoolExecutor(2) as pool:
        codes = sorted(pool.map(deliver, ids))

    assert codes == [200, 422]
    assert stock(sku) == 2


def test_parallel_pulls_create_one_order(api, mock, uid, receive, stock):
    sku, order_id = f"T-{uid}", f"MP-{uid}"
    receive(sku, 10, name="Товар")
    mock.post("/_test/orders", json=[order(order_id, (sku, 1, 10))])

    with ThreadPoolExecutor(5) as pool:
        results = list(pool.map(lambda _: api.post("/exchange/pull-orders").json(), range(5)))

    assert sum(r["created"] for r in results) == 1
    assert all(r["errors"] == [] for r in results)
    ids = [o["id"] for o in api.get("/orders", params={"limit": 1000}).json()["orders"]]
    assert ids.count(order_id) == 1
    assert stock(sku) == 9
