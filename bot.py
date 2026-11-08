import os
import time
import random
import logging
from instagrapi import Client
import database as db

log = logging.getLogger("botx.bot")

SESSION_FILE = "session.json"

class InstagramBot:
    def __init__(self):
        self.cl = Client()
        self.thread_id = os.environ.get("INSTA_THREAD_ID")
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
        
        if os.path.exists(SESSION_FILE):
            try:
                self.cl.load_settings(SESSION_FILE)
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
            raise ValueError("No credentials or session found.")

    def poll_loop(self):
        log.info("Starting bot poll loop for thread %s", self.thread_id)
        seen_messages = set()
        while True:
            try:
                thread = self.cl.direct_thread(self.thread_id)
                for msg in thread.messages[:10]:
                    if msg.id in seen_messages:
                        continue
                    seen_messages.add(msg.id)
                    if len(seen_messages) > 200:
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
                            except TypeError:
                                func(mock_msg)
                            except Exception as e:
                                log.error("Error executing command %s: %s", cmd, e)
            except Exception as e:
                log.error("Polling error: %s", e)
            time.sleep(5)

bot = InstagramBot()

# Register all commands
@bot.command("daily")
def cmd_daily(message):
    uid = str(message.user.pk)
    res = db.db.claim_daily(uid, message.user.username) if hasattr(db, "db") else db.claim_daily(uid, message.user.username)
    if not res["ok"]:
        hours = int(res["remaining"] // 3600)
        mins = int((res["remaining"] % 3600) // 60)
        return bot.reply(message, f"⏳ Daily already claimed! Try again in {hours}h {mins}m. Balance: {res['balance']} coins.")
    bot.reply(message, f"🎁 Daily bonus collected! **+{res['amount']} coins** (Streak: 🔥 {res['streak']} days). Total balance: **{res['balance']} coins**.")

@bot.command("work")
def cmd_work(message):
    uid = str(message.user.pk)
    user = db.get_user(uid, message.user.username)
    cooldown = 1800
    left = cooldown - (time.time() - user.get("last_work", 0))
    if left > 0:
        mins = int(left // 60)
        return bot.reply(message, f"⏳ You are exhausted! Wait another {mins} minutes before working again.")
    
    jobs = [
        ("coding a bug-filled Python script", 60, 120),
        ("cleaning a local cafe floor", 40, 90),
        ("delivering cold pizza in heavy traffic", 80, 150),
        ("fixing a neighbor's broken Wi-Fi router", 50, 110)
    ]
    job_desc, min_c, max_c = random.choice(jobs)
    earned = random.randint(min_c, max_c)
    
    database_inst = db.db if hasattr(db, "db") else db.Database()
    with database_inst._lock:
        u = database_inst._get(uid)
        u["balance"] += earned
        u["last_work"] = time.time()
        database_inst._dirty = True
        new_bal = u["balance"]
        
    bot.reply(message, f"💼 You finished {job_desc} and earned **+{earned} coins**! Total cash: **{new_bal}**.")

@bot.command("crime")
def cmd_crime(message):
    uid = str(message.user.pk)
    user = db.get_user(uid, message.user.username)
    cooldown = 3600
    left = cooldown - (time.time() - user.get("last_crime", 0))
    if left > 0:
        mins = int(left // 60)
        return bot.reply(message, f"🚨 Police alert is too high! Wait another {mins} minutes before committing another crime.")
    
    inv = user.get("inventory", {})
    has_potion = inv.get("luck_potion", 0) > 0
    success_chance = 0.45
    if has_potion:
        success_chance = 0.70
        inv["luck_potion"] -= 1

    crimes = [
        ("hacking a local ATM system", 500, 1500, 300, 800),
        ("stealing a high-end sports bike", 300, 900, 200, 500),
        ("running an underground street gambling scam", 400, 1200, 250, 700)
    ]
    crime_name, min_w, max_w, min_f, max_f = random.choice(crimes)
    
    database_inst = db.db if hasattr(db, "db") else db.Database()
    with database_inst._lock:
        u = database_inst._get(uid)
        u["last_crime"] = time.time()
        if has_potion:
            u["inventory"] = inv
            
        if random.random() < success_chance:
            won = random.randint(min_w, max_w)
            u["balance"] += won
            database_inst._dirty = True
            msg = f"🕶️ MISSION SUCCESS! You successfully completed {crime_name} and looted **+{won} coins**! 🎉"
        else:
            lost = random.randint(min_f, max_f)
            u["balance"] = max(0, u["balance"] - lost)
            database_inst._dirty = True
            msg = f"🚓 CAUGHT BY POLICE! You failed while {crime_name} and paid a fine of **-{lost} coins**! 💀"

    bot.reply(message, msg)

@bot.command("bank")
def cmd_bank(message, action=None, amount=0):
    uid = str(message.user.pk)
    user = db.get_user(uid, message.user.username)
    
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        amount = 0

    if not action:
        return bot.reply(message, f"🏦 **CENTRAL BANK**\n- Cash: {user['balance']} coins\n- Bank Vault: {user['bank']} coins\n- Outstanding Debt: {user['debt']} coins\n\nUsage: `!bank deposit <amt>`, `!bank withdraw <amt>`, `!bank loan <amt>`, `!bank repay <amt>`")
    
    action = action.lower()
    database_inst = db.db if hasattr(db, "db") else db.Database()
    with database_inst._lock:
        u = database_inst._get(uid)
        if action == "deposit":
            if amount <= 0 or amount > u["balance"]:
                return bot.reply(message, "❌ Invalid deposit amount!")
            u["balance"] -= amount
            u["bank"] += amount
            database_inst._dirty = True
            bot.reply(message, f"📥 Successfully deposited **{amount} coins** into your bank vault (safe from robbers).")
            
        elif action == "withdraw":
            if amount <= 0 or amount > u["bank"]:
                return bot.reply(message, "❌ Invalid withdrawal amount!")
            u["bank"] -= amount
            u["balance"] += amount
            database_inst._dirty = True
            bot.reply(message, f"📤 Successfully withdrew **{amount} coins** from your vault.")
            
        elif action == "loan":
            if u["debt"] > 0:
                return bot.reply(message, "❌ You must repay your existing loan before taking a new one!")
            if amount <= 0 or amount > 5000:
                return bot.reply(message, "❌ The bank only allows loans up to 5,000 coins!")
            u["balance"] += amount
            u["debt"] = int(amount * 1.25)
            database_inst._dirty = True
            bot.reply(message, f"💸 Took a loan of **{amount} coins**! Total debt (with 25% interest): **{u['debt']} coins**. Go lose it all in the casino! 😈")
            
        elif action == "repay":
            if u["debt"] <= 0:
                return bot.reply(message, "🎉 You have no active debt!")
            pay_amt = min(amount if amount > 0 else u["debt"], u["balance"], u["debt"])
            u["balance"] -= pay_amt
            u["debt"] -= pay_amt
            database_inst._dirty = True
            bot.reply(message, f"✅ Repaid **{pay_amt} coins** towards your loan. Remaining debt: **{u['debt']} coins**.")

@bot.command("shop")
def cmd_shop(message):
    bot.reply(message, "🛒 **BLACK MARKET SHOP**\n1. `!buy potion` - Luck Potion (Price: 300 coins) -> Increases crime & gamble success rates!\n\nType `!buy potion` to purchase.")

@bot.command("buy")
def cmd_buy(message, item_name=""):
    uid = str(message.user.pk)
    user = db.get_user(uid, message.user.username)
    
    if item_name.lower() in ["potion", "luck"]:
        cost = 300
        if user["balance"] < cost:
            return bot.reply(message, f"❌ You do not have enough coins! A Luck Potion costs {cost} coins.")
        
        database_inst = db.db if hasattr(db, "db") else db.Database()
        with database_inst._lock:
            u = database_inst._get(uid)
            u["balance"] -= cost
            inv = u.get("inventory", {})
            inv["luck_potion"] = inv.get("luck_potion", 0) + 1
            u["inventory"] = inv
            database_inst._dirty = True
            
        bot.reply(message, f"🧪 You purchased a **Luck Potion**! Total potions: {u['inventory']['luck_potion']}. Use it wisely on your next crime or gamble!")

def run_bot(bot_instance=None):
    b = bot_instance if bot_instance else bot
    b.login()
    b.poll_loop()
