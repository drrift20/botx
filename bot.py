import os
import time
import random
import json
import logging
from instagrapi import Client
import database as db

log = logging.getLogger("botx.bot")

SESSION_FILE = "session.json"

class InstagramBot:
    def __init__(self):
        self.cl = Client()
        # Checks THREAD_ID first, then falls back to INSTA_THREAD_ID
        self.thread_id = os.environ.get("THREAD_ID") or os.environ.get("INSTA_THREAD_ID")
        self.commands = {}

    def command(self, name):
        def decorator(func):
            self.commands[name.lower()] = func
            return func
        return decorator

    def reply(self, message, text):
        try:
            self.cl.direct_send(text, thread_ids=[self.thread_id])
        except Exception as e:
            log.error("Failed to send reply: %s", e)

    def login(self):
        username = os.environ.get("INSTA_USERNAME")
        password = os.environ.get("INSTA_PASSWORD")
        session_data = os.environ.get("SESSION_DATA")
        
        # Handle SESSION_DATA env variable if provided
        if session_data and not os.path.exists(SESSION_FILE):
            try:
                with open(SESSION_FILE, "w", encoding="utf-8") as f:
                    f.write(session_data)
                log.info("Successfully generated session.json from SESSION_DATA environment variable.")
            except Exception as e:
                log.warning("Failed to write session.json from SESSION_DATA: %s", e)

        if os.path.exists(SESSION_FILE):
            try:
                self.cl.load_settings(SESSION_FILE)
                if username and password:
                    self.cl.login(username, password)
                log.info("Logged in using session file.")
                return
            except Exception as e:
                log.warning("Session load failed (%s), logging in fresh...", e)
        
        if username and password:
            self.cl.login(username, password)
            self.cl.dump_settings(SESSION_FILE)
            log.info("Logged in with username/password and saved session.")
        else:
            raise ValueError("Both INSTA_USERNAME and INSTA_PASSWORD (or valid session) must be provided.")

    def poll_loop(self):
        log.info("Starting bot poll loop for thread %s", self.thread_id)
        seen_messages = set()
        
        # --- FIX: Mark existing recent messages as seen on startup to avoid spamming old history ---
        try:
            init_thread = self.cl.direct_thread(self.thread_id)
            for msg in init_thread.messages[:20]:
                seen_messages.add(msg.id)
            log.info("Initialized seen_messages with %d existing messages.", len(seen_messages))
        except Exception as e:
            log.warning("Could not pre-fill seen_messages: %s", e)
        # ------------------------------------------------------------------------------------------

        while True:
            try:
                thread = self.cl.direct_thread(self.thread_id)
                for msg in thread.messages[:15]:
                    if msg.id in seen_messages:
                        continue
                    seen_messages.add(msg.id)
                    if len(seen_messages) > 300:
                        seen_messages.pop()

                    text = msg.text
                    if text and text.startswith("!"):
                        parts = text[1:].strip().split()
                        cmd = parts[0].lower()
                        args = parts[1:]
                        if cmd in self.commands:
                            class MockUser:
                                def __init__(self, pk, username):
                                    self.pk = pk
                                    self.username = username

                            class MockMessage:
                                def __init__(self, user, text, args):
                                    self.user = user
                                    self.text = text
                                    self.args = args

                            user_pk = str(msg.user_id)
                            try:
                                u_info = self.cl.user_info(msg.user_id)
                                uname = u_info.username
                            except Exception:
                                uname = f"user_{user_pk[-4:]}"

                            mock_msg = MockMessage(MockUser(user_pk, uname), text, args)
                            try:
                                func = self.commands[cmd]
                                func(mock_msg, *args) if args else func(mock_msg)
                            except Exception as e:
                                log.error("Error executing command %s: %s", cmd, e)
            except Exception as e:
                log.error("Polling error: %s", e)
            time.sleep(5)

bot = InstagramBot()

# --- REGISTER ALL COMMANDS ---

@bot.command("help")
def cmd_help(message):
    bot.reply(message, "🔥 **UNDERGROUND CASINO & MAFIA BOT - HELP** 🔥\n\n"
                      "👤 **Profile & Money:**\n"
                      "- `!daily` - Claim streak bonus (Higher streak = richer rewards!)\n"
                      "- `!profile` (or `!bal`) - Check your net worth, cash & inventory\n"
                      "- `!lb` - View chat richest players\n"
                      "- `!pay <user> <amt>` - Send money to friends\n\n"
                      "⚡ **Action & Chaos:**\n"
                      "- `!work` - Do a gig (30m cooldown)\n"
                      "- `!crime` - High-risk high-reward crime (1h cooldown)\n"
                      "- `!rob <user>` - Mug another player's cash! (Risk of police fine)\n\n"
                      "🏦 **Bank & Black Market:**\n"
                      "- `!bank` - Vault deposits, withdrawals & 25% interest loans\n"
                      "- `!shop` - View Potions, Police Shields & Jackpot Pills\n"
                      "- `!buy <item>` - Buy black market gear\n\n"
                      "🎲 **Gambling & Fun:**\n"
                      "- `!coinflip <amt/all/half> <heads/tails>` - Double or nothing!\n"
                      "- `!roll` - Roll 1-100\n"
                      "- `!ping` - Status check")

@bot.command("ping")
def cmd_ping(message):
    bot.reply(message, "pong! 🏓 Casino server is fully juiced and running.")

@bot.command("profile")
@bot.command("bal")
def cmd_profile(message):
    uid = str(message.user.pk)
    database_inst = db.db if hasattr(db, "db") else db.Database()
    user = database_inst.get_user(uid, message.user.username)
    inv = user.get("inventory", {})
    inv_str = ", ".join([f"{k.replace('_', ' ').title()}: {v}" for k, v in inv.items() if v > 0]) or "Empty 🎒"
    net_worth = user['balance'] + user['bank'] - user['debt']
    bot.reply(message, f"👤 **MAFIA PROFILE: {message.user.username}**\n"
                      f"- Cash in Hand: 💵 {user['balance']} coins\n"
                      f"- Bank Vault: 🏦 {user['bank']} coins\n"
                      f"- Debt: 💳 {user['debt']} coins\n"
                      f"- Net Worth: 💎 {net_worth} coins\n"
                      f"- Gear: {inv_str}")

@bot.command("leaderboard")
@bot.command("lb")
def cmd_leaderboard(message):
    database_inst = db.db if hasattr(db, "db") else db.Database()
    users = list(database_inst._users.values()) if hasattr(database_inst, "_users") else []
    if not users:
        return bot.reply(message, "📊 Leaderboard is empty!")
    
    users.sort(key=lambda u: u.get("balance", 0) + u.get("bank", 0) - u.get("debt", 0), reverse=True)
    top = users[:5]
    
    lb_text = "🏆 **UNDERGROUND RICH LIST (TOP 5)**\n"
    for i, u in enumerate(top, 1):
        name = u.get("username", "Unknown")
        net = u.get("balance", 0) + u.get("bank", 0) - u.get("debt", 0)
        lb_text += f"{i}. **{name}** — 💎 {net} net worth (Cash: {u.get('balance', 0)})\n"
    bot.reply(message, lb_text)

@bot.command("pay")
def cmd_pay(message, target="", amount=0):
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        amount = 0
        
    if amount <= 0 or not target:
        return bot.reply(message, "❌ Format: `!pay <username> <amount>`")
    
    uid = str(message.user.pk)
    database_inst = db.db if hasattr(db, "db") else db.Database()
    sender = database_inst.get_user(uid, message.user.username)
    
    if sender["balance"] < amount:
        return bot.reply(message, "❌ You don't have enough cash in hand!")
    
    target = target.lstrip("@").lower()
    target_uid = None
    if hasattr(database_inst, "_users"):
        for tuid, udata in database_inst._users.items():
            if udata.get("username", "").lower() == target:
                target_uid = tuid
                break
                
    if not target_uid:
        return bot.reply(message, f"❌ User '@{target}' not found in database!")
    if target_uid == uid:
        return bot.reply(message, "❌ You can't pay yourself!")
        
    with database_inst._lock:
        s = database_inst._get(uid)
        t = database_inst._get(target_uid)
        s["balance"] -= amount
        t["balance"] += amount
        database_inst._dirty = True
        
    bot.reply(message, f"💸 Successfully transferred **{amount} coins** to @{target}!")

@bot.command("rob")
def cmd_rob(message, target=""):
    uid = str(message.user.pk)
    database_inst = db.db if hasattr(db, "db") else db.Database()
    user = database_inst.get_user(uid, message.user.username)
    
    cooldown = 1800 # 30 mins
    left = cooldown - (time.time() - user.get("last_rob", 0))
    if left > 0:
        mins = int(left // 60)
        return bot.reply(message, f"⏳ You are hiding from heat! Wait another {mins} minutes before mugging someone.")
        
    target = target.lstrip("@").lower()
    if not target:
        return bot.reply(message, "❌ Usage: `!rob <username>`")
        
    target_uid = None
    if hasattr(database_inst, "_users"):
        for tuid, udata in database_inst._users.items():
            if udata.get("username", "").lower() == target:
                target_uid = tuid
                break
                
    if not target_uid or target_uid == uid:
        return bot.reply(message, f"❌ Target user '@{target}' not found or invalid!")
        
    t_user = database_inst._get(target_uid)
    if t_user["balance"] < 50:
        return bot.reply(message, f"❌ @{target} is too broke to rob! They have less than 50 coins.")
        
    with database_inst._lock:
        u = database_inst._get(uid)
        t = database_inst._get(target_uid)
        u["last_rob"] = time.time()
        
        # 40% success rate to rob
        if random.random() < 0.40:
            stolen = random.randint(30, min(300, t["balance"]))
            t["balance"] -= stolen
            u["balance"] += stolen
            database_inst._dirty = True
            bot.reply(message, f"🥷 SUCCESSFUL HEIST! You ambushed @{target} and looted **+{stolen} coins** from their pockets! 💰")
        else:
            fine = random.randint(50, 150)
            u["balance"] = max(0, u["balance"] - fine)
            database_inst._dirty = True
            bot.reply(message, f"🚨 CAUGHT RED-HANDED! @{target} beat you up and you paid a hospital/police fine of **-{fine} coins**! 🏥")

@bot.command("daily")
def cmd_daily(message):
    uid = str(message.user.pk)
    res = db.db.claim_daily(uid, message.user.username) if hasattr(db, "db") else db.Database().claim_daily(uid, message.user.username)
    if not res["ok"]:
        hours = int(res["remaining"] // 3600)
        mins = int((res["remaining"] % 3600) // 60)
        return bot.reply(message, f"⏳ Daily already claimed! Come back in {hours}h {mins}m.")
    bot.reply(message, f"🎁 Daily bonus claimed! **+{res['amount']} coins** (Streak: 🔥 {res['streak']} days). Total cash: **{res['balance']}**.")

@bot.command("work")
def cmd_work(message):
    uid = str(message.user.pk)
    database_inst = db.db if hasattr(db, "db") else db.Database()
    user = database_inst.get_user(uid, message.user.username)
    
    cooldown = 1800
    left = cooldown - (time.time() - user.get("last_work", 0))
    if left > 0:
        mins = int(left // 60)
        return bot.reply(message, f"⏳ You are too tired! Rest for another {mins} minutes.")
    
    jobs = [
        ("coding a shady dark web script", 60, 130),
        ("washing dishes at an underground diner", 40, 90),
        ("smuggling contraband across town", 90, 160),
        ("fixing broken crypto mining rigs", 50, 120)
    ]
    job_desc, min_c, max_c = random.choice(jobs)
    earned = random.randint(min_c, max_c)
    
    inv = user.get("inventory", {})
    if inv.get("jackpot_pill", 0) > 0:
        inv["jackpot_pill"] -= 1
        earned *= 2
        pill_msg = "💊 **Jackpot Pill active!** Earnings DOUBLED! 🚀\n"
    else:
        pill_msg = ""
        
    with database_inst._lock:
        u = database_inst._get(uid)
        u["balance"] += earned
        u["last_work"] = time.time()
        u["inventory"] = inv
        database_inst._dirty = True
        new_bal = u["balance"]
        
    bot.reply(message, f"{pill_msg}💼 You finished {job_desc} and earned **+{earned} coins**! Cash: **{new_bal}**.")

@bot.command("crime")
def cmd_crime(message):
    uid = str(message.user.pk)
    database_inst = db.db if hasattr(db, "db") else db.Database()
    user = database_inst.get_user(uid, message.user.username)
    
    cooldown = 3600
    left = cooldown - (time.time() - user.get("last_crime", 0))
    if left > 0:
        mins = int(left // 60)
        return bot.reply(message, f"🚨 Heat is too high! Hide out for {mins} more minutes.")
    
    inv = user.get("inventory", {})
    success_chance = 0.70 if inv.get("luck_potion", 0) > 0 else 0.45
    if inv.get("luck_potion", 0) > 0:
        inv["luck_potion"] -= 1

    crimes = [
        ("hacking the central bank mainframe", 600, 1800, 300, 900),
        ("hijacking an armored cash truck", 400, 1100, 200, 600),
        ("running an underground casino scam", 500, 1400, 250, 750)
    ]
    crime_name, min_w, max_w, min_f, max_f = random.choice(crimes)
    
    with database_inst._lock:
        u = database_inst._get(uid)
        u["last_crime"] = time.time()
        
        if random.random() < success_chance:
            won = random.randint(min_w, max_w)
            if inv.get("jackpot_pill", 0) > 0:
                inv["jackpot_pill"] -= 1
                won *= 2
                pill_tag = " (💊 Doubled!)"
            else:
                pill_tag = ""
            u["balance"] += won
            u["inventory"] = inv
            database_inst._dirty = True
            msg = f"🕶️ MASSIVE HEIST! Successfully completed {crime_name} and looted **+{won} coins**{pill_tag}! 🎉"
        else:
            if inv.get("police_shield", 0) > 0:
                inv["police_shield"] -= 1
                u["inventory"] = inv
                database_inst._dirty = True
                msg = f"🛡️ BUSTED BY COPS, BUT SAVED! Your **Police Shield** deflected the arrest while {crime_name}!"
            else:
                lost = random.randint(min_f, max_f)
                u["balance"] = max(0, u["balance"] - lost)
                u["inventory"] = inv
                database_inst._dirty = True
                msg = f"🚓 ARRESTED! Failed while {crime_name} and paid a massive fine of **-{lost} coins**! 💀"

    bot.reply(message, msg)

@bot.command("bank")
def cmd_bank(message, action=None, amount=0):
    uid = str(message.user.pk)
    database_inst = db.db if hasattr(db, "db") else db.Database()
    user = database_inst.get_user(uid, message.user.username)
    
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        amount = 0

    if not action:
        return bot.reply(message, f"🏦 **MAFIA CENTRAL BANK**\n- Cash: {user['balance']} coins\n- Vault: {user['bank']} coins\n- Debt (25% interest): {user['debt']} coins\n\nUsage: `!bank deposit <amt>`, `!bank withdraw <amt>`, `!bank loan <amt>`, `!bank repay <amt>`")
    
    action = action.lower()
    with database_inst._lock:
        u = database_inst._get(uid)
        if action == "deposit":
            if amount <= 0 or amount > u["balance"]:
                return bot.reply(message, "❌ Invalid deposit amount!")
            u["balance"] -= amount
            u["bank"] += amount
            database_inst._dirty = True
            bot.reply(message, f"📥 Deposited **{amount} coins** into your safe vault (robbers can't touch this!).")
            
        elif action == "withdraw":
            if amount <= 0 or amount > u["bank"]:
                return bot.reply(message, "❌ Invalid withdrawal amount!")
            u["bank"] -= amount
            u["balance"] += amount
            database_inst._dirty = True
            bot.reply(message, f"📤 Withdrew **{amount} coins** from your vault.")
            
        elif action == "loan":
            if u["debt"] > 0:
                return bot.reply(message, "❌ Clear your existing loan before taking a new one!")
            if amount <= 0 or amount > 5000:
                return bot.reply(message, "❌ Max loan limit is 5,000 coins!")
            u["balance"] += amount
            u["debt"] = int(amount * 1.25)
            database_inst._dirty = True
            bot.reply(message, f"💸 Loan approved: **{amount} coins**! Total debt with juice: **{u['debt']} coins**. Good luck paying it back! 😈")
            
        elif action == "repay":
            if u["debt"] <= 0:
                return bot.reply(message, "🎉 You have zero debt!")
            pay_amt = min(amount if amount > 0 else u["debt"], u["balance"], u["debt"])
            u["balance"] -= pay_amt
            u["debt"] -= pay_amt
            database_inst._dirty = True
            bot.reply(message, f"✅ Repaid **{pay_amt} coins**. Remaining debt: **{u['debt']} coins**.")

@bot.command("shop")
def cmd_shop(message):
    bot.reply(message, "🛒 **BLACK MARKET SHOP**\n\n"
                      "1. `!buy potion` (300 coins) - Luck Potion (Boosts crime success to 70%)\n"
                      "2. `!buy shield` (500 coins) - Police Shield (Saves you from 1 police fine)\n"
                      "3. `!buy pill` (1000 coins) - Jackpot Pill (Doubles your next work/crime payout)\n\n"
                      "Type `!buy <item>` to grab gear!")

@bot.command("buy")
def cmd_buy(message, item_name=""):
    uid = str(message.user.pk)
    database_inst = db.db if hasattr(db, "db") else db.Database()
    user = database_inst.get_user(uid, message.user.username)
    
    item_name = item_name.lower()
    shop_items = {
        "potion": {"name": "Luck Potion", "cost": 300, "key": "luck_potion"},
        "luck": {"name": "Luck Potion", "cost": 300, "key": "luck_potion"},
        "shield": {"name": "Police Shield", "cost": 500, "key": "police_shield"},
        "police": {"name": "Police Shield", "cost": 500, "key": "police_shield"},
        "pill": {"name": "Jackpot Pill", "cost": 1000, "key": "jackpot_pill"},
        "jackpot": {"name": "Jackpot Pill", "cost": 1000, "key": "jackpot_pill"}
    }
    
    if item_name not in shop_items:
        return bot.reply(message, "❌ Item not found! Check `!shop`.")
        
    item = shop_items[item_name]
    if user["balance"] < item["cost"]:
        return bot.reply(message, f"❌ You need {item['cost']} cash coins to buy a {item['name']}!")
        
    with database_inst._lock:
        u = database_inst._get(uid)
        u["balance"] -= item["cost"]
        inv = u.get("inventory", {})
        inv[item["key"]] = inv.get(item["key"], 0) + 1
        u["inventory"] = inv
        database_inst._dirty = True
        total_qty = u['inventory'][item['key']]
        
    bot.reply(message, f"🧪 Purchased **{item['name']}**! You now own {total_qty}.")

@bot.command("coinflip")
def cmd_coinflip(message, bet=0, choice="heads"):
    uid = str(message.user.pk)
    database_inst = db.db if hasattr(db, "db") else db.Database()
    user = database_inst.get_user(uid, message.user.username)
    
    bet_str = str(bet).lower()
    if bet_str == "all":
        bet = user["balance"]
    elif bet_str == "half":
        bet = user["balance"] // 2
    else:
        try:
            bet = int(bet)
        except (TypeError, ValueError):
            bet = 0

    if bet <= 0 or bet > user["balance"]:
        return bot.reply(message, "❌ Invalid bet! Usage: `!coinflip <amount/all/half> <heads/tails>`")
    
    choice = choice.lower()
    if choice not in ["heads", "tails"]:
        choice = "heads"

    outcome = random.choice(["heads", "tails"])
    
    with database_inst._lock:
        u = database_inst._get(uid)
        if outcome == choice:
            u["balance"] += bet
            database_inst._dirty = True
            bot.reply(message, f"🪙 Coin landed on **{outcome.upper()}**! You won **+{bet} coins**! 🎉 (Balance: {u['balance']})")
        else:
            u["balance"] -= bet
            database_inst._dirty = True
            bot.reply(message, f"🪙 Coin landed on **{outcome.upper()}**! You lost **-{bet} coins**! 💀 (Balance: {u['balance']})")

@bot.command("roll")
def cmd_roll(message):
    val = random.randint(1, 100)
    bot.reply(message, f"🎲 You rolled a **{val}** out of 100!")

def run_bot(*args, **kwargs):
    bot.login()
    bot.poll_loop()
