import os
import uuid

import httpx
import pytest

API_URL = os.environ.get("API_URL", "http://127.0.0.1:8081/warehouse/hs/api")
API_KEY = os.environ.get("API_KEY", "api-test-token")
MOCK_URL = os.environ.get("MOCK_URL", "http://127.0.0.1:8090")


@pytest.fixture(scope="session")
def api():
    with httpx.Client(base_url=API_URL, headers={"X-Api-Key": API_KEY}, timeout=60) as client:
        yield client


@pytest.fixture(scope="session")
def mock():
    with httpx.Client(base_url=MOCK_URL, timeout=10) as client:
        yield client


@pytest.fixture(autouse=True)
def clean_mock(mock):
    mock.post("/_test/reset").raise_for_status()


@pytest.fixture
def uid():
    """Уникальный суффикс: база между запусками не очищается."""
    return uuid.uuid4().hex[:8].upper()


@pytest.fixture
def receive(api):
    def _receive(sku, quantity, name=None):
        item = {"sku": sku, "quantity": quantity}
        if name:
            item["name"] = name
        r = api.post("/receipts", json={"items": [item]})
        assert r.status_code == 201, r.text
        return r.json()

    return _receive


@pytest.fixture
def stock(api):
    def _stock(sku):
        r = api.get(f"/stock/{sku}")
        assert r.status_code == 200, r.text
        return r.json()["quantity"]

    return _stock


@pytest.fixture
def pull(api):
    def _pull():
        r = api.post("/exchange/pull-orders")
        assert r.status_code == 200, r.text
        return r.json()

    return _pull


def order(order_id, *items, status="awaiting_packaging"):
    return {
        "order_id": order_id,
        "status": status,
        "items": [{"offer_id": sku, "quantity": qty, "price": price} for sku, qty, price in items],
    }
