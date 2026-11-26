import datetime, json, math, os, random, subprocess, sys, textwrap, time, requests
import numpy as np, wave
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

GRAPH = "https://graph.facebook.com/v21.0"
YT_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# 1. Ramp Schedule Gate: Days 1-2 = 2x/day (07:00 & 13:00 UTC = 12:30 & 18:30 IST); Day 3+ = 4x/day
STATE_FILE = Path("schedule_state.json")
state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {
    "start_date": datetime.date.today().isoformat(), "posted_titles": []
}
day_num = (datetime.date.today() - datetime.date.fromisoformat(state["start_date"])).days + 1
utc_hour = datetime.datetime.utcnow().hour
if os.getenv("GITHUB_EVENT_NAME") == "schedule" and day_num <= 2 and utc_hour not in (7, 13):
    print(f"Day {day_num} (2x/day phase): skipping slot at {utc_hour:02d}:00 UTC.")
    sys.exit(0)

# 2. Unique Relationship Carousel/Short Series (never repeats)
SERIES = [
    {"emotion": "trust", "c1": (18, 12, 28), "c2": (64, 34, 62), "accent": (253, 224, 171),
     "query": "coffee aesthetic cozy",
     "cover": "4 Quiet Signs Someone Truly Loves You",
     "points": [("01", "They remember the small things", "Not just birthdays—what calms you down on a hard day."),
                ("02", "They stay calm when you are upset", "Real love never turns your worst day into a competition."),
                ("03", "Their actions match their promises", "Consistency replaces guessing where you stand."),
                ("04", "They protect your peace in private", "How they speak about you when you are not there says everything.")],
     "cta": "Send this to the person who does #1.\nComment which sign means the most (1-4)."},
    {"emotion": "heartbreak", "c1": (10, 15, 35), "c2": (30, 48, 84), "accent": (186, 230, 253),
     "query": "rain window night",
     "cover": "4 Hard Truths About Letting Go",
     "points": [("01", "Closure comes from you, not them", "Waiting for an apology only delays your own peace."),
                ("02", "Missing them does not mean go back", "Sometimes you miss the version of them you hoped they were."),
                ("03", "Stop watering dead roots", "If only one person is fighting for it, it is already over."),
                ("04", "Outgrowing someone is not a failure", "Some people arrive to teach you what you deserve.")],
     "cta": "Send this to a friend who needs to hear #3 today.\nSave this for later."},
    {"emotion": "healing", "c1": (8, 32, 36), "c2": (22, 78, 82), "accent": (153, 246, 228),
     "query": "ocean waves sunrise",
     "cover": "4 Things Never To Beg For In Love",
     "points": [("01", "Never beg for basic effort", "Someone who wants you makes time, not endless excuses."),
                ("02", "Never beg to be chosen", "You deserve certainty even on ordinary days."),
                ("03", "Never beg for respect", "Love without respect is just attachment in disguise."),
                ("04", "Never beg for honesty", "Real love feels safe—never like being a detective.")],
     "cta": "Save this reminder for the days you forget your worth.\nSend to someone who needs this."},
    {"emotion": "romantic", "c1": (42, 10, 32), "c2": (110, 26, 68), "accent": (255, 182, 193),)
