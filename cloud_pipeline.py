import datetime, json, math, os, random, re, subprocess, sys, textwrap, time, wave
import numpy as np
import requests
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

GRAPH = "https://graph.facebook.com/v21.0"
YT_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# 1. Ramp Schedule Gate: Days 1-2 = 2x/day (12:30 & 18:30 IST); Day 3+ = 4x/day
STATE_FILE = Path("schedule_state.json")
state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {
    "start_date": datetime.date.today().isoformat(), "posted_titles": [], "used_bg_ids": [], "last_emotion": "", "last_format": ""
}
state.setdefault("used_bg_ids", [])
day_num = (datetime.date.today() - datetime.date.fromisoformat(state["start_date"])).days + 1
utc_hour = datetime.datetime.now(datetime.timezone.utc).hour
if os.getenv("GITHUB_EVENT_NAME") == "schedule" and day_num <= 2 and utc_hour not in (7, 13):
    print(f"Day {day_num} (2x/day phase): skipping slot at {utc_hour:02d}:00 UTC.")
    sys.exit(0)

# 2. Multi-Format Content Bank (Doodle Illustration + 4-Slide Series + 2-Beat POV)
CONTENT = [
    # --- DOODLE / ILLUSTRATED CONFESSION FORMAT ---
    {"format": "doodle", "emotion": "romantic", "query": "couple sunset anime illustration love",
     "cover": "I don't know what you did to me,\nI just feel at home whenever I'm with you",
     "cta": "Send this to the person who feels like home."},
    {"format": "doodle", "emotion": "trust", "query": "couple night stars sky aesthetic",
     "cover": "You don't need a loud love,\njust someone who stays quiet with you at 2 AM",
     "cta": "Tag or send this to your 2 AM person."},
    {"format": "doodle", "emotion": "romantic", "query": "couple rain umbrella street aesthetic",
     "cover": "Rainy evenings feel warmer\nwhen the right person holds the umbrella",
     "cta": "Send this to someone you want to walk in the rain with."},
    {"format": "doodle", "emotion": "missing", "query": "aesthetic pastel clouds twilight sky",
     "cover": "Even on my busiest days,\nmy mind still finds a quiet second to miss you",
     "cta": "Send this to the person on your mind right now."},
    # --- 4-SLIDE SERIES FORMAT ---
    {"format": "series", "emotion": "trust", "c1": (18, 12, 28), "c2": (64, 34, 62), "accent": (253, 224, 171), "query": "coffee aesthetic cozy",
     "cover": "4 Quiet Signs Someone Truly Loves You",
     "points": [("01", "They remember the small things", "Not just birthdays—what calms you down on a hard day."),
                ("02", "They stay calm when you are upset", "Real love never turns your worst day into a competition."),
                ("03", "Their actions match their promises", "Consistency replaces guessing where you stand."),
                ("04", "They protect your peace in private", "How they speak about you when you are not there says everything.")],
     "cta": "Send this to the person who does #1.\nComment which sign means the most (1-4)."},
    {"format": "series", "emotion": "healing", "c1": (8, 32, 36), "c2": (22, 78, 82), "accent": (153, 246, 228), "query": "ocean waves sunrise",
     "cover": "4 Things Never To Beg For In Love",
     "points": [("01", "Never beg for basic effort", "Someone who wants you makes time, not endless excuses."),
                ("02", "Never beg to be chosen", "You deserve certainty even on ordinary days."),
                ("03", "Never beg for respect", "Love without respect is just attachment in disguise."),
                ("04", "Never beg for honesty", "Real love feels safe—never like being a detective.")],
     "cta": "Save this reminder and send it to someone who needs #2 today."},
    {"format": "series", "emotion": "heartbreak", "c1": (10, 15, 35), "c2": (30, 48, 84), "accent": (186, 230, 253), "query": "rain window night",
     "cover": "4 Hard Truths About Letting Go",
     "points": [("01", "Closure comes from you, not them", "Waiting for an apology only delays your own peace."),
                ("02", "Missing them does not mean go back", "Sometimes you miss the version of them you hoped they were."),
                ("03", "Stop watering dead roots", "If only one person is fighting for it, it is already over."),
                ("04", "Outgrowing someone is not a failure", "Some people arrive to teach you what you deserve.")],
     "cta": "Send this to a friend who needs to hear #3 today.\nSave this for later."},
    # --- 2-BEAT POV HOOK FORMAT ---
    {"format": "pov", "emotion": "heartbreak", "c1": (16, 16, 28), "c2": (48, 42, 74), "accent": (199, 210, 254), "query": "lonely street rain night",
     "cover": "You never realize how heavy silence is...",
     "payoff": "until the person you told everything to becomes a stranger.",
     "cta": "Send this to someone who understands this feeling."},
    {"format": "pov", "emotion": "healing", "c1": (12, 28, 38), "c2": (36, 72, 92), "accent": (167, 243, 208), "query": "calm forest morning mist",
     "cover": "One day you will thank yourself...",
     "payoff": "for walking away from the love that kept costing your peace.",
     "cta": "Save this and send it to a friend who is healing."},
]

# 3. Viral Potential Validator (Scores >= 80/100 + enforces format & emotion rotation)
def viral_score(item):
    score = 30  # strong relatable hook/visual
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
assert best_score >= 80, f"FAIL: Best candidate scored {best_score}/100"

if post["cover"] not in state["posted_titles"]:
    state["posted_titles"].append(post["cover"])
if len(state["posted_titles"]) >= len(CONTENT):
    state["posted_titles"] = [post["cover"]]
state["last_emotion"], state["last_format"] = post["emotion"], post["format"]

title_clean = post["cover"].replace("\n", " ")
caption = f"{title_clean}\n\n{post['cta']}\n\n#lovequotes #relationships #{post['emotion']} #reels #shorts"
pixabay_key = os.getenv("PIXABAY_API_KEY", "").strip()

def load_font(size, bold=True):
    for p in (["/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf" if not bold else "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def fetch_unique_pixabay_image(query):
    if not pixabay_key:
        return None
    for img_type in ("illustration", "photo"):
        res = requests.get("https://pixabay.com/api/",
                           params={"key": pixabay_key, "q": query, "image_type": img_type, "per_page": 20}, timeout=25).json()
        hits = [h for h in res.get("hits", []) if str(h["id"]) not in state["used_bg_ids"]] or res.get("hits", [])
        if hits:
            pick = random.choice(hits)
            state["used_bg_ids"].append(str(pick["id"]))
            state["used_bg_ids"] = state["used_bg_ids"][-100:]
            p = Path("fresh_bg.jpg")
            p.write_bytes(requests.get(pick["largeImageURL"], timeout=40).content)
            print(f"[Pixabay Image] Fetched fresh {img_type} ID {pick['id']}")
            return p
    return None

def fetch_unique_pixabay_video(query):
    if not pixabay_key:
        return None
    res = requests.get("https://pixabay.com/api/videos/", params={"key": pixabay_key, "q": query, "per_page": 20}, timeout=25).json()
    hits = [h for h in res.get("hits", []) if str(h["id"]) not in state["used_bg_ids"]] or res.get("hits", [])
    if hits:
        pick = random.choice(hits)
        state["used_bg_ids"].append(str(pick["id"]))
        state["used_bg_ids"] = state["used_bg_ids"][-100:]
        vids = pick["videos"]
        p = Path("bg.mp4")
        p.write_bytes(requests.get((vids.get("large") or vids.get("medium") or vids.get("small"))["url"], timeout=60).content)
        print(f"[Pixabay Video] Fetched fresh video ID {pick['id']}")
        return p
    return None

# Synthesize warm emotional piano audio
DUR = 9.6 if post["format"] == "doodle" else (11.0 if post["format"] == "pov" else 19.2)
SR = 48000
t = np.linspace(0, DUR, int(SR * DUR), endpoint=False)
chords = [[261.63, 329.63, 392.00], [220.00, 261.63, 329.63], [174.61, 220.00, 261.63], [196.00, 246.94, 293.66]]
audio = np.zeros_like(t)
seg_len = DUR / 4.0
for idx, ch in enumerate(chords):
    mask = (t >= idx * seg_len) & (t < (idx + 1) * seg_len)
    lt = t[mask] - idx * seg_len
    audio[mask] = sum(np.sin(2 * math.pi * f * lt) for f in ch) / 3.0 * np.minimum(1.0, lt / 0.15) * np.exp(-lt * 0.45)
audio = (audio / (np.max(np.abs(audio)) + 1e-9) * 0.65 * 32767).astype(np.int16)
with wave.open("music.wav", "wb") as wf:
    wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR)
    wf.writeframes(np.stack([audio, audio], axis=1).tobytes())

if post["format"] == "doodle":
    img_path = fetch_unique_pixabay_image(post["query"])
    if img_path:
        raw = Image.open(img_path).convert("RGB")
        # Crop cleanly to 9:16 portrait
        w, h = raw.size
        target_ratio = 1080 / 1920
        if w / h > target_ratio:
            nw = int(h * target_ratio)
            raw = raw.crop(((w - nw) // 2, 0, (w + nw) // 2, h))
        else:
            nh = int(w / target_ratio)
            raw = raw.crop((0, (h - nh) // 2, w, (h + nh) // 2))
        bg = raw.resize((1080, 1920), Image.Resampling.LANCZOS).convert("RGBA")
    else:
        bg = Image.new("RGBA", (1080, 1920), (252, 232, 224, 255))

    # Soft pastel sky wash at top so dark-ink quote always reads crisply over ANY fresh image
    sky = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    px = sky.load()
    for y in range(680):
        alpha = int(225 * max(0.0, 1.0 - (y / 680) ** 1.6))
        for x in range(1080):
            px[x, y] = (255, 244, 238, alpha)
    bg = Image.alpha_composite(bg, sky).convert("RGB")

    draw = ImageDraw.Draw(bg)
    f_main, f_sig = load_font(46, bold=False), load_font(28, bold=False)
    y = 240
    for ln in post["cover"].split("\n"):
        draw.text((540, y), ln.strip(), fill=(38, 30, 34), font=f_main, anchor="mm")
        y += 66
    draw.line([(330, y + 25), (495, y + 25)], fill=(70, 58, 62), width=2)
    draw.line([(585, y + 25), (750, y + 25)], fill=(70, 58, 62), width=2)
    hx, hy = 540, y + 25
    draw.polygon([(hx, hy + 14), (hx - 15, hy - 2), (hx - 7, hy - 12), (hx, hy - 5), (hx + 7, hy - 12), (hx + 15, hy - 2)], fill=(214, 69, 80))
    draw.text((540, 1835), "—  Daily Love Notes  —", fill=(255, 255, 255), font=f_sig, anchor="mm")
    bg.save("doodle_frame.png")
    frames = int(DUR * 30)
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", "doodle_frame.png", "-i", "music.wav",
        "-t", str(DUR), "-vf", f"scale=1200:-1,zoompan=z='min(zoom+0.0007,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps=30,fade=t=in:st=0:d=0.5,fade=t=out:st={DUR-0.6:.1f}:d=0.6",
        "-af", f"afade=t=in:st=0:d=0.5,afade=t=out:st={DUR-0.8:.1f}:d=0.8",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2", "final_short.mp4"
    ], check=True)
else:
    accent = tuple(post["accent"])
    bg_mp4 = fetch_unique_pixabay_video(post["query"])
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

    def make_card(title, body="", path="ov.png"):
        base = Image.new("RGBA", (1080, 1920), (0, 0, 0, 95))
        cd = ImageDraw.Draw(base)
        top, bot = 440, 1480
        cd.rounded_rectangle([85, top, 995, bot], radius=44, fill=(12, 14, 22, 160), outline=accent + (150,), width=3)
        cd.text((540, top + 75), post["emotion"].upper(), fill=accent + (255,), font=load_font(28), anchor="mm")
        cd.line([(430, top + 110), (650, top + 110)], fill=accent + (200,), width=3)
        y = top + 200
        for ln in textwrap.wrap(title, width=22):
            cd.text((540, y), ln, fill=(255, 255, 255, 255), font=load_font(54), anchor="mm")
            y += 72
        if body:
            y += 34
            for ln in textwrap.wrap(body, width=28):
                cd.text((540, y), ln, fill=(230, 232, 240, 255), font=load_font(38, bold=False), anchor="mm")
                y += 54
        base.save(path)
        return path

    if post["format"] == "pov":
        slides = [(0.0, 3.5, make_card(post["cover"], "", "ov_01.png")),
                  (3.5, DUR, make_card(post["cover"], post["payoff"], "ov_02.png"))]
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
    fc += f"[{prev}]fade=t=in:st=0:d=0.5,fade=t=out:st={DUR-0.7:.2f}:d=0.7[vout];[{a_idx}:a]afade=t=in:st=0:d=0.6,afade=t=out:st={DUR-1.0:.2f}:d=1.0[aout]"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", *v_in, *ov_in, "-i", "music.wav",
        "-t", str(DUR), "-filter_complex", fc, "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2", "final_short.mp4"
    ], check=True)

STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
print("Rendered final_short.mp4!")

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
