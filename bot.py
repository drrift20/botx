import os
import json
import time
import logging
import threading
import asyncio
import random
from collections import deque
from pathlib import Path
from instagrapi import Client
from instagrapi.exceptions import (
    ChallengeRequired,
    LoginRequired,
    PleaseWaitFewMinutes,
    RateLimitError,
    ClientConnectionError
)
import config
import database as db

log = logging.getLogger("bot")


class InstaClient:
    def __init__(self):
        self.cl = Client()
        self.cl.delay_range = [1, 3]
        self.thread_id = int(config.THREAD_ID)
        self._names = {}
        self._lock = threading.Lock()

    @property
    def own_id(self):
        return str(self.cl.user_id)

    def login(self):
        with self._lock:
            cl = self.cl
            session_file = config.BASE_DIR / "session.json"
            
            if session_file.exists():
                try:
                    cl.load_settings(str(session_file))
                    user_info = cl.account_info()
                    log.info("Successfully logged in as @%s using session.json!", user_info.username)
                    return
                except Exception as e:
                    log.warning("session.json load failed (%s); trying fallback...", e)
            
            raw = db.get_state("ig_session")
            if raw:
                try:
                    cl.set_settings(json.loads(raw))
                    cl.account_info()
                    log.info("Logged in using MongoDB saved session")
                    return
                except Exception as e:
                    log.warning("MongoDB session login failed (%s)", e)
            
            raise Exception("No valid session found! Please provide a valid session.json via SESSION_DATA.")

    def fetch(self):
        with self._lock:
            thread = self.cl.direct_thread(self.thread_id, amount=10)
            for u in thread.users:
                self._names[str(u.pk)] = u.username
            return thread.messages

    def send(self, text):
        with self._lock:
            self.cl.direct_answer(self.thread_id, text)


async def _sleep(stop, seconds):
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


async def _login_forever(ig, stop):
    fails = 0
    while not stop.is_set():
        try:
            await asyncio.to_thread(ig.login)
            return True
        except ChallengeRequired:
            log.error("Instagram challenge required. Approve the login in the app.")
            await _sleep(stop, 600)
        except Exception as e:
            fails += 1
            delay = min(600, 15 * 2 ** fails)
            log.error("Login failed (%s). Retrying in %ss", e, delay)
            await _sleep(stop, delay)
    return False


async def run_bot(stop: asyncio.Event):
    if not (config.USERNAME and config.PASSWORD and config.THREAD_ID):
        log.error("Missing IG credentials or THREAD_ID.")
        return

    ig = InstaClient()
    if not await _login_forever(ig, stop):
        return

    send_lock = asyncio.Lock()
    last_cmd = {}
    seen = deque(maxlen=500)

    log.info("Bot loop started. Polling thread %s", ig.thread_id)

    while not stop.is_set():
        try:
            messages = await asyncio.to_thread(ig.fetch)
            if not messages:
                await _sleep(stop, random.uniform(config.POLL_MIN, config.POLL_MAX))
                continue

            for m in reversed(messages):
                m_id = str(m.id)
                if m_id in seen:
                    continue
                seen.append(m_id)

                text = (m.text or "").strip()
                sender_id = str(m.user_id)
                username = ig._names.get(sender_id, "user")

                # Skip bot's own messages
                if sender_id == ig.own_id:
                    continue

                log.info("New message caught from @%s: %s", username, text)

                if not text.startswith("!"):
                    continue

                parts = text.split()
                cmd = parts[0].lower()

                now = time.time()
                cooldown = last_cmd.get(sender_id, 0) + config.USER_CMD_COOLDOWN
                if now < cooldown:
                    continue
                last_cmd[sender_id] = now

                r = None
                if cmd == "!ping":
                    r = f"Pong! @{username}"
                elif cmd == "!help":
                    r = "Available commands: !ping, !help, !profile, !leaderboard"
                elif cmd == "!profile":
                    user_data = db.get_user(sender_id)
                    coins = user_data.get("coins", 0) if user_data else 0
                    r = f"@{username} | Coins: {coins}"
                elif cmd == "!leaderboard":
                    top = db.get_leaderboard(limit=5)
                    lines = [f"{i+1}. {u.get('username', 'User')}: {u.get('coins', 0)} coins" for i, u in enumerate(top)]
                    r = "Leaderboard:\n" + "\n".join(lines) if lines else "No data yet."

                if r:
                    log.info("Sending response: %s", r)
                    async with send_lock:
                        await asyncio.to_thread(ig.send, r)
                        await asyncio.sleep(config.SEND_DELAY)

            await _sleep(stop, random.uniform(config.POLL_MIN, config.POLL_MAX))

        except LoginRequired:
            log.warning("Session lost; re-logging in")
            if not await _login_forever(ig, stop):
                return
        except (PleaseWaitFewMinutes, RateLimitError):
            log.warning("Rate limited by Instagram; sleeping 5 min")
            await _sleep(stop, 300)
        except Exception as e:
            log.error("Error in bot loop: %s", e, exc_info=True)
            await _sleep(stop, 10)
