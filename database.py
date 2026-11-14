"""
MongoDB-backed persistent store for Instagram Economy Bot.
Version 8: Fully restored with gang management (leave/transfer) and duel/fight support.
"""
import json
import logging
import os
import random
import time
from pymongo import MongoClient

log = logging.getLogger("botx.db")

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

TERRITORIES = {
    "docks": {"name": "Underground Docks 🏗️", "cost": 15000, "daily_revenue": 2500},
    "casino": {"name": "Casino Strip 🎰", "cost": 35000, "daily_revenue": 6000},
    "bank": {"name": "Central Bank District 🏛️", "cost": 75000, "daily_revenue": 14000}
}

BUSINESSES = {
    "club": {"name": "Nightclub / Lounge 🍸", "type": "white", "cost": 5000, "daily_income": 800, "desc": "Legal front. Safe steady passive income."},
    "chop_shop": {"name": "Luxury Chop Shop 🚗", "type": "white", "cost": 18000, "daily_income": 2500, "desc": "Legal auto repair & spare parts business."},
    "realty": {"name": "Pawn Shop & Real Estate 🏢", "type": "white", "cost": 45000, "daily_income": 6000, "desc": "High-tier property flipping & collateral pawn."},
    "mint": {"name": "Underground Crypto Rig 💻", "type": "black", "cost": 10000, "daily_income": 2200, "desc": "Requires Gang. Shady server farm."},
    "weapons": {"name": "Arms & Ammunition Depot 🔫", "type": "black", "cost": 30000, "daily_income": 7500, "desc": "Requires Gang. Weapon trafficking network."},
    "contraband": {"name": "High-Seas Contraband Docks ⚓", "type": "black", "cost": 70000, "daily_income": 18000, "desc": "Requires Gang. Massive high-risk shipment harbor."}
}

LUXURY_ITEMS = {
    "rolex": {"name": "Rolex Submariner ⌚", "cost": 25000, "emoji": "⌚", "title": "The Timekeeper"},
    "car": {"name": "Lamborghini Aventador 🚗", "cost": 100000, "emoji": "🚗", "title": "Street Royalty"},
    "mansion": {"name": "Hillside Sky Mansion 🏰", "cost": 500000, "emoji": "🏰", "title": "Estate Overlord"},
    "jet": {"name": "Private Gulfstream Jet ✈️", "cost": 2000000, "emoji": "✈️", "title": "Global Syndicate Elite"},
    "yacht": {"name": "Superyacht 'Poseidon' 🛥️", "cost": 5000000, "emoji": "🛥️", "title": "Ocean Warlord"}
}

GANG_LEVELS = {
    1: {"cost": 0, "max_members": 8, "vault_cap": 50000, "perk": "Standard Vault & Operations"},
    2: {"cost": 10000, "max_members": 12, "vault_cap": 150000, "perk": "+1% Daily Vault Savings Interest"},
    3: {"cost": 50000, "max_members": 20, "vault_cap": 500000, "perk": "+10% Gang War Attack Damage"},
    4: {"cost": 200000, "max_members": 30, "vault_cap": 2000000, "perk": "+15% Central Bank Heist Success"}
}


class Database:
    def __init__(self, uri: str = MONGO_URI, legacy_path: str = "data.json"):
        log.info("Connecting to MongoDB Atlas cluster...")
        self.client = MongoClient(uri)
        self.db = self.client["mafia_casino"]
        self.users = self.db["users"]
        self.gangs = self.db["gangs"]
        self.territories = self.db["territories"]
        self.businesses = self.db["businesses"]
        self.lottery_col = self.db["lottery"]
        self.bounties_col = self.db["bounties"]
        self.welfare_col = self.db["welfare"]
        
        self.creator_username = "v.stray_"
        self.vip_usernames = ["_nuhash_s"]
        
        self._migrate_legacy_json(legacy_path)

    def close(self):
        try:
            self.client.close()
            log.info("MongoDB client connection closed cleanly.")
        except Exception as e:
            log.error("Error closing MongoDB connection: %s", e)

    def _migrate_legacy_json(self, legacy_path: str):
        if os.path.exists(legacy_path):
            try:
                with open(legacy_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                legacy_users = data.get("users", {}) if isinstance(data, dict) else {}
                if legacy_users:
                    for uid, udata in legacy_users.items():
                        uid_str = str(uid)
                        if not self.users.find_one({"_id": uid_str}):
                            udata["_id"] = uid_str
                            self.users.insert_one(udata)
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
                "luxuries": [],
                "guard_expires": 0.0,
                "last_audit": time.time(),
                "last_daily": 0.0,
                "last_work": 0.0,
                "last_crime": 0.0,
                "last_rob": 0.0,
                "last_hunt": 0.0,
                "last_slots": 0.0,
                "last_welfare": 0.0,
                "last_extort": 0.0,
                "heat_until": 0.0,
                "is_police": False,
                "blood_partner": None,
                "pact_pending": None,
                "last_betray": 0.0,
                "streak": 0,
                "wins": 0,
                "losses": 0,
                "gang": None
            }
            self.users.insert_one(u)
        else:
            fields_to_set = {}
            if username and u.get("username") != username:
                fields_to_set["username"] = username
                u["username"] = username
            for key, default_val in [
                ("luxuries", []), ("guard_expires", 0.0), ("last_audit", time.time()),
                ("last_slots", 0.0), ("last_welfare", 0.0), ("last_extort", 0.0),
                ("heat_until", 0.0), ("is_police", False), ("blood_partner", None),
                ("pact_pending", None), ("last_betray", 0.0), ("inventory", {})
            ]:
                if key not in u:
                    fields_to_set[key] = default_val
                    u[key] = default_val
            if fields_to_set:
                self.users.update_one({"_id": uid}, {"$set": fields_to_set})
        return u

    def get_user(self, uid, username: str | None = None) -> dict:
        return dict(self._get(uid, username))

    def find_uid(self, username: str):
        name = username.lower()
        for u in self.users.find({}):
            if u.get("username", "").lower() == name:
                return str(u["_id"])
        return None

    def is_creator(self, username):
        if not username: return False
        return username.lower() == self.creator_username.lower()

    def is_vip(self, username):
        if not username: return False
        return username.lower() in [u.lower() for u in self.vip_usernames]

    # --- ROBIN HOOD TAX & WELFARE ---
    def check_and_apply_irs_tax(self, uid: str) -> dict:
        u = self._get(uid)
        now = time.time()
        if now - u.get("last_audit", 0.0) >= 24 * 3600:
            self.users.update_one({"_id": str(uid)}, {"$set": {"last_audit": now}})
            bank_bal = u.get("bank", 0)
            if bank_bal > 50000 and not self.is_creator(u.get("username")):
                excess = bank_bal - 50000
                tax = int(excess * 0.005)
                if tax > 0:
                    self.users.update_one({"_id": str(uid)}, {"$set": {"bank": bank_bal - tax}})
                    self.welfare_col.update_one({"_id": "pool"}, {"$inc": {"balance": tax}}, upsert=True)
                    return {"audited": True, "tax": tax}
        return {"audited": False}

    def get_welfare_pool_balance(self) -> int:
        doc = self.welfare_col.find_one({"_id": "pool"})
        return doc.get("balance", 0) if doc else 0

    def claim_welfare(self, uid: str) -> dict:
        uid = str(uid)
        u = self._get(uid)
        net_worth = u["balance"] + u["bank"] - u["debt"]
        if net_worth >= 200:
            return {"ok": False, "msg": f"❌ Welfare relief is strictly for bankrupt players with net worth < 200 coins! (Your net worth: {net_worth})"}

        now = time.time()
        if now - u.get("last_welfare", 0.0) < 24 * 3600 and not self.is_creator(u.get("username")):
            left = int(24 * 3600 - (now - u.get("last_welfare", 0.0)))
            return {"ok": False, "msg": f"⏳ Welfare grant already claimed today! Come back in {left // 3600}h {(left % 3600) // 60}m."}

        pool_bal = self.get_welfare_pool_balance()
        grant = min(500, max(50, int(pool_bal * 0.10))) if pool_bal > 200 else max(50, pool_bal)
        if grant <= 0:
            return {"ok": False, "msg": "❌ Welfare pool is currently empty!"}

        self.welfare_col.update_one({"_id": "pool"}, {"$inc": {"balance": -grant}})
        earned_info = self.apply_debt_garnishment(uid, grant)
        self.users.update_one({"_id": uid}, {"$set": {"last_welfare": now}})
        return {"ok": True, "msg": f"🏛️ **WELFARE GRANTED!** Received **+{grant} coins** relief fund. *(Debt paid: {earned_info['garnished']})* 🎉"}

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
        amount = base_amount * 2 if streak % 7 == 0 else base_amount
        new_balance = min(u["balance"] + amount, MAX_BALANCE)
        
        self.users.update_one({"_id": str(uid)}, {"$set": {"balance": new_balance, "last_daily": now, "streak": streak}})
        return {"ok": True, "amount": amount, "streak": streak, "balance": new_balance}

    def apply_debt_garnishment(self, uid: str, income: int) -> dict:
        u = self._get(uid)
        debt = u.get("debt", 0)
        if debt <= 0:
            new_balance = min(u["balance"] + income, MAX_BALANCE)
            self.users.update_one({"_id": str(uid)}, {"$set": {"balance": new_balance}})
            return {"garnished": 0, "net_earned": income, "new_balance": new_balance}

        garnished = min(debt, int(income * 0.35))
        net_earned = income - garnished
        new_balance = min(u["balance"] + net_earned, MAX_BALANCE)
        self.users.update_one({"_id": str(uid)}, {"$set": {"balance": new_balance, "debt": debt - garnished}})
        return {"garnished": garnished, "net_earned": net_earned, "new_balance": new_balance}

    # --- WANTED & POLICE ---
    def get_wanted_level(self, uid: str) -> dict:
        u = self._get(uid)
        net_worth = u["balance"] + u["bank"] - u["debt"]
        if net_worth >= 500000: stars, title = "⭐⭐⭐⭐⭐", "Most Wanted Public Enemy"
        elif net_worth >= 200000: stars, title = "⭐⭐⭐⭐", "High-Profile Syndicate Boss"
        elif net_worth >= 75000: stars, title = "⭐⭐⭐", "Wanted Criminal"
        elif net_worth >= 25000: stars, title = "⭐⭐", "Underground Suspect"
        elif net_worth >= 10000: stars, title = "⭐", "Person of Interest"
        else: stars, title = "⚪", "Clean Citizen"
        return {"net_worth": net_worth, "stars": stars, "title": title}

    def join_police(self, uid: str) -> dict:
        uid = str(uid)
        u = self._get(uid)
        if u.get("is_police"): return {"ok": False, "msg": "❌ Already a Police Officer!"}
        if u.get("gang"): return {"ok": False, "msg": "❌ Leave your gang first (`!gang leave`)!"}
        if self.bounties_col.find_one({"target_uid": uid, "active": True, "expires_at": {"$gt": time.time()}}):
            return {"ok": False, "msg": "❌ Active bounty on your head!"}
        if self.businesses.find_one({"uid": uid, "type": "black"}):
            return {"ok": False, "msg": "❌ Dismantle black market businesses first (`!biz close <key>`)!"}

        self.users.update_one({"_id": uid}, {"$set": {"is_police": True}})
        return {"ok": True, "msg": "👮 **WELCOME TO THE FORCE!** You are an official Police Officer."}

    def leave_police(self, uid: str) -> dict:
        uid = str(uid)
        if not self._get(uid).get("is_police"): return {"ok": False, "msg": "❌ You are not a Police Officer!"}
        self.users.update_one({"_id": uid}, {"$set": {"is_police": False}})
        return {"ok": True, "msg": "🚶 Resigned from the Police Force."}

    def arrest_user(self, cop_uid: str, target_uname: str) -> dict:
        cop = self._get(cop_uid)
        if not cop.get("is_police"): return {"ok": False, "msg": "❌ Only Police Officers can make arrests!"}

        target_uid = self.find_uid(target_uname.lstrip("@").lower())
        if not target_uid or target_uid == cop_uid: return {"ok": False, "msg": "❌ Target invalid!"}
        target = self._get(target_uid)
        if target.get("is_police"): return {"ok": False, "msg": "❌ Cannot arrest a fellow officer!"}

        now = time.time()
        has_heat = target.get("heat_until", 0.0) > now
        has_bounty = self.bounties_col.find_one({"target_uid": target_uid, "active": True, "expires_at": {"$gt": now}})
        if not has_heat and not has_bounty:
            return {"ok": False, "msg": f"❌ @{target_uname} has no active Heat or Wanted Bounty!"}

        fine = int(target["balance"] * 0.30)
        commission = int(fine * 0.50)
        if fine > 0:
            self.users.update_one({"_id": target_uid}, {"$inc": {"balance": -fine}, "$set": {"heat_until": 0.0}})
            earned_info = self.apply_debt_garnishment(cop_uid, commission)
        else:
            earned_info = {"net_earned": 0}

        if has_bounty:
            self.bounties_col.update_many({"target_uid": target_uid, "active": True}, {"$set": {"active": False}})

        return {"ok": True, "msg": f"🚨 **ARREST SUCCESSFUL!** Fined @{target_uname} **{fine} coins** *(Commission added: +{earned_info['net_earned']})* 🚓"}

    def bribe_cop(self, uid: str, amount: int) -> dict:
        u = self._get(uid)
        now = time.time()
        if u.get("heat_until", 0.0) <= now:
            return {"ok": False, "msg": "❌ You have no active police heat! Bribe not needed."}
        if amount <= 0 or u["balance"] < amount:
            return {"ok": False, "msg": f"❌ Invalid bribe amount or insufficient cash ({u['balance']})!"}

        self.users.update_one({"_id": uid}, {"$inc": {"balance": -amount}, "$set": {"heat_until": 0.0}})
        return {"ok": True, "msg": f"🤝 **BRIBE ACCEPTED!** Paid **{amount} coins** to dismiss charges and clear heat. 🕶️"}

    # --- DUEL & FIGHT ---
    def duel_user(self, uid: str, target_uname: str, bet: int) -> dict:
        uid = str(uid)
        u = self._get(uid)
        if bet <= 0 or u["balance"] < bet:
            return {"ok": False, "msg": "❌ Invalid duel bet or insufficient cash!"}
        
        target_uid = self.find_uid(target_uname.lstrip("@").lower())
        if not target_uid or target_uid == uid:
            return {"ok": False, "msg": "❌ Invalid duel opponent!"}
        t_user = self._get(target_uid)
        if t_user["balance"] < bet:
            return {"ok": False, "msg": f"❌ @{target_uname} doesn't have enough cash for this bet!"}

        self.users.update_one({"_id": uid}, {"$inc": {"balance": -bet}})
        self.users.update_one({"_id": target_uid}, {"$inc": {"balance": -bet}})

        winner_uid = random.choice([uid, target_uid])
        loser_uid = target_uid if winner_uid == uid else uid
        winner_user = self._get(winner_uid)
        loser_user = self._get(loser_uid)

        total_pot = bet * 2
        earned = self.apply_debt_garnishment(winner_uid, total_pot)
        self.users.update_one({"_id": winner_uid}, {"$inc": {"wins": 1}})
        self.users.update_one({"_id": loser_uid}, {"$inc": {"losses": 1}})

        return {"ok": True, "msg": f"⚔️ **DUEL ARENA:** @{winner_user['username']} defeated @{loser_user['username']} in a fierce showdown and won **+{total_pot} coins**! 🏆"}

    def fight_user(self, uid: str, target_uname: str) -> dict:
        uid = str(uid)
        u = self._get(uid)
        target_uid = self.find_uid(target_uname.lstrip("@").lower())
        if not target_uid or target_uid == uid:
            return {"ok": False, "msg": "❌ Invalid fighter opponent!"}
        t_user = self._get(target_uid)

        winner_uid = random.choice([uid, target_uid])
        loser_uid = target_uid if winner_uid == uid else uid
        winner_user = self._get(winner_uid)
        loser_user = self._get(loser_uid)

        stake = 200
        if loser_user["balance"] >= stake:
            self.users.update_one({"_id": loser_uid}, {"$inc": {"balance": -stake}})
            earned = self.apply_debt_garnishment(winner_uid, stake)
            msg_stake = f" Stole **{stake} coins** street tax!"
        else:
            msg_stake = " Opponent was too broke to pay street tax!"

        return {"ok": True, "msg": f"🥊 **STREET FIGHT:** @{winner_user['username']} knocked out @{loser_user['username']}!{msg_stake} 🔥"}

    # --- BLOOD PACTS (OMERTA) ---
    def request_blood_pact(self, uid: str, target_uname: str) -> dict:
        uid = str(uid)
        u = self._get(uid)
        if u.get("blood_partner"): return {"ok": False, "msg": "❌ You already have a Blood Pact partner!"}
        
        target_uid = self.find_uid(target_uname.lstrip("@").lower())
        if not target_uid or target_uid == uid: return {"ok": False, "msg": "❌ Invalid partner!"}
        t_user = self._get(target_uid)
        if t_user.get("blood_partner"): return {"ok": False, "msg": "❌ Target already has a Blood Pact!"}

        self.users.update_one({"_id": target_uid}, {"$set": {"pact_pending": uid}})
        return {"ok": True, "msg": f"🩸 Blood Pact invitation sent to @{target_uname}! They must type `!pact accept`."}

    def accept_blood_pact(self, uid: str) -> dict:
        uid = str(uid)
        u = self._get(uid)
        partner_uid = u.get("pact_pending")
        if not partner_uid: return {"ok": False, "msg": "❌ No pending Blood Pact requests!"}

        self.users.update_one({"_id": uid}, {"$set": {"blood_partner": partner_uid, "pact_pending": None}})
        self.users.update_one({"_id": partner_uid}, {"$set": {"blood_partner": uid, "pact_pending": None}})
        return {"ok": True, "msg": "🩸 **BLOOD PACT SEALED!** Mutual defense active between Blood Brothers. ⚔️"}

    def betray_blood_partner(self, uid: str) -> dict:
        uid = str(uid)
        u = self._get(uid)
        partner_uid = u.get("blood_partner")
        if not partner_uid: return {"ok": False, "msg": "❌ You have no Blood Partner to betray!"}
        
        now = time.time()
        if now - u.get("last_betray", 0.0) < 86400 and not self.is_creator(u.get("username")):
            return {"ok": False, "msg": "⏳ Betrayal cooldown active (24 hours)!"}

        p_user = self._get(partner_uid)
        stolen = int(p_user["bank"] * 0.25)

        self.users.update_one({"_id": partner_uid}, {"$inc": {"bank": -stolen}, "$set": {"blood_partner": None}})
        self.users.update_one({"_id": uid}, {"$inc": {"balance": stolen}, "$set": {"blood_partner": None, "last_betray": now}})

        bounty_doc = {
            "creator_uid": uid,
            "target_uid": uid,
            "is_traitor_bounty": True,
            "target_username": u.get("username"),
            "total_escrow": stolen + 5000,
            "fee_burned": 500,
            "created_at": now,
            "expires_at": now + 72 * 3600,
            "active": True
        }
        self.bounties_col.insert_one(bounty_doc)
        return {"ok": True, "msg": f"🗡️ **BETRAYAL!** Stole **+{stolen} coins** from your Blood Brother's bank!\n🚨 A **Traitor Bounty** has been placed on your head for 3 days!"}

    # --- EXTORTION & SMUGGLING ---
    def extort_user(self, uid: str, target_uname: str) -> dict:
        uid = str(uid)
        u = self._get(uid)
        gang = self.get_user_gang(uid)
        if not gang and not self.is_creator(u.get("username")):
            return {"ok": False, "msg": "❌ Extortion requires you to be in a Gang!"}
        
        now = time.time()
        if now - u.get("last_extort", 0.0) < 3600 and not self.is_creator(u.get("username")):
            return {"ok": False, "msg": "⏳ Extortion cooldown active (1 hour)."}

        target_uid = self.find_uid(target_uname.lstrip("@").lower())
        if not target_uid or target_uid == uid: return {"ok": False, "msg": "❌ Invalid target!"}
        t_user = self._get(target_uid)
        
        fee = 1000
        if t_user["balance"] < fee: return {"ok": False, "msg": f"❌ Target is too broke for extortion!"}

        self.users.update_one({"_id": target_uid}, {"$inc": {"balance": -fee}})
        self.users.update_one({"_id": uid}, {"$set": {"last_extort": now}})
        earned_info = self.apply_debt_garnishment(uid, fee)
        return {"ok": True, "msg": f"🔫 **EXTORTION SUCCESSFUL!** Collected **{fee} coins** protection fee. *(Debt paid: {earned_info['garnished']})* 💰"}

    def run_smuggling(self, uid: str, tier: str) -> dict:
        uid = str(uid)
        u = self._get(uid)
        tier = tier.lower().strip()
        tiers = {
            "low": {"cost": 500, "min": 800, "max": 1500, "risk": 0.25},
            "med": {"cost": 2000, "min": 3000, "max": 6000, "risk": 0.45},
            "medium": {"cost": 2000, "min": 3000, "max": 6000, "risk": 0.45},
            "high": {"cost": 5000, "min": 8000, "max": 18000, "risk": 0.65}
        }
        if tier not in tiers: return {"ok": False, "msg": "❌ Usage: `!smuggle <low/med/high>`"}
        t_info = tiers[tier]

        if u["balance"] < t_info["cost"] and not self.is_creator(u.get("username")):
            return {"ok": False, "msg": f"❌ You need {t_info['cost']} cash coins for this shipment!"}

        self.users.update_one({"_id": uid}, {"$inc": {"balance": -t_info['cost']}})
        if self.is_creator(u.get("username")) or random.random() > t_info["risk"]:
            payout = random.randint(t_info["min"], t_info["max"])
            earned = self.apply_debt_garnishment(uid, payout)
            return {"ok": True, "msg": f"🚚 **SMUGGLING SUCCESS!** Delivered cargo safely. Payout: **+{payout} coins**! 🔥"}
        else:
            self.users.update_one({"_id": uid}, {"$set": {"heat_until": time.time() + 900}})
            return {"ok": True, "msg": f"🚨 **POLICE AMBUSH!** Shipment seized and heat timer triggered (15m)! 🚓"}

    # --- LOTTERY SYSTEM ---
    def get_lottery_state(self) -> dict:
        state = self.lottery_col.find_one({"_id": "current"})
        if not state:
            state = {"_id": "current", "pot": 0, "tickets": {}, "last_draw": time.time()}
            self.lottery_col.insert_one(state)
        return state

    def buy_lottery_tickets(self, uid: str, count: int) -> dict:
        uid = str(uid)
        user = self._get(uid)
        if count <= 0: return {"ok": False, "msg": "❌ Ticket amount must be at least 1!"}
        
        state = self.get_lottery_state()
        curr_tickets = state.get("tickets", {}).get(uid, 0)
        if curr_tickets + count > 10 and not self.is_creator(user.get("username")):
            return {"ok": False, "msg": f"❌ Ticket cap reached (10 max)."}
        
        cost = count * 1000
        if user["balance"] < cost and not self.is_creator(user.get("username")):
            return {"ok": False, "msg": f"❌ You need {cost} cash coins!"}

        if not self.is_creator(user.get("username")):
            self.users.update_one({"_id": uid}, {"$inc": {"balance": -cost}})

        self.lottery_col.update_one({"_id": "current"}, {"$inc": {"pot": cost}, "$set": {f"tickets.{uid}": curr_tickets + count}})
        return {"ok": True, "msg": f"🎟️ Purchased {count} ticket(s) for {cost} coins!"}

    def check_and_draw_lottery(self) -> dict:
        state = self.get_lottery_state()
        now = time.time()
        if now - state.get("last_draw", now) < 24 * 3600: return {"drawn": False}

        tickets_dict = state.get("tickets", {})
        total_tix = sum(tickets_dict.values())
        if total_tix < 3:
            self.lottery_col.update_one({"_id": "current"}, {"$set": {"last_draw": now}})
            return {"drawn": True, "msg": f"🎟️ **LOTTERY DELAYED:** Less than 3 tickets sold. Pot of **{state['pot']} coins** carries over!"}

        pool = []
        for tuid, cnt in tickets_dict.items():
            pool.extend([tuid] * int(cnt))
            
        winner_uid = random.choice(pool)
        winner_user = self._get(winner_uid)
        pot = state.get("pot", 0)
        payout = int(pot * 0.70)
        
        self.users.update_one({"_id": winner_uid}, {"$inc": {"balance": payout}})
        self.lottery_col.update_one({"_id": "current"}, {"$set": {"pot": 0, "tickets": {}, "last_draw": now}})
        return {"drawn": True, "msg": f"🎉 **LOTTERY WINNER:** @{winner_user.get('username')} won **+{payout} coins**! 👑"}

    # --- CASINO SLOTS ---
    def play_slots(self, uid: str, bet: int) -> dict:
        uid = str(uid)
        user = self._get(uid)
        if bet < 100 or bet > 5000: return {"ok": False, "msg": "❌ Bet limit: 100 - 5,000 coins."}
        if user["balance"] < bet and not self.is_creator(user.get("username")):
            return {"ok": False, "msg": "❌ Insufficient cash!"}

        is_owner = self.is_creator(user.get("username"))
        actual_bet = 0 if is_owner else bet
        self.users.update_one({"_id": uid}, {"$inc": {"balance": -actual_bet}})

        emojis = ["💎", "7️⃣", "🔔", "🍒", "🍋", "🍇"]
        roll = random.random()
        if is_owner or roll < 0.02: outcome = ["💎", "💎", "💎"]
        elif roll < 0.10: outcome = ["7️⃣", "7️⃣", "7️⃣"]
        elif roll < 0.35:
            s = random.choice(emojis)
            outcome = [s, s, random.choice([e for e in emojis if e != s])]
            random.shuffle(outcome)
        else:
            outcome = random.sample(emojis, 3)

        reel = f"[ {outcome[0]} | {outcome[1]} | {outcome[2]} ]"
        if outcome[0] == outcome[1] == outcome[2]:
            mult = 20 if outcome[0] == "💎" else 8
            payout = bet * mult
            earned = self.apply_debt_garnishment(uid, payout)
            return {"ok": True, "msg": f"🎰 **SLOTS:** {reel}\n🔥 **JACKPOT!** Won **+{payout} coins**! 🎉"}
        elif outcome[0] == outcome[1] or outcome[1] == outcome[2] or outcome[0] == outcome[2]:
            payout = int(bet * 1.5)
            earned = self.apply_debt_garnishment(uid, payout)
            return {"ok": True, "msg": f"🎰 **SLOTS:** {reel}\n✨ **MATCH!** Won **+{payout} coins**! ✨"}
        else:
            return {"ok": True, "msg": f"🎰 **SLOTS:** {reel}\n💀 **NO MATCH!** Lost **-{actual_bet} coins**."}

    # --- LUXURY & BOUNTIES ---
    def buy_luxury(self, uid: str, item_key: str) -> dict:
        item_key = item_key.lower().strip()
        if item_key not in LUXURY_ITEMS: return {"ok": False, "msg": "❌ Invalid item!"}
        item = LUXURY_ITEMS[item_key]
        user = self._get(uid)
        if item_key in user.get("luxuries", []): return {"ok": False, "msg": "❌ Already owned!"}
        if user["balance"] < item["cost"] and not self.is_creator(user.get("username")):
            return {"ok": False, "msg": f"❌ Need {item['cost']} coins!"}

        actual_cost = 0 if self.is_creator(user.get("username")) else item["cost"]
        self.users.update_one({"_id": str(uid)}, {"$inc": {"balance": -actual_cost}, "$push": {"luxuries": item_key}})
        return {"ok": True, "msg": f"💎 Purchased **{item['name']}**! Title: *{item['title']}*"}

    def flex_status(self, uid: str) -> dict:
        user = self._get(uid)
        lux_keys = user.get("luxuries", [])
        if not lux_keys: return {"ok": False, "msg": "❌ No luxury items owned."}
        sorted_lux = sorted(lux_keys, key=lambda k: LUXURY_ITEMS.get(k, {}).get("cost", 0), reverse=True)
        top_item = LUXURY_ITEMS[sorted_lux[0]]
        emojis = [LUXURY_ITEMS[k]["emoji"] for k in sorted_lux if k in LUXURY_ITEMS]
        net = user['balance'] + user['bank'] - user['debt']
        return {"ok": True, "msg": f"💎 **FLEX:@{user.get('username')}**\n👑 Highest Title: *{top_item['title']}*\n✨ {' '.join(emojis)}\n💰 Net: {net}"}

    def place_bounty(self, creator_uid: str, target_uname: str, amount: int) -> dict:
        creator_uid = str(creator_uid)
        creator = self._get(creator_uid)
        if amount < 1000: return {"ok": False, "msg": "❌ Minimum bounty is 1,000 coins!"}
        target_uid = self.find_uid(target_uname.lstrip("@").lower())
        if not target_uid or target_uid == creator_uid: return {"ok": False, "msg": "❌ Invalid target!"}

        if creator["balance"] < amount and not self.is_creator(creator.get("username")):
            return {"ok": False, "msg": f"❌ Need {amount} coins!"}

        fee = int(amount * 0.10)
        escrow = amount - fee
        if not self.is_creator(creator.get("username")):
            self.users.update_one({"_id": creator_uid}, {"$inc": {"balance": -amount}})

        self.bounties_col.insert_one({
            "creator_uid": creator_uid, "target_uid": target_uid, "target_username": target_uname.lstrip("@"),
            "total_escrow": escrow, "fee_burned": fee, "created_at": time.time(), "expires_at": time.time() + 48 * 3600, "active": True
        })
        return {"ok": True, "msg": f"🎯 Bounty placed on @{target_uname} for **{escrow} coins** reward!"}

    def list_active_bounties(self) -> dict:
        now = time.time()
        bounties = list(self.bounties_col.find({"active": True, "expires_at": {"$gt": now}}))
        if not bounties: return {"ok": False, "msg": "🎯 No active bounties."}
        txt = "🎯 **ACTIVE BOUNTIES**\n\n"
        for b in bounties[:10]:
            hrs = int((b["expires_at"] - now) // 3600)
            txt += f"• @{b['target_username']} — Reward: **{b['total_escrow']} coins** ({hrs}h left)\n"
        return {"ok": True, "msg": txt}

    # --- GANGS & TERRITORIES ---
    def create_gang(self, boss_uid: str, name: str) -> dict:
        clean = name.strip()
        if self.gangs.find_one({"name_lower": clean.lower()}): return {"ok": False, "msg": "❌ Gang name taken!"}
        boss = self._get(boss_uid)
        if boss.get("gang"): return {"ok": False, "msg": "❌ Already in a gang!"}
        if boss["balance"] < 2000 and not self.is_creator(boss.get("username")): return {"ok": False, "msg": "❌ Need 2,000 cash!"}

        if not self.is_creator(boss.get("username")):
            self.users.update_one({"_id": str(boss_uid)}, {"$inc": {"balance": -2000}})
        
        self.gangs.insert_one({
            "name": clean, "name_lower": clean.lower(), "boss_uid": str(boss_uid),
            "members": [str(boss_uid)], "vault": 0, "level": 1, "max_members": 8,
            "vault_cap": 50000, "flag": "🏴", "invites": [], "last_war": 0.0
        })
        self.users.update_one({"_id": str(boss_uid)}, {"$set": {"gang": clean}})
        return {"ok": True, "msg": f"🛡️ Gang **{clean}** established!"}

    def get_gang(self, name: str):
        return self.gangs.find_one({"name_lower": name.strip().lower()})

    def get_user_gang(self, uid: str):
        u = self._get(uid)
        return self.get_gang(u["gang"]) if u.get("gang") else None

    def remove_user_from_gang(self, uid: str):
        uid = str(uid)
        user = self._get(uid)
        gname = user.get("gang")
        if not gname: return False, "Not in a gang."
        gang = self.get_gang(gname)
        if gang:
            if gang["boss_uid"] == uid:
                self.gangs.delete_one({"_id": gang["_id"]})
                self.users.update_many({"gang": gang["name"]}, {"$set": {"gang": None}})
                return True, f"Gang **{gang['name']}** disbanded."
            else:
                self.gangs.update_one({"_id": gang["_id"]}, {"$pull": {"members": uid}})
                self.users.update_one({"_id": uid}, {"$set": {"gang": None}})
                return True, f"Left gang **{gang['name']}**."
        return False, "Gang not found."

    def transfer_gang(self, uid: str, target_uname: str) -> dict:
        uid = str(uid)
        gang = self.get_user_gang(uid)
        if not gang or gang["boss_uid"] != uid:
            return {"ok": False, "msg": "❌ Only the Don can transfer gang leadership!"}
        t_uid = self.find_uid(target_uname.lstrip("@").lower())
        if not t_uid or t_uid not in gang["members"]:
            return {"ok": False, "msg": "❌ Target user must be an active member of your gang!"}
        
        self.gangs.update_one({"_id": gang["_id"]}, {"$set": {"boss_uid": t_uid}})
        return {"ok": True, "msg": f"👑 Gang leadership successfully transferred to @{target_uname}!"}

    def upgrade_gang_level(self, uid: str) -> dict:
        gang = self.get_user_gang(uid)
        if not gang or gang["boss_uid"] != str(uid): return {"ok": False, "msg": "❌ Only Don can upgrade!"}
        next_lvl = gang.get("level", 1) + 1
        if next_lvl not in GANG_LEVELS: return {"ok": False, "msg": "❌ Max level reached!"}
        info = GANG_LEVELS[next_lvl]
        if gang["vault"] < info["cost"]: return {"ok": False, "msg": f"❌ Gang vault needs {info['cost']} coins!"}

        self.gangs.update_one({"_id": gang["_id"]}, {"$inc": {"vault": -info["cost"]}, "$set": {"level": next_lvl, "max_members": info["max_members"], "vault_cap": info["vault_cap"]}})
        return {"ok": True, "msg": f"🏴 Gang upgraded to **Level {next_lvl}**! Perk: {info['perk']}"}

    def get_territory(self, key: str):
        key = key.lower().strip()
        if key not in TERRITORIES: return None
        doc = self.territories.find_one({"_id": key})
        if not doc:
            doc = {"_id": key, "name": TERRITORIES[key]["name"], "cost": TERRITORIES[key]["cost"], "daily_revenue": TERRITORIES[key]["daily_revenue"], "owner_gang": None, "last_collected": 0.0}
            self.territories.insert_one(doc)
        return doc

    def list_territories(self):
        return [self.get_territory(k) for k in TERRITORIES]

    def takeover_territory(self, uid: str, key: str) -> dict:
        gang = self.get_user_gang(uid)
        if not gang or gang["boss_uid"] != str(uid): return {"ok": False, "msg": "❌ Only Don can takeover territory!"}
        t = self.get_territory(key)
        if not t: return {"ok": False, "msg": "❌ Invalid district!"}
        if gang["vault"] < t["cost"]: return {"ok": False, "msg": f"❌ Gang vault needs {t['cost']} vault coins!"}

        self.gangs.update_one({"_id": gang["_id"]}, {"$inc": {"vault": -t["cost"]}})
        self.territories.update_one({"_id": key}, {"$set": {"owner_gang": gang["name"], "last_collected": time.time()}})
        return {"ok": True, "msg": f"👑 District **{t['name']}** conquered by **{gang['name']}**!"}

    def collect_territory_revenue(self, uid: str, key: str) -> dict:
        gang = self.get_user_gang(uid)
        if not gang or gang["boss_uid"] != str(uid): return {"ok": False, "msg": "❌ Only Don can collect revenue!"}
        t = self.get_territory(key)
        if not t or t.get("owner_gang") != gang["name"]: return {"ok": False, "msg": "❌ Your gang doesn't control this district!"}
        if time.time() - t.get("last_collected", 0) < 24 * 3600: return {"ok": False, "msg": "⏳ Revenue on cooldown (24h)."}

        self.territories.update_one({"_id": key}, {"$set": {"last_collected": time.time()}})
        self.gangs.update_one({"_id": gang["_id"]}, {"$inc": {"vault": t["daily_revenue"]}})
        return {"ok": True, "msg": f"💰 Collected **+{t['daily_revenue']} coins** into gang vault!"}

    def buy_business(self, uid: str, biz_key: str) -> dict:
        uid = str(uid)
        user = self._get(uid)
        if user.get("is_police"): return {"ok": False, "msg": "❌ Police Officers cannot own businesses!"}
        biz_key = biz_key.lower().strip()
        if biz_key not in BUSINESSES: return {"ok": False, "msg": "❌ Invalid business key!"}
        binfo = BUSINESSES[biz_key]

        if binfo["type"] == "black" and not self.get_user_gang(uid) and not self.is_creator(user.get("username")):
            return {"ok": False, "msg": "❌ Black market businesses require a Gang!"}
        if self.businesses.find_one({"uid": uid, "biz_key": biz_key}): return {"ok": False, "msg": "❌ Already owned!"}
        if user["balance"] < binfo["cost"] and not self.is_creator(user.get("username")): return {"ok": False, "msg": f"❌ Need {binfo['cost']} cash!"}

        actual_cost = 0 if self.is_creator(user.get("username")) else binfo["cost"]
        if actual_cost > 0: self.users.update_one({"_id": uid}, {"$inc": {"balance": -actual_cost}})
        self.businesses.insert_one({"uid": uid, "biz_key": biz_key, "name": binfo["name"], "type": binfo["type"], "last_collected": time.time()})
        return {"ok": True, "msg": f"🏗️ Established **{binfo['name']}**!"}

    def close_business(self, uid: str, biz_key: str) -> dict:
        biz = self.businesses.find_one({"uid": str(uid), "biz_key": biz_key.lower().strip()})
        if not biz: return {"ok": False, "msg": "❌ You do not own this business!"}
        refund = int(BUSINESSES[biz["biz_key"]]["cost"] * 0.40)
        self.businesses.delete_one({"_id": biz["_id"]})
        self.users.update_one({"_id": str(uid)}, {"$inc": {"balance": refund}})
        return {"ok": True, "msg": f"🏗️ Business dismantled. Received **+{refund} coins** liquidation refund."}

    def get_user_businesses(self, uid: str):
        return list(self.businesses.find({"uid": str(uid)}))

    def collect_business_revenue(self, uid: str) -> dict:
        uid = str(uid)
        user = self._get(uid)
        bizs = self.get_user_businesses(uid)
        if not bizs: return {"ok": False, "msg": "❌ No businesses owned."}

        now = time.time()
        total = 0
        details = []
        gang = self.get_user_gang(uid)

        for b in bizs:
            binfo = BUSINESSES.get(b["biz_key"])
            if not binfo: continue
            if now - b.get("last_collected", 0) < 12 * 3600 and not self.is_creator(user.get("username")):
                details.append(f"⏳ {b['name']}: Not ready.")
                continue

            inc = binfo["daily_income"]
            if binfo["type"] == "black" and gang:
                cut = int(inc * (0.10 if gang["boss_uid"] == uid else 0.20))
                inc -= cut
                self.gangs.update_one({"_id": gang["_id"]}, {"$inc": {"vault": cut}})

            total += inc
            self.businesses.update_one({"_id": b["_id"]}, {"$set": {"last_collected": now}})
            details.append(f"✅ {b['name']}: +{inc}")

        if total <= 0: return {"ok": False, "msg": "\n".join(details)}
        earned = self.apply_debt_garnishment(uid, total)
        return {"ok": True, "msg": f"🏢 **REVENUE REPORT**\n\n" + "\n".join(details) + f"\n\n💵 Net Added: **+{earned['net_earned']} coins**"}


db = Database()
