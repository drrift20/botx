import logging
import os
import random
import re
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI
from instagrapi import Client
from instagrapi.exceptions import ChallengeRequired, LoginRequired, PleaseWaitFewMinutes

from database import DAILY_COOLDOWN, Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("botx")

# ----------------------------- config -----------------------------
IG_USERNAME = os.environ.get("IG_USERNAME", "")
IG_PASSWORD = os.environ.get("IG_PASSWORD", "")
IG_SESSIONID = os.environ.get("IG_SESSIONID", "")
THREAD_ID = os.environ.get("THREAD_ID", "").strip()
PREFIX = os.environ.get("PREFIX", "!")
SESSION_FILE = os.environ.get("SESSION_FILE", "session.json")

# Auto-generate session.json from SESSION_DATA env var if present
SESSION_DATA_ENV = os.environ.get("SESSION_DATA", "")
if SESSION_DATA_ENV and not os.path.exists(SESSION_FILE):
    try:
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            f.write(SESSION_DATA_ENV)
        log.info("Successfully generated %s from SESSION_DATA environment variable.", SESSION_FILE)
    except Exception as e:
        log.error("Failed to write session.json from SESSION_DATA: %s", e)

POLL_MIN, POLL_MAX = 4.0, 7.0      # seconds between polls (randomised)
FETCH_AMOUNT = 20                  # messages fetched per poll
USER_CMD_COOLDOWN = 2.5            # anti-spam: seconds between commands per user

ROB_COOLDOWN = 30 * 60
ROB_MIN_BALANCE = 100              # both robber and victim need at least this
ROB_SUCCESS = 0.45
FLIP_SIDES = {"h": "heads", "head": "heads", "heads": "heads",
              "t": "tails", "tail": "tails", "tails": "tails"}
ROLL_RETURNS = {1: 0.0, 2: 0.25, 3: 0.5, 4: 1.0, 5: 1.5, 6: 2.5}
DICE = "⚀⚁⚂⚃⚄⚅"

START_TIME = time.time()
db = Database()


# ----------------------------- helpers -----------------------------
@dataclass
class Ctx:
    uid: str
    name: str
    args: list
    uid_to_name: dict
    name_to_uid: dict
    bot_uid: str


def fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m = max(rem // 60, 1) if not h else rem // 60
    return f"{h}h {m}m" if h else f"{m}m"


_AMOUNT_RE = re.compile(r"^(\d+(?:\.\d+)?)([km]?)$")


def parse_amount(raw: str, balance: int):
    raw = raw.lower().replace(",", "")
    if raw in ("all", "max"):
        return balance
    if len(raw) > 15:
        return None
    m = _AMOUNT_RE.match(raw)
    if not m:
        return None
    val = int(float(m.group(1)) * {"": 1, "k": 1_000, "m": 1_000_000}[m.group(2)])
    return val if val > 0 else None


def check_bet(bet, balance: int):
    if balance <= 0:
        return "💸 You're broke! Use !daily to get coins."
    if bet is None:
        return "❌ Invalid amount. Try a number, 1k, or 'all'."
    if bet > balance:
        return f"❌ You only have {balance:,} coins."
    return None


# ----------------------------- commands -----------------------------
def cmd_ping(ctx: Ctx) -> str:
    return f"🏓 Pong! Online for {fmt_duration(time.time() - START_TIME)}."


def cmd_help(ctx: Ctx) -> str:
    p = PREFIX
    return (
        "🎮 COMMANDS\n"
        f"{p}daily – free coins every 24h (streaks = bigger bonus)\n"
        f"{p}coinflip <heads/tails> <amount> – double or nothing\n"
        f"{p}roll <amount> – 1:lose all, 2:-75%, 3:-50%, 4:push, 5:+50%, 6:+150%\n"
        f"{p}rob <username> – steal coins (risky, 30m cooldown)\n"
        f"{p}profile – your balance & stats\n"
        f"{p}leaderboard – richest members\n"
        f"{p}ping – check the bot\n"
        "Tip: amounts accept 'all', 1k, 2.5k, 1m"
    )


def cmd_daily(ctx: Ctx) -> str:
    r = db.claim_daily(ctx.uid, ctx.name)
    if not r["ok"]:
        return f"⏳ @{ctx.name}, your daily resets in {fmt_duration(r['remaining'])}."
    return (f"🎁 @{ctx.name} claimed +{r['amount']:,} coins!\n"
            f"🔥 Streak: {r['streak']} day(s)\n"
            f"💰 Balance: {r['balance']:,}")


def cmd_coinflip(ctx: Ctx) -> str:
    usage = f"Usage: {PREFIX}coinflip <heads/tails> <amount>"
    if len(ctx.args) < 2:
        return usage
    pick = FLIP_SIDES.get(ctx.args[0].lower())
    if not pick:
        return usage
    bal = db.get_user(ctx.uid)["balance"]
    bet = parse_amount(ctx.args[1], bal)
    err = check_bet(bet, bal)
    if err:
        return err
    result = random.choice(("heads", "tails"))
    won = result == pick
    ok, new_bal = db.settle_bet(ctx.uid, bet, bet * 2 if won else 0)
    if not ok:
        return "❌ Not enough coins."
    if won:
        return f"🪙 It landed on {result.upper()}! @{ctx.name} won +{bet:,}\n💰 Balance: {new_bal:,}"
    return f"🪙 It landed on {result.upper()}... @{ctx.name} lost -{bet:,} 💀\n💰 Balance: {new_bal:,}"


def cmd_roll(ctx: Ctx) -> str:
    if not ctx.args:
        return f"Usage: {PREFIX}roll <amount>"
    bal = db.get_user(ctx.uid)["balance"]
    bet = parse_amount(ctx.args[0], bal)
    err = check_bet(bet, bal)
    if err:
        return err
    die = random.randint(1, 6)
    returned = int(bet * ROLL_RETURNS[die])
    ok, new_bal = db.settle_bet(ctx.uid, bet, returned)
    if not ok:
        return "❌ Not enough coins."
    net = returned - bet
    if net > 0:
        outcome = f"won +{net:,} 🔥"
    elif net < 0:
        outcome = f"lost {net:,} 💀"
    else:
        outcome = "got their bet back 😐"
    return f"🎲 {DICE[die - 1]} @{ctx.name} rolled a {die} and {outcome}\n💰 Balance: {new_bal:,}"


def cmd_rob(ctx: Ctx) -> str:
    if not ctx.args:
        return f"Usage: {PREFIX}rob <username>"
    tname = ctx.args[0].lstrip("@").lower()
    tuid = ctx.name_to_uid.get(tname) or db.find_uid(tname)
    if tuid is None:
        return f"❌ I can't find @{tname} in this chat."
    if tuid == ctx.uid:
        return "🤡 You can't rob yourself."
    if tuid == ctx.bot_uid:
        return "🛡️ Nice try. The bot's vault is unbreakable."
    left = db.rob_cooldown_left(ctx.uid, ROB_COOLDOWN)
    if left > 0:
        return f"🚔 Lay low for {fmt_duration(left)} before your next heist."

    victim_name = ctx.uid_to_name.get(tuid, tname)
    me = db.get_user(ctx.uid, ctx.name)
    victim = db.get_user(tuid, victim_name)
    if me["balance"] < ROB_MIN_BALANCE:
        return f"❌ You need at least {ROB_MIN_BALANCE} coins (bail money) to rob someone."
    if victim["balance"] < ROB_MIN_BALANCE:
        return f"💸 @{victim_name} is too broke to be worth robbing."

    if random.random() < ROB_SUCCESS:
        take = max(1, int(victim["balance"] * random.uniform(0.10, 0.30)))
        moved = db.transfer(tuid, ctx.uid, take)
        db.mark_rob(ctx.uid, True)
        return (f"🥷 @{ctx.name} robbed @{victim_name} and ran off with +{moved:,} coins!\n"
                f"💰 Balance: {db.get_user(ctx.uid)['balance']:,}")
    fine = max(50, int(me["balance"] * random.uniform(0.10, 0.25)))
    moved = db.transfer(ctx.uid, tuid, fine)
    db.mark_rob(ctx.uid, False)
    return (f"🚨 @{ctx.name} got caught robbing @{victim_name} and paid them {moved:,} coins!\n"
            f"💰 Balance: {db.get_user(ctx.uid)['balance']:,}")


def cmd_profile(ctx: Ctx) -> str:
    u = db.get_user(ctx.uid, ctx.name)
    rank, total = db.rank(ctx.uid)
    left = DAILY_COOLDOWN - (time.time() - u["last_daily"])
    daily = "ready ✅" if left <= 0 else f"in {fmt_duration(left)}"
    return (f"👤 @{ctx.name}\n"
            f"💰 Balance: {u['balance']:,}\n"
            f"🏆 Rank: #{rank} of {total}\n"
            f"🎰 Gambling: {u['wins']}W / {u['losses']}L\n"
            f"🥷 Heists: {u['rob_ok']} won / {u['rob_fail']} failed\n"
            f"🔥 Daily streak: {u['streak']}  |  Next daily: {daily}")


def cmd_leaderboard(ctx: Ctx) -> str:
    rows = db.top(10)
    if not rows:
        return "No players yet. Use !daily to start!"
    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 LEADERBOARD"]
    for i, (_, name, bal) in enumerate(rows):
        lines.append(f"{medals[i] if i < 3 else f'{i + 1}.'} @{name} – {bal:,}")
    return "\n".join(lines)


COMMANDS = {
    "ping": cmd_ping, "help": cmd_help, "daily": cmd_daily,
    "coinflip": cmd_coinflip, "cf": cmd_coinflip, "flip": cmd_coinflip,
    "roll": cmd_roll, "rob": cmd_rob,
    "profile": cmd_profile, "bal": cmd_profile, "balance": cmd_profile,
    "leaderboard": cmd_leaderboard, "lb": cmd_leaderboard, "top": cmd_leaderboard,
}


# ----------------------------- instagram plumbing -----------------------------
class SeenIds:
    """Bounded set of processed message ids (no unbounded memory growth)."""

    def __init__(self, cap: int = 1000):
        self._q = deque(maxlen=cap)
        self._s = set()

    def __contains__(self, x):
        return x in self._s

    def add(self, x):
        if x in self._s:
            return
        if len(self._q) == self._q.maxlen:
            self._s.discard(self._q[0])
        self._q.append(x)
        self._s.add(x)


_name_cache: dict = {}


def resolve_name(cl: Client, uid: str) -> str:
    if uid in _name_cache:
        return _name_cache[uid]
    try:
        name = cl.username_from_user_id(int(uid))
    except Exception:
        name = f"user{uid[-4:]}"
    if len(_name_cache) > 500:
        _name_cache.clear()
    _name_cache[uid] = name
    return name


def make_client() -> Client:
    cl = Client()
    cl.delay_range = [1, 3]
    if os.path.exists(SESSION_FILE):
        try:
            cl.load_settings(SESSION_FILE)
        except Exception as e:
            log.warning("Could not load session file: %s", e)
    if IG_SESSIONID:
        cl.login_by_sessionid(IG_SESSIONID)
    else:
        try:
            cl.login(IG_USERNAME, IG_PASSWORD)
        except LoginRequired:
            log.warning("Saved session expired, doing a fresh login.")
            uuids = cl.get_settings().get("uuids")
            cl.set_settings({})
            if uuids:
                cl.set_uuids(uuids)
            cl.login(IG_USERNAME, IG_PASSWORD)
    try:
        cl.dump_settings(SESSION_FILE)
    except Exception as e:
        log.warning("Could not save session: %s", e)
    return cl


def send(cl: Client, text: str):
    time.sleep(random.uniform(0.4, 1.2))  # human-ish delay
    cl.direct_send(text, thread_ids=[int(THREAD_ID)])


def handle_message(cl: Client, m, users: dict, bot_uid: str, last_cmd: dict):
    text = (m.text or "").strip()
    if not text.startswith(PREFIX) or m.user_id is None:
        return
    uid = str(m.user_id)
    if uid == bot_uid:
        return
    parts = text[len(PREFIX):].split()
    if not parts:
        return
    handler = COMMANDS.get(parts[0].lower())
    if handler is None:
        return

    now = time.monotonic()
    prev = last_cmd.get(uid)
    if prev is not None and now - prev < USER_CMD_COOLDOWN:
        return
    if len(last_cmd) > 2000:
        last_cmd.clear()
    last_cmd[uid] = now

    name = users.get(uid) or resolve_name(cl, uid)
    db.get_user(uid, name)  # create user / sync username
    ctx = Ctx(
        uid=uid, name=name, args=parts[1:],
        uid_to_name=users,
        name_to_uid={n.lower(): u for u, n in users.items()},
        bot_uid=bot_uid,
    )
    reply = handler(ctx)
    if reply:
        send(cl, reply)


def poll_once(cl: Client, seen: SeenIds, bot_uid: str, last_cmd: dict):
    thread = cl.direct_thread(int(THREAD_ID), amount=FETCH_AMOUNT)
    users = {str(u.pk): u.username for u in thread.users}
    for m in reversed(thread.messages):
        if m.id in seen:
            continue
        seen.add(m.id)
        try:
            handle_message(cl, m, users, bot_uid, last_cmd)
        except (LoginRequired, ChallengeRequired, PleaseWaitFewMinutes):
            raise
        except Exception:
            log.exception("Error handling message %s", m.id)


def prime_seen(cl: Client) -> SeenIds:
    seen = SeenIds()
    thread = cl.direct_thread(int(THREAD_ID), amount=FETCH_AMOUNT)
    for m in thread.messages:
        seen.add(m.id)
    return seen


def run_bot(stop: threading.Event):
    cl = None
    seen = None
    last_cmd: dict = {}
    backoff = 0
    while not stop.is_set():
        try:
            if cl is None:
                if not (IG_SESSIONID or (IG_USERNAME and IG_PASSWORD)):
                    log.error("Set IG_SESSIONID or IG_USERNAME + IG_PASSWORD.")
                    return
                cl = make_client()
                if not THREAD_ID.isdigit():
                    log.error("THREAD_ID missing/invalid. Your recent threads:")
                    for t in cl.direct_threads(amount=10):
                        log.error("  THREAD_ID=%s  title=%s", t.id, t.thread_title)
                    return
                seen = prime_seen(cl)
                log.info("Logged in as user %s, watching thread %s", cl.user_id, THREAD_ID)
            poll_once(cl, seen, str(cl.user_id), last_cmd)
            backoff = 0
            stop.wait(random.uniform(POLL_MIN, POLL_MAX))
        except LoginRequired:
            log.warning("Session expired; re-logging in.")
            cl = None
            stop.wait(10)
        except ChallengeRequired:
            log.error("Instagram challenge required. Retrying in 15 min.")
            cl = None
            stop.wait(900)
        except PleaseWaitFewMinutes:
            log.warning("Instagram rate limit hit; cooling down for ~8 min.")
            stop.wait(random.uniform(420, 540))
        except Exception:
            backoff = min(backoff * 2 if backoff else 10, 600)
            log.exception("Poll error; retrying in %ss", backoff)
            stop.wait(backoff)


# ----------------------------- FastAPI -----------------------------
_stop = threading.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    t = threading.Thread(target=run_bot, args=(_stop,), daemon=True, name="ig-bot")
    t.start()
    yield
    _stop.set()
    db.close()


app = FastAPI(lifespan=lifespan)


@app.api_route("/", methods=["GET", "HEAD"])
@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    return {"status": "ok", "uptime_s": int(time.time() - START_TIME), "players": db.user_count()}
