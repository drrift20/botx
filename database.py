"""
Ultra-light JSON-backed store.

- Everything lives in one in-memory dict (a few KB even with hundreds of users).
- Disk is touched only by a debounced, atomic flush (tmp file + os.replace),
  so a crash mid-write can never corrupt the data file.
- One RLock guards all access, so the FastAPI thread and the bot thread are safe.
"""
import json
import logging
import os
import threading
import time

log = logging.getLogger("botx.db")

DB_PATH = os.environ.get("DB_PATH", "data.json")
FLUSH_INTERVAL = 15          # seconds between disk writes (only if something changed)
START_BALANCE = 500
MAX_BALANCE = 10 ** 12       # sanity cap

DAILY_COOLDOWN = 24 * 3600
STREAK_WINDOW = 48 * 3600    # claim again within 48h to keep your streak
DAILY_BASE = 500
STREAK_STEP = 50             # +50 per streak day
STREAK_CAP = 10              # bonus maxes out at +500


class Database:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._lock = threading.RLock()
        self._io_lock = threading.Lock()
        self._users: dict = {}
        self._dirty = False
        self._stop = threading.Event()
        self._load()
        threading.Thread(target=self._flush_loop, daemon=True, name="db-flush").start()

    # ---------- persistence ----------
    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            users = data.get("users", {}) if isinstance(data, dict) else {}
            self._users = users if isinstance(users, dict) else {}
            log.info("Loaded %d users from %s", len(self._users), self.path)
        except FileNotFoundError:
            log.info("No data file yet, starting fresh.")
        except (json.JSONDecodeError, OSError) as e:
            log.error("Data file unreadable (%s); keeping a backup and starting fresh.", e)
            try:
                os.replace(self.path, self.path + ".corrupt")
            except OSError:
                pass

    def flush(self):
        with self._io_lock:
            with self._lock:
                if not self._dirty:
                    return
                payload = json.dumps({"users": self._users}, separators=(",", ":"))
                self._dirty = False
            try:
                folder = os.path.dirname(os.path.abspath(self.path))
                os.makedirs(folder, exist_ok=True)
                tmp = self.path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(payload)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, self.path)
            except OSError as e:
                log.error("Flush failed: %s", e)
                with self._lock:
                    self._dirty = True

    def _flush_loop(self):
        while not self._stop.wait(FLUSH_INTERVAL):
            self.flush()

    def close(self):
        self._stop.set()
        self.flush()

    # ---------- internals ----------
    def _get(self, uid: str, username: str | None = None) -> dict:
        """Get-or-create. Caller must hold the lock."""
        uid = str(uid)
        u = self._users.get(uid)
        if u is None:
            u = {
                "username": username or f"user{uid[-4:]}",
                "balance": START_BALANCE,
                "last_daily": 0.0,
                "streak": 0,
                "last_rob": 0.0,
                "wins": 0,
                "losses": 0,
                "rob_ok": 0,
                "rob_fail": 0,
            }
            self._users[uid] = u
            self._dirty = True
        elif username and u.get("username") != username:
            u["username"] = username
            self._dirty = True
        return u

    # ---------- public API ----------
    def get_user(self, uid, username: str | None = None) -> dict:
        """Returns a snapshot copy (safe to read without the lock)."""
        with self._lock:
            return dict(self._get(uid, username))

    def user_count(self) -> int:
        with self._lock:
            return len(self._users)

    def find_uid(self, username: str):
        name = username.lower()
        with self._lock:
            for uid, u in self._users.items():
                if u.get("username", "").lower() == name:
                    return uid
        return None

    def claim_daily(self, uid, username: str | None = None) -> dict:
        now = time.time()
        with self._lock:
            u = self._get(uid, username)
            left = DAILY_COOLDOWN - (now - u["last_daily"])
            if left > 0:
                return {"ok": False, "remaining": left, "balance": u["balance"], "streak": u["streak"]}
            if u["last_daily"] and now - u["last_daily"] <= STREAK_WINDOW:
                u["streak"] += 1
            else:
                u["streak"] = 1
            amount = DAILY_BASE + min(u["streak"] - 1, STREAK_CAP) * STREAK_STEP
            u["balance"] = min(u["balance"] + amount, MAX_BALANCE)
            u["last_daily"] = now
            self._dirty = True
            return {"ok": True, "amount": amount, "streak": u["streak"], "balance": u["balance"]}

    def settle_bet(self, uid, bet: int, returned: int):
        """Take `bet`, pay back `returned`. Returns (ok, new_balance)."""
        with self._lock:
            u = self._get(uid)
            if bet <= 0 or bet > u["balance"]:
                return False, u["balance"]
            u["balance"] = min(u["balance"] - bet + returned, MAX_BALANCE)
            if returned > bet:
                u["wins"] += 1
            elif returned < bet:
                u["losses"] += 1
            self._dirty = True
            return True, u["balance"]

    def transfer(self, src, dst, amount: int) -> int:
        """Moves up to `amount` coins from src to dst. Returns what actually moved."""
        with self._lock:
            a, b = self._get(src), self._get(dst)
            amt = max(0, min(int(amount), a["balance"]))
            if amt:
                a["balance"] -= amt
                b["balance"] = min(b["balance"] + amt, MAX_BALANCE)
                self._dirty = True
            return amt

    def rob_cooldown_left(self, uid, cooldown: float) -> float:
        with self._lock:
            u = self._get(uid)
            return max(0.0, cooldown - (time.time() - u["last_rob"]))

    def mark_rob(self, uid, success: bool):
        with self._lock:
            u = self._get(uid)
            u["last_rob"] = time.time()
            u["rob_ok" if success else "rob_fail"] += 1
            self._dirty = True

    def top(self, n: int = 10):
        with self._lock:
            rows = sorted(self._users.items(), key=lambda kv: kv[1]["balance"], reverse=True)[:n]
            return [(uid, u["username"], u["balance"]) for uid, u in rows]

    def rank(self, uid):
        uid = str(uid)
        with self._lock:
            rows = sorted(self._users.items(), key=lambda kv: kv[1]["balance"], reverse=True)
            for i, (k, _) in enumerate(rows, 1):
                if k == uid:
                    return i, len(rows)
            return len(rows) + 1, len(rows)
