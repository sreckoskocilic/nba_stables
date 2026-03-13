import importlib

from fastapi.middleware.cors import CORSMiddleware


def test_cors_not_wildcard_by_default(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    app_module = importlib.reload(importlib.import_module("main"))
    app = app_module.app
    cors = next(
        (m for m in app.user_middleware if m.cls is CORSMiddleware),
        None,
    )
    assert cors is not None
    assert cors.kwargs.get("allow_origins") != ["*"]
