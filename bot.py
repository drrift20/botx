"""Instagram listener. instagrapi is synchronous, so every API call runs in a worker
thread via asyncio.to_thread; a lock serialises them (the client isn't thread-safe)."""
import asyncio
import json
import logging
import random
import threading
import time
from collections import deque

import requests
from instagrapi import Client
from instagrapi.exceptions import (ChallengeRequired, ClientConnectionError,
                                   LoginRequired, PleaseWaitFewMinutes, RateLimitError)

import config
import database as db
import game

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
        """Log in, reusing the session stored in MongoDB (Render's disk is ephemeral,
        so a session.json file would be lost on every deploy/restart)."""
        with self._lock:
            cl = self.cl
            raw = db.get_state("ig_session")
            if raw:
                try:
                    cl.set_settings(json.loads(raw))
                    cl.login(config.USERNAME, config.PASSWORD)
                    cl.get_timeline_feed()  # verifies the session is still valid
                    log.info("Logged in using saved session")
                    return
                except LoginRequired:
                    log.warning("Saved session expired; logging in fresh")
                    old = cl.get_settings()
                    cl.set_settings({})
                    cl.set_uuids(old["uuids"])  # keep device identity
                except Exception as e:
                    log.warning("Session login failed (%s); logging in fresh", e)
            cl.login(config.USERNAME, config.PASSWORD)
            db.set_state("ig_session", json.dumps(cl.get_settings()))
            log.info("Logged in with password; session saved to MongoDB")

    def fetch(self):
        with self._lock:
            thread = self.cl.direct_thread(self.thread_id, amount=20)
            for u in thread.users:
                self._names[str(u.pk)] = u.username
            return thread.messages

    def username_for(self, uid):
        uid = str(uid)
        if uid not in self._names:
            with self._lock:
                try:
                    self._names[uid] = self.cl.username_from_user_id(int(uid))
                except Exception:
                    self._names[uid] = f"user{uid[-4:]}"
        return self._names[uid]

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
            log.error("Instagram challenge required. Approve the login in the app, "
                      "then wait; retrying in 10 min.")
            await _sleep(stop, 600)
        except Exception as e:
            fails += 1
            delay = min(600, 15 * 2 ** fails)
            log.error("Login failed (%s). Retrying in %ss", e, delay)
            await _sleep(stop, delay)
    return False


async def run_bot(stop: asyncio.Event):
    if not (config.USERNAME and config.PASSWORD and config.THREAD_ID):
        log.error("Set IG_USERNAME, IG_PASSWORD and THREAD_ID. Bot disabled; web UI still runs.")
        return

    ig = InstaClient()
    if not await _login_forever(ig, stop):
        return

    send_lock = asyncio.Lock()
    last_cmd = {}
    seen = deque(maxlen=500)
    last_id = await asyncio.to_thread(db.get_state, "last_id")
    if last_id:
        seen.append(last_id)
    ts_raw = await asyncio.to_thread(db.get_state, "last_ts")
    last_ts = float(ts_raw) if ts_raw else None

    async def say(text):
        async with send_lock:
            for attempt in range(3):
                try:
                    await asyncio.to_thread(ig.send, text)
                    break
                except (PleaseWaitFewMinutes, RateLimitError):
                    await _sleep(stop, 60 * (attempt + 1))
                except Exception as e:
                    log.warning("Send failed (%s), attempt %d", e, attempt + 1)
                    await _sleep(stop, 3 * (attempt + 1))
            await asyncio.sleep(config.SEND_DELAY)

    fails = 0
    log.info("Bot is listening on thread %s", config.THREAD_ID)
    while not stop.is_set():
        try:
            msgs = sorted(await asyncio.to_thread(ig.fetch), key=lambda m: m.timestamp)

            if last_ts is None:  # first ever run: skip history instead of replaying it
                last_ts = msgs[-1].timestamp.timestamp() if msgs else time.time()
                seen.extend(m.id for m in msgs)
                await asyncio.to_thread(db.set_state, "last_ts", last_ts)
                msgs = []

            for m in msgs:
                ts = m.timestamp.timestamp()
                if m.id in seen or ts < last_ts:
                    continue
                seen.append(m.id)
                last_ts, last_id = max(last_ts, ts), m.id
                if m.user_id is None or str(m.user_id) == ig.own_id or not m.text:
                    continue

                uid = str(m.user_id)
                if m.text.startswith(game.PREFIX):  # per-user anti-spam
                    now = time.monotonic()
                    if now - last_cmd.get(uid, 0) < config.USER_CMD_COOLDOWN:
                        continue
                    last_cmd[uid] = now

                name = await asyncio.to_thread(ig.username_for, uid)
                try:
                    replies = await asyncio.to_thread(game.process, uid, name, m.text)
                except Exception:
                    log.exception("Command failed: %r", m.text)
                    continue
                for r in replies:
                    await say(r)

            await asyncio.to_thread(db.set_state, "last_ts", last_ts)
            if last_id:
                await asyncio.to_thread(db.set_state, "last_id", last_id)
            fails = 0
            await _sleep(stop, random.uniform(config.POLL_MIN, config.POLL_MAX))

        except LoginRequired:
            log.warning("Session lost; re-logging in")
            if not await _login_forever(ig, stop):
                return
        except (PleaseWaitFewMinutes, RateLimitError):
            log.warning("Rate limited by Instagram; sleeping 5 min")
            await _sleep(stop, 300)
        except ChallengeRequired:
            log.error("Challenge required; sleeping 10 min")
            await _sleep(stop, 600)
        except (ClientConnectionError, requests.RequestException, ConnectionError, TimeoutError) as e:
            fails += 1
            delay = min(300, 5 * 2 ** fails)
            log.warning("Network error (%s). Retrying in %ss", e, delay)
            await _sleep(stop, delay)
        except asyncio.CancelledError:
            raise
        except Exception:
            fails += 1
            delay = min(300, 5 * 2 ** fails)
            log.exception("Unexpected error. Retrying in %ss", delay)
            await _sleep(stop, delay)
