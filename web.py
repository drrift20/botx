from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
import config
from database import Database

router = APIRouter()
templates = Jinja2Templates(directory=str(config.BASE_DIR / "templates"))
db = Database()

@router.get("/")
@router.get("/health")
def home(request: Request = None):
    count = 0
    try:
        count = db.user_count()
    except Exception:
        pass
    
    # If UptimeRobot pings /health or raw API, return JSON if no request template context
    if request and request.url.path == "/health":
        return {"status": "ok", "users": count}
        
    try:
        return templates.TemplateResponse(
            request, "index.html", {"page": "home", "users_count": count}
        )
    except Exception:
        return {"status": "ok", "users_count": count}

@router.get("/leaderboard")
def leaderboard(request: Request):
    try:
        users = db.top(10)
    except Exception:
        users = []
    return templates.TemplateResponse(
        request, "leaderboard.html", {"users": users, "page": "leaderboard"}
    )
