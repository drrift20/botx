"""Entry point. Locally:  python main.py
On Render:  Start Command = python main.py    (Render injects PORT)
Run ONE instance only: each process starts its own Instagram listener."""
import asyncio
import logging
import os
import threading
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import config
import database as db
from bot import run_bot
from web import router

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("main")

_stop = threading.Event()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the bot in a background daemon thread (compatible with Database sync methods)
    t = threading.Thread(target=run_bot, args=(_stop,), daemon=True, name="ig-bot")
    t.start()
    log.info("Startup complete - Bot thread started.")
    yield
    _stop.set()
    db.db.close() if hasattr(db, "db") else None


app = FastAPI(title="GC Economy Bot", lifespan=lifespan)
# Make sure static directory exists or skip mounting if not needed
static_dir = config.BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(router)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port,
                proxy_headers=True, forwarded_allow_ips="*", log_level="info")
