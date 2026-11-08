"""Helper (run locally): lists your recent DM threads using session.json."""
from dotenv import load_dotenv
load_dotenv()

from instagrapi import Client
import os

cl = Client()
session_file = "session.json"

if os.path.exists(session_file):
    print("Loading session from session.json...")
    cl.load_settings(session_file)
else:
    print("Error: session.json not found!")
    exit(1)

# Fetch direct threads to get the thread ID
for t in cl.direct_threads(amount=20):
    names = ", ".join(u.username for u in t.users[:4])
    print(f"THREAD_ID: {t.id}  |  Title: {t.thread_title or '(no title)'}  |  Users: {names}")
