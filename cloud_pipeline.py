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
    "start_date": datetime.date.today().isoformat(), "posted_titles": [], "last_emotion": ""
}
day_num = (datetime.date.today() - datetime.date.fromisoformat(state["start_date"])).days + 1
utc_hour = datetime.datetime.now(datetime.timezone.utc).hour
if os.getenv("GITHUB_EVENT_NAME") == "schedule" and day_num <= 2 and utc_hour not in (7, 13):
    print(f"Day {day_num} (2x/day phase): skipping slot at {utc_hour:02d}:00 UTC.")
    sys.exit(0)

# 2. High-Shareability Relationship Series Bank
SERIES = [
    {"emotion": "trust", "c1": (18, 12, 28), "c2": (64, 34, 62), "accent": (253, 224, 171), "query": "coffee aesthetic cozy",
     "cover": "4 Quiet Signs Someone Truly Loves You",
     "points": [("01", "They remember the small things", "Not just birthdays—what calms you down on a hard day."),
                ("02", "They stay calm when you are upset", "Real love never turns your worst day into a competition."),
                ("03", "Their actions match their promises", "Consistency replaces guessing where you stand."),
                ("04", "They protect your peace in private", "How they speak about you when you are not there says everything.")],
     "cta": "Send this to the person who does #1.\nComment which sign means the most (1-4)."},
    {"emotion": "heartbreak", "c1": (10, 15, 35), "c2": (30, 48, 84), "accent": (186, 230, 253), "query": "rain window night",
     "cover": "4 Hard Truths About Letting Go",
     "points": [("01", "Closure comes from you, not them", "Waiting for an apology only delays your own peace."),
                ("02", "Missing them does not mean go back", "Sometimes you miss the version of them you hoped they were."),
                ("03", "Stop watering dead roots", "If only one person is fighting for it, it is already over."),
                ("04", "Outgrowing someone is not a failure", "Some people arrive to teach you what you deserve.")],
     "cta": "Send this to a friend who needs to hear #3 today.\nSave this for later."},
    {"emotion": "healing", "c1": (8, 32, 36), "c2": (22, 78, 82), "accent": (153, 246, 228), "query": "ocean waves sunrise",
     "cover": "4 Things Never To Beg For In Love",
     "points": [("01", "Never beg for basic effort", "Someone who wants you makes time, not endless excuses."),
                ("02", "Never beg to be chosen", "You deserve certainty even on ordinary days."),
                ("03", "Never beg for respect", "Love without respect is just attachment in disguise."),
                ("04", "Never beg for honesty", "Real love feels safe—never like being a detective.")],
     "cta": "Save this reminder and send it to someone who needs #2 today."},
    {"emotion": "romantic", "c1": (42, 10, 32), "c2": (110, 26, 68), "accent": (255, 182, 193), "query": "couple sunset aesthetic",
     "cover": "4 Green Flags Of A Healthy Relationship",
     "points": [("01", "You can be 100% yourself", "No walking on eggshells, no shrinking your joy."),
                ("02", "Arguments end in understanding", "It is always you and them versus the problem."),
                ("03", "Silence feels comfortable", "Sitting together doing nothing still feels like home."),
                ("04", "They cheer for your growth", "True partners are always your loudest fan.")],
     "cta": "Send this to the person who feels like home.\nComment your favorite green flag (1-4)."},
    {"emotion": "missing", "c1": (18, 12, 46), "c2": (62, 38, 112), "accent": (216, 180, 254), "query": "night city lights bokeh",
     "cover": "4 Things Nobody Tells You About Missing Someone",
     "points": [("01", "It hits hardest in quiet moments", "You stay busy all day, then one song brings everything back."),
                ("02", "You miss how they made you feel", "Often you ache for the safety, not just the person."),
                ("03", "Silence is still an answer", "Not texting back tells you everything you need to know."),
                ("04", "Healing happens in tiny steps", "One day you will wake up and it will hurt a little less.")],
     "cta": "Send this to someone awake thinking about the past.\nSave this for midnight."},
    {"emotion": "trust", "c1": (30, 18, 14), "c2": (86, 52, 34), "accent": (253, 230, 138), "query": "golden hour nature",
     "cover": "4 Rules For A Relationship That Lasts",
     "points": [("01", "Never let ego last longer than love", "Apologize fast when you care more about the bond than winning."),
                ("02", "Keep private problems private", "Protect your relationship from outside noise."),
                ("03", "Keep dating each other", "Effort should not stop once you feel comfortable."),
                ("04", "Listen to understand, not reply", "Most fights end the moment someone truly feels heard.")],
     "cta": "Send this to your forever person.\nWhich rule matters most (1-4)?"},
    {"emotion": "healing", "c1": (12, 28, 38), "c2": (36, 72, 92), "accent": (167, 243, 208), "query": "calm forest morning mist",
     "cover": "4 Signs You Are Finally Healing",
     "points": [("01", "Their name stops hurting", "You can hear about them without your whole mood changing."),
                ("02", "You stop checking their status", "Your peace becomes more valuable than their updates."),
                ("03", "You forgive yourself", "You realize you did the best you could with what you knew."),
                ("04", "You protect your energy", "Not everyone deserves front-row access to your heart.")],
     "cta": "Send this to a friend who is getting stronger every day.\nComment which sign you feel (1-4)."},
    {"emotion": "romantic", "c1": (48, 12, 28), "c2": (118, 36, 62), "accent": (254, 205, 211), "query": "romantic candles evening",
     "cover": "4 Small Habits That Make Love Stronger",
     "points": [("01", "Texting when you arrive safely", "Small check-ins say I care without needing big speeches."),
                ("02", "Holding hands during hard talks", "Touch reminds both hearts you are on the same team."),
                ("03", "Saying thank you for daily things", "Never let appreciation fade just because it feels routine."),
                ("04", "Choosing patience over pride", "A calm tone heals faster than winning an argument.")],
     "cta": "Send this to someone you want to build #1-#4 with.\nSave for later."},
    {"emotion": "heartbreak", "c1": (16, 16, 28), "c2": (48, 42, 74), "accent": (199, 210, 254), "query": "lonely street rain night",
     "cover": "4 Red Flags We Ignore When In Love",
     "points": [("01", "Hot and cold attention", "Confusion is not chemistry—it is inconsistency."),
                ("02", "Every concern becomes your fault", "Someone who loves you listens instead of deflecting."),
                ("03", "Secretly hiding the relationship", "Real love never asks you to stay a secret."),
                ("04", "Empty promises without change", "An apology without changed behavior is just manipulation.")],
     "cta": "Send this to a friend who needs a gentle wake-up call.\nWhich red flag is hardest to spot (1-4)?"},
    {"emotion": "missing", "c1": (22, 16, 40), "c2": (72, 48, 98), "accent": (233, 213, 255), "query": "moonlight night sky clouds",
     "cover": "4 Unspoken Feelings Late At Night",
     "points": [("01", "Waiting for one specific notification", "Your phone lights up and your heart still hopes it is them."),
                ("02", "Re-reading old messages", "Visiting memories you know you cannot live in anymore."),
                ("03", "Smiling at strangers who remind you", "For one split second, you forget they are not here."),
                ("04", "Wishing them well from afar", "Loving someone quietly even when your paths split.")],
     "cta": "Send this to someone who understands late-night thoughts.\nComment 1, 2, 3, or 4."},
]

# 3. Viral Potential Validator (Must score >= 80/100 to pass)
def viral_score(item):
    score, reasons = 0, []
    words_cover = len(item["cover"].split())
    if re.match(r"^\d+\s", item["cover"]) and words_cover <= 10:
        score += 30
    else:
        reasons.append("Weak hook")
    if any(k in item["cta"].lower() for k in ("send", "tag", "share")):
        score += 30
    else:
        reasons.append("No DM-share CTA")
    if len(item["points"]) == 4 and all(4 <= len(d.split()) <= 18 for _, _, d in item["points"]):
        score += 20
    else:
        reasons.append("Pacing too dense")
    if item["cover"] not in state["posted_titles"] and item["emotion"] != state.get("last_emotion", ""):
        score += 20
    elif item["cover"] not in state["posted_titles"]:
        score += 10
    return score, reasons

ranked = sorted(((viral_score(s)[0], s) for s in SERIES), key=lambda x: x[0], reverse=True)
best_score, post = ranked[0]
print(f"[Viral Validator] Selected: '{post['cover']}' ({post['emotion']}) | Score: {best_score}/100")
assert best_score >= 80, f"FAIL: Best candidate scored only {best_score}/100 (below 80 threshold)."

if post["cover"] not in state["posted_titles"]:
    state["posted_titles"].append(post["cover"])
if len(state["posted_titles"]) >= len(SERIES):
    state["posted_titles"] = [post["cover"]]  # Reset cycle cleanly once all series have run
state["last_emotion"] = post["emotion"]
STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

caption = f"{post['cover']}\n\n{post['cta']}\n\n#lovequotes #relationshipadvice #{post['emotion']} #reels #shorts"
emotion, accent = post["emotion"], tuple(post["accent"])

def load_font(size, bold=True):
    for p in (["/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def make_designed_bg(W, H, c1, c2, acc):
    img = Image.new("RGBA", (W, H))
    px = img.load()
    for y in range(H):
        t = y / H
        r, g, b = int(c1[0]+(c2[0]-c1[0])*t), int(c1[1]+(c2[1]-c1[1])*t), int(c1[2]+(c2[2]-c1[2])*t)
        for x in range(W):
            px[x, y] = (r, g, b, 255)
    orbs = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(orbs)
    for cx, cy, rad, alpha in [(int(W*0.18), int(H*0.22), 240, 60), (int(W*0.84), int(H*0.74), 290, 70), (int(W*0.72), int(H*0.18), 160, 45)]:
        od.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=acc + (alpha,))
    return Image.alpha_composite(img, orbs.filter(ImageFilter.GaussianBlur(70)))

def render_overlay(W, H, acc, title, body=""):
    base = Image.new("RGBA", (W, H), (0, 0, 0, 95))
    card = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card)
    pad_x, top, bot = 85, int(H * 0.23), int(H * 0.77)
    cd.rounded_rectangle([pad_x, top, W - pad_x, bot], radius=44, fill=(12, 14, 22, 155), outline=acc + (145,), width=3)
    img = Image.alpha_composite(base, card)
    draw = ImageDraw.Draw(img)
    tag_f, big_f, body_f = load_font(28), load_font(56), load_font(38, bold=False)
    draw.text((W // 2, top + 75), emotion.upper(), fill=acc + (255,), font=tag_f, anchor="mm")
    draw.line([(W // 2 - 110, top + 110), (W // 2 + 110, top + 110)], fill=acc + (200,), width=3)
    y = top + 200
    for ln in textwrap.wrap(title, width=22):
        draw.text((W // 2, y), ln, fill=(255, 255, 255, 255), font=big_f, anchor="mm")
        y += 72
    if body:
        y += 34
        for ln in textwrap.wrap(body, width=28):
            draw.text((W // 2, y), ln, fill=(230, 232, 240, 255), font=body_f, anchor="mm")
            y += 54
    return img

bg_mp4 = None
pixabay_key = os.getenv("PIXABAY_API_KEY", "").strip()
if pixabay_key:
    try:
        res = requests.get("https://pixabay.com/api/videos/", params={"key": pixabay_key, "q": post["query"], "per_page": 10}, timeout=25).json()
        hits = res.get("hits", [])
        if hits:
            pick = random.choice(hits)["videos"]
            link = (pick.get("large") or pick.get("medium") or pick.get("small"))["url"]
            bg_mp4 = Path("bg.mp4")
            bg_mp4.write_bytes(requests.get(link, timeout=60).content)
            print("Downloaded Pixabay HD background.")
    except Exception as e:
        print("Pixabay fallback to designed bokeh background:", e)

if not bg_mp4:
    make_designed_bg(1080, 1920, post["c1"], post["c2"], accent).convert("RGB").save("designed_bg.png")

SR, DUR = 48000, 19.2
t = np.linspace(0, DUR, int(SR * DUR), endpoint=False)
chords = [[261.63, 329.63, 392.00], [220.00, 261.63, 329.63], [174.61, 220.00, 261.63], [196.00, 246.94, 293.66]]
audio = np.zeros_like(t)
for idx, ch in enumerate(chords):
    mask = (t >= idx * 4.8) & (t < (idx + 1) * 4.8)
    lt = t[mask] - idx * 4.8
    audio[mask] = sum(np.sin(2 * math.pi * f * lt) for f in ch) / 3.0 * np.minimum(1.0, lt / 0.15) * np.exp(-lt * 0.45)
audio = (audio / (np.max(np.abs(audio)) + 1e-9) * 0.65 * 32767).astype(np.int16)
with wave.open("music.wav", "wb") as wf:
    wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR)
    wf.writeframes(np.stack([audio, audio], axis=1).tobytes())

slides = [(post["cover"], "")] + [(f"{n}. {h}", d) for n, h, d in post["points"]] + [("Your Turn", post["cta"])]
SLIDE_SEC, overlays = 3.2, []
for i, (t_txt, b_txt) in enumerate(slides):
    p = f"ov_{i+1:02d}.png"
    render_overlay(1080, 1920, accent, t_txt, b_txt).save(p)
    overlays.append(p)

v_in = ["-stream_loop", "-1", "-i", str(bg_mp4)] if bg_mp4 else ["-loop", "1", "-i", "designed_bg.png"]
v_prep = "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30[bg];" if bg_mp4 else "[0:v]scale=1200:-1,zoompan=z='min(zoom+0.0006,1.10)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=576:s=1080x1920:fps=30[bg];"
ov_in = sum([["-i", p] for p in overlays], [])
fc, prev = v_prep, "bg"
for i in range(len(overlays)):
    nxt = f"v{i+1}"
    fc += f"[{prev}][{i+1}:v]overlay=0:0:enable='between(t,{i*SLIDE_SEC:.2f},{(i+1)*SLIDE_SEC:.2f})'[{nxt}];"
    prev = nxt
a_idx = len(overlays) + 1
fc += f"[{prev}]fade=t=in:st=0:d=0.5,fade=t=out:st={DUR-0.7:.2f}:d=0.7[vout];[{a_idx}:a]afade=t=in:st=0:d=0.6,afade=t=out:st={DUR-1.0:.2f}:d=1.0[aout]"

subprocess.run([
    "ffmpeg", "-y", "-loglevel", "error", *v_in, *ov_in, "-i", "music.wav",
    "-t", str(DUR), "-filter_complex", fc, "-map", "[vout]", "-map", "[aout]",
    "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2", "final_short.mp4"
], check=True)
print("Rendered final_short.mp4!")

if os.getenv("YT_CLIENT_SECRETS") and os.getenv("YT_TOKEN_JSON"):
    Path("client_secrets.json").write_text(os.getenv("YT_CLIENT_SECRETS"), encoding="utf-8")
    Path("token.json").write_text(os.getenv("YT_TOKEN_JSON"), encoding="utf-8")
    creds = Credentials.from_authorized_user_file("token.json", YT_SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    yt = build("youtube", "v3", credentials=creds)
    req = yt.videos().insert(part="snippet,status",
        body={"snippet": {"title": f"{post['cover']} #Shorts"[:95], "description": caption, "categoryId": "22"},
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
