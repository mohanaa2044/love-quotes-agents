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

# 1. Ramp Schedule Gate: Days 1-2 = 2x/day (12:30 & 18:30 IST); Day 3+ = 4x/day
STATE_FILE = Path("schedule_state.json")
state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {
    "start_date": datetime.date.today().isoformat(),
    "posted_titles": [], "used_bg_ids": [], "used_music_sigs": [],
    "last_emotion": "", "last_format": ""
}
for k in ("posted_titles", "used_bg_ids", "used_music_sigs"):
    state.setdefault(k, [])

day_num = (datetime.date.today() - datetime.date.fromisoformat(state["start_date"])).days + 1
utc_hour = datetime.datetime.now(datetime.timezone.utc).hour
if os.getenv("GITHUB_EVENT_NAME") == "schedule" and day_num <= 2 and utc_hour not in (7, 13):
    print(f"Day {day_num} (2x/day phase): skipping slot at {utc_hour:02d}:00 UTC.")
    sys.exit(0)

# 2. Multi-Format Content Bank + Rotating Visual Queries
QUERY_POOL = {
    "romantic":   ["couple sunset silhouette", "cherry blossom aesthetic", "warm candle lights", "golden hour beach walk"],
    "trust":      ["cozy coffee rain window", "starry night couple", "warm fireplace aesthetic", "autumn forest path"],
    "healing":    ["calm ocean waves sunrise", "misty mountain dawn", "sunlight through leaves", "peaceful lake reflection"],
    "heartbreak": ["rainy city night neon", "lonely street rain", "stormy clouds twilight", "raindrops window bokeh"],
    "missing":    ["night driving city lights", "moonlight clouds sky", "twilight city skyline", "train window evening"],
}

CONTENT = [
    {"format": "doodle", "emotion": "romantic",
     "cover": "I don't know what you did to me,\nI just feel at home whenever I'm with you",
     "cta": "Send this to the person who feels like home."},
    {"format": "doodle", "emotion": "trust",
     "cover": "You don't need a loud love,\njust someone who stays quiet with you at 2 AM",
     "cta": "Tag or send this to your 2 AM person."},
    {"format": "doodle", "emotion": "romantic",
     "cover": "Rainy evenings feel warmer\nwhen the right person holds the umbrella",
     "cta": "Send this to someone you want to walk in the rain with."},
    {"format": "doodle", "emotion": "missing",
     "cover": "Even on my busiest days,\nmy mind still finds a quiet second to miss you",
     "cta": "Send this to the person on your mind right now."},
    {"format": "series", "emotion": "trust", "c1": (18, 12, 28), "c2": (64, 34, 62), "accent": (253, 224, 171),
     "cover": "4 Quiet Signs Someone Truly Loves You",
     "points": [("01", "They remember the small things", "Not just birthdays—what calms you down on a hard day."),
                ("02", "They stay calm when you are upset", "Real love never turns your worst day into a competition."),
                ("03", "Their actions match their promises", "Consistency replaces guessing where you stand."),
                ("04", "They protect your peace in private", "How they speak about you when you are not there says everything.")],
     "cta": "Send this to the person who does #1.\nComment which sign means the most (1-4)."},
    {"format": "series", "emotion": "healing", "c1": (8, 32, 36), "c2": (22, 78, 82), "accent": (153, 246, 228),
     "cover": "4 Things Never To Beg For In Love",
     "points": [("01", "Never beg for basic effort", "Someone who wants you makes time, not endless excuses."),
                ("02", "Never beg to be chosen", "You deserve certainty even on ordinary days."),
                ("03", "Never beg for respect", "Love without respect is just attachment in disguise."),
                ("04", "Never beg for honesty", "Real love feels safe—never like being a detective.")],
     "cta": "Save this reminder and send it to someone who needs #2 today."},
    {"format": "series", "emotion": "heartbreak", "c1": (10, 15, 35), "c2": (30, 48, 84), "accent": (186, 230, 253),
     "cover": "4 Hard Truths About Letting Go",
     "points": [("01", "Closure comes from you, not them", "Waiting for an apology only delays your own peace."),
                ("02", "Missing them does not mean go back", "Sometimes you miss the version of them you hoped they were."),
                ("03", "Stop watering dead roots", "If only one person is fighting for it, it is already over."),
                ("04", "Outgrowing someone is not a failure", "Some people arrive to teach you what you deserve.")],
     "cta": "Send this to a friend who needs to hear #3 today.\nSave this for later."},
    {"format": "pov", "emotion": "heartbreak", "c1": (16, 16, 28), "c2": (48, 42, 74), "accent": (199, 210, 254),
     "cover": "You never realize how heavy silence is...",
     "payoff": "until the person you told everything to becomes a stranger.",
     "cta": "Send this to someone who understands this feeling."},
    {"format": "pov", "emotion": "healing", "c1": (12, 28, 38), "c2": (36, 72, 92), "accent": (167, 243, 208),
     "cover": "One day you will thank yourself...",
     "payoff": "for walking away from the love that kept costing your peace.",
     "cta": "Save this and send it to a friend who is healing."},
    {"format": "pov", "emotion": "missing", "c1": (22, 14, 38), "c2": (68, 42, 94), "accent": (233, 213, 255),
     "cover": "Some people stay in your heart...",
     "payoff": "long after they stop appearing in your daily life.",
     "cta": "Send this to someone awake thinking about the past."},
]

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

title_clean = post["cover"].replace("\n", " ")
caption = f"{title_clean}\n\n{post['cta']}\n\n#lovequotes #relationships #{post['emotion']} #reels #shorts"
pixabay_key = os.getenv("PIXABAY_API_KEY", "").strip()
query = random.choice(QUERY_POOL[post["emotion"]])

def load_font(size, bold=True):
    for p in (["/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf" if not bold else "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def fetch_unique_pixabay_image(q):
    if not pixabay_key:
        return None
    for img_type in ("illustration", "photo"):
        res = requests.get("https://pixabay.com/api/", params={"key": pixabay_key, "q": q, "image_type": img_type, "per_page": 25}, timeout=25).json()
        hits = [h for h in res.get("hits", []) if str(h["id"]) not in state["used_bg_ids"]] or res.get("hits", [])
        if hits:
            pick = random.choice(hits)
            state["used_bg_ids"] = (state["used_bg_ids"] + [str(pick["id"])])[-500:]
            p = Path("fresh_bg.jpg")
            p.write_bytes(requests.get(pick["largeImageURL"], timeout=40).content)
            print(f"[Pixabay Image] Unique {img_type} ID {pick['id']} ({q})")
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

# 3. Unique Hooked Music Engine (Never repeats the same track/progression)
DUR = 9.6 if post["format"] == "doodle" else (11.0 if post["format"] == "pov" else 19.2)
music_dir = Path("music")
mp3s = sorted(music_dir.glob("*.mp3")) if music_dir.exists() else []
unused_mp3s = [m for m in mp3s if m.name not in state["used_music_sigs"]]
audio_input = random.choice(unused_mp3s or mp3s) if mp3s else None

if audio_input:
    state["used_music_sigs"] = (state["used_music_sigs"] + [audio_input.name])[-20:]
    print(f"[Audio] Using unique MP3: {audio_input.name}")
else:
    # Procedural Hook-to-Drop Synth: varies key, progression, BPM, timbre, and ambience every run
    PROGRESSIONS = [
        ("Am-F-C-G",   [[57,60,64,69], [53,57,60,64], [48,55,60,64], [55,59,62,67]], [76,74,72,71,72,76,79,76]),
        ("Fmaj-G-Em-Am", [[53,57,60,64], [55,59,62,67], [52,55,59,64], [57,60,64,69]], [72,74,76,79,76,74,72,69]),
        ("Dm-Bb-F-C",  [[50,53,57,62], [46,50,53,58], [53,57,60,65], [48,52,55,60]], [74,72,70,69,70,74,77,74]),
        ("Em-C-G-D",   [[52,55,59,64], [48,52,55,60], [55,59,62,67], [50,54,57,62]], [76,74,71,67,71,74,78,76]),
    ]
    TIMBRES = ["felt_piano", "rhodes_bell", "warm_strings"]
    BPMS = [66, 72, 78, 84]
    SHIFTS = [-2, 0, 2, 4]  # semitone transpose for unique key every video

    for _ in range(12):
        prog_name, prog, mel = random.choice(PROGRESSIONS)
        timbre, bpm, shift = random.choice(TIMBRES), random.choice(BPMS), random.choice(SHIFTS)
        sig = f"{prog_name}_{timbre}_{bpm}_{shift}"
        if sig not in state["used_music_sigs"]:
            break
    state["used_music_sigs"] = (state["used_music_sigs"] + [sig])[-30:]

    SR = 48000
    N = int(SR * DUR)
    L, R = np.zeros(N), np.zeros(N)
    beat = 60.0 / bpm
    def mf(m): return 440.0 * (2.0 ** (((m + shift) - 69) / 12.0))
    def synth_note(buf, start_s, freq, dur_s, vel):
        i0 = int(start_s * SR)
        n = min(int(dur_s * SR), N - i0)
        if n <= 0: return
        lt = np.linspace(0, n / SR, n, endpoint=False)
        if timbre == "felt_piano":
            sig = (np.sin(2*np.pi*freq*lt) + 0.25*np.sin(4*np.pi*freq*lt)*np.exp(-lt*3.0)) * np.minimum(1.0, lt/0.02) * np.exp(-lt*1.1)
        elif timbre == "rhodes_bell":
            sig = (np.sin(2*np.pi*freq*lt) + 0.35*np.sin(6*np.pi*freq*lt)*np.exp(-lt*5.0)) * np.minimum(1.0, lt/0.01) * np.exp(-lt*1.4)
        else:
            sig = (0.6*np.sin(2*np.pi*freq*lt) + 0.4*np.sin(2*np.pi*(freq*1.004)*lt)) * np.minimum(1.0, lt/0.25) * np.exp(-lt*0.55)
        buf[i0:i0+n] += sig * vel

    step_t = beat * 0.75
    steps = int(DUR / step_t)
    for step in range(steps):
        t0 = step * step_t
        ch = prog[(step // 4) % len(prog)]
        for j, m in enumerate(ch):
            synth_note(L if j % 2 == 0 else R, t0 + j * (beat * 0.18), mf(m), beat * 2.0, 0.20)
            synth_note(R if j % 2 == 0 else L, t0 + j * (beat * 0.18), mf(m), beat * 2.0, 0.14)
        m_note = mel[step % len(mel)]
        synth_note(L, t0, mf(m_note), beat * 1.6, 0.26)
        synth_note(R, t0, mf(m_note), beat * 1.6, 0.26)
        # Hook Drop at 3.2s: deep sub-bass + soft lo-fi heartbeat kick!
        if t0 >= 3.1:
            bf = mf(ch[0] - 24)
            synth_note(L, t0, bf, beat * 2.2, 0.34)
            synth_note(R, t0, bf, beat * 2.2, 0.34)
            if step % 2 == 0:
                i0 = int(t0 * SR)
                kn = min(int(0.18 * SR), N - i0)
                if kn > 0:
                    kt = np.linspace(0, kn / SR, kn, endpoint=False)
                    kick = np.sin(2 * np.pi * (95 * np.exp(-kt * 18) + 38) * kt) * np.exp(-kt * 16) * 0.38
                    L[i0:i0+kn] += kick; R[i0:i0+kn] += kick

    stereo = np.stack([L, R], axis=1)
    if post["emotion"] in ("heartbreak", "missing"):
        rng = np.random.default_rng(int(time.time()))
        rain = rng.normal(0, 1, (N, 2))
        ker = np.ones(16) / 16.0
        stereo[:, 0] += np.convolve(rain[:, 0], ker, mode="same") * 0.028
        stereo[:, 1] += np.convolve(rain[:, 1], ker, mode="same") * 0.028
    for ms, g in [(90, 0.32), (165, 0.18)]:
        sh = int(SR * ms / 1000)
        if sh < N:
            stereo[sh:, 0] += stereo[:-sh, 1] * g
            stereo[sh:, 1] += stereo[:-sh, 0] * g
    stereo = (stereo / (np.max(np.abs(stereo)) + 1e-9) * 0.78 * 32767).astype(np.int16)
    with wave.open("music.wav", "wb") as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR)
        wf.writeframes(stereo.tobytes())
    audio_input = Path("music.wav")
    print(f"[Audio] Synthesized unique hooked track: {sig}")

# 4. Render Unique Visual Style + Motion
if post["format"] == "doodle":
    img_path = fetch_unique_pixabay_image(query)
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
        bg = Image.new("RGBA", (1080, 1920), (252, 232, 224, 255))
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
    draw.text((540, 1835), "—  Heartful Quotes  —", fill=(255, 255, 255), font=f_sig, anchor="mm")
    bg.save("doodle_frame.png")
    frames = int(DUR * 30)
    motion = random.choice([
        f"scale=1200:-1,zoompan=z='min(zoom+0.0007,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps=30",
        f"scale=1200:-1,zoompan=z='1.08-0.0007*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps=30",
        f"scale=1200:-1,zoompan=z='1.08':x='(iw-iw/zoom)*(on/{frames})':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps=30",
    ])
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", "doodle_frame.png", "-stream_loop", "-1", "-i", str(audio_input),
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
                cd.text((540, y), ln, fill=(230, 232, 240, 255), font=load_font(38, bold=False), anchor="mm")
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
