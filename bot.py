import random
import time
import logging
import database as db

log = logging.getLogger("botx.bot")

def register_commands(bot):
    
    @bot.command(name="daily")
    def cmd_daily(message):
        uid = str(message.user.pk)
        res = db.db.claim_daily(uid, message.user.username) if hasattr(db, "db") else db.claim_daily(uid, message.user.username)
        if not res["ok"]:
            hours = int(res["remaining"] // 3600)
            mins = int((res["remaining"] % 3600) // 60)
            return bot.reply(message, f"⏳ Daily already claimed! Try again in {hours}h {mins}m. Balance: {res['balance']} coins.")
        bot.reply(message, f"🎁 Daily bonus collected! **+{res['amount']} coins** (Streak: 🔥 {res['streak']} days). Total balance: **{res['balance']} coins**.")

    @bot.command(name="work")
    def cmd_work(message):
        uid = str(message.user.pk)
        user = db.get_user(uid, message.user.username)
        
        cooldown = 1800 # 30 mins
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

    @bot.command(name="crime")
    def cmd_crime(message):
        uid = str(message.user.pk)
        user = db.get_user(uid, message.user.username)
        
        cooldown = 3600 # 1 hour
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

    @bot.command(name="bank")
    def cmd_bank(message, action=None, amount: int = 0):
        uid = str(message.user.pk)
        user = db.get_user(uid, message.user.username)
        
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

    @bot.command(name="shop")
    def cmd_shop(message):
        bot.reply(message, "🛒 **BLACK MARKET SHOP**\n1. `!buy potion` - Luck Potion (Price: 300 coins) -> Increases crime & gamble success rates!\n\nType `!buy potion` to purchase.")

    @bot.command(name="buy")
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
