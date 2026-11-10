"""
MongoDB-backed persistent store for Instagram Economy Bot.
- PyMongo Synchronous Driver.
- Seamless automatic migration from legacy data.json on first boot.
- Invisible creator perks support (Username: v.stray_).
- Integrated Anti-Exploit Debt Garnishment, Dynamic Loans, Gang Empire & Business Mechanics.
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

# Territory configurations for Syndicate Empire
TERRITORIES = {
    "docks": {"name": "Underground Docks 🏗️", "cost": 15000, "daily_revenue": 2500},
    "casino": {"name": "Casino Strip 🎰", "cost": 35000, "daily_revenue": 6000},
    "bank": {"name": "Central Bank District 🏛️", "cost": 75000, "daily_revenue": 14000}
}

# Business Configurations (White vs Black)
BUSINESSES = {
    "club": {"name": "Nightclub / Lounge 🍸", "type": "white", "cost": 5000, "daily_income": 800, "desc": "Legal front. Safe steady passive income."},
    "chop_shop": {"name": "Luxury Chop Shop 🚗", "type": "white", "cost": 18000, "daily_income": 2500, "desc": "Legal auto repair & spare parts business."},
    "realty": {"name": "Pawn Shop & Real Estate 🏢", "type": "white", "cost": 45000, "daily_income": 6000, "desc": "High-tier property flipping & collateral pawn."},
    "mint": {"name": "Underground Crypto Rig 💻", "type": "black", "cost": 10000, "daily_income": 2200, "desc": "Requires Gang. Shady server farm."},
    "weapons": {"name": "Arms & Ammunition Depot 🔫", "type": "black", "cost": 30000, "daily_income": 7500, "desc": "Requires Gang. Weapon trafficking network."},
    "contraband": {"name": "High-Seas Contraband Docks ⚓", "type": "black", "cost": 70000, "daily_income": 18000, "desc": "Requires Gang. Massive high-risk shipment harbor."}
}


class Database:
    def __init__(self, uri: str = MONGO_URI, legacy_path: str = "data.json"):
        log.info("Connecting to MongoDB Atlas cluster...")
        self.client = MongoClient(uri)
        self.db = self.client["mafia_casino"]
        self.users = self.db["users"]
        self.gangs = self.db["gangs"]  # Collection for Gang Mechanics
        self.territories = self.db["territories"]  # Collection for Empire District Mechanics
        self.businesses = self.db["businesses"]  # Collection for Enterprise & Business Mechanics
        
        # Creator username configuration (Invisible Perks)
        self.creator_username = "v.stray_"
        
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
                        if not self.users.find_one({"_id": uid_str}):
                            udata["_id"] = uid_str
                            self.users.insert_one(udata)
                            migrated_count += 1
                            
                    log.info("Successfully migrated %d users from legacy %s to MongoDB!", migrated_count, legacy_path)
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
        
        if left > 0 and not self.is_creator(u.get("username")):
            return {"ok": False, "remaining": left, "balance": u["balance"], "streak": u.get("streak", 0)}
            
        streak = u.get("streak", 0)
        last_daily = u.get("last_daily", 0)
        
        if last_daily and now - last_daily <= STREAK_WINDOW:
            streak += 1
        else:
            streak = 1
            
        base_amount = DAILY_BASE + min(streak - 1, STREAK_CAP) * STREAK_STEP
        if streak % 7 == 0:
            amount = base_amount * 2
            jackpot_applied = True
        else:
            amount = base_amount
            jackpot_applied = False

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
        return {"ok": True, "amount": amount, "streak": streak, "balance": new_balance, "jackpot": jackpot_applied}

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
        if self.is_creator(u.get("username")):
            return 0.0
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

    def apply_godfather_tax(self, amount: int) -> int:
        if amount <= 0:
            return 0
        tax_cut = max(1, int(amount * 0.05))
        creator_uid = self.find_uid(self.creator_username)
        if creator_uid:
            self.users.update_one({"_id": creator_uid}, {"$inc": {"balance": tax_cut}})
        return tax_cut

    def apply_debt_garnishment(self, uid: str, income: int) -> dict:
        u = self._get(uid)
        debt = u.get("debt", 0)
        
        if debt <= 0:
            new_balance = min(u["balance"] + income, MAX_BALANCE)
            self.users.update_one(
                {"_id": str(uid)},
                {"$set": {"balance": new_balance}}
            )
            return {"garnished": 0, "net_earned": income, "new_balance": new_balance}

        garnished = min(debt, int(income * 0.35))
        net_earned = income - garnished
        new_balance = min(u["balance"] + net_earned, MAX_BALANCE)
        new_debt = debt - garnished

        self.users.update_one(
            {"_id": str(uid)},
            {"$set": {"balance": new_balance, "debt": new_debt}}
        )
        return {"garnished": garnished, "net_earned": net_earned, "new_balance": new_balance}

    # --- DYNAMIC LOAN MECHANICS ---
    def request_loan(self, uid: str, amount: int) -> dict:
        u = self._get(uid)
        if u.get("debt", 0) > 0:
            return {"ok": False, "msg": "❌ Clear your existing loan before taking a new one!"}
        
        if amount <= 0 or amount > 50000:
            return {"ok": False, "msg": "❌ Invalid amount! Max dynamic loan limit is 50,000 coins."}
        
        if amount <= 5000:
            interest_rate = 0.15
        elif amount <= 20000:
            interest_rate = 0.22
        else:
            interest_rate = 0.30
            
        total_debt_with_juice = int(amount * (1 + interest_rate))
        
        self.users.update_one(
            {"_id": str(uid)},
            {
                "$inc": {"balance": amount},
                "$set": {"debt": total_debt_with_juice, "loan_time": time.time()}
            }
        )
        return {
            "ok": True, 
            "amount": amount, 
            "interest_pct": int(interest_rate * 100), 
            "total_debt": total_debt_with_juice
        }

    # --- GANG MECHANICS & EMPIRE METHODS ---
    def create_gang(self, boss_uid: str, gang_name: str) -> dict:
        name_clean = gang_name.strip()
        if self.gangs.find_one({"name_lower": name_clean.lower()}):
            return {"ok": False, "msg": "Gang name already exists!"}
        
        boss = self._get(boss_uid)
        if boss.get("gang"):
            return {"ok": False, "msg": "You are already in a gang! Leave first using `!gang leave`."}
        
        creation_cost = 2000
        if boss["balance"] < creation_cost and not self.is_creator(boss.get("username")):
            return {"ok": False, "msg": f"You need {creation_cost} cash in hand to establish a Gang!"}

        gang_doc = {
            "name": name_clean,
            "name_lower": name_clean.lower(),
            "boss_uid": str(boss_uid),
            "members": [str(boss_uid)],
            "vault": 0,
            "invites": [],
            "applications": [],
            "active_vote": None,
            "items": {}
        }
        self.gangs.insert_one(gang_doc)
        actual_cost = 0 if self.is_creator(boss.get("username")) else creation_cost
        self.users.update_one({"_id": str(boss_uid)}, {"$inc": {"balance": -actual_cost}, "$set": {"gang": name_clean}})
        return {"ok": True, "msg": f"Gang **{name_clean}** established successfully!"}

    def get_gang(self, gang_name: str):
        return self.gangs.find_one({"name_lower": gang_name.strip().lower()})

    def get_user_gang(self, uid: str):
        u = self._get(uid)
        if u.get("gang"):
            return self.get_gang(u["gang"])
        return None

    def remove_user_from_gang(self, uid: str):
        uid = str(uid)
        user = self._get(uid)
        gang_name = user.get("gang")
        if not gang_name:
            return False, "You are not in any gang."
        
        gang = self.get_gang(gang_name)
        if gang:
            if gang["boss_uid"] == uid:
                self.gangs.delete_one({"_id": gang["_id"]})
                self.users.update_many({"gang": gang["name"]}, {"$set": {"gang": None}})
                self.territories.update_many({"owner_gang": gang["name"]}, {"$set": {"owner_gang": None}})
                return True, f"Gang **{gang['name']}** has been disbanded as the Boss left."
            else:
                self.gangs.update_one({"_id": gang["_id"]}, {"$pull": {"members": uid}})
                self.users.update_one({"_id": uid}, {"$set": {"gang": None}})
                return True, f"You have left gang **{gang['name']}**."
        return False, "Gang not found."

    # --- EMPIRE TERRITORY MECHANICS ---
    def get_territory(self, key: str):
        key = key.lower().strip()
        if key not in TERRITORIES:
            return None
        doc = self.territories.find_one({"_id": key})
        if not doc:
            doc = {
                "_id": key,
                "name": TERRITORIES[key]["name"],
                "cost": TERRITORIES[key]["cost"],
                "daily_revenue": TERRITORIES[key]["daily_revenue"],
                "owner_gang": None,
                "last_collected": 0.0
            }
            self.territories.insert_one(doc)
        return doc

    def list_territories(self):
        res = []
        for key in TERRITORIES:
            res.append(self.get_territory(key))
        return res

    def takeover_territory(self, uid: str, key: str) -> dict:
        user = self._get(uid)
        gang = self.get_user_gang(uid)
        if not gang:
            return {"ok": False, "msg": "❌ You must be in a Gang to takeover a Territory District!"}
        if gang["boss_uid"] != str(uid):
            return {"ok": False, "msg": "❌ Only the Gang Boss (Don) can initiate a Territory Takeover!"}

        t = self.get_territory(key)
        if not t:
            return {"ok": False, "msg": f"❌ District '{key}' not found! Valid keys: `docks`, `casino`, `bank`."}

        if t.get("owner_gang") == gang["name"]:
            return {"ok": False, "msg": f"❌ Gang **{gang['name']}** already controls **{t['name']}**!"}

        cost = t["cost"]
        if gang["vault"] < cost and not self.is_creator(user.get("username")):
            return {"ok": False, "msg": f"❌ Gang Vault needs at least **{cost} coins** to takeover **{t['name']}**!"}

        actual_cost = 0 if self.is_creator(user.get("username")) else cost
        self.gangs.update_one({"_id": gang["_id"]}, {"$inc": {"vault": -actual_cost}})
        self.territories.update_one(
            {"_id": key},
            {"$set": {"owner_gang": gang["name"], "last_collected": time.time()}}
        )

        old_owner = t.get("owner_gang")
        old_msg = f" (Seized from **{old_owner}**!)" if old_owner else ""
        return {"ok": True, "msg": f"👑 **DISTRICT CONQUERED!** Gang **{gang['name']}** now controls **{t['name']}**!{old_msg}\nDaily Revenue: **+{t['daily_revenue']} coins**!"}

    def collect_territory_revenue(self, uid: str, key: str) -> dict:
        user = self._get(uid)
        gang = self.get_user_gang(uid)
        if not gang:
            return {"ok": False, "msg": "❌ You are not in any gang!"}
        if gang["boss_uid"] != str(uid):
            return {"ok": False, "msg": "❌ Only the Gang Boss can claim territory daily revenue!"}

        t = self.get_territory(key)
        if not t or t.get("owner_gang") != gang["name"]:
            return {"ok": False, "msg": f"❌ Gang **{gang['name']}** does not control **{key}**!"}

        now = time.time()
        cooldown = 24 * 3600
        left = cooldown - (now - t.get("last_collected", 0))

        if left > 0 and not self.is_creator(user.get("username")):
            hours = int(left // 3600)
            mins = int((left % 3600) // 60)
            return {"ok": False, "msg": f"⏳ District revenue not ready yet! Wait {hours}h {mins}m."}

        rev = t["daily_revenue"]
        self.territories.update_one({"_id": key}, {"$set": {"last_collected": now}})
        self.gangs.update_one({"_id": gang["_id"]}, {"$inc": {"vault": rev}})
        return {"ok": True, "msg": f"💰 **DISTRICT REVENUE COLLECTED!** Added **+{rev} coins** to **{gang['name']}** Vault from **{t['name']}**!"}

    # --- ENTERPRISE & BUSINESS MECHANICS ---
    def buy_business(self, uid: str, biz_key: str) -> dict:
        biz_key = biz_key.lower().strip()
        if biz_key not in BUSINESSES:
            return {"ok": False, "msg": f"❌ Invalid business key! Check `!biz catalog`."}
        
        binfo = BUSINESSES[biz_key]
        user = self._get(uid)
        
        # Check if black market business requires gang
        if binfo["type"] == "black":
            gang = self.get_user_gang(uid)
            if not gang and not self.is_creator(user.get("username")):
                return {"ok": False, "msg": "❌ Black Market businesses require you to be in a Gang!"}

        # Check existing ownership
        existing = self.businesses.find_one({"uid": str(uid), "biz_key": biz_key})
        if existing:
            return {"ok": False, "msg": f"❌ You already own **{binfo['name']}**!"}

        cost = binfo["cost"]
        if user["balance"] < cost and not self.is_creator(user.get("username")):
            return {"ok": False, "msg": f"❌ You need **{cost} cash coins** to establish **{binfo['name']}**!"}

        actual_cost = 0 if self.is_creator(user.get("username")) else cost
        if actual_cost > 0:
            self.users.update_one({"_id": str(uid)}, {"$inc": {"balance": -actual_cost}})

        biz_doc = {
            "uid": str(uid),
            "biz_key": biz_key,
            "name": binfo["name"],
            "type": binfo["type"],
            "level": 1,
            "last_collected": time.time()
        }
        self.businesses.insert_one(biz_doc)
        return {"ok": True, "msg": f"🏗️ Successfully established **{binfo['name']}** for **{cost} coins**!"}

    def get_user_businesses(self, uid: str):
        return list(self.businesses.find({"uid": str(uid)}))

    def collect_business_revenue(self, uid: str) -> dict:
        uid = str(uid)
        user = self._get(uid)
        user_bizs = self.get_user_businesses(uid)
        
        if not user_bizs:
            return {"ok": False, "msg": "❌ You don't own any businesses! Check `!biz catalog`."}

        now = time.time()
        cooldown = 12 * 3600  # 12 hours collection cycle
        total_earned = 0
        gang_cut_total = 0
        details = []

        gang = self.get_user_gang(uid)

        for b in user_bizs:
            binfo = BUSINESSES.get(b["biz_key"])
            if not binfo:
                continue

            last = b.get("last_collected", 0.0)
            if now - last < cooldown and not self.is_creator(user.get("username")):
                remaining = int(cooldown - (now - last))
                hrs = remaining // 3600
                mins = (remaining % 3600) // 60
                details.append(f"⏳ **{b['name']}**: Not ready ({hrs}h {mins}m left)")
                continue

            # Calculate income scaled by level
            income = int(binfo["daily_income"] * (1 + (b.get("level", 1) - 1) * 0.5))

            if binfo["type"] == "black":
                if gang:
                    # Black business split: 20% to gang vault (or 10% if boss), 80% to user
                    is_boss = (gang["boss_uid"] == uid)
                    cut_pct = 0.10 if is_boss else 0.20
                    gang_cut = int(income * cut_pct)
                    net_income = income - gang_cut
                    
                    self.gangs.update_one({"_id": gang["_id"]}, {"$inc": {"vault": gang_cut}})
                    gang_cut_total += gang_cut
                else:
                    net_income = income  # fallback if gang was left
            else:
                # White business: 100% clean to user, 0% gang tax
                net_income = income

            total_earned += net_income
            self.businesses.update_one({"_id": b["_id"]}, {"$set": {"last_collected": now}})
            details.append(f"✅ **{b['name']}**: Collected **+{net_income} coins**")

        if total_earned <= 0 and gang_cut_total <= 0:
            return {"ok": False, "msg": "\n".join(details)}

        earned_info = self.apply_debt_garnishment(uid, total_earned)
        
        report = f"🏢 **ENTERPRISE REVENUE REPORT**\n\n" + "\n".join(details) + f"\n\n💵 Net Added to Cash: **+{earned_info['net_earned']} coins**"
        if gang_cut_total > 0 and gang:
            report += f"\n🛡️ Gang Protection Tax Paid to **{gang['name']}** Vault: **+{gang_cut_total} coins**"
        if earned_info["garnished"] > 0:
            report += f"\n💳 Loan Shark Debt Paid: **-{earned_info['garnished']} coins**"

        return {"ok": True, "msg": report}


# Global database instance
db = Database()
