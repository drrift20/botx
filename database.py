"""In-memory database mock supporting all bot, game, and web features."""
import time

# In-memory stores
_state = {}
_users = {}

def init_db():
    print("⚠️ Running with In-Memory Database (No MongoDB required for testing)")

# State management (used by bot.py for session & timestamps)
def get_state(key: str, default=None):
    return _state.get(key, default)

def set_state(key: str, value):
    _state[key] = value

# User management & economy
def get_user(user_id: str):
    uid = str(user_id)
    if uid not in _users:
        _users[uid] = {"user_id": uid, "username": f"user_{uid}", "balance": 1000, "inventory": [], "streak": 0}
    return _users[uid]

def upsert_user(user_id: str, username: str):
    uid = str(user_id)
    u = get_user(uid)
    if username:
        u["username"] = username
    return u

def get_user_by_username(username: str):
    for u in _users.values():
        if u.get("username", "").lower() == username.lower():
            return u
    return None

def claim_daily(user_id: str):
    uid = str(user_id)
    u = get_user(uid)
    now = time.time()
    last = u.get("last_daily", 0)
    if now - last < 86400:
        return False, int(86400 - (now - last))
    u["last_daily"] = now
    u["streak"] = u.get("streak", 0) + 1
    reward = 250
    bonus = 20 * u["streak"]
    streak = u["streak"]
    u["balance"] += (reward + bonus)
    return True, (reward, bonus, streak, u["balance"])

def claim_work(user_id: str):
    uid = str(user_id)
    u = get_user(uid)
    now = time.time()
    last = u.get("last_work", 0)
    if now - last < 3600:
        return False, int(3600 - (now - last))
    u["last_work"] = now
    earned = 50
    u["balance"] += earned
    return True, (earned, u["balance"])

def claim_chest(user_id: str):
    uid = str(user_id)
    u = get_user(uid)
    reward = 150
    u["balance"] += reward
    return reward, u["balance"]

def rob(robber_id: str, victim_id: str):
    r = get_user(robber_id)
    v = get_user(victim_id)
    if v["balance"] < 50:
        return {"success": False, "reason": "poor"}
    amount = int(v["balance"] * 0.2)
    v["balance"] -= amount
    r["balance"] += amount
    return {"success": True, "amount": amount, "balance": r["balance"]}

def duel(from_id: str, to_id: str, amount: int):
    f = get_user(from_id)
    t = get_user(to_id)
    if f["balance"] < amount or t["balance"] < amount:
        return {"success": False, "reason": "balance"}
    f["balance"] += amount
    t["balance"] -= amount
    return {"success": True, "winner": from_id, "amount": amount}

def buy_item(user_id: str, item_id: int):
    u = get_user(user_id)
    if u["balance"] < 100:
        return {"success": False, "reason": "balance"}
    u["balance"] -= 100
    u["inventory"].append(f"Item {item_id}")
    return {"success": True}

def register_message():
    return True

def top_users(limit=10):
    sorted_users = sorted(_users.values(), key=lambda x: x["balance"], reverse=True)
    return sorted_users[:limit]

def shop_items():
    return [
        {"id": 1, "name": "Shield", "price": 100},
        {"id": 2, "name": "Sword", "price": 250}
    ]
