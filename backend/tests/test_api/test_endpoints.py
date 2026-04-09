"""
API integration tests — health, template, and generate endpoints.

Strategy: The FastAPI app uses a lifespan that connects to MongoDB.
In tests we use TestClient with `with` context to trigger lifespan,
and override the `get_db` dependency to return a MagicMock that
satisfies every async collection call without a real database.
"""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app import main as app_module
from app.api.dependencies import get_db
from tests.conftest import make_minimal_pptx

# ─── Mock DB fixture ─────────────────────────────────────────────────────────

def _make_mock_db():
    """Return a coroutine-friendly mock MongoDB database.

    NOTE: MagicMock does NOT support setting magic/dunder methods via attribute
    assignment (e.g. `mock.__getattr__ = ...` raises AttributeError).
    Use `configure_mock` or `type(mock).__dunder__ = ...` instead.
    """
    mock_db = MagicMock()

    # Mock collection methods used by generation and template services
    mock_col = MagicMock()
    mock_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
    mock_col.find_one = AsyncMock(return_value=None)
    mock_col.update_one = AsyncMock()

    # list_templates iterates an async cursor — use configure_mock so the
    # dunder is properly set on the MagicMock subclass (not the instance).
    async def _async_iter_fn():
        return
        yield  # empty async generator — pragma: no cover

    # Patch the class-level __aiter__ so `async for` works
    type(mock_col.find.return_value).__aiter__ = lambda self: _async_iter_fn()

    mock_cursor = mock_col.find.return_value
    # .find().sort(...) must return the same async-iterable cursor
    mock_col.find.return_value.sort = MagicMock(return_value=mock_cursor)

    # MagicMock auto-creates child mocks for any attribute access, so we only
    # need to explicitly wire the two collections the services use.
    mock_db.command = AsyncMock(return_value={"ok": 1})
    mock_db.template_profiles = mock_col
    mock_db.generations = mock_col

    return mock_db


def _mock_db_dep():
    """FastAPI dependency override that returns the mock DB."""
    return _make_mock_db()


# ─── App with mocked DB dependency ───────────────────────────────────────────

def _get_client() -> TestClient:
    """
    Create a TestClient with the DB dependency overridden.
    Also patches db_manager.connect/disconnect so lifespan doesn't touch MongoDB.
    """
    from app.main import app

    # Override the get_db dependency so routes don't call real DB
    app.dependency_overrides[get_db] = _mock_db_dep

    # Patch db_manager so lifespan connect/disconnect are no-ops
    with (
        patch("app.database.db_manager.connect", new_callable=AsyncMock),
        patch("app.database.db_manager.disconnect", new_callable=AsyncMock),
    ):
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client

    # Clean up overrides after tests
    app.dependency_overrides.clear()


@pytest.fixture()
def client():
    """
    Pytest fixture that provides a TestClient with all DB operations mocked.
    - FastAPI dependency `get_db` is overridden to return a fully mocked async DB.
    - `db_manager.connect` / `disconnect` are no-op'd so lifespan doesn't touch MongoDB.
    - `get_template_bucket` / `get_generated_bucket` are patched at the module level
      because they are called directly inside service code (not via FastAPI DI).
    """
    from app.main import app

    mock_bucket = MagicMock()

    app.dependency_overrides[get_db] = _mock_db_dep

    connect_patcher = patch("app.database.db_manager.connect", new_callable=AsyncMock)
    disconnect_patcher = patch("app.database.db_manager.disconnect", new_callable=AsyncMock)
    template_bucket_patcher = patch(
        "app.database.get_template_bucket", return_value=mock_bucket
    )
    generated_bucket_patcher = patch(
        "app.database.get_generated_bucket", return_value=mock_bucket
    )
    # Also patch where the services import them from (they import directly)
    svc_template_bucket_patcher = patch(
        "app.services.template_service.get_template_bucket", return_value=mock_bucket
    )
    svc_generated_bucket_patcher = patch(
        "app.services.template_service.get_generated_bucket", return_value=mock_bucket
    )
    route_generated_bucket_patcher = patch(
        "app.api.routes.generate.get_generated_bucket", return_value=mock_bucket
    )

    connect_patcher.start()
    disconnect_patcher.start()
    template_bucket_patcher.start()
    generated_bucket_patcher.start()
    svc_template_bucket_patcher.start()
    svc_generated_bucket_patcher.start()
    route_generated_bucket_patcher.start()

    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
    finally:
        connect_patcher.stop()
        disconnect_patcher.stop()
        template_bucket_patcher.stop()
        generated_bucket_patcher.stop()
        svc_template_bucket_patcher.stop()
        svc_generated_bucket_patcher.stop()
        route_generated_bucket_patcher.stop()
        app.dependency_overrides.clear()



# ─── Health ──────────────────────────────────────────────────────────────────

def test_health_endpoint(client):
    """GET /api/health should return 200 with status=ok."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "llm_model" in data
    assert "guidance_model" in data

# ─── Template list ────────────────────────────────────────────────────────────

def test_list_templates_returns_list(client):
    """GET /api/templates should return a JSON list (possibly empty)."""
    response = client.get("/api/templates")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


# ─── Template upload — validation failures ───────────────────────────────────

def test_upload_template_no_file_returns_422(client):
    """POST /api/templates/upload with no file part → 422 Unprocessable Entity."""
    response = client.post("/api/templates/upload", data={"name": "Test"})
    assert response.status_code == 422


def test_upload_template_no_name_returns_422(client):
    """POST /api/templates/upload with no name field → 422 Unprocessable Entity."""
    fake_pptx = make_minimal_pptx(3)
    response = client.post(
        "/api/templates/upload",
        files={"file": ("deck.pptx", fake_pptx, "application/octet-stream")},
        # missing 'name' form field
    )
    assert response.status_code == 422


def test_upload_template_invalid_file_type(client):
    """POST /api/templates/upload with a non-PPTX file should return 400 or 500."""
    fake_file = b"this is not a pptx"
    response = client.post(
        "/api/templates/upload",
        files={"file": ("test.pptx", fake_file, "application/octet-stream")},
        data={"name": "Test"},
    )
    # Must fail — not a valid PPTX (no PK magic bytes), service raises ValueError → 400
    assert response.status_code in (400, 500)


def test_upload_valid_pptx_returns_201(client):
    """POST /api/templates/upload with a valid minimal PPTX → 201 Created."""
    pptx_bytes = make_minimal_pptx(3)

    # Mock GridFS store so the buckets don't need to be real
    with (
        patch("app.services.template_service.store_template_binary", new_callable=AsyncMock,
              return_value=str(ObjectId())),
        patch("app.database.get_template_bucket", return_value=MagicMock()),
    ):
        response = client.post(
            "/api/templates/upload",
            files={"file": ("test_deck.pptx", pptx_bytes, "application/octet-stream")},
            data={"name": "Integration Test Template"},
        )

    assert response.status_code == 201
    data = response.json()
    assert "template_id" in data
    assert data["status"] == "analyzing"
    assert data["name"] == "Integration Test Template"


# ─── Template get — invalid ID ────────────────────────────────────────────────

def test_get_template_invalid_object_id(client):
    """GET /api/templates/<garbage-id> should return 404 (invalid bson ObjectId)."""
    response = client.get("/api/templates/not-a-valid-id")
    assert response.status_code == 404


def test_get_template_nonexistent_id(client):
    """GET /api/templates/<valid-but-missing ObjectId> → 404."""
    response = client.get("/api/templates/000000000000000000000000")
    assert response.status_code == 404


# ─── Generate — validation failures ──────────────────────────────────────────

def test_generate_missing_template_id_returns_422(client):
    """POST /api/generate with no template_id → 422."""
    response = client.post(
        "/api/generate",
        json={"prompt": "Quarterly business review"},
    )
    assert response.status_code == 422


def test_generate_missing_prompt_returns_422(client):
    """POST /api/generate with no prompt → 422."""
    response = client.post(
        "/api/generate",
        json={"template_id": "000000000000000000000000"},
    )
    assert response.status_code == 422


def test_generate_prompt_too_long_returns_400(client):
    """POST /api/generate with a prompt exceeding MAX_PROMPT_CHARS → 400."""
    long_prompt = "A" * 9000  # exceeds default 8000-char limit
    response = client.post(
        "/api/generate",
        json={"template_id": "000000000000000000000000", "prompt": long_prompt},
    )
    assert response.status_code == 400


def test_generate_invalid_template_id_queues_with_202(client):
    """
    POST /api/generate — generation queues and returns 202.
    The pipeline will fail asynchronously when the template isn't found.
    """
    response = client.post(
        "/api/generate",
        json={"template_id": "000000000000000000000000", "prompt": "Test presentation"},
    )
    assert response.status_code == 202
    data = response.json()
    assert "generation_id" in data
    assert data["status"] == "processing"


def test_generate_empty_prompt_accepted_as_202(client):
    """
    POST /api/generate with an empty string prompt.
    GenerateRequest has no min_length constraint, so Pydantic accepts it (202).
    """
    response = client.post(
        "/api/generate",
        json={"template_id": "000000000000000000000000", "prompt": ""},
    )
    assert response.status_code == 202


# ─── Generation download — invalid IDs ───────────────────────────────────────

def test_download_nonexistent_generation_returns_404(client):
    """GET /api/generate/<valid-ObjectId>/download → 404 when generation not found."""
    # get_generated_bucket needs to be mocked too
    with patch("app.database.get_generated_bucket", return_value=MagicMock()):
        response = client.get("/api/generate/000000000000000000000000/download")
    assert response.status_code == 404


def test_download_invalid_id_returns_404(client):
    """GET /api/generate/<garbage-id>/download → 404."""
    with patch("app.database.get_generated_bucket", return_value=MagicMock()):
        response = client.get("/api/generate/garbage-id-xyz/download")
    assert response.status_code == 404

