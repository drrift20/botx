import config
import database as db
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=str(config.BASE_DIR / "templates"))
router = APIRouter()


@router.get("/", include_in_schema=False)
def index():
    return RedirectResponse("/leaderboard")


# Plain `def` routes run in FastAPI's threadpool, so SQLite calls never block the loop.
@router.get("/leaderboard", response_class=HTMLResponse)
def leaderboard(request: Request):
    return templates.TemplateResponse(
        request, "leaderboard.html", {"users": db.top_users(10), "page": "leaderboard"})


@router.get("/shop", response_class=HTMLResponse)
def shop(request: Request):
    return templates.TemplateResponse(
        request, "shop.html", {"items": db.shop_items(), "page": "shop"})


@router.api_route("/health", methods=["GET", "HEAD"], include_in_schema=False)
def health():
    """Render health check / uptime-pinger target."""
    return {"status": "ok"}
