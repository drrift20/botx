"""Central configuration. Secrets come ONLY from environment variables."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file if present locally
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# --- Automatic Session File Generator for Render ---
# If SESSION_DATA environment variable is set (on Render), write it to session.json
session_data = os.environ.get("SESSION_DATA")
if session_data:
    session_file = BASE_DIR / "session.json"
    try:
        with open(session_file, "w", encoding="utf-8") as f:
            f.write(session_data)
        print("Successfully generated session.json from SESSION_DATA environment variable.")
    except Exception as e:
        print(f"Failed to write session.json: {e}")

# --- Secrets / environment (set these in the Render dashboard) --------------
USERNAME = os.environ.get("IG_USERNAME", "")
PASSWORD = os.environ.get("IG_PASSWORD", "")
THREAD_ID = os.environ.get("THREAD_ID", "")
MONGO_URI = os.environ.get("MONGO_URI", "")
MONGO_DB = os.environ.get("MONGO_DB", "gcbot")

# Public URL used in !leaderboard / !shop replies. Render sets RENDER_EXTERNAL_URL.
DASHBOARD_URL = (os.environ.get("DASHBOARD_URL")
                 or os.environ.get("RENDER_EXTERNAL_URL")
                 or "https://your-domain.com").rstrip("/")

# --- Polling / rate limiting ----------------------------------------------
POLL_MIN, POLL_MAX = 3.0, 6.0
SEND_DELAY = 1.5
USER_CMD_COOLDOWN = 2.0

# --- Game balance ----------------------------------------------------------
DROP_MIN, DROP_MAX = 20, 40
CHEST_MIN, CHEST_MAX = 100, 300

DAILY_REWARD = 250
DAILY_COOLDOWN = 24 * 3600
STREAK_WINDOW = 48 * 3600
STREAK_BONUS = 20
STREAK_BONUS_MAX_DAYS = 14

WORK_COOLDOWN = 3600
WORK_MIN, WORK_MAX = 30, 90

ROB_COOLDOWN = 300
ROB_MIN_BALANCE = 50
ROB_SUCCESS_CHANCE = 0.5
ROB_PCT_MIN, ROB_PCT_MAX = 0.10, 0.30

DUEL_TIMEOUT = 60
