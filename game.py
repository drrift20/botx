"""Command logic. process() is synchronous and returns a list of reply strings;
the bot runs it in a worker thread so the event loop never blocks on SQLite."""
import random
import time

import config
import database as db

PREFIX = "!"
_pending_duels = {}  # target_user_id -> {from_id, from_name, amount, expires}

JOBS = ["delivered pizzas 🍕", "debugged some spaghetti code 🍝", "walked dogs 🐕",
        "streamed to 3 viewers 🎮", "sold limited-edition stickers 🖼️",
        "fixed a neighbor's wifi 📶", "drew anime commissions ✏️"]


def fmt_duration(sec):
    sec = int(max(sec, 0))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    return f"{m}m {s}s" if m else f"{s}s"


def _target(args):
    if not args:
        return None
    return db.get_user_by_username(args[0].lstrip("@"))


def cmd_claim(uid, name, args):
    reward = db.claim_chest(uid)
    if reward is None:
        return []  # stay silent so late claimers don't spam the chat
    return [f"🎉 @{name} grabbed the chest and won {reward} coins!"]


def cmd_daily(uid, name, args):
    ok, p = db.claim_daily(uid)
    if not ok:
        return [f"⏳ @{name}, your daily is on cooldown. Back in {fmt_duration(p)}."]
    reward, bonus, streak, bal = p
    msg = f"🌅 @{name} claimed {reward} coins! 🔥 Streak: {streak}"
    if bonus:
        msg += f" (+{bonus} streak bonus)"
    return [msg + f"\n💰 Balance: {bal}"]


def cmd_work(uid, name, args):
    ok, p = db.claim_work(uid)
    if not ok:
        return [f"😮‍💨 @{name}, you're tired. Work again in {fmt_duration(p)}."]
    reward, bal = p
    return [f"💼 @{name} {random.choice(JOBS)} and earned {reward} coins.\n💰 Balance: {bal}"]


def cmd_bal(uid, name, args):
    u = db.get_user(uid)
    return [f"💰 @{name}: {u['balance']} coins | 🔥 streak {u['streak']}"]


def cmd_rob(uid, name, args):
    victim = _target(args)
    if not victim:
        return ["Usage: !rob @username (they must have chatted here before)"]
    if victim["user_id"] == str(uid):
        return ["🤡 You can't rob yourself."]
    res = db.rob(uid, victim["user_id"])
    s = res["status"]
    if s == "cooldown":
        return [f"🚔 Lay low, @{name}. Rob again in {fmt_duration(res['wait'])}."]
    if s == "robber_poor":
        return [f"🪙 You need at least {config.ROB_MIN_BALANCE} coins to risk a heist."]
    if s == "victim_poor":
        return [f"🪹 @{victim['username']} is too broke to be worth robbing."]
    if s == "success":
        return [f"🥷 @{name} robbed {res['amount']} coins from @{victim['username']}!"]
    return [f"🚨 @{name} got caught and paid a {res['amount']} coin fine to @{victim['username']}!"]


def cmd_duel(uid, name, args):
    if len(args) < 2 or not args[1].isdigit() or int(args[1]) <= 0:
        return ["Usage: !duel @username <amount>"]
    target, amount = _target(args), int(args[1])
    if not target:
        return ["Can't find that user. They must have chatted here before."]
    if target["user_id"] == str(uid):
        return ["🤡 You can't duel yourself."]
    if db.get_user(uid)["balance"] < amount:
        return ["💸 You don't have enough coins for that wager."]
    _pending_duels[target["user_id"]] = {
        "from_id": str(uid), "from_name": name, "amount": amount,
        "expires": time.time() + config.DUEL_TIMEOUT}
    return [f"⚔️ @{target['username']}, @{name} challenged you to a {amount} coin duel!\n"
            f"Type !accept or !decline within {config.DUEL_TIMEOUT}s."]


def cmd_accept(uid, name, args):
    d = _pending_duels.pop(str(uid), None)
    if not d or d["expires"] < time.time():
        return []
    res = db.duel(d["from_id"], uid, d["amount"])
    if res["status"] == "broke":
        return [f"💸 Duel cancelled: @{res['who']} can't cover the wager."]
    return [f"🎲 Rolling the dice...\n🏆 @{res['winner']} beat @{res['loser']} and won {d['amount']} coins!"]


def cmd_decline(uid, name, args):
    d = _pending_duels.pop(str(uid), None)
    return [f"🐔 @{name} declined @{d['from_name']}'s duel."] if d else []


def cmd_buy(uid, name, args):
    if not args or not args[0].isdigit():
        return [f"Usage: !buy <item id>. See items: {config.DASHBOARD_URL}/shop"]
    res = db.buy_item(uid, int(args[0]))
    s = res["status"]
    if s == "no_item":
        return ["❓ No such item id."]
    if s == "owned":
        return [f"You already own {res['name']}."]
    if s == "broke":
        return [f"💸 That costs {res['price']} coins. You have {res['balance']}."]
    return [f"🛍️ @{name} bought {res['emoji']} {res['name']}! Balance: {res['balance']}"]


def cmd_leaderboard(uid, name, args):
    return [f"🏆 Leaderboard: {config.DASHBOARD_URL}/leaderboard"]


def cmd_shop(uid, name, args):
    return [f"🛒 Shop: {config.DASHBOARD_URL}/shop\nBuy with !buy <id>"]


def cmd_help(uid, name, args):
    return ["📖 Commands: !daily !work !bal !rob @user !duel @user <amt> "
            "!accept !decline !claim !buy <id> !leaderboard !shop"]


COMMANDS = {
    "claim": cmd_claim, "daily": cmd_daily, "work": cmd_work,
    "bal": cmd_bal, "balance": cmd_bal, "rob": cmd_rob, "duel": cmd_duel,
    "accept": cmd_accept, "decline": cmd_decline, "buy": cmd_buy,
    "leaderboard": cmd_leaderboard, "lb": cmd_leaderboard, "shop": cmd_shop,
    "help": cmd_help,
}


def process(user_id, username, text):
    """Handle one incoming chat message. Returns a list of reply strings."""
    db.upsert_user(user_id, username)
    text = (text or "").strip()
    if not text.startswith(PREFIX):
        if db.register_message():
            return ["🎁 A RANDOM CHEST APPEARED! Type !claim first to grab the coins!"]
        return []
    parts = text[len(PREFIX):].split()
    if not parts:
        return []
    handler = COMMANDS.get(parts[0].lower())
    return handler(user_id, username, parts[1:]) if handler else []
