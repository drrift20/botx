"""Entry point. Locally:  python main.py
On Render:  Start Command = python main.py   (Render injects PORT)
Run ONE instance only: each process starts its own Instagram listener."""
import asyncio
import logging
import os
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(db.init_db)  # connects to MongoDB, creates indexes/seed data
    stop = asyncio.Event()
    task = asyncio.create_task(run_bot(stop))
    log.info("Startup complete")
    yield
    stop.set()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="GC Economy Bot", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(config.BASE_DIR / "static")), name="static")
app.include_router(router)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port,
                proxy_headers=True, forwarded_allow_ips="*", log_level="info")
