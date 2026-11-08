"""API integration tests."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

# Use in-memory SQLite for tests
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.main import app
from app.database import Base, get_db


@pytest.fixture(scope="module")
def test_client():
    # Create test DB
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


def test_root(test_client):
    r = test_client.get("/")
    assert r.status_code == 200
    assert r.json()["app"] == "Udyam Digital API"


def test_health(test_client):
    r = test_client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_catalogue_endpoint(test_client):
    r = test_client.get("/recommend/catalogue")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 25
    assert len(data["products"]) == 25


def test_recommendations_endpoint(test_client):
    r = test_client.post("/recommend/", json={
        "city_tier": 2,
        "employee_count": 5,
        "num_sites": 1,
        "has_gstin": False,
        "gstin_active": False,
    })
    assert r.status_code == 200
    data = r.json()
    assert "eligible" in data
    assert "ineligible" in data


def test_recommendations_tier1_only_filtered():
    """P03 should not appear as eligible for tier 2."""
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        r = client.post("/recommend/", json={
            "city_tier": 2,
            "employee_count": 20,
            "num_sites": 1,
            "has_gstin": True,
            "gstin_active": True,
        })
        eligible_ids = [p["product_id"] for p in r.json()["eligible"]]
        assert "P03" not in eligible_ids


def test_validate_gstin_endpoint(test_client):
    r = test_client.post("/kyc/validate-gstin", json={"gstin": "32TTNXB7384T1ZW"})
    assert r.status_code == 200
    data = r.json()
    assert data["format_valid"]
    assert data["found_in_registry"]
    assert data["active"]
    assert data["status"] == "VERIFIED"


def test_validate_gstin_invalid(test_client):
    r = test_client.post("/kyc/validate-gstin", json={"gstin": "INVALID"})
    assert r.status_code == 200
    data = r.json()
    assert not data["format_valid"]
    assert data["status"] == "FAILED"


def test_validate_udyam_endpoint(test_client):
    r = test_client.post("/kyc/validate-udyam", json={"udyam_number": "UDYAM-KL-00-3078801"})
    assert r.status_code == 200
    data = r.json()
    assert data["format_valid"]
    assert data["found_in_registry"]


def test_create_business(test_client):
    r = test_client.post("/business/", json={
        "name": "Test Bakery",
        "business_type": "Bakery",
        "segment": "micro",
        "city": "Pune",
        "city_tier": 2,
        "state": "Maharashtra",
        "employee_count": 5,
        "num_sites": 1,
    })
    assert r.status_code == 200
    data = r.json()
    assert "business_id" in data
    return data["business_id"]


def test_auth_register_and_login(test_client):
    # Register
    r = test_client.post("/auth/register", json={
        "email": "test@example.com",
        "password": "testpass123",
        "full_name": "Test User",
        "role": "customer",
    })
    assert r.status_code == 200
    assert "access_token" in r.json()

    # Login
    r2 = test_client.post("/auth/token", data={
        "username": "test@example.com",
        "password": "testpass123",
    })
    assert r2.status_code == 200
    assert "access_token" in r2.json()


def test_categories_endpoint(test_client):
    r = test_client.get("/recommend/categories")
    assert r.status_code == 200
    cats = r.json()["categories"]
    assert "Connectivity" in cats
    assert "Security" in cats


def test_quote_creation_with_invalid_product(test_client):
    """Quote with non-existent product should return 400."""
    # Create a business first
    biz_r = test_client.post("/business/", json={
        "name": "Quote Test Biz", "city_tier": 2, "employee_count": 5, "num_sites": 1
    })
    biz_id = biz_r.json()["business_id"]

    r = test_client.post("/quotes/", json={
        "business_id": biz_id,
        "line_items": [{"product_id": "PZZZZ", "quantity": 1}],
        "city_tier": 2,
    })
    assert r.status_code == 400
