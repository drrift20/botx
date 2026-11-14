"""
Instagram Economy Bot - Command Router & Message Loop.
Version 8: Fully restored commands for dueling, fighting, and gang ownership transfer/leaving.
"""
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
        self.thread_id = os.environ.get("THREAD_ID") or os.environ.get("INSTA_THREAD_ID")
        self.commands = {}
        self.bot_user_id = None
        self.username_cache = {}

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
                with open(SESSION_FILE, "w", encoding="utf-8") as f: f.write(session_data)
            except Exception as e: log.warning("Failed to write session.json: %s", e)

        if os.path.exists(SESSION_FILE):
            try:
                self.cl.load_settings(SESSION_FILE)
                if username and password: self.cl.login(username, password)
                self.bot_user_id = str(self.cl.user_id)
                return
            except Exception as e: log.warning("Session load failed (%s)...", e)
        
        if username and password:
            self.cl.login(username, password)
            self.cl.dump_settings(SESSION_FILE)
            self.bot_user_id = str(self.cl.user_id)
        else:
            raise ValueError("INSTA_USERNAME and INSTA_PASSWORD required.")

    def get_username(self, user_pk):
        if user_pk in self.username_cache: return self.username_cache[user_pk]
        try:
            u_info = self.cl.user_info(int(user_pk))
            uname = u_info.username
            self.username_cache[user_pk] = uname
            return uname
        except Exception:
            return f"user_{user_pk[-4:]}"

    def poll_loop(self):
        log.info("Starting bot poll loop for thread %s", self.thread_id)
        seen_messages = set()
        try:
            for msg in self.cl.direct_thread(self.thread_id).messages[:25]:
                seen_messages.add(msg.id)
        except Exception as e: log.warning("Could not pre-fill seen messages: %s", e)

        while True:
            try:
                thread = self.cl.direct_thread(self.thread_id)
                for msg in thread.messages[:15]:
                    if msg.id in seen_messages: continue
                    seen_messages.add(msg.id)
                    if len(seen_messages) > 500: seen_messages = {m.id for m in thread.messages[:15]}
                    if str(msg.user_id) == str(self.bot_user_id): continue

                    text = msg.text
                    if text and text.startswith("!"):
                        parts = text[1:].strip().split()
                        if not parts: continue
                        cmd = parts[0].lower()
                        args = parts[1:]
                        
                        if cmd in self.commands:
                            class MockUser:
                                def __init__(self, pk, username): self.pk = pk; self.username = username
                            class MockMessage:
                                def __init__(self, user, text, args): self.user = user; self.text = text; self.args = args

                            uid = str(msg.user_id)
                            uname = self.get_username(uid)
                            mock_msg = MockMessage(MockUser(uid, uname), text, args)

                            try:
                                db_inst = db.db if hasattr(db, "db") else db.Database()
                                
                                tax = db_inst.check_and_apply_irs_tax(uid)
                                if tax.get("audited"):
                                    self.reply(mock_msg, f"🏛️ **ROBIN HOOD TAX:** Deducted -{tax['tax']} coins from @{uname}'s bank.")
                                    time.sleep(1)

                                draw = db_inst.check_and_draw_lottery()
                                if draw.get("drawn") and draw.get("msg"):
                                    self.reply(mock_msg, draw["msg"])
                                    time.sleep(1)

                                self.commands[cmd](mock_msg, *args) if args else self.commands[cmd](mock_msg)
                            except Exception as e: log.error("Error executing %s: %s", cmd, e)
            except Exception as e: log.error("Polling error: %s", e)
            time.sleep(5)

bot = InstagramBot()

# --- COMMANDS ---

@bot.command("help")
def cmd_help(message):
    bot.reply(message, "🔥 **MAFIA RPG ECOSYSTEM (1/3)** 🔥\n- `!daily` | `!profile` (or `!bal`) | `!wanted` | `!welfare`\n- `!lb` | `!coinflip <amt> <side>` | `!slots <amt>` | `!duel <user> <bet>` | `!fight <user>`")
    time.sleep(1)
    bot.reply(message, "💎 **POLICE & PACTS (2/3)** 💎\n- `!police join` / `!police leave` | `!arrest <user>` | `!bribe <amt>`\n- `!pact <user>` / `!pact accept` / `!betray`\n- `!extort <user>` | `!smuggle <low/med/high>` | `!bounty <user> <amt>` | `!bounties`")
    time.sleep(1)
    bot.reply(message, "🏛️ **ENTERPRISE & GANGS (3/3)** 🏛️\n- `!shop` / `!buy <item>` / `!buy luxury <key>` / `!flex`\n- `!biz catalog` / `!biz buy <key>` / `!biz close <key>` / `!biz list` / `!biz collect`\n- `!gang create <name>` / `!gang invite <user>` / `!gang accept` / `!gang leave` / `!gang transfer <user>`\n- `!gang empire` / `!gang takeover <district>` / `!gang collect <district>`\n- `!gang upgrade` / `!gang vault` / `!gang deposit <amt>` / `!gang war <rival>`")

@bot.command("ping")
def cmd_ping(message): bot.reply(message, "pong! 🏓 Precinct & Syndicate online.")

@bot.command("profile")
@bot.command("bal")
def cmd_profile(message):
    uid = str(message.user.pk)
    db_inst = db.db if hasattr(db, "db") else db.Database()
    user = db_inst.get_user(uid, message.user.username)
    w = db_inst.get_wanted_level(uid)
    
    guard = "🛡️ Active" if user.get("guard_expires", 0) > time.time() else "None ❌"
    bot.reply(message, f"👤 **PROFILE: {message.user.username}**\n- Status: {'👮 Cop' if user.get('is_police') else 'Gangster'} | Gang: {user.get('gang', 'None')}\n- Wanted: {w['stars']} ({w['title']})\n- Blood Pact: {'🩸 Active' if user.get('blood_partner') else 'None'}\n- Cash: 💵 {user['balance']} | Bank: 🏦 {user['bank']} | Debt: 💳 {user['debt']}\n- Bodyguard: {guard}")

@bot.command("wanted")
def cmd_wanted(message):
    w = (db.db if hasattr(db, "db") else db.Database()).get_wanted_level(message.user.pk)
    bot.reply(message, f"⭐ **WANTED LEVEL:** {w['stars']}\n- Title: *{w['title']}*\n- Net Worth: {w['net_worth']} coins")

@bot.command("welfare")
def cmd_welfare(message):
    db_inst = db.db if hasattr(db, "db") else db.Database()
    pool = db_inst.get_welfare_pool_balance()
    if not message.args:
        return bot.reply(message, f"🏛️ **WELFARE POOL**\n- Pool Balance: **{pool} coins**\n- Type `!welfare claim` if net worth < 200.")
    if message.args[0].lower() == "claim":
        bot.reply(message, db_inst.claim_welfare(message.user.pk)["msg"])

@bot.command("leaderboard")
@bot.command("lb")
def cmd_leaderboard(message):
    db_inst = db.db if hasattr(db, "db") else db.Database()
    users = list(db_inst.users.find({}))
    if not users: return bot.reply(message, "📊 Leaderboard empty!")
    users.sort(key=lambda u: u.get("balance", 0) + u.get("bank", 0) - u.get("debt", 0), reverse=True)
    text = "🏆 **RICH LIST (TOP 5)**\n"
    for i, u in enumerate(users[:5], 1):
        net = u.get("balance", 0) + u.get("bank", 0) - u.get("debt", 0)
        text += f"{i}. **{u.get('username')}** — 💎 {net}\n"
    bot.reply(message, text)

@bot.command("police")
def cmd_police(message, action=""):
    db_inst = db.db if hasattr(db, "db") else db.Database()
    act = action.lower()
    if act == "join": bot.reply(message, db_inst.join_police(message.user.pk)["msg"])
    elif act == "leave": bot.reply(message, db_inst.leave_police(message.user.pk)["msg"])
    else: bot.reply(message, "❌ Usage: `!police join` or `!police leave`")

@bot.command("arrest")
def cmd_arrest(message, target=""):
    if not target: return bot.reply(message, "❌ Usage: `!arrest <username>`")
    bot.reply(message, (db.db if hasattr(db, "db") else db.Database()).arrest_user(message.user.pk, target)["msg"])

@bot.command("bribe")
def cmd_bribe(message, amount_str="1000"):
    db_inst = db.db if hasattr(db, "db") else db.Database()
    u = db_inst.get_user(message.user.pk)
    ast = str(amount_str).lower()
    amt = u["balance"] if ast == "all" else (u["balance"] // 2 if ast == "half" else int(ast or 1000))
    bot.reply(message, db_inst.bribe_cop(message.user.pk, amt)["msg"])

@bot.command("duel")
def cmd_duel(message, target="", bet=0):
    try: bet_amt = int(bet)
    except ValueError: bet_amt = 0
    if not target or bet_amt <= 0:
        return bot.reply(message, "❌ Usage: `!duel <username> <bet_amount>`")
    bot.reply(message, (db.db if hasattr(db, "db") else db.Database()).duel_user(message.user.pk, target, bet_amt)["msg"])

@bot.command("fight")
def cmd_fight(message, target=""):
    if not target:
        return bot.reply(message, "❌ Usage: `!fight <username>`")
    bot.reply(message, (db.db if hasattr(db, "db") else db.Database()).fight_user(message.user.pk, target)["msg"])

@bot.command("pact")
def cmd_pact(message, action="", target=""):
    db_inst = db.db if hasattr(db, "db") else db.Database()
    act = action.lower()
    if act == "accept":
        bot.reply(message, db_inst.accept_blood_pact(message.user.pk)["msg"])
    elif action:
        bot.reply(message, db_inst.request_blood_pact(message.user.pk, action)["msg"])
    else:
        bot.reply(message, "❌ Usage: `!pact <username>` or `!pact accept`")

@bot.command("betray")
def cmd_betray(message):
    bot.reply(message, (db.db if hasattr(db, "db") else db.Database()).betray_blood_partner(message.user.pk)["msg"])

@bot.command("extort")
def cmd_extort(message, target=""):
    if not target: return bot.reply(message, "❌ Usage: `!extort <username>`")
    bot.reply(message, (db.db if hasattr(db, "db") else db.Database()).extort_user(message.user.pk, target)["msg"])

@bot.command("smuggle")
def cmd_smuggle(message, tier="low"):
    bot.reply(message, (db.db if hasattr(db, "db") else db.Database()).run_smuggling(message.user.pk, tier)["msg"])

@bot.command("shop")
def cmd_shop(message):
    bot.reply(message, "🛒 **BLACK MARKET SHOP**\n1. `!buy charm` (500) - Lucky Charm\n2. `!buy shield` (500) - Police Shield\n3. `!buy pill` (1000) - Jackpot Pill\n4. `!buy luxury <key>` - Flex items")

@bot.command("buy")
def cmd_buy(message, item="", *args):
    uid = str(message.user.pk)
    db_inst = db.db if hasattr(db, "db") else db.Database()
    user = db_inst.get_user(uid, message.user.username)
    item = item.lower()

    if item == "luxury" and args:
        return bot.reply(message, db_inst.buy_luxury(uid, args[0])["msg"])

    items = {"charm": ("luck_charm", 500), "shield": ("police_shield", 500), "pill": ("jackpot_pill", 1000)}
    if item not in items: return bot.reply(message, "❌ Item not found! Check `!shop`.")
    key, cost = items[item]

    if user["balance"] < cost and not db_inst.is_creator(user.get("username")):
        return bot.reply(message, f"❌ Need {cost} cash!")

    inv = user.get("inventory", {})
    inv[key] = inv.get(key, 0) + 1
    actual_cost = 0 if db_inst.is_creator(user.get("username")) else cost
    db_inst.users.update_one({"_id": uid}, {"$inc": {"balance": -actual_cost}, "$set": {"inventory": inv}})
    bot.reply(message, f"🧪 Purchased {item}! Total owned: {inv[key]}")

@bot.command("luxury")
def cmd_luxury(message):
    text = "💎 **LUXURY CATALOG**\n"
    for k, i in db.LUXURY_ITEMS.items():
        text += f"{i['emoji']} **{i['name']}** (`!buy luxury {k}`) - {i['cost']} coins (*{i['title']}*)\n"
    bot.reply(message, text)

@bot.command("flex")
def cmd_flex(message):
    bot.reply(message, (db.db if hasattr(db, "db") else db.Database()).flex_status(message.user.pk)["msg"])

@bot.command("bounty")
def cmd_bounty(message, target="", amount=0):
    try: amt = int(amount)
    except ValueError: amt = 0
    if not target or amt <= 0: return bot.reply(message, "❌ Usage: `!bounty <username> <amt>` (Min 1k)")
    bot.reply(message, (db.db if hasattr(db, "db") else db.Database()).place_bounty(message.user.pk, target, amt)["msg"])

@bot.command("bounties")
def cmd_bounties(message):
    bot.reply(message, (db.db if hasattr(db, "db") else db.Database()).list_active_bounties()["msg"])

@bot.command("biz")
def cmd_biz(message, action=None, *args):
    uid = str(message.user.pk)
    db_inst = db.db if hasattr(db, "db") else db.Database()
    if not action:
        return bot.reply(message, "🏢 **ENTERPRISE**\n- `!biz catalog`\n- `!biz buy <key>`\n- `!biz close <key>`\n- `!biz list`\n- `!biz collect`")
    
    act = action.lower()
    if act == "catalog":
        txt = "📋 **CATALOG**\n"
        for k, b in db.BUSINESSES.items(): txt += f"• **{b['name']}** (`{k}`) - {b['cost']} coins (+{b['daily_income']})\n"
        bot.reply(message, txt)
    elif act == "buy": bot.reply(message, db_inst.buy_business(uid, args[0] if args else "")["msg"])
    elif act == "close": bot.reply(message, db_inst.close_business(uid, args[0] if args else "")["msg"])
    elif act == "list":
        bizs = db_inst.get_user_businesses(uid)
        if not bizs: return bot.reply(message, "❌ No businesses owned.")
        txt = "🏢 **YOUR BUSINESSES**\n" + "\n".join([f"• {b['name']} (`{b['biz_key']}`)" for b in bizs])
        bot.reply(message, txt)
    elif act == "collect": bot.reply(message, db_inst.collect_business_revenue(uid)["msg"])

@bot.command("gang")
def cmd_gang(message, action=None, *args):
    uid = str(message.user.pk)
    db_inst = db.db if hasattr(db, "db") else db.Database()
    if not action:
        return bot.reply(message, "🛡️ **GANG SYSTEM**\n- `!gang create <name>` | `!gang invite <user>` | `!gang accept` | `!gang leave` | `!gang transfer <user>`\n- `!gang empire` | `!gang takeover <district>` | `!gang collect <district>`\n- `!gang upgrade` | `!gang vault` | `!gang deposit <amt>` | `!gang war <rival>`")

    act = action.lower()
    if act == "create": bot.reply(message, db_inst.create_gang(uid, args[0] if args else "")["msg"])
    elif act == "invite":
        gang = db_inst.get_user_gang(uid)
        if not gang or gang["boss_uid"] != uid: return bot.reply(message, "❌ Only Don can invite!")
        t_uid = db_inst.find_uid(args[0].lstrip("@") if args else "")
        if not t_uid: return bot.reply(message, "❌ User not found!")
        db_inst.gangs.update_one({"_id": gang["_id"]}, {"$addToSet": {"invites": t_uid}})
        bot.reply(message, f"💌 Invitation sent!")
    elif act == "accept":
        gang = db_inst.gangs.find_one({"invites": uid})
        if not gang: return bot.reply(message, "❌ No pending invitations!")
        db_inst.remove_user_from_gang(uid)
        db_inst.gangs.update_one({"_id": gang["_id"]}, {"$pull": {"invites": uid}, "$addToSet": {"members": uid}})
        db_inst.users.update_one({"_id": uid}, {"$set": {"gang": gang["name"]}})
        bot.reply(message, f"🎉 Joined gang **{gang['name']}**!")
    elif act == "leave": bot.reply(message, f"🚪 {db_inst.remove_user_from_gang(uid)[1]}")
    elif act == "transfer":
        target_uname = args[0] if args else ""
        if not target_uname: return bot.reply(message, "❌ Usage: `!gang transfer <username>`")
        bot.reply(message, db_inst.transfer_gang(uid, target_uname)["msg"])
    elif act == "upgrade": bot.reply(message, db_inst.upgrade_gang_level(uid)["msg"])
    elif act == "empire":
        if args and args[0].lower() == "takeover":
            bot.reply(message, db_inst.takeover_territory(uid, args[1] if len(args) > 1 else "")["msg"])
        elif args and args[0].lower() == "collect":
            bot.reply(message, db_inst.collect_territory_revenue(uid, args[1] if len(args) > 1 else "")["msg"])
        else:
            ts = db_inst.list_territories()
            txt = "🏙️ **CITY DISTRICTS**\n" + "\n".join([f"• {t['name']} (`{t['_id']}`): {t['owner_gang'] or 'Unclaimed'} (Cost: {t['cost']} vault)" for t in ts])
            bot.reply(message, txt + "\n\nUse: `!gang empire takeover <key>` or `!gang empire collect <key>`")
    elif act == "takeover": bot.reply(message, db_inst.takeover_territory(uid, args[0] if args else "")["msg"])
    elif act == "vault":
        gang = db_inst.get_user_gang(uid)
        if not gang: return bot.reply(message, "❌ Not in a gang!")
        bot.reply(message, f"{gang['flag']} **{gang['name']} VAULT**\n- Balance: {gang['vault']}/{gang['vault_cap']} coins\n- Members: {len(gang['members'])}/{gang['max_members']}")
    elif act == "deposit":
        try: amt = int(args[0])
        except (ValueError, TypeError): amt = 0
        if amt <= 0: return bot.reply(message, "❌ Deposit amount must be positive!")
        gang = db_inst.get_user_gang(uid)
        user = db_inst.get_user(uid)
        if not gang: return bot.reply(message, "❌ Not in a gang!")
        if user["balance"] < amt: return bot.reply(message, "❌ Insufficient cash!")
        db_inst.users.update_one({"_id": uid}, {"$inc": {"balance": -amt}})
        db_inst.gangs.update_one({"_id": gang["_id"]}, {"$inc": {"vault": amt}})
        bot.reply(message, f"📥 Deposited {amt} coins into gang vault.")
    elif act == "war":
        if not args: return bot.reply(message, "❌ Usage: `!gang war <rival>`")
        my_gang = db_inst.get_user_gang(uid)
        if not my_gang or my_gang["boss_uid"] != uid: return bot.reply(message, "❌ Only Don can declare war!")
        if time.time() - my_gang.get("last_war", 0) < 7200 and not db_inst.is_creator(db_inst.get_user(uid).get("username")):
            return bot.reply(message, "⏳ Gang weapons cooling down (2h cooldown)!")
        rival = db_inst.get_gang(args[0])
        if not rival: return bot.reply(message, "❌ Rival gang not found!")
        db_inst.gangs.update_one({"_id": my_gang["_id"]}, {"$set": {"last_war": time.time()}})
        stolen = int(rival["vault"] * 0.20)
        db_inst.gangs.update_one({"_id": rival["_id"]}, {"$inc": {"vault": -stolen}})
        db_inst.gangs.update_one({"_id": my_gang["_id"]}, {"$inc": {"vault": stolen}})
        bot.reply(message, f"⚔️ **GANG WAR VICTORY!** Raided **{rival['name']}** and looted **+{stolen} vault coins**! 🔥")

@bot.command("coinflip")
def cmd_coinflip(message, bet=0, choice="heads"):
    uid = str(message.user.pk)
    db_inst = db.db if hasattr(db, "db") else db.Database()
    user = db_inst.get_user(uid, message.user.username)
    bs = str(bet).lower()
    bet = user["balance"] if bs == "all" else (user["balance"] // 2 if bs == "half" else int(bet or 0))

    if bet <= 0 or bet > user["balance"]: return bot.reply(message, "❌ Invalid bet!")
    choice = choice.lower()
    if choice not in ["heads", "tails"]: return bot.reply(message, "❌ Choose heads or tails.")

    outcome = choice if db_inst.is_creator(message.user.username) else random.choice(["heads", "tails"])
    if outcome == choice:
        db_inst.apply_debt_garnishment(uid, bet)
        bot.reply(message, f"🪙 Coin landed on **{outcome.upper()}**! Won **+{bet} coins**! 🎉")
    else:
        db_inst.users.update_one({"_id": uid}, {"$inc": {"balance": -bet}})
        bot.reply(message, f"🪙 Coin landed on **{outcome.upper()}**! Lost **-{bet} coins**! 💀")

@bot.command("slots")
def cmd_slots(message, bet=100):
    try: bet = int(bet)
    except ValueError: bet = 100
    bot.reply(message, (db.db if hasattr(db, "db") else db.Database()).play_slots(message.user.pk, bet)["msg"])

@bot.command("roll")
def cmd_roll(message): bot.reply(message, f"🎲 Rolled a **{random.randint(1, 100)}** out of 100!")

def run_bot(*args, **kwargs):
    bot.login()
    bot.poll_loop()
