"""
MongoDB-backed persistent store for Instagram Economy Bot.
- PyMongo Synchronous Driver.
- Seamless automatic migration from legacy data.json on first boot.
- Invisible creator perks support.
- Integrated Anti-Exploit Debt Garnishment & Gang Mechanics.
"""
import json
import logging
import os
import time
from pymongo import MongoClient

log = logging.getLogger("botx.db")

# MongoDB Atlas URI configuration
MONGO_URI = os.environ.get(
    "MONGO_URI",
    "mongodb+srv://lionexplainy_db_user:5r491TzvELxhiQrP@cluster0.hsyilwm.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
)

START_BALANCE = 500
MAX_BALANCE = 10 ** 12

DAILY_COOLDOWN = 24 * 3600
STREAK_WINDOW = 48 * 3600
DAILY_BASE = 500
STREAK_STEP = 50
STREAK_CAP = 10


class Database:
    def __init__(self, uri: str = MONGO_URI, legacy_path: str = "data.json"):
        log.info("Connecting to MongoDB Atlas cluster...")
        self.client = MongoClient(uri)
        self.db = self.client["mafia_casino"]
        self.users = self.db["users"]
        self.gangs = self.db["gangs"]  # Collection for Gang Mechanics
        
        # Creator username configuration (Invisible Perks)
        self.creator_username = "rift.away"
        
        # Run one-time migration from legacy data.json if it exists
        self._migrate_legacy_json(legacy_path)

    def _migrate_legacy_json(self, legacy_path: str):
        if os.path.exists(legacy_path):
            try:
                with open(legacy_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                legacy_users = data.get("users", {}) if isinstance(data, dict) else {}
                
                if legacy_users:
                    migrated_count = 0
                    for uid, udata in legacy_users.items():
                        uid_str = str(uid)
                        # Check if user already exists in MongoDB
                        if not self.users.find_one({"_id": uid_str}):
                            udata["_id"] = uid_str
                            self.users.insert_one(udata)
                            migrated_count += 1
                            
                    log.info("Successfully migrated %d users from legacy %s to MongoDB!", migrated_count, legacy_path)
                    
                    # Backup or rename old file so it doesn't migrate twice
                    os.replace(legacy_path, legacy_path + ".migrated")
            except Exception as e:
                log.error("Failed to migrate legacy json data: %s", e)

    def _get(self, uid: str, username: str | None = None) -> dict:
        uid = str(uid)
        u = self.users.find_one({"_id": uid})
        
        if u is None:
            u = {
                "_id": uid,
                "username": username or f"user{uid[-4:]}",
                "balance": START_BALANCE,
                "bank": 0,
                "debt": 0,
                "inventory": {},
                "last_daily": 0.0,
                "last_work": 0.0,
                "last_crime": 0.0,
                "last_rob": 0.0,
                "last_hunt": 0.0,
                "streak": 0,
                "wins": 0,
                "losses": 0,
                "rob_ok": 0,
                "rob_fail": 0,
                "gang": None
            }
            self.users.insert_one(u)
        elif username and u.get("username") != username:
            self.users.update_one({"_id": uid}, {"$set": {"username": username}})
            u["username"] = username
            
        return u

    def get_user(self, uid, username: str | None = None) -> dict:
        return dict(self._get(uid, username))

    def user_count(self) -> int:
        return self.users.count_documents({})

    def find_uid(self, username: str):
        name = username.lower()
        for u in self.users.find({}):
            if u.get("username", "").lower() == name:
                return str(u["_id"])
        return None

    def is_creator(self, username):
        if not username:
            return False
        return username.lower() == self.creator_username.lower()

    def claim_daily(self, uid, username: str | None = None) -> dict:
        now = time.time()
        u = self._get(uid, username)
        left = DAILY_COOLDOWN - (now - u.get("last_daily", 0))
        
        if left > 0:
            return {"ok": False, "remaining": left, "balance": u["balance"], "streak": u.get("streak", 0)}
            
        streak = u.get("streak", 0)
        last_daily = u.get("last_daily", 0)
        
        if last_daily and now - last_daily <= STREAK_WINDOW:
            streak += 1
        else:
            streak = 1
            
        amount = DAILY_BASE + min(streak - 1, STREAK_CAP) * STREAK_STEP
        new_balance = min(u["balance"] + amount, MAX_BALANCE)
        
        self.users.update_one(
            {"_id": str(uid)},
            {
                "$set": {
                    "balance": new_balance,
                    "last_daily": now,
                    "streak": streak,
                    "username": u.get("username", username)
                }
            }
        )
        return {"ok": True, "amount": amount, "streak": streak, "balance": new_balance}

    def settle_bet(self, uid, bet: int, returned: int):
        u = self._get(uid)
        if bet <= 0 or bet > u["balance"]:
            return False, u["balance"]
            
        new_bal = min(u["balance"] - bet + returned, MAX_BALANCE)
        wins_add = 1 if returned > bet else 0
        losses_add = 1 if returned < bet else 0
        
        self.users.update_one(
            {"_id": str(uid)},
            {
                "$set": {"balance": new_bal},
                "$inc": {"wins": wins_add, "losses": losses_add}
            }
        )
        return True, new_bal

    def transfer(self, src, dst, amount: int) -> int:
        a = self._get(src)
        b = self._get(dst)
        amt = max(0, min(int(amount), a["balance"]))
        if amt:
            self.users.update_one({"_id": str(src)}, {"$inc": {"balance": -amt}})
            self.users.update_one({"_id": str(dst)}, {"$inc": {"balance": amt}})
        return amt

    def rob_cooldown_left(self, uid, cooldown: float) -> float:
        u = self._get(uid)
        return max(0.0, cooldown - (time.time() - u.get("last_rob", 0)))

    def mark_rob(self, uid, success: bool):
        self._get(uid)
        field = "rob_ok" if success else "rob_fail"
        self.users.update_one(
            {"_id": str(uid)},
            {
                "$set": {"last_rob": time.time()},
                "$inc": {field: 1}
            }
        )

    def top(self, n: int = 10):
        cursor = self.users.find({}).sort("balance", -1).limit(n)
        return [(str(u["_id"]), u.get("username", "Unknown"), u.get("balance", 0)) for u in cursor]

    def top_users(self, n: int = 10):
        return self.top(n)

    def rank(self, uid):
        uid_str = str(uid)
        all_users = list(self.users.find({}, {"_id": 1, "balance": 1}).sort("balance", -1))
        total = len(all_users)
        for i, u in enumerate(all_users, 1):
            if str(u["_id"]) == uid_str:
                return i, total
        return total + 1, total

    # --- ANTI-EXPLOIT DEBT GARNISHMENT HELPER ---
    def apply_debt_garnishment(self, uid: str, income: int) -> dict:
        """
        Automatically deducts 35% of any income earned to pay off active loan shark debt.
        If no debt, adds full income to balance.
        """
        u = self._get(uid)
        debt = u.get("debt", 0)
        
        # FIX: Jodi debt na thake, tahole income-ta balance-e direct jog kore database update korte hobe!
        if debt <= 0:
            new_balance = u["balance"] + income
            self.users.update_one(
                {"_id": str(uid)},
                {"$set": {"balance": new_balance}}
            )
            return {"garnished": 0, "net_earned": income, "new_balance": new_balance}

        garnished = min(debt, int(income * 0.35))
        net_earned = income - garnished
        new_balance = u["balance"] + net_earned
        new_debt = debt - garnished

        self.users.update_one(
            {"_id": str(uid)},
            {"$set": {"balance": new_balance, "debt": new_debt}}
        )
        return {"garnished": garnished, "net_earned": net_earned, "new_balance": new_balance}

    # --- GANG MECHANICS DATABASE METHODS ---
    def create_gang(self, boss_uid: str, gang_name: str) -> dict:
        name_clean = gang_name.strip()
        if self.gangs.find_one({"name_lower": name_clean.lower()}):
            return {"ok": False, "msg": "Gang name already exists!"}
        
        boss = self._get(boss_uid)
        if boss.get("gang"):
            return {"ok": False, "msg": "You are already in a gang!"}
        
        creation_cost = 2000
        if boss["balance"] < creation_cost:
            return {"ok": False, "msg": f"You need {creation_cost} cash in hand to establish a Gang!"}

        gang_doc = {
            "name": name_clean,
            "name_lower": name_clean.lower(),
            "boss_uid": str(boss_uid),
            "members": [str(boss_uid)],
            "vault": 0,
            "invites": [],      # List of pending user_ids invited by Boss
            "applications": [], # List of pending user_ids applying to join
            "active_vote": None, # For Underboss Vote-Protected Vault withdrawals
            "items": {}         # Gang black market items (e.g. C4, Shields)
        }
        self.gangs.insert_one(gang_doc)
        self.users.update_one({"_id": str(boss_uid)}, {"$inc": {"balance": -creation_cost}, "$set": {"gang": name_clean}})
        return {"ok": True, "msg": f"Gang **{name_clean}** established successfully!"}

    def get_gang(self, gang_name: str):
        return self.gangs.find_one({"name_lower": gang_name.strip().lower()})

    def get_user_gang(self, uid: str):
        u = self._get(uid)
        if u.get("gang"):
            return self.get_gang(u["gang"])
        return None


# Global database instance
db = Database()
