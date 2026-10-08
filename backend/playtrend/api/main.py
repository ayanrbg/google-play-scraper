"""FastAPI application. In production Caddy serves the built frontend and proxies /api here."""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from playtrend.api import account, admin, games, keywords, picks, ratelimit

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="PlayTrend", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.middleware("http")(ratelimit.middleware)
app.include_router(account.router)
app.include_router(games.router)
app.include_router(keywords.router)
app.include_router(picks.router)
app.include_router(admin.router)


@app.get("/api/health")
def health():
    return {"ok": True}


# Optional: serve a built frontend directly (single-container setups, local preview).
_dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        target = _dist / path
        if path and target.is_file():
            return FileResponse(target)
        return FileResponse(_dist / "index.html")
