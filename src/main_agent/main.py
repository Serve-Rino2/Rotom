"""Uvicorn entrypoint for the main_agent HTTP service."""

from __future__ import annotations

import logging

import uvicorn

from .api import create_app
from .config import load_settings


def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    settings = load_settings()
    app = create_app(settings)
    uvicorn.run(
        app,
        host=settings.bind_host,
        port=settings.bind_port,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    run()
