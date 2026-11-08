from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
import config
import database as db

router = APIRouter()
templates = Jinja2Templates(directory=str(config.BASE_DIR / "templates"))

@router.get("/")
def home(request: Request):
    return templates.TemplateResponse(
        request, "index.html", {"page": "home", "users_count": db.db.user_count() if hasattr(db, "db") else db.user_count()}
    )

@router.get("/leaderboard")
def leaderboard(request: Request):
    # Changed top_users to top to match database.py completely
    top_func = db.top_users if hasattr(db, "top_users") else db.top
    users = top_func(10)
    return templates.TemplateResponse(
        request, "leaderboard.html", {"users": users, "page": "leaderboard"}
    )
