"""Convenience launcher: initialise the DB and start the dev server.

    python run.py            # serve on http://127.0.0.1:8000
    HOST=0.0.0.0 PORT=9000 python run.py
"""
from __future__ import annotations

import os

import uvicorn

from app.database import init_db

if __name__ == "__main__":
    init_db()
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "false").lower() == "true",
    )
