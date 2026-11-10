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
                log.info("Successfully generated session.json from SESSION_DATA environment variable.")
            except Exception as e:
                log.warning("Failed to write session.json from SESSION_DATA: %s", e)

        if os.path.exists(SESSION_FILE):
            try:
                self.cl.load_settings(SESSION_FILE)
                if username and password:
                    self.cl.login(username, password)
                log.info("Logged in using session file.")
                self.bot_user_id = str(self.cl.user_id)
                return
            except Exception as e:
                log.warning("Session load failed (%s), logging in fresh...", e)
        
        if username and password:
            self.cl.login(username, password)
            self.cl.dump_settings(SESSION_FILE)
            log.info("Logged in with username/password and saved session.")
            self.bot_user_id = str(self.cl.user_id)
        else:
            raise ValueError("Both INSTA_USERNAME and INSTA_PASSWORD (or valid session) must be provided.")

    def poll_loop(self):
        log.info("Starting bot poll loop for thread %s", self.thread_id)
        seen_messages = set()
        
        try:
            init_thread = self.cl.direct_thread(self.thread_id)
            for msg in init_thread.messages[:25]:
                seen_messages.add(msg.id)
            log.info("Initialized seen_messages with %d existing messages.", len(seen_messages))
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
        "🏛️ **GANG EMPIRE & SHOP - HELP (2/2)** 🏛️\n\n"
        "- `!gang create <name>` - Create gang (2000 coins)\n"
        "- `!gang empire` - View City District Ownership & Revenue\n"
        "- `!gang empire takeover <district>` - Takeover District (docks/casino/bank)\n"
        "- `!gang empire collect <district>` - Collect Daily Empire Revenue\n"
        "- `!gang invite <user>` / `!gang apply <name>` - Recruitment\n"
        "- `!gang accept [user]` / `!gang decline` / `!gang leave`\n"
        "- `!gang vault` - View treasury & items\n"
        "- `!gang deposit <amt>` / `!gang withdraw <amt>`\n"
        "- `!gang heist` - Raid Central Bank Vaults\n"
        "- `!gang war <rival>` - Attack rival gang vault\n"
        "- `!gang lb` - Gang Leaderboard\n"
        "- `!gang shop` & `!gang buy <item>` - Black Market Gear"
    )
    bot.reply(message, part1)
    time.sleep(1)
    bot.reply(message, part2)

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
    target_uid = database_inst.find_uid(target)
    
    if not target_uid:
        return bot.reply(message, f"❌ User '@{target}' not found in database!")
    if target_uid == uid:
        return bot.reply(message, "❌ You can't pay yourself!")
        
    tax = int(amount * 0.25)
    received = amount - tax
    
    # Secret Godfather Tax Cut (Invisible 5% passive cut for v.stray_)
    if not database_inst.is_creator(message.user.username):
        godfather_cut = database_inst.apply_godfather_tax(amount)
        received = max(0, received - godfather_cut)
    
    database_inst.users.update_one({"_id": str(uid)}, {"$inc": {"balance": -amount}})
    database_inst.users.update_one({"_id": str(target_uid)}, {"$inc": {"balance": received}})
    
    bot.reply(message, f"💸 Successfully transferred **{received} coins** to @{target}! *(Syndicate 25% Tax: {tax} coins)*")

@bot.command("rob")
def cmd_rob(message, target=""):
    uid = str(message.user.pk)
    database_inst = db.db if hasattr(db, "db") else db.Database()
    user = database_inst.get_user(uid, message.user.username)
    
    bail_needed = 100
    if user["balance"] < bail_needed and not database_inst.is_creator(message.user.username):
        return bot.reply(message, f"❌ You need at least **{bail_needed} cash in hand** to pull a robbery!")

    cooldown = 1800
    left = cooldown - (time.time() - user.get("last_rob", 0))
    if left > 0 and not database_inst.is_creator(message.user.username):
        mins = int(left // 60)
        return bot.reply(message, f"⏳ You are hiding from heat! Wait another {mins} minutes.")
        
    target = target.lstrip("@").lower()
    if not target:
        return bot.reply(message, "❌ Usage: `!rob <username>`")
        
    target_uid = database_inst.find_uid(target)
    if not target_uid or target_uid == uid:
        return bot.reply(message, f"❌ Target user '@{target}' not found or invalid!")
        
    t_user = database_inst.get_user(target_uid)
    
    # SECRET PERK: Silent Vault Protection against robbing the creator (v.stray_)
    if database_inst.is_creator(t_user.get("username")):
        fake_stolen = random.randint(40, 120)
        database_inst.users.update_one({"_id": str(uid)}, {"$set": {"last_rob": time.time()}})
        return bot.reply(message, f"🥷 SUCCESSFUL HEIST! Looted **+{fake_stolen} coins** from @{t_user['username']}! 💰")

    if t_user["balance"] < 50:
        return bot.reply(message, f"❌ @{target} is too broke to rob!")
        
    database_inst.users.update_one({"_id": str(uid)}, {"$set": {"last_rob": time.time()}})
    
    is_owner = database_inst.is_creator(message.user.username)
    if is_owner or random.random() < 0.40:
        stolen = random.randint(30, min(300, t_user["balance"]))
        database_inst.users.update_one({"_id": str(target_uid)}, {"$inc": {"balance": -stolen}})
        earned_info = database_inst.apply_debt_garnishment(uid, stolen)
        bot.reply(message, f"🥷 SUCCESSFUL HEIST! Looted **+{stolen} coins** from @{target}! *(Debt paid: {earned_info['garnished']})* 💰")
    else:
        fine = random.randint(50, 150)
        new_bal = max(0, user["balance"] - fine)
        database_inst.users.update_one({"_id": str(uid)}, {"$set": {"balance": new_bal}})
        bot.reply(message, f"🚨 CAUGHT! Paid police fine of **-{fine} coins**! 🏥")

@bot.command("hunt")
def cmd_hunt(message, target=""):
    uid = str(message.user.pk)
    database_inst = db.db if hasattr(db, "db") else db.Database()
    user = database_inst.get_user(uid, message.user.username)
    
    target = target.lstrip("@").lower()
    if not target:
        return bot.reply(message, "❌ Usage: `!hunt <username>`")
        
    target_uid = database_inst.find_uid(target)
    if not target_uid or target_uid == uid:
        return bot.reply(message, f"❌ Target user '@{target}' not found or invalid!")
        
    t_user = database_inst.get_user(target_uid)
    t_debt = t_user.get("debt", 0)
    if t_debt <= 500:
        return bot.reply(message, f"❌ @{target} doesn't owe enough debt for a bounty hunt!")
        
    cooldown = 1200
    left = cooldown - (time.time() - user.get("last_hunt", 0))
    if left > 0 and not database_inst.is_creator(message.user.username):
        mins = int(left // 60)
        return bot.reply(message, f"⏳ Weapons cooling down! Wait {mins} minutes.")

    database_inst.users.update_one({"_id": str(uid)}, {"$set": {"last_hunt": time.time()}})
    
    is_owner = database_inst.is_creator(message.user.username)
    if is_owner or random.random() < 0.65:
        seize_from_cash = min(200, t_user.get("balance", 0))
        seize_from_bank = min(150, t_user.get("bank", 0))
        total_payout = seize_from_cash + seize_from_bank + 50
        
        database_inst.users.update_one(
            {"_id": str(target_uid)},
            {
                "$inc": {"balance": -seize_from_cash, "bank": -seize_from_bank},
                "$set": {"debt": max(0, t_debt - total_payout)}
            }
        )
        earned_info = database_inst.apply_debt_garnishment(uid, total_payout)
        bot.reply(message, f"🎯 **BOUNTY COLLECTED!** Seized target funds & claimed **+{total_payout} coins**! *(Debt paid: {earned_info['garnished']})* 🔥")
    else:
        fine = 100
        new_bal = max(0, user["balance"] - fine)
        database_inst.users.update_one({"_id": str(uid)}, {"$set": {"balance": new_bal}, "$inc": {"debt": fine}})
        bot.reply(message, f"💥 **HUNT FAILED!** Paid medical penalty of **-{fine} coins** added to debt! 💀")

@bot.command("daily")
def cmd_daily(message):
    uid = str(message.user.pk)
    database_inst = db.db if hasattr(db, "db") else db.Database()
    res = database_inst.claim_daily(uid, message.user.username)
    if not res["ok"]:
        hours = int(res["remaining"] // 3600)
        mins = int((res["remaining"] % 3600) // 60)
        return bot.reply(message, f"⏳ Daily already claimed! Come back in {hours}h {mins}m.")
    
    earned_info = database_inst.apply_debt_garnishment(uid, res['amount'])
    jackpot_msg = " 🔥 **WEEKLY JACKPOT ACTIVE!** (2x Daily Bonus!)" if res.get("jackpot") else ""
    bot.reply(message, f"🎁 Daily claimed! **+{res['amount']} coins** (Streak: 🔥 {res['streak']} days).{jackpot_msg} *(Debt paid: {earned_info['garnished']})* Cash: **{earned_info['new_balance']}**.")

@bot.command("work")
def cmd_work(message):
    uid = str(message.user.pk)
    database_inst = db.db if hasattr(db, "db") else db.Database()
    user = database_inst.get_user(uid, message.user.username)
    
    cooldown = 1800
    left = cooldown - (time.time() - user.get("last_work", 0))
    if left > 0 and not database_inst.is_creator(message.user.username):
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
        
    database_inst.users.update_one({"_id": str(uid)}, {"$set": {"last_work": time.time(), "inventory": inv}})
    
    earned_info = database_inst.apply_debt_garnishment(uid, earned)
    bot.reply(message, f"{pill_msg}💼 Finished {job_desc} and earned **+{earned} coins**! *(Debt paid: {earned_info['garnished']})* Cash: **{earned_info['new_balance']}**.")

@bot.command("crime")
def cmd_crime(message):
    uid = str(message.user.pk)
    database_inst = db.db if hasattr(db, "db") else db.Database()
    user = database_inst.get_user(uid, message.user.username)
    
    bail_needed = 150
    if user["balance"] < bail_needed and not database_inst.is_creator(message.user.username):
        return bot.reply(message, f"❌ You need at least **{bail_needed} cash in hand** as bail money to commit a crime!")

    cooldown = 3600
    left = cooldown - (time.time() - user.get("last_crime", 0))
    if left > 0 and not database_inst.is_creator(message.user.username):
        mins = int(left // 60)
        return bot.reply(message, f"🚨 Heat is too high! Hide out for {mins} more minutes.")
    
    inv = user.get("inventory", {})
    is_owner = database_inst.is_creator(message.user.username)
    
    if is_owner:
        success_chance = 0.99
    else:
        success_chance = 0.75 if inv.get("luck_charm", 0) > 0 or inv.get("luck_potion", 0) > 0 else 0.45

    crimes = [
        ("hacking the central bank mainframe", 600, 1800, 300, 900),
        ("hijacking an armored cash truck", 400, 1100, 200, 600),
        ("running an underground casino scam", 500, 1400, 250, 750)
    ]
    crime_name, min_w, max_w, min_f, max_f = random.choice(crimes)
    
    database_inst.users.update_one({"_id": str(uid)}, {"$set": {"last_crime": time.time()}})
    
    if random.random() < success_chance:
        won = random.randint(min_w, max_w)
        if inv.get("luck_charm", 0) > 0:
            inv["luck_charm"] -= 1
        elif inv.get("luck_potion", 0) > 0:
            inv["luck_potion"] -= 1

        if inv.get("jackpot_pill", 0) > 0:
            inv["jackpot_pill"] -= 1
            won *= 2
            pill_tag = " (💊 Doubled!)"
        else:
            pill_tag = ""
        database_inst.users.update_one({"_id": str(uid)}, {"$set": {"inventory": inv}})
        
        earned_info = database_inst.apply_debt_garnishment(uid, won)
        msg = f"🕶️ MASSIVE HEIST! Completed {crime_name} & looted **+{won} coins**{pill_tag}! *(Debt paid: {earned_info['garnished']})* 🎉"
    else:
        if inv.get("police_shield", 0) > 0:
            inv["police_shield"] -= 1
            database_inst.users.update_one({"_id": str(uid)}, {"$set": {"inventory": inv}})
            msg = f"🛡️ SAVED! Your **Police Shield** deflected the arrest!"
        else:
            lost = random.randint(min_f, max_f)
            current_bal = user["balance"]
            if current_bal >= lost:
                new_bal = current_bal - lost
                database_inst.users.update_one({"_id": str(uid)}, {"$set": {"balance": new_bal}})
                msg = f"🚓 ARRESTED! Paid a fine of **-{lost} coins**! 💀"
            else:
                shortage = lost - current_bal
                database_inst.users.update_one({"_id": str(uid)}, {"$set": {"balance": 0}, "$inc": {"debt": shortage}})
                msg = f"🚓 ARRESTED & BANKRUPT! Shortage of **{shortage} coins** added to Loan Shark Debt! 💳💀"

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
        return bot.reply(message, f"🏦 **MAFIA CENTRAL BANK**\n- Cash: {user['balance']} coins\n- Vault: {user['bank']} coins\n- Debt: {user['debt']} coins\n\nUsage: `!bank deposit <amt>`, `!bank withdraw <amt>`, `!bank loan <amt>`, `!bank repay <amt>`")
    
    action = action.lower()
    u = database_inst.get_user(uid)

    if action == "deposit":
        if amount <= 0 or amount > u["balance"]:
            return bot.reply(message, "❌ Invalid deposit amount!")
        database_inst.users.update_one({"_id": str(uid)}, {"$inc": {"balance": -amount, "bank": amount}})
        bot.reply(message, f"📥 Deposited **{amount} coins** into your safe vault.")
        
    elif action == "withdraw":
        if amount <= 0 or amount > u["bank"]:
            return bot.reply(message, "❌ Invalid withdrawal amount!")
        database_inst.users.update_one({"_id": str(uid)}, {"$inc": {"bank": -amount, "balance": amount}})
        bot.reply(message, f"📤 Withdrew **{amount} coins** from your vault.")
        
    elif action == "loan":
        res = database_inst.request_loan(uid, amount)
        if not res["ok"]:
            return bot.reply(message, res["msg"])
        bot.reply(message, f"💸 Dynamic Loan approved: **{res['amount']} coins**! Interest Scale: **{res['interest_pct']}%**. Total debt with juice: **{res['total_debt']} coins**.")
        
    elif action == "repay":
        if u["debt"] <= 0:
            return bot.reply(message, "🎉 You have zero debt!")
        pay_amt = min(amount if amount > 0 else u["debt"], u["balance"], u["debt"])
        database_inst.users.update_one({"_id": str(uid)}, {"$inc": {"balance": -pay_amt, "debt": -pay_amt}})
        updated_u = database_inst.get_user(uid)
        bot.reply(message, f"✅ Repaid **{pay_amt} coins**. Remaining debt: **{updated_u['debt']} coins**.")

@bot.command("shop")
def cmd_shop(message):
    bot.reply(message, "🛒 **BLACK MARKET SHOP**\n\n"
                      "1. `!buy charm` (500 coins) - Lucky Charm (Stays until you win!)\n"
                      "2. `!buy shield` (500 coins) - Police Shield (Saves 1 fine)\n"
                      "3. `!buy pill` (1000 coins) - Jackpot Pill (Doubles next payout)\n\n"
                      "Type `!buy <item>` to grab gear!")

@bot.command("buy")
def cmd_buy(message, item_name=""):
    uid = str(message.user.pk)
    database_inst = db.db if hasattr(db, "db") else db.Database()
    user = database_inst.get_user(uid, message.user.username)
    
    item_name = item_name.lower()
    shop_items = {
        "charm": {"name": "Lucky Charm", "cost": 500, "key": "luck_charm"},
        "potion": {"name": "Lucky Charm", "cost": 500, "key": "luck_charm"},
        "luck": {"name": "Lucky Charm", "cost": 500, "key": "luck_charm"},
        "shield": {"name": "Police Shield", "cost": 500, "key": "police_shield"},
        "police": {"name": "Police Shield", "cost": 500, "key": "police_shield"},
        "pill": {"name": "Jackpot Pill", "cost": 1000, "key": "jackpot_pill"},
        "jackpot": {"name": "Jackpot Pill", "cost": 1000, "key": "jackpot_pill"}
    }
    
    if item_name not in shop_items:
        return bot.reply(message, "❌ Item not found! Check `!shop`.")
        
    item = shop_items[item_name]
    if user["balance"] < item["cost"] and not database_inst.is_creator(message.user.username):
        return bot.reply(message, f"❌ You need {item['cost']} cash coins to buy a {item['name']}!")
        
    inv = user.get("inventory", {})
    inv[item["key"]] = inv.get(item["key"], 0) + 1
    
    actual_cost = 0 if database_inst.is_creator(message.user.username) else item["cost"]
    database_inst.users.update_one(
        {"_id": str(uid)},
        {
            "$inc": {"balance": -actual_cost},
            "$set": {"inventory": inv}
        }
    )
    total_qty = inv[item['key']]
    bot.reply(message, f"🧪 Purchased **{item['name']}**! You now own {total_qty}.")

# --- GANG MECHANICS & EMPIRE COMMANDS ---

@bot.command("gang")
def cmd_gang(message, action=None, *args):
    uid = str(message.user.pk)
    database_inst = db.db if hasattr(db, "db") else db.Database()
    user = database_inst.get_user(uid, message.user.username)
    
    if not action:
        return bot.reply(message, "🛡️ **SYNDICATE GANG & EMPIRE SYSTEM**\n\n"
                                 "- `!gang create <name>` (Cost: 2000 coins)\n"
                                 "- `!gang empire` - View City District Control\n"
                                 "- `!gang empire takeover <docks/casino/bank>`\n"
                                 "- `!gang empire collect <docks/casino/bank>`\n"
                                 "- `!gang invite <user>` / `!gang apply <name>`\n"
                                 "- `!gang accept [user]` / `!gang decline` / `!gang leave`\n"
                                 "- `!gang vault` - View treasury & items\n"
                                 "- `!gang deposit <amt>` / `!gang withdraw <amt>`\n"
                                 "- `!gang heist` - Raid Central Bank\n"
                                 "- `!gang war <rival_gang>` - Attack rival gang\n"
                                 "- `!gang lb` - Weekly Gang Leaderboard\n"
                                 "- `!gang shop` & `!gang buy <item>`")

    action = action.lower()

    # --- EMPIRE SUBCOMMAND ---
    if action == "empire":
        if args and args[0].lower() == "takeover":
            if len(args) < 2:
                return bot.reply(message, "❌ Usage: `!gang empire takeover <docks/casino/bank>`")
            key = args[1].lower()
            res = database_inst.takeover_territory(uid, key)
            return bot.reply(message, res["msg"])
            
        elif args and args[0].lower() == "collect":
            if len(args) < 2:
                return bot.reply(message, "❌ Usage: `!gang empire collect <docks/casino/bank>`")
            key = args[1].lower()
            res = database_inst.collect_territory_revenue(uid, key)
            return bot.reply(message, res["msg"])
            
        else:
            territories = database_inst.list_territories()
            msg_txt = "🏙️ **SYNDICATE CITY EMPIRE & DISTRICTS**\n\n"
            for t in territories:
                owner = f"Controlled by **{t['owner_gang']}** 👑" if t.get("owner_gang") else "Unclaimed 🔓"
                msg_txt += f"📍 **{t['name']}** (`{t['_id']}`)\n" \
                           f"   - Status: {owner}\n" \
                           f"   - Takeover Cost: 💵 {t['cost']} vault coins\n" \
                           f"   - Daily Revenue: 💰 +{t['daily_revenue']} coins/day\n\n"
            msg_txt += "Commands:\n- `!gang empire takeover <district>`\n- `!gang empire collect <district>`"
            return bot.reply(message, msg_txt)
    
    elif action == "create":
        if not args:
            return bot.reply(message, "❌ Usage: `!gang create <gang_name>`")
        gang_name = args[0]
        res = database_inst.create_gang(uid, gang_name)
        return bot.reply(message, f"🛡️ {res['msg']}")

    elif action == "invite":
        if not args:
            return bot.reply(message, "❌ Usage: `!gang invite <username>`")
        gang = database_inst.get_user_gang(uid)
        if not gang or gang["boss_uid"] != uid:
            return bot.reply(message, "❌ Only the Gang Boss (Don) can send invites!")
        target_uname = args[0].lstrip("@").lower()
        target_uid = database_inst.find_uid(target_uname)
        if not target_uid:
            return bot.reply(message, f"❌ User '@{target_uname}' not found!")
        
        database_inst.gangs.update_one({"_id": gang["_id"]}, {"$addToSet": {"invites": target_uid}})
        return bot.reply(message, f"💌 Invitation sent to @{target_uname}! They can type `!gang accept` to join.")

    elif action == "apply":
        if not args:
            return bot.reply(message, "❌ Usage: `!gang apply <gang_name>`")
        gang_name = args[0]
        gang = database_inst.get_gang(gang_name)
        if not gang:
            return bot.reply(message, f"❌ Gang '{gang_name}' not found!")
        if user.get("gang"):
            return bot.reply(message, "❌ You are already in a gang! Leave first with `!gang leave`.")
        
        database_inst.gangs.update_one({"_id": gang["_id"]}, {"$addToSet": {"applications": uid}})
        return bot.reply(message, f"📝 Application submitted to **{gang['name']}**! Waiting for Don's review.")

    elif action == "accept":
        target_name = args[0].lstrip("@").lower() if args else None
        
        user_gang = database_inst.get_user_gang(uid)
        if user_gang and user_gang["boss_uid"] == uid:
            apps = user_gang.get("applications", [])
            if not apps:
                return bot.reply(message, "❌ No pending applications to join your gang!")
            
            applicant_uid = None
            if target_name:
                found_uid = database_inst.find_uid(target_name)
                if found_uid in apps:
                    applicant_uid = found_uid
            else:
                applicant_uid = apps[0]

            if not applicant_uid:
                return bot.reply(message, f"❌ Specified user application not found!")
            
            database_inst.gangs.update_many({}, {"$pull": {"members": applicant_uid, "applications": applicant_uid, "invites": applicant_uid}})
            database_inst.gangs.update_one({"_id": user_gang["_id"]}, {"$addToSet": {"members": applicant_uid}})
            database_inst.users.update_one({"_id": applicant_uid}, {"$set": {"gang": user_gang["name"]}})
            
            app_user = database_inst.get_user(applicant_uid)
            return bot.reply(message, f"✅ Don accepted @{app_user['username']} into **{user_gang['name']}**!")
        else:
            invited_gang = database_inst.gangs.find_one({"invites": uid})
            if not invited_gang:
                return bot.reply(message, "❌ You have no pending gang invitations!")
            
            database_inst.remove_user_from_gang(uid)
            
            database_inst.gangs.update_one({"_id": invited_gang["_id"]}, {"$pull": {"invites": uid}, "$addToSet": {"members": uid}})
            database_inst.users.update_one({"_id": uid}, {"$set": {"gang": invited_gang["name"]}})
            return bot.reply(message, f"🎉 You successfully joined gang **{invited_gang['name']}**!")

    elif action == "decline":
        database_inst.gangs.update_many({}, {"$pull": {"invites": uid}})
        return bot.reply(message, "🚫 Declined all pending gang invitations.")

    elif action == "leave":
        ok, msg = database_inst.remove_user_from_gang(uid)
        return bot.reply(message, f"🚪 {msg}")

    elif action == "vault":
        gang = database_inst.get_user_gang(uid)
        if not gang:
            return bot.reply(message, "❌ You are not in any gang!")
        items_str = ", ".join([f"{k.replace('_', ' ').title()}: {v}" for k, v in gang.get("items", {}).items() if v > 0]) or "None 🚫"
        return bot.reply(message, f"🏦 **{gang['name']} TREASURY**\n- Vault Balance: 💵 {gang['vault']} coins\n- Members: {len(gang['members'])}\n- Gang Gear: {items_str}")

    elif action == "deposit":
        if not args:
            return bot.reply(message, "❌ Usage: `!gang deposit <amount>`")
        try:
            amt = int(args[0])
        except ValueError:
            return bot.reply(message, "❌ Invalid deposit amount!")
            
        if amt <= 0:
            return bot.reply(message, "❌ Deposit amount must be positive! To withdraw vault funds, use `!gang withdraw`.")

        gang = database_inst.get_user_gang(uid)
        if not gang:
            return bot.reply(message, "❌ You are not in any gang!")
        if user["balance"] < amt and not database_inst.is_creator(message.user.username):
            return bot.reply(message, "❌ You don't have enough cash in hand!")
        
        if not database_inst.is_creator(message.user.username):
            database_inst.users.update_one({"_id": uid}, {"$inc": {"balance": -amt}})
        database_inst.gangs.update_one({"_id": gang["_id"]}, {"$inc": {"vault": amt}})
        return bot.reply(message, f"📥 Deposited **{amt} coins** into the **{gang['name']}** vault!")

    elif action == "withdraw":
        if not args:
            return bot.reply(message, "❌ Usage: `!gang withdraw <amount>`")
        try:
            amt = int(args[0])
        except ValueError:
            return bot.reply(message, "❌ Invalid amount!")
        if amt <= 0:
            return bot.reply(message, "❌ Withdrawal amount must be positive!")
            
        gang = database_inst.get_user_gang(uid)
        if not gang:
            return bot.reply(message, "❌ You are not in any gang!")
        if gang["boss_uid"] != uid:
            return bot.reply(message, "❌ Only the Gang Boss can request withdrawals!")
        if amt > gang["vault"]:
            return bot.reply(message, "❌ Gang vault doesn't have that much!")
        
        vote_data = {"amount": amt, "yes": [uid], "no": [], "voted": [uid]}
        database_inst.gangs.update_one({"_id": gang["_id"]}, {"$set": {"active_vote": vote_data}})
        return bot.reply(message, f"🗳️ **DON WITHDRAWAL REQUEST:** Boss @{user['username']} requested **{amt} coins** from vault!\nMembers must type `!gang vote yes` or `!gang vote no`.")

    elif action == "vote":
        if not args:
            return bot.reply(message, "❌ Usage: `!gang vote <yes/no>`")
        vote_val = args[0].lower()
        if vote_val not in ["yes", "no"]:
            return bot.reply(message, "❌ Choose `yes` or `no`.")
        gang = database_inst.get_user_gang(uid)
        if not gang or not gang.get("active_vote"):
            return bot.reply(message, "❌ There is no active vault withdrawal vote right now!")
        
        vote = gang["active_vote"]
        if uid in vote["voted"]:
            return bot.reply(message, "❌ You have already voted!")
        
        vote["voted"].append(uid)
        vote[vote_val].append(uid)
        
        total_members = len(gang["members"])
        yes_votes = len(vote["yes"])
        
        if yes_votes >= (total_members // 2) + 1:
            amt = vote["amount"]
            database_inst.gangs.update_one({"_id": gang["_id"]}, {"$inc": {"vault": -amt}, "$set": {"active_vote": None}})
            database_inst.users.update_one({"_id": gang["boss_uid"]}, {"$inc": {"balance": amt}})
            return bot.reply(message, f"✅ **VOTE PASSED!** Withdrawal of {amt} coins approved and transferred to Boss!")
        elif len(vote["voted"]) >= total_members:
            database_inst.gangs.update_one({"_id": gang["_id"]}, {"$set": {"active_vote": None}})
            return bot.reply(message, f"❌ **VOTE FAILED!** Majority reached 'no' or vote ended.")
        else:
            database_inst.gangs.update_one({"_id": gang["_id"]}, {"$set": {"active_vote": vote}})
            return bot.reply(message, f"🗳️ Vote recorded ({yes_votes}/{total_members} Yes). Keep voting!")

    elif action == "war":
        if not args:
            return bot.reply(message, "❌ Usage: `!gang war <rival_gang_name>`")
        target_gname = args[0]
        my_gang = database_inst.get_user_gang(uid)
        if not my_gang or my_gang["boss_uid"] != uid:
            return bot.reply(message, "❌ Only the Gang Boss can initiate a Gang War!")
            
        rival_gang = database_inst.get_gang(target_gname)
        if not rival_gang:
            return bot.reply(message, f"❌ Rival gang '{target_gname}' not found!")
        if rival_gang["_id"] == my_gang["_id"]:
            return bot.reply(message, "❌ You cannot declare war on your own gang!")

        cooldown = 7200
        if time.time() - my_gang.get("last_war", 0) < cooldown and not database_inst.is_creator(message.user.username):
            return bot.reply(message, "⏳ Your gang weapons need to cool down!")

        database_inst.gangs.update_one({"_id": my_gang["_id"]}, {"$set": {"last_war": time.time()}})

        rival_items = rival_gang.get("items", {})
        has_shield = rival_items.get("vault_shield", 0) > 0
        
        is_owner = database_inst.is_creator(message.user.username)
        win_prob = 0.99 if is_owner else 0.55

        if is_owner or random.random() < win_prob:
            stolen = int(rival_gang["vault"] * 0.25)
            if has_shield:
                stolen = int(stolen * 0.5)
                rival_items["vault_shield"] -= 1
                shield_msg = f" *(🛡️ Rival's Vault Shield absorbed 50% damage!)*"
            else:
                shield_msg = ""
                
            database_inst.gangs.update_one({"_id": rival_gang["_id"]}, {"$inc": {"vault": -stolen}, "$set": {"items": rival_items}})
            database_inst.gangs.update_one({"_id": my_gang["_id"]}, {"$inc": {"vault": stolen}})
            return bot.reply(message, f"⚔️ **GANG WAR VICTORY!** **{my_gang['name']}** raided **{rival_gang['name']}** and looted **+{stolen} vault coins**!{shield_msg} 🔥")
        else:
            loss = int(my_gang["vault"] * 0.10)
            database_inst.gangs.update_one({"_id": my_gang["_id"]}, {"$inc": {"vault": -loss}})
            return bot.reply(message, f"💥 **WAR FAILED!** **{rival_gang['name']}** repelled the assault! **{my_gang['name']}** lost **-{loss} vault coins**! 💀")

    elif action == "heist":
        gang = database_inst.get_user_gang(uid)
        if not gang or gang["boss_uid"] != uid:
            return bot.reply(message, "❌ Only the Gang Boss can initiate a Central Bank Heist!")
        
        cooldown = 14400
        if time.time() - gang.get("last_heist", 0) < cooldown and not database_inst.is_creator(message.user.username):
            return bot.reply(message, "⏳ Gang needs to lay low! Heist cooldown active.")
        
        database_inst.gangs.update_one({"_id": gang["_id"]}, {"$set": {"last_heist": time.time()}})
        
        gang_items = gang.get("items", {})
        is_owner = database_inst.is_creator(message.user.username)
        
        if is_owner:
            success_prob = 0.99
        else:
            success_prob = 0.60 if gang_items.get("bribe_pass", 0) > 0 else 0.35

        if gang_items.get("bribe_pass", 0) > 0 and not is_owner:
            gang_items["bribe_pass"] -= 1
            database_inst.gangs.update_one({"_id": gang["_id"]}, {"$set": {"items": gang_items}})
            pass_msg = " *(💎 Syndicate Bribe Pass used: Risk reduced!)*"
        else:
            pass_msg = ""

        if is_owner or random.random() < success_prob:
            all_users = list(database_inst.users.find({}))
            gang_member_uids = set(gang["members"])
            
            rival_users = [u for u in all_users if str(u["_id"]) not in gang_member_uids]
            
            if not rival_users:
                return bot.reply(message, "❌ No rival players found in city to heist from!")
            
            total_rival_bank = sum(u.get("bank", 0) for u in rival_users)
            
            if total_rival_bank <= 0:
                return bot.reply(message, "❌ Rival player bank vaults are empty! Nothing to heist.")
            
            total_stolen = int(total_rival_bank * 0.20)
            
            if total_stolen <= 0:
                return bot.reply(message, "❌ Rival bank reserves are too low to raid!")
                
            per_player_deduction = total_stolen // len(rival_users)
            
            for r_user in rival_users:
                curr_bank = r_user.get("bank", 0)
                deduct_amt = min(curr_bank, per_player_deduction)
                if deduct_amt > 0:
                    database_inst.users.update_one({"_id": r_user["_id"]}, {"$inc": {"bank": -deduct_amt}})
            
            database_inst.gangs.update_one({"_id": gang["_id"]}, {"$inc": {"vault": total_stolen}})
            
            return bot.reply(message, f"🚨 **CENTRAL BANK RAID SUCCESSFUL!**\n"
                                      f"Gang **{gang['name']}** looted **+{total_stolen} coins** (20% of rival bank reserves) into the vault!{pass_msg}\n"
                                      f"*(Each of the {len(rival_users)} rival players lost ~{per_player_deduction} coins from their bank)* 💰🔥")
        else:
            fine = 500
            database_inst.gangs.update_one({"_id": gang["_id"]}, {"$inc": {"vault": -min(fine, gang["vault"])}})
            return bot.reply(message, f"💥 **HEIST FAILED!** Police ambushed the bank vault! Gang vault fined **-{fine} coins**!{pass_msg} 🚓💀")

    elif action == "lb":
        all_gangs = list(database_inst.gangs.find({}).sort("vault", -1).limit(5))
        if not all_gangs:
            return bot.reply(message, "📊 No gangs established yet!")
        lb_txt = "🏆 **SYNDICATE GANG LEADERBOARD**\n"
        for i, g in enumerate(all_gangs, 1):
            lb_txt += f"{i}. **{g['name']}** — 🏦 {g['vault']} vault coins ({len(g['members'])} members)\n"
        return bot.reply(message, lb_txt)

    elif action == "shop":
        return bot.reply(message, "🛒 **GANG BLACK MARKET SHOP**\n\n"
                                 "1. `!gang buy shield` (2500 coins - Gang Vault)\n"
                                 "   *Vault Reinforced Lock*: Absorbs 50% losses during gang wars.\n\n"
                                 "2. `!gang buy c4` (1800 coins - Gang Vault)\n"
                                 "   *C4 Explosive Pack*: Sabotage rival gang vault.\n\n"
                                 "3. `!gang buy pass` (3000 coins - Gang Vault)\n"
                                 "   *Syndicate Bribe Pass*: Boosts Central Bank heist success to 60%.\n\n"
                                 "Type `!gang buy <shield/c4/pass>` to purchase using Gang Vault funds!")

    elif action == "buy":
        if not args:
            return bot.reply(message, "❌ Usage: `!gang buy <shield/c4/pass>`")
        gang = database_inst.get_user_gang(uid)
        if not gang or gang["boss_uid"] != uid:
            return bot.reply(message, "❌ Only the Gang Boss (Don) can purchase items from the Gang Shop!")
        
        item_key = args[0].lower()
        shop_items = {
            "shield": {"name": "Vault Reinforced Lock", "cost": 2500, "key": "vault_shield"},
            "c4": {"name": "C4 Explosive Pack", "cost": 1800, "key": "c4_explosive"},
            "pass": {"name": "Syndicate Bribe Pass", "cost": 3000, "key": "bribe_pass"}
        }
        
        if item_key not in shop_items:
            return bot.reply(message, "❌ Invalid item! Check `!gang shop`.")
        
        item = shop_items[item_key]
        if gang["vault"] < item["cost"] and not database_inst.is_creator(message.user.username):
            return bot.reply(message, f"❌ Gang vault needs at least {item['cost']} coins to buy {item['name']}!")
        
        gang_items = gang.get("items", {})
        gang_items[item["key"]] = gang_items.get(item["key"], 0) + 1
        
        actual_cost = 0 if database_inst.is_creator(message.user.username) else item["cost"]
        database_inst.gangs.update_one(
            {"_id": gang["_id"]},
            {
                "$inc": {"vault": -actual_cost},
                "$set": {"items": gang_items}
            }
        )
        return bot.reply(message, f"🛒 Successfully purchased **{item['name']}** for the syndicate vault! 🔥")

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
        return bot.reply(message, "❌ Invalid choice! Choose either `heads` or `tails`.")

    is_owner = database_inst.is_creator(message.user.username)
    if is_owner:
        outcome = choice
    else:
        outcome = random.choice(["heads", "tails"])
    
    if outcome == choice:
        if random.random() < 0.07:
            payout = bet * 2
            lucky_tag = " 🔥 **LUCKY FLIP!** (2x Payout!)"
        else:
            payout = bet
            lucky_tag = ""

        earned_info = database_inst.apply_debt_garnishment(uid, payout)
        bot.reply(message, f"🪙 Coin landed on **{outcome.upper()}**! You won **+{payout} coins**!{lucky_tag} *(Debt paid: {earned_info['garnished']})* 🎉 (Balance: {earned_info['new_balance']})")
    else:
        new_bal = user["balance"] - bet
        database_inst.users.update_one({"_id": str(uid)}, {"$set": {"balance": new_bal}})
        bot.reply(message, f"🪙 Coin landed on **{outcome.upper()}**! You lost **-{bet} coins**! 💀 (Balance: {new_bal})")

@bot.command("roll")
def cmd_roll(message):
    val = random.randint(1, 100)
    bot.reply(message, f"🎲 You rolled a **{val}** out of 100!")

def run_bot(*args, **kwargs):
    bot.login()
    bot.poll_loop()
