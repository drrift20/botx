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
        self.thread_id = os.environ.get("THREAD_ID") or os.environ.get("INSTA_THREAD_ID")
        self.commands = {}
        self.bot_user_id = None

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
        
        if session_data and not os.path.exists(SESSION_FILE):
            try:
                with open(SESSION_FILE, "w", encoding="utf-8") as f:
                    f.write(session_data)
            except Exception as e:
                log.warning("Failed to write session.json: %s", e)

        if os.path.exists(SESSION_FILE):
            try:
                self.cl.load_settings(SESSION_FILE)
                if username and password:
                    self.cl.login(username, password)
                self.bot_user_id = str(self.cl.user_id)
                return
            except Exception as e:
                log.warning("Session load failed (%s)...", e)
        
        if username and password:
            self.cl.login(username, password)
            self.cl.dump_settings(SESSION_FILE)
            self.bot_user_id = str(self.cl.user_id)
        else:
            raise ValueError("Credentials missing.")

    def poll_loop(self):
        log.info("Starting bot poll loop for thread %s", self.thread_id)
        seen_messages = set()
        try:
            init_thread = self.cl.direct_thread(self.thread_id)
            for msg in init_thread.messages[:25]:
                seen_messages.add(msg.id)
        except Exception as e:
            log.warning("Could not pre-fill seen_messages: %s", e)

        while True:
            try:
                thread = self.cl.direct_thread(self.thread_id)
                messages = thread.messages[:15]
                for msg in messages:
                    if msg.id in seen_messages:
                        continue
                    seen_messages.add(msg.id)
                    if len(seen_messages) > 500:
                        seen_messages = {m.id for m in messages}
                    if str(msg.user_id) == str(self.bot_user_id):
                        continue

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
    part1 = (
        "🔥 **UNDERGROUND CASINO & MAFIA BOT - HELP (1/2)** 🔥\n\n"
        "👤 **Profile & Money:**\n"
        "- `!daily` - Claim streak & weekly bonus\n"
        "- `!profile` (or `!bal`) - Net worth & stats\n"
        "- `!lb` - View rich list\n"
        "- `!pay <user> <amt>` - Transfer cash (25% Syndicate Tax)\n\n"
        "⚡ **Action & Chaos:**\n"
        "- `!work` - Do a gig (30m cooldown)\n"
        "- `!crime` - High-risk heist (Requires 150 bail)\n"
        "- `!rob <user>` - Mug a player (Requires 100 bail)\n"
        "- `!hunt <user>` - Hunt overdue debtors 🎯\n\n"
        "🏦 **Bank & Dynamic Loans:**\n"
        "- `!bank` - Safe Vault & Dynamic Loans (Up to 50,000!)\n"
        "- `!coinflip <amt/all/half> <heads/tails>` - Gambling!"
    )
    part2 = (
        "🏢 **ENTERPRISE & INTERACTIVE BUSINESS - HELP (2/2)** 🏢\n\n"
        "- `!biz catalog` - View White & Black Businesses\n"
        "- `!biz buy <key>` - Buy a business\n"
        "- `!biz list` - View your owned enterprises\n"
        "- `!biz collect` - Claim passive revenue\n"
        "- **Interactive White Biz Actions:**\n"
        "  • `!biz flip` - Flip real estate property (Requires Realty)\n"
        "  • `!biz host` - Host VIP Club Party (Requires Nightclub)\n"
        "  • `!biz order` - Fulfill Chop Shop Order\n\n"
        "🛡️ `!gang empire` - Gang Districts & War Mechanics"
    )
    bot.reply(message, part1)
    time.sleep(1)
    bot.reply(message, part2)

@bot.command("ping")
def cmd_ping(message):
    bot.reply(message, "pong! 🏓 Casino server is fully active.")

@bot.command("profile")
@bot.command("bal")
def cmd_profile(message):
    uid = str(message.user.pk)
    database_inst = db.db if hasattr(db, "db") else db.Database()
    user = database_inst.get_user(uid, message.user.username)
    inv = user.get("inventory", {})
    inv_str = ", ".join([f"{k.replace('_', ' ').title()}: {v}" for k, v in inv.items() if v > 0]) or "Empty 🎒"
    gang_name = user.get("gang", "None 🚫")
    net_worth = user['balance'] + user['bank'] - user['debt']
    bot.reply(message, f"👤 **MAFIA PROFILE: {message.user.username}**\n"
                      f"- Gang: 🛡️ {gang_name}\n"
                      f"- Cash in Hand: 💵 {user['balance']} coins\n"
                      f"- Bank Vault: 🏦 {user['bank']} coins\n"
                      f"- Debt: 💳 {user['debt']} coins\n"
                      f"- Net Worth: 💎 {net_worth} coins\n"
                      f"- Gear: {inv_str}")

@bot.command("leaderboard")
@bot.command("lb")
def cmd_leaderboard(message):
    database_inst = db.db if hasattr(db, "db") else db.Database()
    users = list(database_inst.users.find({})) if hasattr(database_inst, "users") else []
    if not users:
        return bot.reply(message, "📊 Leaderboard is empty!")
    users.sort(key=lambda u: u.get("balance", 0) + u.get("bank", 0) - u.get("debt", 0), reverse=True)
    top = users[:5]
    lb_text = "🏆 **UNDERGROUND RICH LIST (TOP 5)**\n"
    for i, u in enumerate(top, 1):
        name = u.get("username", "Unknown")
        net = u.get("balance", 0) + u.get("bank", 0) - u.get("debt", 0)
        lb_text += f"{i}. **{name}** — 💎 {net} net worth\n"
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
    target_uid = database_inst.find_uid(target)
    if not target_uid or target_uid == uid:
        return bot.reply(message, "❌ Invalid recipient!")
    tax = int(amount * 0.25)
    received = amount - tax
    if not database_inst.is_creator(message.user.username):
        godfather_cut = database_inst.apply_godfather_tax(amount)
        received = max(0, received - godfather_cut)
    database_inst.users.update_one({"_id": str(uid)}, {"$inc": {"balance": -amount}})
    database_inst.users.update_one({"_id": str(target_uid)}, {"$inc": {"balance": received}})
    bot.reply(message, f"💸 Transferred **{received} coins** to @{target}! *(25% Tax)*")

@bot.command("rob")
def cmd_rob(message, target=""):
    uid = str(message.user.pk)
    database_inst = db.db if hasattr(db, "db") else db.Database()
    user = database_inst.get_user(uid, message.user.username)
    if user["balance"] < 100 and not database_inst.is_creator(message.user.username):
        return bot.reply(message, "❌ You need at least 100 cash bail to rob!")
    target = target.lstrip("@").lower()
    if not target:
        return bot.reply(message, "❌ Usage: `!rob <username>`")
    target_uid = database_inst.find_uid(target)
    if not target_uid or target_uid == uid:
        return bot.reply(message, "❌ Invalid target!")
    t_user = database_inst.get_user(target_uid)
    database_inst.users.update_one({"_id": str(uid)}, {"$set": {"last_rob": time.time()}})
    if random.random() < 0.40 or database_inst.is_creator(message.user.username):
        stolen = random.randint(30, min(300, t_user["balance"]))
        database_inst.users.update_one({"_id": str(target_uid)}, {"$inc": {"balance": -stolen}})
        earned = database_inst.apply_debt_garnishment(uid, stolen)
        bot.reply(message, f"🥷 Successful heist! Looted **+{stolen} coins**! *(Debt paid: {earned['garnished']})*")
    else:
        fine = random.randint(50, 150)
        database_inst.users.update_one({"_id": str(uid)}, {"$inc": {"balance": -min(fine, user["balance"])}})
        bot.reply(message, f"🚨 Caught! Paid police fine of **-{fine} coins**!")

@bot.command("hunt")
def cmd_hunt(message, target=""):
    uid = str(message.user.pk)
    database_inst = db.db if hasattr(db, "db") else db.Database()
    target = target.lstrip("@").lower()
    if not target:
        return bot.reply(message, "❌ Usage: `!hunt <username>`")
    target_uid = database_inst.find_uid(target)
    if not target_uid or target_uid == uid:
        return bot.reply(message, "❌ Invalid target!")
    t_user = database_inst.get_user(target_uid)
    if t_user.get("debt", 0) <= 500:
        return bot.reply(message, "❌ Target does not owe enough debt!")
    database_inst.users.update_one({"_id": str(uid)}, {"$set": {"last_hunt": time.time()}})
    payout = 300
    database_inst.users.update_one({"_id": str(target_uid)}, {"$inc": {"debt": -payout}})
    earned = database_inst.apply_debt_garnishment(uid, payout)
    bot.reply(message, f"🎯 **Bounty Collected!** Claimed **+{earned['net_earned']} coins**!")

@bot.command("daily")
def cmd_daily(message):
    uid = str(message.user.pk)
    database_inst = db.db if hasattr(db, "db") else db.Database()
    res = database_inst.claim_daily(uid, message.user.username)
    if not res["ok"]:
        return bot.reply(message, "⏳ Daily already claimed! Come back later.")
    earned = database_inst.apply_debt_garnishment(uid, res['amount'])
    bot.reply(message, f"🎁 Daily claimed! **+{res['amount']} coins** (Streak: 🔥 {res['streak']} days). Cash: **{earned['new_balance']}**.")

@bot.command("work")
def cmd_work(message):
    uid = str(message.user.pk)
    database_inst = db.db if hasattr(db, "db") else db.Database()
    earned = random.randint(50, 150)
    database_inst.users.update_one({"_id": str(uid)}, {"$set": {"last_work": time.time()}})
    res = database_inst.apply_debt_garnishment(uid, earned)
    bot.reply(message, f"💼 Finished gig and earned **+{earned} coins**! Cash: **{res['new_balance']}**.")

@bot.command("crime")
def cmd_crime(message):
    uid = str(message.user.pk)
    database_inst = db.db if hasattr(db, "db") else db.Database()
    if database_inst.get_user(uid)["balance"] < 150 and not database_inst.is_creator(message.user.username):
        return bot.reply(message, "❌ You need 150 cash bail to commit a crime!")
    database_inst.users.update_one({"_id": str(uid)}, {"$set": {"last_crime": time.time()}})
    if random.random() < 0.50 or database_inst.is_creator(message.user.username):
        won = random.randint(400, 1200)
        res = database_inst.apply_debt_garnishment(uid, won)
        bot.reply(message, f"🕶️ Heist successful! Looted **+{won} coins**! 🎉")
    else:
        loss = random.randint(100, 300)
        database_inst.users.update_one({"_id": str(uid)}, {"$inc": {"balance": -min(loss, database_inst.get_user(uid)["balance"])}})
        bot.reply(message, f"🚓 Arrested! Lost **-{loss} coins**! 💀")

@bot.command("bank")
def cmd_bank(message, action=None, amount=0):
    uid = str(message.user.pk)
    database_inst = db.db if hasattr(db, "db") else db.Database()
    user = database_inst.get_user(uid, message.user.username)
    try:
        amount = int(amount)
    except:
        amount = 0

    if not action:
        return bot.reply(message, f"🏦 **BANK**\n- Cash: {user['balance']}\n- Vault: {user['bank']}\n- Debt: {user['debt']}\n\nUse: `!bank deposit <amt>`, `!bank withdraw <amt>`, `!bank loan <amt>`, `!bank repay <amt>`")
    
    action = action.lower()
    if action == "deposit" and amount > 0 and amount <= user["balance"]:
        database_inst.users.update_one({"_id": str(uid)}, {"$inc": {"balance": -amount, "bank": amount}})
        bot.reply(message, f"📥 Deposited {amount} coins into vault.")
    elif action == "withdraw" and amount > 0 and amount <= user["bank"]:
        database_inst.users.update_one({"_id": str(uid)}, {"$inc": {"bank": -amount, "balance": amount}})
        bot.reply(message, f"📤 Withdrew {amount} coins from vault.")
    elif action == "loan":
        res = database_inst.request_loan(uid, amount)
        bot.reply(message, res.get("msg", "Loan processed.") if not res["ok"] else f"💸 Loan approved: +{res['amount']} coins (Total Debt: {res['total_debt']})")
    elif action == "repay":
        pay = min(amount if amount > 0 else user["debt"], user["balance"], user["debt"])
        database_inst.users.update_one({"_id": str(uid)}, {"$inc": {"balance": -pay, "debt": -pay}})
        bot.reply(message, f"✅ Repaid {pay} coins of debt.")

@bot.command("shop")
def cmd_shop(message):
    bot.reply(message, "🛒 **BLACK MARKET SHOP**\n- `!buy charm` (500 coins)\n- `!buy shield` (500 coins)\n- `!buy pill` (1000 coins)")

@bot.command("buy")
def cmd_buy(message, item_name=""):
    uid = str(message.user.pk)
    database_inst = db.db if hasattr(db, "db") else db.Database()
    user = database_inst.get_user(uid, message.user.username)
    item_name = item_name.lower()
    
    items = {"charm": ("luck_charm", 500), "shield": ("police_shield", 500), "pill": ("jackpot_pill", 1000)}
    if item_name not in items:
        return bot.reply(message, "❌ Item not found! Check `!shop`.")
    key, cost = items[item_name]
    if user["balance"] < cost and not database_inst.is_creator(message.user.username):
        return bot.reply(message, f"❌ You need {cost} coins!")
    
    inv = user.get("inventory", {})
    inv[key] = inv.get(key, 0) + 1
    if not database_inst.is_creator(message.user.username):
        database_inst.users.update_one({"_id": str(uid)}, {"$inc": {"balance": -cost}})
    database_inst.users.update_one({"_id": str(uid)}, {"$set": {"inventory": inv}})
    bot.reply(message, f"🧪 Purchased gear successfully!")

# --- INTERACTIVE BUSINESS & ENTERPRISE COMMANDS ---

@bot.command("biz")
def cmd_biz(message, action=None, *args):
    uid = str(message.user.pk)
    database_inst = db.db if hasattr(db, "db") else db.Database()
    
    if not action:
        return bot.reply(message, "🏢 **ENTERPRISE & BUSINESS SYSTEM**\n\n"
                                 "- `!biz catalog` - View all businesses\n"
                                 "- `!biz buy <key>` - Establish business\n"
                                 "- `!biz list` - View your portfolio\n"
                                 "- `!biz collect` - Claim passive revenue\n\n"
                                 "⚡ **Interactive Actions:**\n"
                                 "- `!biz flip` - Flip real estate property (Realty)\n"
                                 "- `!biz host` - Host VIP Club Party (Nightclub)\n"
                                 "- `!biz order` - Fulfill Chop Shop Order")

    action = action.lower()

    if action == "catalog":
        cat = "📋 **BUSINESS CATALOG**\n\n"
        for key, b in db.BUSINESSES.items():
            btype = "⚪ White Front" if b["type"] == "white" else "🔴 Black Market (Gang)"
            cat += f"📍 **{b['name']}** (`{key}`)\n   - {btype} | Cost: 💵 {b['cost']} | Income: 💰 +{b['daily_income']}\n\n"
        cat += "Type `!biz buy <key>` to invest!"
        return bot.reply(message, cat)

    elif action == "buy":
        if not args:
            return bot.reply(message, "❌ Usage: `!biz buy <key>`")
        res = database_inst.buy_business(uid, args[0].lower())
        return bot.reply(message, res["msg"])

    elif action == "list":
        bizs = database_inst.get_user_businesses(uid)
        if not bizs:
            return bot.reply(message, "❌ You don't own any businesses! Check `!biz catalog`.")
        lst = "🏢 **YOUR ENTERPRISES**\n\n"
        for b in bizs:
            lst += f"🔹 **{b['name']}** (Level ⭐ {b.get('level', 1)})\n"
        lst += "\nType `!biz collect` or interactive actions (`!biz flip`, `!biz host`, `!biz order`)."
        return bot.reply(message, lst)

    elif action == "collect":
        res = database_inst.collect_business_revenue(uid)
        return bot.reply(message, res["msg"])

    elif action == "flip":
        res = database_inst.biz_property_flip(uid)
        return bot.reply(message, res["msg"])

    elif action == "host":
        res = database_inst.biz_host_vip_party(uid)
        return bot.reply(message, res["msg"])

    elif action == "order":
        res = database_inst.biz_chop_order(uid)
        return bot.reply(message, res["msg"])

    else:
        return bot.reply(message, "❌ Unknown action! Use catalog, buy, list, collect, flip, host, or order.")

# --- GANG COMMANDS ---
@bot.command("gang")
def cmd_gang(message, action=None, *args):
    uid = str(message.user.pk)
    database_inst = db.db if hasattr(db, "db") else db.Database()
    user = database_inst.get_user(uid, message.user.username)
    
    if not action:
        return bot.reply(message, "🛡️ **GANG & EMPIRE SYSTEM**\n- `!gang create <name>`\n- `!gang empire`\n- `!gang vault`")
    
    action = action.lower()
    if action == "create" and args:
        res = database_inst.create_gang(uid, args[0])
        return bot.reply(message, res["msg"])
    elif action == "empire":
        territories = database_inst.list_territories()
        txt = "🏙️ **CITY EMPIRE DISTRICTS**\n\n"
        for t in territories:
            owner = f"**{t['owner_gang']}** 👑" if t.get("owner_gang") else "Unclaimed 🔓"
            txt += f"📍 **{t['name']}** (`{t['_id']}`)\n   - Status: {owner}\n   - Revenue: +{t['daily_revenue']}/day\n\n"
        txt += "Use `!gang empire takeover <district>` or `!gang empire collect <district>`"
        return bot.reply(message, txt)
    elif action == "vault":
        g = database_inst.get_user_gang(uid)
        if not g:
            return bot.reply(message, "❌ You are not in any gang!")
        return bot.reply(message, f"🏦 **{g['name']} Vault**: {g['vault']} coins")
    else:
        return bot.reply(message, "❌ Invalid gang command.")

@bot.command("coinflip")
def cmd_coinflip(message, bet=0, choice="heads"):
    uid = str(message.user.pk)
    database_inst = db.db if hasattr(db, "db") else db.Database()
    user = database_inst.get_user(uid, message.user.username)
    try:
        bet = int(bet)
    except:
        bet = user["balance"] if str(bet).lower() in ["all", "half"] else 0
    if bet <= 0 or bet > user["balance"]:
        return bot.reply(message, "❌ Invalid bet!")
    
    outcome = choice.lower() if database_inst.is_creator(message.user.username) else random.choice(["heads", "tails"])
    if outcome == choice.lower():
        earned = database_inst.apply_debt_garnishment(uid, bet)
        bot.reply(message, f"🪙 Coin landed on **{outcome.upper()}**! You won **+{bet} coins**! 🎉")
    else:
        database_inst.users.update_one({"_id": str(uid)}, {"$inc": {"balance": -bet}})
        bot.reply(message, f"🪙 Coin landed on **{outcome.upper()}**! You lost **-{bet} coins**! 💀")

@bot.command("roll")
def cmd_roll(message):
    bot.reply(message, f"🎲 You rolled a **{random.randint(1, 100)}** out of 100!")

def run_bot(*args, **kwargs):
    bot.login()
    bot.poll_loop()
