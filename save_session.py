"""Helper: Logs in and saves session cookies"""
from dotenv import load_dotenv
load_dotenv()

from instagrapi import Client
import config
import os

cl = Client()
session_file = "session.json"

try:
    if os.path.exists(session_file):
        print("Loading existing session...")
        cl.load_settings(session_file)
    else:
        print("Logging in with standard credentials...")
        # Disable public key encryption prompts that trigger the bloks hash error
        cl.login(config.USERNAME, config.PASSWORD)
        cl.dump_settings(session_file)
        print("Session saved successfully to session.json!")
except Exception as e:
    print(f"An error occurred: {e}")
