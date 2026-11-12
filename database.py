"""
MongoDB-backed persistent store for Instagram Economy Bot.
- PyMongo Synchronous Driver.
- Seamless automatic migration from legacy data.json on first boot.
- Invisible creator perks support (Username: v.stray_).
- Special VIP Boosted Luck support (Username: _nuhash_s).
- Integrated Anti-Exploit Debt Garnishment, Dynamic Loans, Gang Empire & Interactive Business Mechanics.
- Phase 1 Additions: Automated Daily Lottery, Casino Slots, Luxury Items Collection & Flex System,
  Bodyguard Security, Escrow Bounty Contracts, Automatic IRS Wealth Tax, and Advanced Gang Upgrades.
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
        
        self.creator_username = "v.stray_"
        self.vip_usernames = ["_nuhash_s"]  # Boosted luck for your friend
        
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
                    migrated_count = 0
                    for uid, udata in legacy_users.items():
                        uid_str = str(uid)
                        if not self.users.find_one({"_id": uid_str}):
                            udata["_id"] = uid_str
                            self.users.insert_one(udata)
                            migrated_count += 1
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
                "streak": 0,
                "wins": 0,
                "losses": 0,
                "rob_ok": 0,
                "rob_fail": 0,
                "gang": None
            }
            self.users.insert_one(u)
        else:
            fields_to_set = {}
            if username and u.get("username") != username:
                fields_to_set["username"] = username
                u["username"] = username
            if "luxuries" not in u:
                fields_to_set["luxuries"] = []
                u["luxuries"] = []
            if "guard_expires" not in u:
                fields_to_set["guard_expires"] = 0.0
                u["guard_expires"] = 0.0
            if "last_audit" not in u:
                fields_to_set["last_audit"] = time.time()
                u["last_audit"] = time.time()
            if "last_slots" not in u:
                fields_to_set["last_slots"] = 0.0
                u["last_slots"] = 0.0
            if fields_to_set:
                self.users.update_one({"_id": uid}, {"$set": fields_to_set})
            
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

    def is_vip(self, username):
        if not username:
            return False
        return username.lower() in [u.lower() for u in self.vip_usernames]

    def check_and_apply_irs_tax(self, uid: str) -> dict:
        u = self._get(uid)
        now = time.time()
        last_audit = u.get("last_audit", 0.0)
        
        if now - last_audit >= 24 * 3600:
            self.users.update_one({"_id": str(uid)}, {"$set": {"last_audit": now}})
            bank_bal = u.get("bank", 0)
            if bank_bal > 50000 and not self.is_creator(u.get("username")):
                excess = bank_bal - 50000
                tax = int(excess * 0.015)
                if tax > 0:
                    new_bank = bank_bal - tax
                    self.users.update_one({"_id": str(uid)}, {"$set": {"bank": new_bank}})
                    return {"audited": True, "tax": tax, "new_bank": new_bank}
        return {"audited": False}

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
        jackpot_applied = (streak % 7 == 0)

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

    # --- LOTTERY SYSTEM ---
    def get_lottery_state(self) -> dict:
        state = self.lottery_col.find_one({"_id": "current"})
        if not state:
            state = {
                "_id": "current",
                "pot": 0,
                "tickets": {},  # uid_str -> count
                "last_draw": time.time()
            }
            self.lottery_col.insert_one(state)
        return state

    def buy_lottery_tickets(self, uid: str, count: int) -> dict:
        uid = str(uid)
        user = self._get(uid)
        if count <= 0:
            return {"ok": False, "msg": "❌ Ticket amount must be at least 1!"}
        
        state = self.get_lottery_state()
        curr_tickets = state.get("tickets", {}).get(uid, 0)
        
        if curr_tickets + count > 10 and not self.is_creator(user.get("username")):
            return {"ok": False, "msg": f"❌ Ticket cap reached! You already own **{curr_tickets}/10 tickets** for this draw."}
        
        ticket_price = 1000
        total_cost = count * ticket_price
        
        if user["balance"] < total_cost and not self.is_creator(user.get("username")):
            return {"ok": False, "msg": f"❌ You need **{total_cost} cash coins** to buy {count} ticket(s)!"}
        
        actual_cost = 0 if self.is_creator(user.get("username")) else total_cost
        if actual_cost > 0:
            self.users.update_one({"_id": uid}, {"$inc": {"balance": -actual_cost}})
        
        new_tickets = curr_tickets + count
        self.lottery_col.update_one(
            {"_id": "current"},
            {
                "$inc": {"pot": total_cost},
                "$set": {f"tickets.{uid}": new_tickets}
            }
        )
        
        updated_state = self.get_lottery_state()
        total_tix = sum(updated_state.get("tickets", {}).values())
        return {
            "ok": True,
            "msg": f"🎟️ Purchased **{count} ticket(s)** for **{total_cost} coins**!\nTotal Tickets Owned: **{new_tickets}/10** | Current Pot: **{updated_state['pot']} coins** ({total_tix} tickets sold)"
        }

    def check_and_draw_lottery(self) -> dict:
        state = self.get_lottery_state()
        now = time.time()
        last_draw = state.get("last_draw", now)
        
        if now - last_draw < 24 * 3600:
            return {"drawn": False}

        tickets_dict = state.get("tickets", {})
        total_tickets_count = sum(tickets_dict.values())
        
        if total_tickets_count < 3:
            # Carry over pot
            self.lottery_col.update_one({"_id": "current"}, {"$set": {"last_draw": now}})
            return {
                "drawn": True,
                "winner": None,
                "msg": f"🎟️ **LOTTERY DRAW DELAYED!** Less than 3 tickets sold. Pot of **{state['pot']} coins** carries over to next draw! 🚀"
            }

        # Select winner
        pool = []
        for tuid, cnt in tickets_dict.items():
            pool.extend([tuid] * cnt)
            
        winner_uid = random.choice(pool)
        winner_user = self._get(winner_uid)
        
        pot = state.get("pot", 0)
        payout = int(pot * 0.70)
        burned = pot - payout
        
        self.users.update_one({"_id": winner_uid}, {"$inc": {"balance": payout}})
        
        # Reset lottery
        self.lottery_col.update_one(
            {"_id": "current"},
            {
                "$set": {
                    "pot": 0,
                    "tickets": {},
                    "last_draw": now
                }
            }
        )
        
        return {
            "drawn": True,
            "winner": winner_user.get("username", "Unknown"),
            "payout": payout,
            "burned": burned,
            "msg": f"🎉 **LOTTERY DRAW RESULT!**\n👑 Winner: @{winner_user.get('username', 'Unknown')}\n💰 Jackpot Payout: **+{payout} coins** (70% of pot)\n🔥 Syndicate Burn: **{burned} coins** deleted!"
        }

    # --- CASINO SLOTS ---
    def play_slots(self, uid: str, bet: int) -> dict:
        uid = str(uid)
        user = self._get(uid)
        now = time.time()
        
        if now - user.get("last_slots", 0.0) < 5 and not self.is_creator(user.get("username")):
            return {"ok": False, "msg": "⏳ Slot machine is spinning! Wait 5 seconds between spins."}
        
        if bet < 100 or bet > 5000:
            return {"ok": False, "msg": "❌ Bet limit for Slots: Minimum 100, Maximum 5,000 coins!"}

        if user["balance"] < bet and not self.is_creator(user.get("username")):
            return {"ok": False, "msg": "❌ You don't have enough cash in hand for this bet!"}

        self.users.update_one({"_id": uid}, {"$set": {"last_slots": now}})
        
        emojis = ["💎", "7️⃣", "🔔", "🍒", "🍋", "🍇"]
        is_owner = self.is_creator(user.get("username"))
        is_vip = self.is_vip(user.get("username"))

        if is_owner:
            outcome = ["💎", "💎", "💎"]
        elif is_vip and random.random() < 0.40:
            s = random.choice(["💎", "7️⃣", "🔔"])
            outcome = [s, s, s]
        else:
            roll = random.random()
            if roll < 0.015:  
                outcome = ["💎", "💎", "💎"]
            elif roll < 0.08:   
                s = random.choice(["7️⃣", "🔔", "🍒"])
                outcome = [s, s, s]
            elif roll < 0.38:   
                s = random.choice(emojis)
                other = random.choice([e for e in emojis if e != s])
                res = [s, s, other]
                random.shuffle(res)
                outcome = res
            else:
                outcome = random.sample(emojis, 3)

        reel_str = f"[ {outcome[0]} | {outcome[1]} | {outcome[2]} ]"

        if outcome[0] == outcome[1] == outcome[2]:
            if outcome[0] == "💎":
                multiplier = 50
                title = "💎💎💎 TRIPLE DIAMOND JACKPOT!"
            else:
                multiplier = 10
                title = "🎉 TRIPLE MATCH!"
            
            payout = bet * multiplier
            earned_info = self.apply_debt_garnishment(uid, payout)
            self.users.update_one({"_id": uid}, {"$inc": {"wins": 1}})
            return {
                "ok": True,
                "msg": f"🎰 **SLOTS:** {reel_str}\n🔥 **{title}** You won **+{payout} coins**! *(Debt paid: {earned_info['garnished']})* Cash: **{earned_info['new_balance']}**"
            }
        elif outcome[0] == outcome[1] or outcome[1] == outcome[2] or outcome[0] == outcome[2]:
            multiplier = 2
            payout = bet * multiplier
            earned_info = self.apply_debt_garnishment(uid, payout)
            self.users.update_one({"_id": uid}, {"$inc": {"wins": 1}})
            return {
                "ok": True,
                "msg": f"🎰 **SLOTS:** {reel_str}\n✨ **DOUBLE MATCH!** You won **+{payout} coins**! *(Debt paid: {earned_info['garnished']})* Cash: **{earned_info['new_balance']}**"
            }
        else:
            actual_loss = 0 if is_owner else bet
            self.users.update_one({"_id": uid}, {"$inc": {"balance": -actual_loss, "losses": 1}})
            updated_u = self.get_user(uid)
            return {
                "ok": True,
                "msg": f"🎰 **SLOTS:** {reel_str}\n💀 **NO MATCH!** Lost **-{actual_loss} coins**. Cash: **{updated_u['balance']}**"
            }

    # --- LUXURY FLEX & COLLECTION ---
    def buy_luxury(self, uid: str, item_key: str) -> dict:
        item_key = item_key.lower().strip()
        if item_key not in LUXURY_ITEMS:
            return {"ok": False, "msg": "❌ Invalid luxury item key! Check `!luxury` catalog."}

        item = LUXURY_ITEMS[item_key]
        user = self._get(uid)
        lux_list = user.get("luxuries", [])

        if item_key in lux_list:
            return {"ok": False, "msg": f"❌ You already own the **{item['name']}**!"}

        cost = item["cost"]
        if user["balance"] < cost and not self.is_creator(user.get("username")):
            return {"ok": False, "msg": f"❌ You need **{cost} cash coins** to buy {item['name']}!"}

        actual_cost = 0 if self.is_creator(user.get("username")) else cost
        self.users.update_one(
            {"_id": str(uid)},
            {
                "$inc": {"balance": -actual_cost},
                "$push": {"luxuries": item_key}
            }
        )
        return {
            "ok": True,
            "msg": f"💎 **LUXURY ACQUIRED!** Purchased **{item['name']}** for **{cost} coins**!\nUnlocked Status Title: *\"{item['title']}\"* ✨"
        }

    def flex_status(self, uid: str) -> dict:
        user = self._get(uid)
        lux_keys = user.get("luxuries", [])
        
        if not lux_keys:
            return {"ok": False, "msg": "❌ You don't own any luxury items to flex! Type `!luxury` to browse the luxury catalog."}

        emojis = [LUXURY_ITEMS[k]["emoji"] for k in lux_keys if k in LUXURY_ITEMS]
        titles = [LUXURY_ITEMS[k]["title"] for k in lux_keys if k in LUXURY_ITEMS]
        flex_icons = " ".join(emojis)
        highest_title = titles[-1] if titles else "High Roller"

        net_worth = user['balance'] + user['bank'] - user['debt']
        return {
            "ok": True,
            "msg": f"💎 **FLEX STATUS:** @{user.get('username')}\n"
                   f"👑 Title: *{highest_title}*\n"
                   f"✨ Collection: {flex_icons}\n"
                   f"💰 Net Worth: **{net_worth} coins**\n"
                   f"🔥 *\"Flashing luxury items in the chat! Status: UNTOUCHABLE.\"*"
        }

    # --- BODYGUARD SECURITY ---
    def buy_bodyguard(self, uid: str) -> dict:
        user = self._get(uid)
        now = time.time()
        
        if user.get("guard_expires", 0.0) > now:
            left = int(user["guard_expires"] - now)
            hrs = left // 3600
            mins = (left % 3600) // 60
            return {"ok": False, "msg": f"🛡️ You already have active Bodyguard security! ({hrs}h {mins}m left)"}

        net_worth = max(0, user['balance'] + user['bank'] - user['debt'])
        cost = max(2000, int(net_worth * 0.05))

        if user["balance"] < cost and not self.is_creator(user.get("username")):
            return {"ok": False, "msg": f"❌ Bodyguard security costs **{cost} cash coins** (5% net worth / min 2,000)!"}

        actual_cost = 0 if self.is_creator(user.get("username")) else cost
        expires_at = now + 24 * 3600
        
        self.users.update_one(
            {"_id": str(uid)},
            {
                "$inc": {"balance": -actual_cost},
                "$set": {"guard_expires": expires_at}
            }
        )
        return {
            "ok": True,
            "msg": f"🛡️ **BODYGUARD HIRED!** Paid **{cost} coins** for 24-hour elite tactical security!\nAny player attempting to `!rob` or `!hunt` you will be neutralized! 🔫"
        }

    # --- BOUNTY CONTRACTS ---
    def place_bounty(self, creator_uid: str, target_uname: str, amount: int) -> dict:
        creator_uid = str(creator_uid)
        creator = self._get(creator_uid)
        
        if amount < 1000:
            return {"ok": False, "msg": "❌ Minimum bounty contract size is 1,000 coins!"}

        target_uname = target_uname.lstrip("@").lower()
        target_uid = self.find_uid(target_uname)
        
        if not target_uid or target_uid == creator_uid:
            return {"ok": False, "msg": "❌ Target user invalid or not found!"}

        if creator["balance"] < amount and not self.is_creator(creator.get("username")):
            return {"ok": False, "msg": f"❌ You need **{amount} cash coins** to issue this bounty contract!"}

        actual_cost = 0 if self.is_creator(creator.get("username")) else amount
        fee = int(amount * 0.10)
        escrow_reward = amount - fee

        if actual_cost > 0:
            self.users.update_one({"_id": creator_uid}, {"$inc": {"balance": -actual_cost}})

        bounty_doc = {
            "creator_uid": creator_uid,
            "target_uid": target_uid,
            "target_username": target_uname,
            "total_escrow": escrow_reward,
            "fee_burned": fee,
            "created_at": time.time(),
            "expires_at": time.time() + 48 * 3600,
            "active": True
        }
        self.bounties_col.insert_one(bounty_doc)
        
        return {
            "ok": True,
            "msg": f"🎯 **BOUNTY CONTRACT ISSUED!**\nTarget: @{target_uname}\nReward Pool: **{escrow_reward} coins** *(10% Syndicate Fee Burned: {fee} coins)*\nValid for 48 hours!"
        }

    def claim_bounty_on_hit(self, attacker_uid: str, target_uid: str) -> str:
        attacker_uid = str(attacker_uid)
        target_uid = str(target_uid)
        
        bounties = list(self.bounties_col.find({"target_uid": target_uid, "active": True}))
        if not bounties:
            return ""

        total_reward = 0
        now = time.time()

        for b in bounties:
            if b.get("expires_at", 0) > now and b["creator_uid"] != attacker_uid:
                total_reward += b["total_escrow"]
                self.bounties_col.update_one({"_id": b["_id"]}, {"$set": {"active": False}})

        if total_reward > 0:
            self.users.update_one({"_id": attacker_uid}, {"$inc": {"balance": total_reward}})
            return f"\n🎯 **BOUNTY CONTRACT CLAIMED!** Claimed **+{total_reward} escrow coins** for hitting target!"
        return ""

    def list_active_bounties(self) -> dict:
        now = time.time()
        bounties = list(self.bounties_col.find({"active": True}))
        valid_bounties = [b for b in bounties if b.get("expires_at", 0) > now]

        if not valid_bounties:
            return {"ok": False, "msg": "🎯 No active bounty contracts found in the Syndicate network."}

        text = "🎯 **ACTIVE SYNDICATE BOUNTIES**\n\n"
        for b in valid_bounties[:10]:
            target = b.get("target_username", "Unknown")
            reward = b.get("total_escrow", 0)
            hrs_left = int((b["expires_at"] - now) // 3600)
            text += f"• @{target} — Reward: 💰 **{reward} coins** ({hrs_left}h left)\n"
        
        return {"ok": True, "msg": text}

    # --- ADVANCED GANG UPGRADES ---
    def upgrade_gang_level(self, uid: str) -> dict:
        user = self._get(uid)
        gang = self.get_user_gang(uid)
        if not gang:
            return {"ok": False, "msg": "❌ You are not in any gang!"}
        if gang["boss_uid"] != str(uid):
            return {"ok": False, "msg": "❌ Only the Gang Boss (Don) can upgrade Gang Level!"}

        curr_lvl = gang.get("level", 1)
        next_lvl = curr_lvl + 1
        
        if next_lvl not in GANG_LEVELS:
            return {"ok": False, "msg": "❌ Gang is already at maximum level!"}

        lvl_info = GANG_LEVELS[next_lvl]
        cost = lvl_info["cost"]

        if gang["vault"] < cost and not self.is_creator(user.get("username")):
            return {"ok": False, "msg": f"❌ Gang Vault needs at least **{cost} vault coins** for Level {next_lvl} upgrade!"}

        actual_cost = 0 if self.is_creator(user.get("username")) else cost
        self.gangs.update_one(
            {"_id": gang["_id"]},
            {
                "$inc": {"vault": -actual_cost},
                "$set": {
                    "level": next_lvl,
                    "max_members": lvl_info["max_members"],
                    "vault_cap": lvl_info["vault_cap"]
                }
            }
        )
        return {
            "ok": True,
            "msg": f"🏴 **GANG UPGRADED TO LEVEL {next_lvl}!**\n- Max Members: **{lvl_info['max_members']}**\n- Vault Cap: **{lvl_info['vault_cap']} coins**\n- New Perk: **{lvl_info['perk']}** 🔥"
        }

    def set_gang_flag(self, uid: str, flag_emoji: str) -> dict:
        user = self._get(uid)
        gang = self.get_user_gang(uid)
        if not gang or gang["boss_uid"] != str(uid):
            return {"ok": False, "msg": "❌ Only the Gang Boss can set the Gang Flag!"}

        cost = 15000
        if gang["vault"] < cost and not self.is_creator(user.get("username")):
            return {"ok": False, "msg": f"❌ Gang Vault needs **{cost} coins** to buy custom Flag Emoji!"}

        actual_cost = 0 if self.is_creator(user.get("username")) else cost
        self.gangs.update_one(
            {"_id": gang["_id"]},
            {
                "$inc": {"vault": -actual_cost},
                "$set": {"flag": flag_emoji.strip()}
            }
        )
        return {"ok": True, "msg": f"🚩 **GANG FLAG UPDATED!** Gang flag set to {flag_emoji.strip()} for **{cost} vault coins**!"}

    def rename_gang(self, uid: str, new_name: str) -> dict:
        user = self._get(uid)
        gang = self.get_user_gang(uid)
        if not gang or gang["boss_uid"] != str(uid):
            return {"ok": False, "msg": "❌ Only the Gang Boss can rename the Gang!"}

        clean_name = new_name.strip()
        if self.gangs.find_one({"name_lower": clean_name.lower()}):
            return {"ok": False, "msg": f"❌ Gang name '{clean_name}' is already taken!"}

        cost = 20000
        if gang["vault"] < cost and not self.is_creator(user.get("username")):
            return {"ok": False, "msg": f"❌ Gang Vault needs **{cost} coins** to rename the Gang!"}

        old_name = gang["name"]
        actual_cost = 0 if self.is_creator(user.get("username")) else cost

        self.gangs.update_one(
            {"_id": gang["_id"]},
            {
                "$inc": {"vault": -actual_cost},
                "$set": {"name": clean_name, "name_lower": clean_name.lower()}
            }
        )
        self.users.update_many({"gang": old_name}, {"$set": {"gang": clean_name}})
        self.territories.update_many({"owner_gang": old_name}, {"$set": {"owner_gang": clean_name}})

        return {"ok": True, "msg": f"🏷️ **GANG RENAMED!** **{old_name}** is now officially **{clean_name}**!"}

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
            "level": 1,
            "max_members": 8,
            "vault_cap": 50000,
            "flag": "🏴",
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
        
        vault_cap = gang.get("vault_cap", 50000)
        new_vault = min(gang["vault"] + rev, vault_cap)
        self.gangs.update_one({"_id": gang["_id"]}, {"$set": {"vault": new_vault}})
        return {"ok": True, "msg": f"💰 **DISTRICT REVENUE COLLECTED!** Added **+{rev} coins** to **{gang['name']}** Vault from **{t['name']}**! (Vault: {new_vault}/{vault_cap})"}

    def buy_business(self, uid: str, biz_key: str) -> dict:
        biz_key = biz_key.lower().strip()
        if biz_key not in BUSINESSES:
            return {"ok": False, "msg": f"❌ Invalid business key! Check `!biz catalog`."}
        
        binfo = BUSINESSES[biz_key]
        user = self._get(uid)
        
        if binfo["type"] == "black":
            gang = self.get_user_gang(uid)
            if not gang and not self.is_creator(user.get("username")):
                return {"ok": False, "msg": "❌ Black Market businesses require you to be in a Gang!"}

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
            "last_collected": time.time(),
            "last_event": 0.0
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
        cooldown = 12 * 3600
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

            income = int(binfo["daily_income"] * (1 + (b.get("level", 1) - 1) * 0.5))

            if binfo["type"] == "black":
                if gang:
                    is_boss = (gang["boss_uid"] == uid)
                    cut_pct = 0.10 if is_boss else 0.20
                    gang_cut = int(income * cut_pct)
                    net_income = income - gang_cut
                    
                    vault_cap = gang.get("vault_cap", 50000)
                    new_vault = min(gang["vault"] + gang_cut, vault_cap)
                    self.gangs.update_one({"_id": gang["_id"]}, {"$set": {"vault": new_vault}})
                    gang_cut_total += gang_cut
                else:
                    net_income = income
            else:
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

    # --- INTERACTIVE BUSINESS ACTIONS (FLIP, HOST, ORDER) ---
    def biz_property_flip(self, uid: str) -> dict:
        uid = str(uid)
        biz = self.businesses.find_one({"uid": uid, "biz_key": "realty"})
        if not biz:
            return {"ok": False, "msg": "❌ You must own the **Pawn Shop & Real Estate** (`realty`) to flip properties!"}
        
        user = self._get(uid)
        now = time.time()
        if now - biz.get("last_event", 0.0) < 3600 and not self.is_creator(user.get("username")):
            left = int(3600 - (now - biz.get("last_event", 0.0)))
            return {"ok": False, "msg": f"⏳ Property market cooling down! Try flipping again in {left // 60}m."}

        self.businesses.update_one({"_id": biz["_id"]}, {"$set": {"last_event": now}})
        
        if random.random() < 0.65:
            profit = random.randint(1500, 4500)
            earned_info = self.apply_debt_garnishment(uid, profit)
            return {"ok": True, "msg": f"🏢 **PROPERTY FLIPPED!** Successfully sold real estate for a massive profit of **+{profit} coins**! *(Debt paid: {earned_info['garnished']})* 💰"}
        else:
            loss = random.randint(800, 2000)
            new_bal = max(0, user["balance"] - loss)
            self.users.update_one({"_id": uid}, {"$set": {"balance": new_bal}})
            return {"ok": True, "msg": f"📉 **FLIP FAILED!** Market crashed and property value tanked. Lost **-{loss} coins** on renovation! 💀"}

    def biz_host_vip_party(self, uid: str) -> dict:
        uid = str(uid)
        biz = self.businesses.find_one({"uid": uid, "biz_key": "club"})
        if not biz:
            return {"ok": False, "msg": "❌ You must own the **Nightclub / Lounge** (`club`) to host VIP parties!"}
        
        user = self._get(uid)
        now = time.time()
        if now - biz.get("last_event", 0.0) < 3600 and not self.is_creator(user.get("username")):
            left = int(3600 - (now - biz.get("last_event", 0.0)))
            return {"ok": False, "msg": f"⏳ Club recovering from last party! Wait {left // 60}m."}

        self.businesses.update_one({"_id": biz["_id"]}, {"$set": {"last_event": now}})
        
        if random.random() < 0.70:
            revenue = random.randint(1000, 3500)
            earned_info = self.apply_debt_garnishment(uid, revenue)
            return {"ok": True, "msg": f"🍸 **VIP PARTY SUCCESS!** Club packed out with high rollers. Earned **+{revenue} coins** from bar sales & entry! *(Debt paid: {earned_info['garnished']})* 🎉"}
        else:
            cost = 500
            new_bal = max(0, user["balance"] - cost)
            self.users.update_one({"_id": uid}, {"$set": {"balance": new_bal}})
            return {"ok": True, "msg": f"💥 **PARTY RAIDED!** Police raided the club due to noise complaints. Paid **-{cost} coins** in hush money! 🚨"}

    def biz_chop_order(self, uid: str) -> dict:
        uid = str(uid)
        biz = self.businesses.find_one({"uid": uid, "biz_key": "chop_shop"})
        if not biz:
            return {"ok": False, "msg": "❌ You must own the **Luxury Chop Shop** (`chop_shop`) to fulfill custom orders!"}
        
        user = self._get(uid)
        now = time.time()
        if now - biz.get("last_event", 0.0) < 3600 and not self.is_creator(user.get("username")):
            left = int(3600 - (now - biz.get("last_event", 0.0)))
            return {"ok": False, "msg": f"⏳ Chop shop tools cooling down! Wait {left // 60}m."}

        self.businesses.update_one({"_id": biz["_id"]}, {"$set": {"last_event": now}})
        
        if random.random() < 0.60:
            payout = random.randint(2000, 5000)
            earned_info = self.apply_debt_garnishment(uid, payout)
            return {"ok": True, "msg": f"🚗 **CUSTOM CHOP ORDER FULFILLED!** Stripped and sold rare exotic car parts for **+{payout} coins**! *(Debt paid: {earned_info['garnished']})* 🔥"}
        else:
            penalty = 1000
            new_bal = max(0, user["balance"] - penalty)
            self.users.update_one({"_id": uid}, {"$set": {"balance": new_bal}})
            return {"ok": True, "msg": f"🚨 **STING OPERATION!** Undercover cops traced the chassis numbers. Fined **-{penalty} coins**! 💀"}


db = Database()
