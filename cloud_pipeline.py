import datetime, json, math, os, random, re, subprocess, sys, textwrap, time, wave
import numpy as np
import requests
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

GRAPH = "https://graph.facebook.com/v21.0"
YT_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# 1. IST Time & Ramp Schedule Gate (Days 1-2 = 2x/day; Day 3+ = 6x/day)
ist_now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
ist_today = ist_now.date().isoformat()
ist_mmdd = ist_now.strftime("%m-%d")

STATE_FILE = Path("schedule_state.json")
state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {
    "start_date": ist_today, "posted_titles": [], "used_bg_ids": [], "used_music_sigs": [],
    "last_emotion": "", "last_format": "", "festival_posted_date": "", "vara_posted_date": ""
}
for k in ("posted_titles", "used_bg_ids", "used_music_sigs"):
    state.setdefault(k, [])

day_num = (ist_now.date() - datetime.date.fromisoformat(state["start_date"])).days + 1
utc_hour = datetime.datetime.now(datetime.timezone.utc).hour
if os.getenv("GITHUB_EVENT_NAME") == "schedule" and day_num <= 2 and utc_hour not in (7, 14):
    print(f"Day {day_num} (2x/day phase): skipping slot at {utc_hour:02d}:00 UTC.")
    sys.exit(0)

# 2. Indian Holidays, Festivals & Hindu Tithi Specials (2026-2027)
FESTIVALS = {
    "2026-12-01": ("Kaal Bhairav Jayanti (Kalabhairava Ashtami)", "temple diya night spiritual lamp",
                   "On this sacred Kaal Bhairav Ashtami,\nmay the Guardian of Time remove every hidden fear,\nprotect your peace, and give you courage to walk away from all negativity."),
    "2026-12-30": ("Masik Kalashtami", "evening diya lamp temple",
                   "Time heals what ego cannot.\nRelease anger, attachment, and fear tonight—\nand trust divine protection over your path."),
    "12-25": ("Christmas", "christmas lights warm cozy couple",
              "This Christmas, may the warmth you give to others\nfind its way back to your own heart,\nwrapped in peace, love, and someone who truly stays."),
    "01-01": ("New Year", "fireworks night sky celebration",
              "Leave behind everyone who made you question your worth.\nMay this New Year bring you a love that feels calm,\ncertain, and completely yours."),
    "2027-01-15": ("Makar Sankranti & Pongal", "kites colorful sky sunrise",
                   "Like kites rising against the winter sky,\nmay your heart let go of old heaviness\nand welcome brighter mornings with people who care."),
    "01-26": ("Republic Day", "india flag sunrise sky",
              "Freedom is not just a word on a calendar—\nit is also choosing peace over toxic ties\nand respecting every heart you meet."),
    "02-14": ("Valentine's Day", "romantic couple sunset beach",
              "Real love is not loud gifts once a year.\nIt is the quiet effort on ordinary Tuesdays,\nthe patience in hard moments, and choosing each other daily."),
    "2027-03-06": ("Maha Shivaratri", "peaceful night moon mountains",
                   "On this quiet sacred night,\nmay you find the strength to release what hurts\nand the calm to trust what is meant for you."),
    "2027-03-10": ("Eid Mubarak", "crescent moon lantern night",
                   "Eid Mubarak.\nMay this blessed day fill your home with warmth,\nheal unspoken wounds, and bring your loved ones closer."),
    "2027-03-22": ("Happy Holi", "holi colors celebration joy",
                   "May this Holi wash away every silent hurt\nand paint your life with people whose love\nnever fades when the colors do."),
    "2027-04-07": ("Ugadi & Gudi Padwa", "fresh spring flowers sunrise",
                   "A new year begins.\nMay every sweet and bitter chapter ahead\nteach you deeper love and unshakable peace."),
    "08-15": ("Independence Day", "sunrise mountains freedom",
              "Happy Independence Day.\nMay you always have the courage to protect your peace\nand build relationships rooted in respect."),
    "2027-08-17": ("Raksha Bandhan", "warm family celebration lamps",
                   "Some bonds don't need daily calls to stay unbreakable.\nSend this to the sibling who always had your back."),
    "2027-08-25": ("Krishna Janmashtami", "peacock feather flute aesthetic",
                   "True love never demands control—\njust like devotion, it brings peace even in silence."),
    "2027-09-04": ("Ganesh Chaturthi", "festive marigold flowers lamps",
                   "May Bappa remove every obstacle between your heart\nand the peace, love, and clarity you deserve."),
    "2027-10-09": ("Happy Dussehra", "golden sunset sky warm",
                   "Every ending makes room for light.\nLet go of yesterday's battles and step into a gentler chapter."),
    "2027-10-18": ("Karwa Chauth", "full moon night romantic",
                   "Under tonight's moonlight,\nmay the person you pray for always be the one\nwho protects your smile every day."),
    "2027-10-29": ("Happy Diwali", "diwali diyas warm bokeh lights",
                   "May this Diwali light up every quiet corner of your heart\nand keep you surrounded by people\nwho never dim your glow."),
}

VARA_THEMES = {
    0: ("Somavara — Lord Shiva & Chandra", "calm moonlit lake night",
        "On this Somavara, may Lord Shiva calm every restless thought\nand bless your heart with deep emotional peace."),
    1: ("Mangalavara — Courage & Protection", "warm temple lamp glow",
        "On this Mangalavara, remember:\nstrength is not shouting louder—it is staying fearless\nwhile protecting your peace."),
    2: ("Budhavara — Lord Ganesha Wisdom", "peaceful morning sunlight nature",
        "May Lord Ganesha clear every unspoken misunderstanding today\nand guide your words with clarity and kindness."),
    3: ("Guruvara — Trusting Divine Timing", "golden sunrise clouds sky",
        "On this Guruvara, stop rushing what is meant for you.\nWhat is written for your heart will arrive at the right moment."),
    4: ("Shukravara — Love & Grace", "warm flowers sunset aesthetic",
        "On this Shukravara, cherish the souls who bring warmth,\nharmony, and quiet grace into your everyday life."),
    5: ("Shanivara — Karma & Letting Go", "quiet twilight sky stars",
        "On this Shanivara, leave karma to time.\nDo good, stay honest, and release anyone who mistreated your pure heart."),
    6: ("Ravivara — Surya Dev Renewal", "bright sunrise ocean horizon",
        "As Surya rises this Ravivara,\nleave yesterday's heaviness behind and step into warmth and hope."),
}

QUERY_POOL = {
    "romantic":   ["couple sunset silhouette", "cherry blossom aesthetic", "warm candle lights", "golden hour beach walk"],
    "trust":      ["cozy coffee rain window", "starry night couple", "warm fireplace aesthetic", "autumn forest path"],
    "healing":    ["calm ocean waves sunrise", "misty mountain dawn", "sunlight through leaves", "peaceful lake reflection"],
    "heartbreak": ["rainy city night neon", "lonely street rain", "stormy clouds twilight", "raindrops window bokeh"],
    "missing":    ["night driving city lights", "moonlight clouds sky", "twilight city skyline", "train window evening"],
}

# 3. 20 Unique Relationship Posts Across All 5 Formats
CONTENT = [
    # --- SUNSET SKY (Raw Emotional Confessions — High Saves & DM Sends) ---
    {"format": "sunset_sky", "emotion": "healing", "query": "woman sunset ocean beach back",
     "cover": "The scariest part about healing is realizing\njust how much disrespect you used to call love",
     "cta": "Read that twice. Send this to someone who needs this wake-up call today."},
    {"format": "sunset_sky", "emotion": "missing", "query": "person ocean sunset silhouette",
     "cover": "You don't miss them.\nYou miss who you thought they were\nbefore they showed you who they actually are.",
     "cta": "Save this for the nights you feel like texting back."},
    {"format": "sunset_sky", "emotion": "romantic", "query": "couple beach sunset silhouette",
     "cover": "When it's real, you won't have to beg for replies,\ndecode mixed signals, or cry yourself to sleep.\nIt will just feel peaceful.",
     "cta": "Send this to the person who gives you peace."},
    {"format": "sunset_sky", "emotion": "trust", "query": "golden hour hills silhouette",
     "cover": "A relationship gets ten times stronger\nthe day both people realize\nlistening matters more than winning the argument.",
     "cta": "Send this to someone you want to grow with forever."},

    # --- PARCHMENT JOURNAL (Long-Form Watch-Time Letters — High Replays & Saves) ---
    {"format": "parchment_journal", "emotion": "heartbreak",
     "cover": "Read This When You Feel Hard To Love",
     "stanzas": [
         "Sometimes you look at everyone else's love stories and quietly wonder what is wrong with you.",
         "Why is it so effortless for others to be chosen, protected, and understood without having to beg?",
         "Here is the truth nobody tells you: you were never hard to love—you were just giving your whole heart to people who only knew how to take.",
         "The right person will never make basic affection feel like a reward you have to earn."
     ],
     "cta": "Save this and send it to a friend who doubts their worth."},
    {"format": "parchment_journal", "emotion": "missing",
     "cover": "The 2 AM Honesty Nobody Admits",
     "stanzas": [
         "It is strange how you can go all day smiling, working, and acting completely fine.",
         "Then 2 AM hits, the room goes quiet, and one memory undoes weeks of pretending you moved on.",
         "You don't even want the chaos back—you just wish things had ended with the same kindness they started with.",
         "Take a deep breath. Healing is not linear, and missing someone does not mean going back."
     ],
     "cta": "Send this to someone awake overthinking tonight."},
    {"format": "parchment_journal", "emotion": "romantic",
     "cover": "What Real Love Actually Looks Like",
     "stanzas": [
         "Real love is not butterflies and dramatic promises that disappear in two weeks.",
         "It is someone checking if you reached home safely, remembering what makes you anxious, and staying calm when you shut down.",
         "It is feeling completely safe to be quiet, messy, and imperfect without fearing they will leave.",
         "If you found someone like that, hold on tight—they are rare."
     ],
     "cta": "Send this to the person who does this for you without even trying."},
    {"format": "parchment_journal", "emotion": "healing",
     "cover": "The Day Everything Changed For Me",
     "stanzas": [
         "The moment I stopped chasing people who were unsure about me, my whole life became calmer.",
         "I realized I didn't lose anyone—I just stopped abandoning myself to keep someone else comfortable.",
         "Silence used to terrify me. Now it feels like self-respect.",
         "Never shrink your heart just to fit inside someone else's convenience."
     ],
     "cta": "Drop a heart in the comments if you are in your self-respect era—and share this."},

    # --- DOODLE COUPLE (Warm Viral Confessions — Highest Couple DM Shares) ---
    {"format": "doodle", "emotion": "romantic", "query": "couple sunset anime illustration love",
     "cover": "Out of 8 billion people,\nmy favorite sound is still your laugh",
     "cta": "Send this to the person whose laugh fixes your whole day."},
    {"format": "doodle", "emotion": "trust", "query": "couple night stars sky aesthetic",
     "cover": "I don't want a perfect love.\nI just want us never giving up on each other.",
     "cta": "Tag or send this to your forever person."},
    {"format": "doodle", "emotion": "romantic", "query": "couple rain umbrella street aesthetic",
     "cover": "Notice who stays gentle with you\neven when you're hard to handle.\nKeep them forever.",
     "cta": "Send this to the one who never gave up on you."},
    {"format": "doodle", "emotion": "missing", "query": "aesthetic pastel clouds twilight sky",
     "cover": "Distance is hard, but losing you\nwould be a hundred times harder.",
     "cta": "Send this to someone you miss across the miles right now."},

    # --- 4-SLIDE SERIES (Save-Bait Checklists — Pushes Non-Follower Reach) ---
    {"format": "series", "emotion": "trust", "c1": (18, 12, 28), "c2": (64, 34, 62), "accent": (253, 224, 171),
     "cover": "4 Silent Signs Someone Is Obsessed With You",
     "points": [("01", "They notice when your tone changes", "Even over text, they immediately ask if something is wrong."),
                ("02", "They remember tiny details", "Your favorite snack, your stress triggers, and things you mentioned once."),
                ("03", "They make time even when busy", "Nobody is ever too busy for someone they genuinely want."),
                ("04", "They look at you when everyone laughs", "In a crowded room, their eyes still find yours first.")],
     "cta": "Send this to the person who does #4—or comment which sign hit hardest (1-4)."},
    {"format": "series", "emotion": "heartbreak", "c1": (10, 15, 35), "c2": (30, 48, 84), "accent": (186, 230, 253),
     "cover": "4 Brutal Truths You Learn After Heartbreak",
     "points": [("01", "If they wanted to, they would", "Mixed signals are just a polite way of saying no."),
                ("02", "Apologies without change are manipulation", "Watch patterns, not sweet paragraphs."),
                ("03", "You can't love someone into loving you", "Giving more never fixes someone who isn't ready."),
                ("04", "Losing the wrong person is protection", "Time always proves why it didn't work out.")],
     "cta": "Which truth took you longest to learn? Comment 1, 2, 3, or 4 and share this."},
    {"format": "series", "emotion": "healing", "c1": (8, 32, 36), "c2": (22, 78, 82), "accent": (153, 246, 228),
     "cover": "4 Boundaries That Protect Your Heart",
     "points": [("01", "Never explain your worth twice", "The right person sees your value without a presentation."),
                ("02", "Match effort, not potential", "Date who they are today, not who they might become."),
                ("03", "Walk away from hot-and-cold love", "Peaceful love never keeps you guessing."),
                ("04", "Stop apologizing for having standards", "Asking for basic respect is never asking for too much.")],
     "cta": "Save this before you forget—and send #2 to a friend who needs it."},
    {"format": "series", "emotion": "romantic", "c1": (42, 10, 32), "c2": (110, 26, 68), "accent": (255, 182, 193),
     "cover": "4 Green Flags That Beat Looks Every Time",
     "points": [("01", "Emotional maturity during fights", "They talk it out instead of disappearing for days."),
                ("02", "Consistent reassurance", "They never let overthinking grow in silence."),
                ("03", "Respecting your boundaries", "When you say no, they listen without guilt-tripping."),
                ("04", "Clarity and honesty", "You never have to play detective with their intentions.")],
     "cta": "Send this to someone who has all 4 green flags. Which one is #1 for you?"},

    # --- 2-BEAT POV HOOK (Looping Punchlines — High Completion Rate) ---
    {"format": "pov", "emotion": "heartbreak", "c1": (16, 16, 28), "c2": (48, 42, 74), "accent": (199, 210, 254),
     "cover": "The saddest part of growing up is...",
     "payoff": "watching someone you promised forever to slowly turn into a stranger.",
     "cta": "Send this to someone who felt this."},
    {"format": "pov", "emotion": "healing", "c1": (12, 28, 38), "c2": (36, 72, 92), "accent": (167, 243, 208),
     "cover": "One day it won't hurt anymore...",
     "payoff": "you'll just smile and feel grateful you survived what almost broke you.",
     "cta": "Save this for better days—and send it to a friend healing right now."},
    {"format": "pov", "emotion": "missing", "c1": (22, 14, 38), "c2": (68, 42, 94), "accent": (233, 213, 255),
     "cover": "It's crazy how one person...",
     "payoff": "can be the reason you smile at your phone and also the reason you overthink at 3 AM.",
     "cta": "Send this to someone who knows exactly who came to mind."},
    {"format": "pov", "emotion": "trust", "c1": (30, 18, 14), "c2": (86, 52, 34), "accent": (253, 230, 138),
     "cover": "Don't look for someone perfect...",
     "payoff": "look for someone who refuses to walk away when things get imperfect.",
     "cta": "Tag or send this to your person today."},
]

# 4. Select Today's Post (Festival -> Daily Hindu Vara -> 20 Universal Relationship Posts)
fest = FESTIVALS.get(ist_today) or FESTIVALS.get(ist_mmdd)
if fest and state.get("festival_posted_date") != ist_today:
    fname, fquery, fquote = fest
    post = {
        "format": "sunset_sky", "emotion": "healing", "query": fquery,
        "cover": f"✨ {fname} ✨\n\n{fquote}",
        "cta": f"Wishing you and your loved ones a peaceful {fname}. Share this with someone special today!",
        "festival": fname,
    }
    state["festival_posted_date"] = ist_today
    print(f"[Festival Special] {fname}")
elif state.get("vara_posted_date") != ist_today:
    vname, vquery, vquote = VARA_THEMES[ist_now.weekday()]
    post = {
        "format": "sunset_sky", "emotion": "healing", "query": vquery,
        "cover": f"{vname}\n\n{vquote}",
        "cta": "Type Amen / Om Namah Shivaya or send this blessing to someone you care about today.",
        "festival": vname.split("—")[0].strip(),
    }
    state["vara_posted_date"] = ist_today
    print(f"[Hindu Vara Special] {vname}")
else:
    def viral_score(item):
        score = 30
        if any(k in item["cta"].lower() for k in ("send", "tag", "share")):
            score += 35
        if item["cover"] not in state["posted_titles"]:
            score += 20
        if item["format"] != state.get("last_format", ""):
            score += 10
        if item["emotion"] != state.get("last_emotion", ""):
            score += 5
        return score

    ranked = sorted(((viral_score(s), s) for s in CONTENT), key=lambda x: x[0], reverse=True)
    best_score, post = ranked[0]
    print(f"[Viral Validator] Format: {post['format'].upper()} | Emotion: {post['emotion']} | Score: {best_score}/100")
    if post["cover"] not in state["posted_titles"]:
        state["posted_titles"].append(post["cover"])
    if len(state["posted_titles"]) >= len(CONTENT):
        state["posted_titles"] = [post["cover"]]
    state["last_emotion"], state["last_format"] = post["emotion"], post["format"]

title_clean = post["cover"].replace("\n", " ").strip()
fest_tag = f" #{re.sub(r'[^A-Za-z0-9]', '', post['festival'])}" if post.get("festival") else ""
caption = f"{title_clean}\n\n{post['cta']}\n\n#lovequotes #relationships #{post['emotion']}{fest_tag} #reels #shorts"
pixabay_key = os.getenv("PIXABAY_API_KEY", "").strip()
query = post.get("query") or random.choice(QUERY_POOL[post["emotion"]])

def load_font(size, italic=False, bold=True):
    if italic:
        paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"]
    elif bold:
        paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
    else:
        paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def draw_safe_lines(draw, text, y_start, max_w=820, max_h=620, start_size=44, italic=False, bold=False, fill=(34, 26, 30)):
    # Auto-wrap & shrink font until EVERY line fits inside safe margins (130px left/right)
    for size in range(start_size, 24, -2):
        font = load_font(size, italic=italic, bold=bold)
        lines = []
        for para in text.split("\n"):
            p_clean = para.strip()
            if not p_clean:
                lines.append("")
                continue
            words, cur = p_clean.split(), ""
            for w in words:
                cand = f"{cur} {w}".strip()
                if draw.textbbox((0, 0), cand, font=font)[2] <= max_w:
                    cur = cand
                else:
                    if cur: lines.append(cur)
                    cur = w
            if cur: lines.append(cur)
        line_h = int(size * 1.35)
        total_h = len(lines) * line_h
        max_line_w = max((draw.textbbox((0, 0), ln, font=font)[2] for ln in lines if ln), default=0)
        if max_line_w <= max_w and total_h <= max_h:
            y = y_start
            for ln in lines:
                if ln:
                    bbox = draw.textbbox((540, y), ln, font=font, anchor="mm")
                    assert bbox[0] >= 100 and bbox[2] <= 980, f"FAIL: Text clipped X {bbox}"
                    draw.text((540, y), ln, fill=fill, font=font, anchor="mm")
                y += line_h
            print(f"[Layout Validator] PASS: {len(lines)} lines, max width {max_line_w}px/{max_w}px, font {size}px")
            return y
    raise RuntimeError("FAIL: Text exceeded safe bounds even at minimum font size.")

def fetch_unique_pixabay_image(q, img_type="photo"):
    if not pixabay_key:
        return None
    for t_mode in (img_type, "photo", "illustration"):
        res = requests.get("https://pixabay.com/api/", params={"key": pixabay_key, "q": q, "image_type": t_mode, "per_page": 25}, timeout=25).json()
        hits = [h for h in res.get("hits", []) if str(h["id"]) not in state["used_bg_ids"]] or res.get("hits", [])
        if hits:
            pick = random.choice(hits)
            state["used_bg_ids"] = (state["used_bg_ids"] + [str(pick["id"])])[-500:]
            p = Path("fresh_bg.jpg")
            p.write_bytes(requests.get(pick["largeImageURL"], timeout=40).content)
            print(f"[Pixabay Image] Unique {t_mode} ID {pick['id']} ({q})")
            return p
    return None

def fetch_unique_pixabay_video(q):
    if not pixabay_key:
        return None
    res = requests.get("https://pixabay.com/api/videos/", params={"key": pixabay_key, "q": q, "per_page": 25}, timeout=25).json()
    hits = [h for h in res.get("hits", []) if str(h["id"]) not in state["used_bg_ids"]] or res.get("hits", [])
    if hits:
        pick = random.choice(hits)
        state["used_bg_ids"] = (state["used_bg_ids"] + [str(pick["id"])])[-500:]
        vids = pick["videos"]
        p = Path("bg.mp4")
        p.write_bytes(requests.get((vids.get("large") or vids.get("medium") or vids.get("small"))["url"], timeout=60).content)
        print(f"[Pixabay Video] Unique video ID {pick['id']} ({q})")
        return p
    return None

# 5. Unique Hooked Music Engine
DUR = 13.0 if post["format"] == "parchment_journal" else (10.5 if post["format"] in ("doodle", "sunset_sky") else (11.0 if post["format"] == "pov" else 19.2))
music_dir = Path("music")
mp3s = sorted(music_dir.glob("*.mp3")) if music_dir.exists() else []
unused_mp3s = [m for m in mp3s if m.name not in state["used_music_sigs"]]
audio_input = random.choice(unused_mp3s or mp3s) if mp3s else None

if audio_input:
    state["used_music_sigs"] = (state["used_music_sigs"] + [audio_input.name])[-20:]
else:
    PROGRESSIONS = [
        ("Am-F-C-G", [[57,60,64,69], [53,57,60,64], [48,55,60,64], [55,59,62,67]], [76,74,72,71,72,76,79,76]),
        ("Fmaj-G-Em-Am", [[53,57,60,64], [55,59,62,67], [52,55,59,64], [57,60,64,69]], [72,74,76,79,76,74,72,69]),
        ("Dm-Bb-F-C", [[50,53,57,62], [46,50,53,58], [53,57,60,65], [48,52,55,60]], [74,72,70,69,70,74,77,74]),
        ("Em-C-G-D", [[52,55,59,64], [48,52,55,60], [55,59,62,67], [50,54,57,62]], [76,74,71,67,71,74,78,76]),
    ]
    TIMBRES, BPMS, SHIFTS = ["felt_piano", "rhodes_bell", "warm_strings"], [66, 72, 78, 84], [-2, 0, 2, 4]
    for _ in range(12):
        prog_name, prog, mel = random.choice(PROGRESSIONS)
        timbre, bpm, shift = random.choice(TIMBRES), random.choice(BPMS), random.choice(SHIFTS)
        sig = f"{prog_name}_{timbre}_{bpm}_{shift}"
        if sig not in state["used_music_sigs"]:
            break
    state["used_music_sigs"] = (state["used_music_sigs"] + [sig])[-30:]
    SR, N = 48000, int(48000 * DUR)
    L, R = np.zeros(N), np.zeros(N)
    beat = 60.0 / bpm
    def mf(m): return 440.0 * (2.0 ** (((m + shift) - 69) / 12.0))
    def synth_note(buf, start_s, freq, dur_s, vel):
        i0 = int(start_s * SR); n = min(int(dur_s * SR), N - i0)
        if n <= 0: return
        lt = np.linspace(0, n / SR, n, endpoint=False)
        if timbre == "felt_piano":
            sig_a = (np.sin(2*np.pi*freq*lt) + 0.25*np.sin(4*np.pi*freq*lt)*np.exp(-lt*3.0)) * np.minimum(1.0, lt/0.02) * np.exp(-lt*1.1)
        elif timbre == "rhodes_bell":
            sig_a = (np.sin(2*np.pi*freq*lt) + 0.35*np.sin(6*np.pi*freq*lt)*np.exp(-lt*5.0)) * np.minimum(1.0, lt/0.01) * np.exp(-lt*1.4)
        else:
            sig_a = (0.6*np.sin(2*np.pi*freq*lt) + 0.4*np.sin(2*np.pi*(freq*1.004)*lt)) * np.minimum(1.0, lt/0.25) * np.exp(-lt*0.55)
        buf[i0:i0+n] += sig_a * vel
    step_t = beat * 0.75
    for step in range(int(DUR / step_t)):
        t0 = step * step_t
        ch = prog[(step // 4) % len(prog)]
        for j, m in enumerate(ch):
            synth_note(L if j % 2 == 0 else R, t0 + j * (beat * 0.18), mf(m), beat * 2.0, 0.20)
            synth_note(R if j % 2 == 0 else L, t0 + j * (beat * 0.18), mf(m), beat * 2.0, 0.14)
        synth_note(L, t0, mf(mel[step % len(mel)]), beat * 1.6, 0.26)
        synth_note(R, t0, mf(mel[step % len(mel)]), beat * 1.6, 0.26)
        if t0 >= 3.1:
            bf = mf(ch[0] - 24)
            synth_note(L, t0, bf, beat * 2.2, 0.34); synth_note(R, t0, bf, beat * 2.2, 0.34)
            if step % 2 == 0:
                i0 = int(t0 * SR); kn = min(int(0.18 * SR), N - i0)
                if kn > 0:
                    kt = np.linspace(0, kn / SR, kn, endpoint=False)
                    kick = np.sin(2 * np.pi * (95 * np.exp(-kt * 18) + 38) * kt) * np.exp(-kt * 16) * 0.38
                    L[i0:i0+kn] += kick; R[i0:i0+kn] += kick
    stereo = np.stack([L, R], axis=1)
    if post["emotion"] in ("heartbreak", "missing"):
        rng = np.random.default_rng(int(time.time()))
        rain = rng.normal(0, 1, (N, 2)); ker = np.ones(16) / 16.0
        stereo[:, 0] += np.convolve(rain[:, 0], ker, mode="same") * 0.028
        stereo[:, 1] += np.convolve(rain[:, 1], ker, mode="same") * 0.028
    for ms, g in [(90, 0.32), (165, 0.18)]:
        sh = int(SR * ms / 1000)
        if sh < N:
            stereo[sh:, 0] += stereo[:-sh, 1] * g; stereo[sh:, 1] += stereo[:-sh, 0] * g
    stereo = (stereo / (np.max(np.abs(stereo)) + 1e-9) * 0.78 * 32767).astype(np.int16)
    with wave.open("music.wav", "wb") as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR); wf.writeframes(stereo.tobytes())
    audio_input = Path("music.wav")
    print(f"[Audio] Synthesized unique hooked track: {sig}")

# 6. Render Format
if post["format"] == "parchment_journal":
    rng = np.random.default_rng(int(time.time()))
    grain = rng.normal(0, 6.5, (1920, 1080))
    base_rgb = np.zeros((1920, 1080, 3), dtype=np.float32)
    base_rgb[:, :, 0] = 228 + grain; base_rgb[:, :, 1] = 214 + grain; base_rgb[:, :, 2] = 190 + grain
    yy, xx = np.ogrid[:1920, :1080]
    dist = np.sqrt(((xx - 540) / 540.0) ** 2 + ((yy - 960) / 960.0) ** 2)
    vig = np.clip(1.0 - 0.16 * (dist ** 2), 0.78, 1.0)[..., None]
    paper = Image.fromarray(np.clip(base_rgb * vig, 0, 255).astype(np.uint8), "RGB")
    draw = ImageDraw.Draw(paper)
    f_stanza, f_sig = load_font(39, italic=True), load_font(26, italic=False, bold=False)
    draw.ellipse([860, 80, 1030, 250], fill=(246, 212, 148), outline=(145, 112, 72), width=3)
    y = 330
    for stanza in post["stanzas"]:
        for ln in textwrap.wrap(stanza, width=36):
            draw.text((540, y), ln, fill=(32, 26, 24), font=f_stanza, anchor="mm")
            y += 52
        y += 48
    draw.line([(360, 1780), (720, 1780)], fill=(120, 102, 84), width=2)
    draw.text((540, 1740), "—  Heartful Quotes  —", fill=(72, 58, 48), font=f_sig, anchor="mm")
    paper.save("journal_frame.png")
    frames = int(DUR * 30)
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", "journal_frame.png", "-stream_loop", "-1", "-i", str(audio_input),
        "-t", str(DUR), "-vf", f"scale=1160:-1,zoompan=z='min(zoom+0.0004,1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps=30,fade=t=in:st=0:d=0.6,fade=t=out:st={DUR-0.7:.1f}:d=0.7",
        "-af", f"afade=t=in:st=0:d=0.4,afade=t=out:st={DUR-0.9:.1f}:d=0.9",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2", "final_short.mp4"
    ], check=True)

elif post["format"] in ("doodle", "sunset_sky"):
    img_type = "illustration" if post["format"] == "doodle" else "photo"
    img_path = fetch_unique_pixabay_image(query, img_type=img_type)
    if img_path:
        raw = Image.open(img_path).convert("RGB")
        w, h = raw.size
        if w / h > 1080 / 1920:
            nw = int(h * 1080 / 1920)
            raw = raw.crop(((w - nw) // 2, 0, (w + nw) // 2, h))
        else:
            nh = int(w * 1920 / 1080)
            raw = raw.crop((0, (h - nh) // 2, w, (h + nh) // 2))
        bg = raw.resize((1080, 1920), Image.Resampling.LANCZOS).convert("RGBA")
    else:
        bg = Image.new("RGBA", (1080, 1920), (252, 224, 210, 255))
    sky = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    px = sky.load()
    for y in range(740):
        alpha = int(215 * max(0.0, 1.0 - (y / 740) ** 1.6))
        for x in range(1080):
            px[x, y] = (255, 240, 232, alpha)
    bg = Image.alpha_composite(bg, sky).convert("RGB")
    draw = ImageDraw.Draw(bg)
    f_sig = load_font(26, italic=False, bold=False)
    y = draw_safe_lines(draw, post["cover"], y_start=250, max_w=800, max_h=440, start_size=44, italic=(post["format"] == "sunset_sky"), bold=False, fill=(34, 26, 30))
    if post["format"] == "doodle":
        draw.line([(330, y + 20), (495, y + 20)], fill=(70, 58, 62), width=2)
        draw.line([(585, y + 20), (750, y + 20)], fill=(70, 58, 62), width=2)
        hx, hy = 540, y + 20
        draw.polygon([(hx, hy + 14), (hx - 15, hy - 2), (hx - 7, hy - 12), (hx, hy - 5), (hx + 7, hy - 12), (hx + 15, hy - 2)], fill=(214, 69, 80))
    draw.text((540, 1740), "—  Heartful Quotes  —", fill=(255, 255, 255), font=f_sig, anchor="mm")
    bg.save("sky_frame.png")
    frames = int(DUR * 30)
    motion = random.choice([
        f"scale=1200:-1,zoompan=z='min(zoom+0.0007,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps=30",
        f"scale=1200:-1,zoompan=z='1.08-0.0007*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps=30",
        f"scale=1200:-1,zoompan=z='1.08':x='(iw-iw/zoom)*(on/{frames})':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps=30",
    ])
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", "sky_frame.png", "-stream_loop", "-1", "-i", str(audio_input),
        "-t", str(DUR), "-vf", f"{motion},fade=t=in:st=0:d=0.5,fade=t=out:st={DUR-0.6:.1f}:d=0.6",
        "-af", f"afade=t=in:st=0:d=0.4,afade=t=out:st={DUR-0.8:.1f}:d=0.8",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2", "final_short.mp4"
    ], check=True)

else:
    accent = tuple(post["accent"])
    bg_mp4 = fetch_unique_pixabay_video(query)
    if not bg_mp4:
        c1, c2 = post["c1"], post["c2"]
        img = Image.new("RGBA", (1080, 1920))
        px = img.load()
        for y in range(1920):
            tt = y / 1920
            rgb = (int(c1[0]+(c2[0]-c1[0])*tt), int(c1[1]+(c2[1]-c1[1])*tt), int(c1[2]+(c2[2]-c1[2])*tt), 255)
            for x in range(1080):
                px[x, y] = rgb
        img.convert("RGB").save("designed_bg.png")

    card_style = random.choice(["glass_card", "editorial_bar"])
    def make_card(title, body="", path="ov.png"):
        base = Image.new("RGBA", (1080, 1920), (0, 0, 0, 105))
        cd = ImageDraw.Draw(base)
        top, bot = 440, 1480
        if card_style == "glass_card":
            cd.rounded_rectangle([85, top, 995, bot], radius=44, fill=(12, 14, 22, 160), outline=accent + (155,), width=3)
        else:
            cd.rectangle([95, top + 60, 105, bot - 60], fill=accent + (235,))
        cd.text((540, top + 75), post["emotion"].upper(), fill=accent + (255,), font=load_font(28), anchor="mm")
        cd.line([(430, top + 110), (650, top + 110)], fill=accent + (200,), width=3)
        y = top + 200
        for ln in textwrap.wrap(title, width=22):
            cd.text((540, y), ln, fill=(255, 255, 255, 255), font=load_font(54), anchor="mm")
            y += 72
        if body:
            y += 34
            for ln in textwrap.wrap(body, width=28):
                cd.text((540, y), ln, fill=(230, 232, 240, 255), font=load_font(38, italic=True), anchor="mm")
                y += 54
        cd.text((540, 1835), "—  Heartful Quotes  —", fill=(255, 255, 255, 210), font=load_font(26, bold=False), anchor="mm")
        base.save(path)
        return path

    if post["format"] == "pov":
        slides = [(0.0, 3.5, make_card(post["cover"], "", "ov_01.png")), (3.5, DUR, make_card(post["cover"], post["payoff"], "ov_02.png"))]
    else:
        raw_slides = [(post["cover"], "")] + [(f"{n}. {h}", d) for n, h, d in post["points"]] + [("Your Turn", post["cta"])]
        slides = [(i * 3.2, (i + 1) * 3.2, make_card(t_txt, b_txt, f"ov_{i+1:02d}.png")) for i, (t_txt, b_txt) in enumerate(raw_slides)]

    v_in = ["-stream_loop", "-1", "-i", str(bg_mp4)] if bg_mp4 else ["-loop", "1", "-i", "designed_bg.png"]
    v_prep = "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30[bg];" if bg_mp4 else "[0:v]copy[bg];"
    ov_in = sum([["-i", p] for _, _, p in slides], [])
    fc, prev = v_prep, "bg"
    for i, (t0, t1, _) in enumerate(slides):
        nxt = f"v{i+1}"
        fc += f"[{prev}][{i+1}:v]overlay=0:0:enable='between(t,{t0:.2f},{t1:.2f})'[{nxt}];"
        prev = nxt
    a_idx = len(slides) + 1
    fc += f"[{prev}]fade=t=in:st=0:d=0.5,fade=t=out:st={DUR-0.7:.2f}:d=0.7[vout];[{a_idx}:a]afade=t=in:st=0:d=0.4,afade=t=out:st={DUR-1.0:.2f}:d=1.0[aout]"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", *v_in, *ov_in, "-stream_loop", "-1", "-i", str(audio_input),
        "-t", str(DUR), "-filter_complex", fc, "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2", "final_short.mp4"
    ], check=True)

STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
print("Rendered final_short.mp4!")

try:
    if os.getenv("YT_CLIENT_SECRETS") and os.getenv("YT_TOKEN_JSON"):
        Path("client_secrets.json").write_text(os.getenv("YT_CLIENT_SECRETS"), encoding="utf-8")
        Path("token.json").write_text(os.getenv("YT_TOKEN_JSON"), encoding="utf-8")
        creds = Credentials.from_authorized_user_file("token.json", YT_SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        yt = build("youtube", "v3", credentials=creds)
        req = yt.videos().insert(part="snippet,status",
            body={"snippet": {"title": f"{title_clean} #Shorts"[:95], "description": caption, "categoryId": "22"},
                  "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}},
            media_body=MediaFileUpload("final_short.mp4", chunksize=5*1024*1024, resumable=True))
        resp = None
        while resp is None:
            _, resp = req.next_chunk()
        print("[YouTube] PUBLISHED:", resp["id"])
except Exception as e:
    print("[YouTube] ERROR (skipped):", e)

try:
    ig_id, token = os.getenv("IG_USER_ID", "").strip(), os.getenv("META_ACCESS_TOKEN", "").strip()
    if ig_id and token:
        init = requests.post(f"{GRAPH}/{ig_id}/media", data={"media_type": "REELS", "upload_type": "resumable", "caption": caption, "access_token": token}).json()
        cid, uri = init["id"], init["uri"]
        raw = Path("final_short.mp4").read_bytes()
        requests.post(uri, headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(len(raw))}, data=raw).raise_for_status()
        for _ in range(20):
            if requests.get(f"{GRAPH}/{cid}", params={"fields": "status_code", "access_token": token}).json().get("status_code") == "FINISHED":
                break
            time.sleep(4)
        pub = requests.post(f"{GRAPH}/{ig_id}/media_publish", data={"creation_id": cid, "access_token": token}).json()
        print("[Instagram] PUBLISHED:", pub)
except Exception as e:
    print("[Instagram] ERROR (skipped):", e)
