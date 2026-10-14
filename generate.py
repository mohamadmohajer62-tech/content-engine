import os, csv, re, sys, time, base64, io, random, math
import html as htmllib
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

WP = "https://mohammadmohajer.ir"
AUTH = (os.environ["WP_USER"], os.environ["WP_APP_PASSWORD"])
SYSTEM = open("prompt.md", encoding="utf-8").read()
SYSTEM = re.sub(r"^- طول:.*$", "", SYSTEM, flags=re.M)
GAP = os.environ.get("GAPGPT_API_KEY", "").strip()
OR_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
IMG_MODEL = os.environ.get("IMAGE_MODEL", "").strip()
IMG_SIZE = os.environ.get("IMAGE_SIZE", "1536x1024").strip() or "1536x1024"
GAP_BASE = "https://api.gapgpt.app/v1"
MAKE_PDF = os.environ.get("MAKE_PDF", "1").strip() != "0"
MAGAZINE_NAME = "مجله رشد کسب‌وکار"
MAGAZINE_URL = os.environ.get("MAGAZINE_URL", "").strip() or "https://mohammadmohajer.ir/"
AUTHOR_LINE = "محمد مهاجر | استراتژیست رشد کسب‌وکار"
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
BALE_TOKEN = os.environ.get("BALE_BOT_TOKEN", "").strip()
BALE_CHAT = os.environ.get("BALE_CHAT_ID", "").strip()

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (compatible; ContentEngine/1.0; +https://mohammadmohajer.ir)"})
S.mount("https://", HTTPAdapter(max_retries=Retry(total=5, connect=5, read=4, backoff_factor=5,
                                                   status_forcelist=[502, 503, 504])))

IMG_STYLE = ("Clean professional flat business illustration, bold simple shapes, soft depth, deep navy and warm orange palette, "
             "one clear central metaphor object, generous empty space, wide 3:2 composition. "
             "No text, no letters, no numbers, no logos.")
try:
    _st = open("image-style.txt", encoding="utf-8").read().strip()
    if _st:
        IMG_STYLE = _st
except Exception:
    pass

MAX_W = 1200
MAX_KB = 150


def fill(_tpl, **kw):
    for k, v in kw.items():
        _tpl = _tpl.replace("@@%s@@" % k, str(v))
    return _tpl


def fa(n):
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def esc(t):
    return htmllib.escape(str(t).strip(), quote=True)


def plain(h, n=900):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h)).strip()[:n]


def grab(text, key):
    m = re.search(r"^%s\s*[:：]\s*(.+)$" % key, text, re.M)
    return m.group(1).strip() if m else ""


def clean(t):
    t = re.sub(r"```(html)?", "", t).strip()
    t = re.sub(r"^#{2,4}\s*(.+)$", r"<h3>\1</h3>", t, flags=re.M)
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"</?strong>", "", t)
    return t.replace("\u06d5", "ه")


# ---------------- ارتباط با وردپرس ----------------
def wp(method, url, tries=5, **kw):
    kw["timeout"] = max(kw.get("timeout", 0), 90)
    last = None
    for i in range(tries):
        try:
            r = S.request(method, url, **kw)
            _ = r.content
            if r.status_code in (502, 503, 504, 524) and i < tries - 1:
                print("WP %s status %s, retry %d/%d" % (method, r.status_code, i + 1, tries))
                time.sleep(15 * (i + 1))
                continue
            return r
        except requests.exceptions.RequestException as e:
            last = e
            print("WP %s error %s, retry %d/%d" % (method, type(e).__name__, i + 1, tries))
            time.sleep(15 * (i + 1))
    raise last


# ---------------- مدل متن ----------------
def chat(url, key, model, user, max_tokens, system=None):
    body = {"model": model, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system or SYSTEM},
                         {"role": "user", "content": user}]}
    for attempt in range(3):
        r = requests.post(url, headers={"Authorization": "Bearer " + key}, json=body, timeout=300)
        if r.status_code == 429:
            print("[%s] rate-limited, waiting 40s" % model)
            time.sleep(40)
            continue
        if r.status_code != 200:
            print("[%s] status %s %s" % (model, r.status_code, r.text[:150]))
            return ""
        return r.json()["choices"][0]["message"].get("content") or ""
    return ""


def free_models():
    data = requests.get("https://openrouter.ai/api/v1/models", timeout=30).json()["data"]
    bad = ["code", "coder", "lyria", "clip", "safety", "guard", "embed", "audio", "image",
           "vision", "omni", "agent", "stealth"]
    out = []
    for m in data:
        p = m.get("pricing", {})
        try:
            free = float(p.get("prompt", "1")) == 0 and float(p.get("completion", "1")) == 0
        except Exception:
            free = False
        if free and not m["id"].startswith("openrouter/") and not any(b in m["id"].lower() for b in bad) \
                and (m.get("context_length") or 0) >= 16000:
            out.append(m["id"])
    pref = ["gemma", "llama", "qwen", "deepseek", "mistral", "gpt-oss"]
    out.sort(key=lambda i: (not any(k in i.lower() for k in pref), i))
    return out


def ask(user, max_tokens, system=None, min_len=50):
    if GAP:
        t = chat(GAP_BASE + "/chat/completions", GAP, MODEL, user, max_tokens, system)
        if len(t) > min_len:
            print("[GapGPT]", MODEL, "OK")
            return t
        print("GapGPT failed, trying OpenRouter free models.")
    if not OR_KEY:
        sys.exit("هیچ کلیدی برای مدل پیدا نشد.")
    for m in free_models()[:6]:
        t = chat("https://openrouter.ai/api/v1/chat/completions", OR_KEY, m, user, max_tokens, system)
        if len(t) > min_len:
            print("[%s] OK" % m)
            return t
    sys.exit("هیچ مدلی پاسخ نداد.")


# ---------------- تصویر شاخص ----------------
def extract_image(j):
    try:
        d = j["data"][0]
        if d.get("b64_json"):
            return base64.b64decode(d["b64_json"])
        if d.get("url"):
            return requests.get(d["url"], timeout=120).content
    except Exception:
        pass
    try:
        msg = j["choices"][0]["message"]
    except Exception:
        return None
    cands = []
    for im in (msg.get("images") or []):
        u = im.get("image_url") if isinstance(im, dict) else im
        cands.append(u.get("url") if isinstance(u, dict) else u)
    c = msg.get("content")
    if isinstance(c, list):
        for p in c:
            if isinstance(p, dict) and p.get("image_url"):
                u = p["image_url"]
                cands.append(u.get("url") if isinstance(u, dict) else u)
    elif isinstance(c, str):
        cands += re.findall(r"data:image/[a-zA-Z+]+;base64,[A-Za-z0-9+/=]+", c)
        cands += re.findall(r"!\[[^\]]*\]\((https?://[^)\s]+)\)", c)
        cands += re.findall(r"(https?://\S+?\.(?:png|jpg|jpeg|webp))", c)
    for u in cands:
        if not u:
            continue
        if u.startswith("data:"):
            return base64.b64decode(u.split("base64,", 1)[1])
        if u.startswith("http"):
            return requests.get(u, timeout=120).content
    return None


METAPHORS = [
    (["بازار هدف", "مشتری ایده‌آل", "مشتری هدف"], "a target with tiny customer figurines standing on its rings and one arrow near the center", "target"),
    (["هدف‌گذاری", "اهداف", "شاخص", "KPI"], "a classic dartboard with one dart in the bullseye, small bar-chart cards on a desk beside it", "target"),
    (["رقابت", "رقبا", "رقابتی", "تمایز"], "a chessboard seen from a low angle with a white knight facing dark pieces", "rook"),
    (["قیف", "لید", "سرنخ", "نرخ تبدیل", "تبدیل"], "a glass funnel pouring small coins and tiny customer figurines into a basket", "funnel"),
    (["تحلیل", "داده", "SWOT", "داشبورد", "پایش", "اندازه", "سئو"], "a large magnifying glass over a bar chart with a rising line", "magnifier"),
    (["استراتژی", "نقشه", "مسیر", "جهت", "برنامه"], "a brass compass resting on an unfolded map with a small flag marker", "compass"),
    (["رشد", "نگهداشت", "وفاداری", "حفظ", "سیستم"], "a small plant growing out of a stack of coins on a staircase", "stairs"),
    (["فروش", "اعتراض", "قیمت", "پیگیری"], "a shop counter with a cash register, a shopping bag and a rising sales chart on the wall", "funnel"),
    (["محتوا", "تقویم", "نوشتن", "کپی"], "an open notebook with a pen, a monthly calendar and a small lamp on a wooden desk", "stairs"),
    (["تصمیم", "سوگیری", "ذهنیت"], "a balance scale weighing a lightbulb against a stack of coins, with a signpost at a crossroads behind it", "magnifier"),
    (["مشتری", "بازار"], "a group of tiny customer figurines walking toward a shop front along a path lit by warm lamps", "stairs"),
    (["ارزش پیشنهادی", "ارزش"], "a gift box with an orange ribbon on a pedestal with soft spotlight", "target"),
]


def pick_metaphor(title, kw):
    text = title + " " + kw
    for words, desc, icon in METAPHORS:
        if any(w in text for w in words):
            return desc, icon
    return "", "stairs"


ART_SYSTEM = ("You are an art director for a Persian business-strategy blog. "
              "You write precise image briefs in English for an AI image generator.")


def art_brief(title, context, hint=""):
    use = ("Use this metaphor as the main object: %s. " % hint) if hint else (
        "Choose ONE clear visual metaphor OBJECT tied to the article's core concept "
        "(dartboard for goals, chessboard for competition, compass for strategy, funnel for sales funnels, "
        "magnifying glass over a chart for analysis, scale for decisions, stairs for a roadmap). ")
    q = ("Article title (Persian): %s\nArticle summary (Persian): %s\n\n"
         "Write ONE paragraph (45-70 words, English) describing a cover image for this article. %s"
         "Add 2-4 specific supporting details that tie the object to this exact topic (small shop, customers, coins, calendar, charts). "
         "Describe the main object, the supporting details, the background, the composition and the lighting. "
         "The picture must contain no text, letters, numbers, logos or readable signs. "
         "If people appear they should look Iranian, but prefer an object-only composition. "
         "Return only the paragraph." % (title, context, use))
    out = ask(q, 400, ART_SYSTEM)
    out = re.sub(r"\s+", " ", out).strip().strip('"')
    return out if len(out) > 40 else ""


def make_image(prompt, model=None):
    model = model or IMG_MODEL
    if not (GAP and model):
        return None
    full = IMG_STYLE + " " + prompt
    heads = {"Authorization": "Bearer " + GAP}
    attempts = []
    for size in (IMG_SIZE, None):
        body = {"model": model, "prompt": full, "n": 1}
        if size:
            body["size"] = size
        attempts.append((GAP_BASE + "/images/generations", body))
    attempts.append((GAP_BASE + "/chat/completions",
                     {"model": model, "messages": [{"role": "user", "content": "Generate an image: " + full}]}))
    for url, body in attempts:
        try:
            r = requests.post(url, headers=heads, json=body, timeout=300)
        except Exception as e:
            print("Image error [%s]: %s" % (model, type(e).__name__))
            continue
        if r.status_code != 200:
            print("Image status [%s] %s %s" % (model, r.status_code, r.text[:300]))
            continue
        img = extract_image(r.json())
        if img and len(img) > 1000:
            return img
        print("Image response had no image [%s] %s" % (model, url.split("/v1")[1]))
    return None


def compress(data):
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        if im.mode == "RGBA":
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[3])
            im = bg
        if im.width > MAX_W:
            im = im.resize((MAX_W, int(im.height * MAX_W / im.width)), Image.LANCZOS)
        out = data
        for q in (82, 74, 66, 58, 50):
            buf = io.BytesIO()
            im.save(buf, "WEBP", quality=q, method=6)
            out = buf.getvalue()
            if len(out) <= MAX_KB * 1024:
                break
        print("Image compressed: %d KB -> %d KB (%dx%d)" % (len(data) // 1024, len(out) // 1024, im.width, im.height))
        return out
    except Exception as e:
        print("Compression skipped:", type(e).__name__, str(e)[:100])
        return data


def upload_media(data, filename, mime, title):
    r = wp("POST", WP + "/wp-json/wp/v2/media", auth=AUTH, timeout=180, data=data,
           headers={"Content-Disposition": 'attachment; filename="%s"' % filename, "Content-Type": mime})
    if r.status_code not in (200, 201):
        print("Media upload failed", r.status_code, r.text[:150])
        return None, None
    j = r.json()
    try:
        wp("POST", "%s/wp-json/wp/v2/media/%s" % (WP, j["id"]), tries=2, auth=AUTH,
           json={"alt_text": title, "title": title}, timeout=60)
    except Exception:
        pass
    return j["id"], j.get("source_url")


# ---------------- بلوک‌های طراحی‌شده ----------------
PALETTES = [("#1b2a4a", "#e8590c"), ("#0f3d3e", "#d97706"), ("#2b2d6e", "#c2410c")]
NAVY, ORANGE = PALETTES[0]
SOFT, LINE, MUTED = "#f8fafc", "#e3e8f0", "#475569"
INFO_SYSTEM = ("You extract structured infographic data from Persian business text. "
               "Reply only in the requested format, in fluent Persian, with no English words.")


def set_palette(seed):
    global NAVY, ORANGE
    NAVY, ORANGE = PALETTES[seed % len(PALETTES)]


def info_wrap(title, inner):
    return fill('<div dir="rtl" style="margin:2em 0;padding:1.3em 1.4em;border:1px solid @@line@@;border-radius:14px;'
                'background:@@soft@@;text-align:right"><div style="font-weight:800;font-size:22px;line-height:1.7;'
                'color:@@navy@@;margin-bottom:.9em">@@title@@</div>@@inner@@</div>\n',
                line=LINE, soft=SOFT, navy=NAVY, title=esc(title), inner=inner)


def render_steps(title, items):
    rows = ""
    for i, (t, d) in enumerate(items, 1):
        rows += fill('<div style="display:flex;gap:14px;align-items:flex-start;margin-bottom:14px">'
                     '<div style="flex:0 0 40px;height:40px;border-radius:50%;background:@@o@@;color:#fff;text-align:center;'
                     'line-height:40px;font-weight:700">@@n@@</div><div><div style="font-weight:700;color:@@navy@@;line-height:1.8">@@t@@</div>'
                     '<div style="font-size:16px;line-height:1.9;color:@@m@@">@@d@@</div></div></div>',
                     o=ORANGE, n=fa(i), navy=NAVY, t=esc(t), m=MUTED, d=esc(d))
    return info_wrap(title, rows)


def render_steps_cards(title, items):
    cards = ""
    for i, (t, d) in enumerate(items, 1):
        cards += fill('<div style="background:#fff;border:1px solid @@line@@;border-top:4px solid @@o@@;border-radius:12px;padding:1em">'
                      '<div style="width:34px;height:34px;border-radius:50%;background:@@navy@@;color:#fff;text-align:center;'
                      'line-height:34px;font-weight:700;margin-bottom:.5em">@@n@@</div>'
                      '<div style="font-weight:700;color:@@navy@@;line-height:1.8">@@t@@</div>'
                      '<div style="font-size:15px;line-height:1.9;color:@@m@@">@@d@@</div></div>',
                      line=LINE, o=ORANGE, navy=NAVY, n=fa(i), t=esc(t), m=MUTED, d=esc(d))
    grid = '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px">' + cards + "</div>"
    return info_wrap(title, grid)


def render_cards(title, items):
    cards = ""
    for t, d in items:
        cards += fill('<div style="background:#fff;border:1px solid @@line@@;border-right:5px solid @@o@@;border-radius:12px;padding:.9em 1em">'
                      '<div style="font-weight:700;color:@@navy@@;line-height:1.8">@@t@@</div>'
                      '<div style="font-size:15px;line-height:1.9;color:@@m@@">@@d@@</div></div>',
                      line=LINE, o=ORANGE, navy=NAVY, t=esc(t), m=MUTED, d=esc(d))
    grid = '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px">' + cards + "</div>"
    return info_wrap(title, grid)


def render_checklist(title, items):
    rows = ""
    for t, d in items:
        rows += fill('<div style="display:flex;gap:12px;align-items:flex-start;margin-bottom:12px">'
                     '<div style="flex:0 0 28px;height:28px;border-radius:8px;background:@@o@@;color:#fff;text-align:center;'
                     'line-height:28px;font-weight:700">&#10003;</div><div><span style="font-weight:700;color:@@navy@@">@@t@@</span>'
                     '<span style="color:@@m@@"> @@d@@</span></div></div>',
                     o=ORANGE, navy=NAVY, t=esc(t), m=MUTED, d=("— " + esc(d)) if d else "")
    return info_wrap(title, rows)


def render_compare(title, items, left, right):
    head = fill('<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">'
                '<div style="background:#b91c1c;color:#fff;border-radius:10px;padding:.5em .8em;font-weight:700;text-align:center">@@l@@</div>'
                '<div style="background:#15803d;color:#fff;border-radius:10px;padding:.5em .8em;font-weight:700;text-align:center">@@r@@</div></div>',
                l=esc(left), r=esc(right))
    rows = ""
    for a, b in items:
        rows += fill('<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">'
                     '<div style="background:#fff;border:1px solid #fecaca;border-radius:10px;padding:.6em .8em;line-height:1.9;color:@@m@@">@@a@@</div>'
                     '<div style="background:#fff;border:1px solid #bbf7d0;border-radius:10px;padding:.6em .8em;line-height:1.9;color:@@m@@">@@b@@</div></div>',
                     m=MUTED, a=esc(a), b=esc(b))
    return info_wrap(title, head + rows)


def make_infographic(sec_name, sec_html, kind):
    text = plain(sec_html, 1800)
    if kind == "compare":
        fmt = ("TYPE: compare\nTITLE: عنوان کوتاه\nLEFT: عنوان ستون اول (مثلاً «اشتباه رایج»)\n"
               "RIGHT: عنوان ستون دوم (مثلاً «روش درست»)\nITEM1: اشتباه | روش درست\nITEM2: ... | ...")
        how = "یک مقایسه‌ی دوستونه (اشتباه رایج در برابر روش درست)"
    elif kind == "checklist":
        fmt = "TYPE: checklist\nTITLE: عنوان کوتاه\nITEM1: عنوان | توضیح کوتاه\nITEM2: ... | ..."
        how = "یک چک‌لیست"
    elif kind == "cards":
        fmt = "TYPE: cards\nTITLE: عنوان کوتاه\nITEM1: عنوان نکته | توضیح کوتاه\nITEM2: ... | ..."
        how = "چند کارت نکته"
    else:
        fmt = "TYPE: steps\nTITLE: عنوان کوتاه\nITEM1: عنوان گام | توضیح کوتاه\nITEM2: ... | ..."
        how = "یک نقشه‌ی گام‌به‌گام"
    q = ("متن بخش «%s»:\n%s\n\nاز همین متن %s برای اینفوگرافیک بساز. فقط از مطالب همین متن استفاده کن و چیز تازه نساز. "
         "۳ تا ۵ آیتم؛ عنوان هر آیتم حداکثر ۴ کلمه و توضیح حداکثر ۱۰ کلمه؛ فارسی روان و بدون کلمه‌ی انگلیسی.\n"
         "دقیقاً در این قالب و بدون هیچ توضیح دیگر:\n%s" % (sec_name, text, how, fmt))
    out = ask(q, 700, INFO_SYSTEM)
    title = grab(out, "TITLE") or sec_name
    items = []
    for line in re.findall(r"^ITEM\d+\s*[:：]\s*(.+)$", out, re.M):
        a, _, b = line.partition("|")
        if a.strip():
            items.append((a.strip(), b.strip()))
    if len(items) < 3:
        return ""
    items = items[:5]
    if kind == "compare":
        return render_compare(title, [(a, b) for a, b in items if b], grab(out, "LEFT") or "اشتباه رایج", grab(out, "RIGHT") or "روش درست")
    if kind == "checklist":
        return render_checklist(title, items)
    if kind == "cards":
        return render_cards(title, items)
    if kind == "steps_cards":
        return render_steps_cards(title, items)
    return render_steps(title, items)


def pick_slots(hd, rnd):
    n = len(hd)

    def find(words):
        c = [i for i in range(1, n - 1) if any(w in hd[i][0] for w in words)]
        return rnd.choice(c) if c else None
    a = find(["قدم", "مراحل", "برنامه", "راهکار", "روش", "چطور", "چگونه"])
    b = find(["اشتباه", "نشانه", "خطا", "مشکل", "چرا"])
    if a is None:
        a = max(2, min(n - 2, (n * 2) // 3))
    if b is None or b == a:
        b = 1 if a != 1 else 2
    ka = rnd.choice(["steps", "steps_cards", "checklist"])
    mistaken = any(w in hd[b][0] for w in ["اشتباه", "خطا"])
    kb = rnd.choice(["compare", "cards"] if mistaken else ["cards", "checklist", "compare"])
    if kb == ka:
        kb = "cards" if ka != "cards" else "compare"
    return [(a, ka), (b, kb)]


HERO_C1, HERO_C2, HERO_BAR = "#CC6A45", "#A84F31", "#F6E7D2"


def build_hero(title, subtitle):
    sub = ('<div style="margin-top:.7em;font-size:19px;line-height:2;color:#fff7ed">%s</div>' % esc(subtitle)) if subtitle else ""
    return ('<div dir="rtl" style="margin:0 0 1.6em;padding:1.8em 2em;border-radius:18px;'
            'background:linear-gradient(135deg,%s 0%%,%s 100%%);color:#fff;text-align:right;'
            'border-right:8px solid %s">'
            '<div style="font-weight:800;font-size:30px;line-height:1.7">%s</div>%s</div>\n' % (HERO_C1, HERO_C2, HERO_BAR, esc(title), sub))


def build_toc(items):
    links = "".join(fill('<a href="#@@id@@" style="display:block;padding:.5em 0;color:@@navy@@;text-decoration:none;border-bottom:1px dashed @@line@@">@@n@@. @@t@@</a>',
                         id=i, navy=NAVY, line=LINE, n=fa(k), t=esc(t)) for k, (i, t) in enumerate(items, 1))
    return fill('<details dir="rtl" style="margin:0 0 2em;border:1px solid @@line@@;border-radius:12px;background:#fff;padding:0 1.1em;text-align:right">'
                '<summary style="cursor:pointer;font-weight:800;padding:.8em 0;color:@@navy@@">فهرست مطالب</summary>'
                '<div style="padding-bottom:.6em">@@links@@</div></details>\n', line=LINE, navy=NAVY, links=links)


def build_faq(faq):
    items = ""
    for i, (q, a) in enumerate(faq):
        items += fill('<details@@open@@ dir="rtl" style="border:1px solid @@line@@;border-radius:12px;margin-bottom:10px;background:#fff;padding:0 1.1em;text-align:right">'
                      '<summary style="cursor:pointer;font-weight:700;padding:.85em 0;color:@@navy@@">@@q@@</summary>'
                      '<div style="padding:0 0 1em;line-height:2;color:@@m@@">@@a@@</div></details>\n',
                      open=" open" if i == 0 else "", line=LINE, navy=NAVY, m=MUTED, q=esc(q), a=esc(a))
    return '<h2 id="mm-faq" style="scroll-margin-top:90px">سوالات متداول</h2>\n' + items


def pdf_button(url):
    return fill('<a href="@@u@@" download target="_blank" rel="noopener" style="display:inline-block;background:@@o@@;color:#fff;'
                'padding:.65em 1.3em;border-radius:10px;font-weight:700;text-decoration:none">دانلود PDF مقاله</a>', u=esc(url), o=ORANGE)


def justify(h):
    chunks = re.split(r"(<blockquote>.*?</blockquote>)", h, flags=re.S)
    out = []
    for c in chunks:
        if c.startswith("<blockquote>"):
            out.append(c)
        else:
            c = c.replace("<p>", '<p style="text-align:justify;text-justify:inter-word">')
            c = c.replace("<li>", '<li style="text-align:justify">')
            out.append(c)
    return "".join(out)


# ---------------- منابع مطالعه‌ی بیشتر ----------------
def load_registry():
    try:
        with open("sources.csv", encoding="utf-8-sig", newline="") as f:
            return [r for r in csv.DictReader(f) if r.get("url")]
    except Exception:
        return []


def url_ok(u):
    try:
        r = requests.get(u, timeout=20, stream=True, allow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0 (compatible; ContentEngine/1.0)"})
        r.close()
        return r.status_code not in (404, 410)
    except Exception:
        return False


def pick_sources(title, kw, reg):
    if not reg:
        return []
    listing = "\n".join("%s | %s | %s" % (r["id"], r["title"], r.get("tags", "")) for r in reg[:60])
    out = ask("مقاله: «%s» | کلمه‌ی کلیدی: %s\n\nفهرست منابع (شناسه | عنوان | موضوع‌ها):\n%s\n\n"
              "۲ یا ۳ منبع را که بیشترین ارتباط موضوعی را با این مقاله دارند انتخاب کن. فقط شناسه‌ها را بده، "
              "جداشده با کاما، در یک خط، به این شکل:\nPICK: 3, 7, 12" % (title, kw, listing), 100,
              "You pick relevant reference ids from a given list. Answer only in the requested format.", 5)
    ids = [x.strip() for x in re.findall(r"\d+", grab(out, "PICK"))]
    chosen = [r for i in ids for r in reg if r["id"] == i]
    if not chosen:
        words = set(re.findall(r"\w+", (title + " " + kw)))
        scored = sorted(reg, key=lambda r: -len(words & set(re.findall(r"\w+", r.get("tags", "") + " " + r["title"]))))
        chosen = scored[:3]
    final = []
    for r in chosen:
        if len(final) == 3:
            break
        if str(r.get("check", "1")).strip() == "0" or url_ok(r["url"]):
            final.append(r)
        else:
            print("Source dropped (dead link):", r["url"])
    return final


def build_sources(entries):
    if not entries:
        return ""
    lis = "".join(fill('<div style="margin-bottom:.7em;line-height:1.9"><a href="@@u@@" target="_blank" rel="noopener noreferrer" '
                       'style="color:@@o@@;font-weight:700;text-decoration:none">@@t@@</a><span style="color:@@m@@"> — @@s@@</span></div>',
                       u=esc(r["url"]), o=ORANGE, t=esc(r["title"]), m=MUTED, s=esc(r.get("site", ""))) for r in entries)
    return fill('<details id="mm-src" dir="rtl" style="margin:1.6em 0;border:1px solid @@line@@;border-radius:12px;background:#fff;padding:0 1.1em;text-align:right;scroll-margin-top:90px">'
                '<summary style="cursor:pointer;font-weight:800;padding:.8em 0;color:@@navy@@">برای مطالعه‌ی بیشتر (منابع)</summary>'
                '<div style="padding-bottom:.6em"><div style="line-height:1.9;color:@@m@@;margin-bottom:.8em">این منابع برای مطالعه‌ی تکمیلی انتخاب شده‌اند:</div>@@lis@@</div></details>\n',
                line=LINE, navy=NAVY, m=MUTED, lis=lis)


# ---------------- لینک‌سازی داخلی ----------------
def fetch_published():
    items = []
    try:
        r = wp("GET", WP + "/wp-json/wp/v2/posts", tries=3, auth=AUTH, timeout=90,
               params={"status": "publish", "per_page": 100, "context": "edit", "_fields": "id,link,title,slug,meta"})
        if r.status_code != 200:
            print("Published posts fetch status", r.status_code)
            return items
        for p in r.json():
            t = p.get("title") or {}
            title = plain(t.get("raw") or t.get("rendered") or "", 200)
            focus = ((p.get("meta") or {}).get("rank_math_focus_keyword") or "")
            if title and p.get("link"):
                items.append({"id": str(p["id"]), "url": p["link"], "title": title, "focus": focus})
    except Exception as e:
        print("Published posts fetch failed (%s); skipping internal links." % type(e).__name__)
    print("Published posts found:", len(items))
    return items


def pick_related(title, kw, items, slug):
    cand = [i for i in items if slug not in i["url"]]
    if not cand:
        return []
    listing = "\n".join("%s | %s | %s" % (i["id"], i["title"], i["focus"]) for i in cand[:80])
    out = ask("مقاله‌ی جدید: «%s» | کلمه‌ی کلیدی: %s\n\nمقاله‌های منتشرشده (شناسه | عنوان | کلمه‌ی کلیدی):\n%s\n\n"
              "حداکثر ۴ مقاله را که از نظر موضوعی بیشترین ارتباط را با مقاله‌ی جدید دارند انتخاب کن (اگر ارتباطی نیست، کمتر انتخاب کن). "
              "فقط شناسه‌ها را بده، در یک خط:\nPICK: 12, 7, 3" % (title, kw, listing), 100,
              "You pick relevant ids from a given list. Answer only in the requested format.", 5)
    ids = re.findall(r"\d+", grab(out, "PICK"))
    chosen = [i for x in ids for i in cand if i["id"] == x]
    if not chosen:
        words = set(re.findall(r"\w+", title + " " + kw))
        chosen = [i for i in sorted(cand, key=lambda i: -len(words & set(re.findall(r"\w+", i["title"] + " " + i["focus"]))))
                  if words & set(re.findall(r"\w+", i["title"] + " " + i["focus"]))][:3]
    seen, final = set(), []
    for i in chosen:
        if i["id"] not in seen:
            seen.add(i["id"])
            final.append(i)
    return final[:4]


def anchors_for(item):
    cands = [x.strip() for x in re.split(r"[,،]", item.get("focus", "")) if len(x.strip()) >= 4]
    cands.sort(key=lambda x: -len(x))
    return cands


def add_inline_links(parts, targets, max_links=3):
    count = 0
    style = "color:%s;text-decoration:underline;font-weight:600" % ORANGE
    for t in targets:
        if count >= max_links:
            break
        placed = False
        for a in anchors_for(t):
            for idx, part in enumerate(parts):
                for m in re.finditer(r"<p>(.*?)</p>", part, flags=re.S):
                    inner = m.group(1)
                    if "<a " in inner or a not in inner:
                        continue
                    link = '<a href="%s" title="%s" style="%s">%s</a>' % (esc(t["url"]), esc(t["title"]), style, a)
                    parts[idx] = part[:m.start(1)] + inner.replace(a, link, 1) + part[m.end(1):]
                    placed = True
                    print("Internal link: '%s' -> %s" % (a, t["url"]))
                    break
                if placed:
                    break
            if placed:
                break
        if placed:
            count += 1
    return count


def build_related(targets):
    if not targets:
        return ""
    items = "".join(fill('<a href="@@u@@" style="display:block;padding:.75em 1em;border:1px solid @@line@@;border-right:5px solid @@o@@;border-radius:10px;'
                         'margin-bottom:8px;color:@@navy@@;text-decoration:none;font-weight:700;background:#fff">@@t@@</a>',
                         u=esc(t["url"]), line=LINE, o=ORANGE, navy=NAVY, t=esc(t["title"])) for t in targets)
    return '<h2 id="mm-rel" style="scroll-margin-top:90px">مقاله‌های مرتبط</h2>\n' + items + "\n"


def build_cta():
    return fill('<div dir="rtl" style="margin:2em 0 1em;padding:1.5em 1.6em;border-radius:16px;background:#fff7ed;border:1px solid #fed7aa;text-align:center">'
                '<div style="font-weight:800;font-size:21px;color:@@navy@@;margin-bottom:.4em">مقاله‌های بیشتر @@mag@@</div>'
                '<div style="color:@@m@@;line-height:1.9;margin-bottom:1em">برای خواندن تحلیل‌ها و راهکارهای تازه‌ی رشد کسب‌وکار به مجله سر بزنید.</div>'
                '<a href="@@u@@" style="display:inline-block;background:@@o@@;color:#fff;padding:.65em 1.4em;border-radius:10px;font-weight:700;text-decoration:none">دیدن مقاله‌های بیشتر</a></div>\n',
                navy=NAVY, mag=MAGAZINE_NAME, m=MUTED, u=esc(MAGAZINE_URL), o=ORANGE)


# ---------------- اعلان تلگرام و بله ----------------
def notify(text):
    targets = [("Telegram", "https://api.telegram.org/bot%s/sendMessage", TG_TOKEN, TG_CHAT),
               ("Bale", "https://tapi.bale.ai/bot%s/sendMessage", BALE_TOKEN, BALE_CHAT)]
    sent = 0
    for name, url, tok, chat in targets:
        if not (tok and chat):
            continue
        try:
            r = requests.post(url % tok, json={"chat_id": chat, "text": text, "disable_web_page_preview": True}, timeout=30)
            print("Notify %s: %s %s" % (name, r.status_code, "" if r.status_code == 200 else r.text[:150]))
            sent += 1 if r.status_code == 200 else 0
        except Exception as e:
            print("Notify %s failed: %s" % (name, type(e).__name__))
    if not sent:
        print("Notify: no message delivered (tokens missing or services unreachable).")


# ---------------- PDF ----------------
def pdf_document(title, cover_b64, core, minutes):
    core = core.replace("<details", "<details open")
    cover = ('<img class="cover" src="data:image/webp;base64,%s">' % cover_b64) if cover_b64 else ""
    css = """
@page { size: A4; }
body { font-family: 'Vazirmatn','Noto Sans Arabic','Noto Naskh Arabic','DejaVu Sans',sans-serif; font-size: 12.5pt; line-height: 2.0; color:#1f2937; }
.brand { color:@@o@@; font-weight:700; font-size:11pt; margin-bottom:6px; }
h1 { font-size:24pt; line-height:1.6; color:@@navy@@; margin:0 0 6px; }
.meta { color:#64748b; font-size:10.5pt; margin-bottom:14px; }
.cover { width:100%; border-radius:10px; margin:6px 0 16px; }
h2 { font-size:17pt; color:@@navy@@; margin:22px 0 8px; page-break-after:avoid; }
h3 { font-size:14pt; color:@@navy@@; page-break-after:avoid; }
p, li { text-align:justify; }
blockquote { border-right:4px solid @@o@@; background:#fff7ed; margin:14px 0; padding:8px 14px; }
details, div[dir=rtl] { break-inside: avoid; }
a { color:@@o@@; text-decoration:none; }
.foot { margin-top:26px; padding-top:8px; border-top:1px solid #e3e8f0; color:#64748b; font-size:10pt; text-align:center; }
""".replace("@@o@@", ORANGE).replace("@@navy@@", NAVY)
    return ('<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><style>%s</style></head><body>'
            '<div class="brand"><a href="%s">%s</a></div><h1>%s</h1>'
            '<div class="meta">زمان مطالعه: %s دقیقه</div>%s%s'
            '<div class="foot"><div>برای مطالعه‌ی مقاله‌های بیشتر به <a href="%s">%s</a> سر بزنید.</div>'
            '<div style="margin-top:4px">%s — <a href="%s">mohammadmohajer.ir</a></div></div></body></html>'
            % (css, esc(MAGAZINE_URL), esc(MAGAZINE_NAME), esc(title), fa(minutes), cover, core,
               esc(MAGAZINE_URL), esc(MAGAZINE_NAME), esc(AUTHOR_LINE), esc(WP)))


def make_pdf(doc):
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page()
            pg.set_content(doc, wait_until="load")
            data = pg.pdf(format="A4", print_background=True,
                          margin={"top": "16mm", "bottom": "18mm", "left": "14mm", "right": "14mm"},
                          display_header_footer=True, header_template="<div></div>",
                          footer_template='<div style="font-size:9px;width:100%;text-align:center;color:#64748b"><span class="pageNumber"></span> / <span class="totalPages"></span></div>')
            b.close()
        print("PDF generated: %d KB" % (len(data) // 1024))
        return data
    except Exception as e:
        print("PDF generation skipped:", type(e).__name__, str(e)[:150])
        return None


ICONS = {
    "target": '<circle cx="200" cy="200" r="170" fill="#fff" opacity=".12"/><circle cx="200" cy="200" r="125" fill="none" stroke="#fff" stroke-width="14" opacity=".8"/>'
              '<circle cx="200" cy="200" r="80" fill="none" stroke="#fff" stroke-width="14" opacity=".8"/><circle cx="200" cy="200" r="32" fill="@@o@@"/>'
              '<line x1="200" y1="200" x2="335" y2="65" stroke="@@o@@" stroke-width="12" stroke-linecap="round"/><polygon points="335,65 300,72 328,100" fill="@@o@@"/>',
    "funnel": '<polygon points="40,70 360,70 240,210 240,340 160,300 160,210" fill="@@o@@"/><circle cx="120" cy="40" r="22" fill="#fff" opacity=".85"/>'
              '<circle cx="200" cy="25" r="22" fill="#fff" opacity=".85"/><circle cx="280" cy="40" r="22" fill="#fff" opacity=".85"/>',
    "stairs": '<rect x="40" y="290" width="70" height="60" fill="#fff" opacity=".85"/><rect x="110" y="235" width="70" height="115" fill="@@o@@"/>'
              '<rect x="180" y="180" width="70" height="170" fill="#fff" opacity=".85"/><rect x="250" y="125" width="70" height="225" fill="@@o@@"/>'
              '<polygon points="285,40 335,100 235,100" fill="#fff"/>',
    "magnifier": '<circle cx="170" cy="170" r="115" fill="#fff" opacity=".1" stroke="#fff" stroke-width="22"/><line x1="255" y1="255" x2="350" y2="350" stroke="@@o@@" stroke-width="32" stroke-linecap="round"/>'
                 '<rect x="105" y="170" width="30" height="55" fill="@@o@@"/><rect x="155" y="135" width="30" height="90" fill="#fff"/><rect x="205" y="105" width="30" height="120" fill="@@o@@"/>',
    "compass": '<circle cx="200" cy="200" r="160" fill="none" stroke="#fff" stroke-width="14" opacity=".85"/><polygon points="200,60 235,200 165,200" fill="@@o@@"/>'
               '<polygon points="200,340 235,200 165,200" fill="#fff" opacity=".9"/><circle cx="200" cy="200" r="14" fill="#0b1226"/>',
    "rook": '<rect x="85" y="305" width="230" height="40" rx="6" fill="#fff" opacity=".9"/><rect x="120" y="140" width="160" height="165" fill="#fff" opacity=".9"/>'
            '<rect x="100" y="105" width="200" height="38" fill="#fff"/><rect x="100" y="62" width="44" height="48" fill="#fff"/><rect x="178" y="62" width="44" height="48" fill="#fff"/>'
            '<rect x="256" y="62" width="44" height="48" fill="#fff"/><rect x="150" y="215" width="100" height="14" fill="@@o@@"/>',
}


def branded_cover(title, icon="stairs"):
    """کاور برندی ساخته‌شده با HTML و آیکون استعاری (پشتیبان وقتی تصویر هوش مصنوعی ساخته نشود)."""
    try:
        from playwright.sync_api import sync_playwright
        svg = fill('<svg viewBox="0 0 400 400" width="380" height="380" xmlns="http://www.w3.org/2000/svg">%s</svg>' % ICONS.get(icon, ICONS["stairs"]), o=ORANGE)
        page = fill(
            '<html lang="fa" dir="rtl"><body style="margin:0"><div style="width:1200px;height:800px;box-sizing:border-box;padding:80px 90px;'
            'background:linear-gradient(135deg,@@navy@@ 0%,#0b1226 100%);color:#fff;'
            "font-family:'Vazirmatn','Noto Sans Arabic','Noto Naskh Arabic','DejaVu Sans',sans-serif;"
            'display:flex;flex-direction:column;justify-content:space-between;position:relative;overflow:hidden">'
            '<div style="position:absolute;left:-150px;bottom:-150px;width:520px;height:520px;border-radius:50%;background:@@o@@;opacity:.18"></div>'
            '<div style="position:relative;font-size:28px;font-weight:700;color:@@o@@">محمد مهاجر | استراتژیست رشد کسب‌وکار</div>'
            '<div style="position:relative;display:flex;align-items:center;justify-content:space-between;gap:40px">'
            '<div style="font-size:62px;font-weight:800;line-height:1.75;max-width:640px">@@title@@</div>'
            '<div style="flex:0 0 380px">@@svg@@</div></div>'
            '<div style="position:relative;font-size:26px;opacity:.8">mohammadmohajer.ir</div></div></body></html>',
            navy=NAVY, o=ORANGE, title=esc(title), svg=svg)
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1200, "height": 800})
            pg.set_content(page, wait_until="load")
            png = pg.screenshot(type="png")
            b.close()
        print("Branded cover generated (icon: %s)." % icon)
        return png
    except Exception as e:
        print("Branded cover failed:", type(e).__name__, str(e)[:120])
        return None


def make_cover(title, ctx, alt, slug, kw=""):
    """تصویر شاخص: هوش مصنوعی (چند مدل پشت‌سرهم)، وگرنه کاور برندی. خروجی: (شناسه رسانه، base64، منبع)"""
    data, source = None, "none"
    hint, icon = pick_metaphor(title, kw)
    print("Metaphor hint:", hint or "(none)", "| icon:", icon)
    if IMG_MODEL and GAP:
        idea = ""
        try:
            idea = art_brief(title, ctx, hint)
        except SystemExit:
            pass
        idea = idea or hint or "a clear visual metaphor for the main idea of a business strategy article"
        print("Cover brief:", idea[:220])
        models = [IMG_MODEL] + [m.strip() for m in os.environ.get("IMAGE_FALLBACKS", "gapgpt/qwen-image-2.1,gpt-image-1-mini").split(",") if m.strip()]
        seen = []
        for m in models:
            if m in seen:
                continue
            seen.append(m)
            try:
                data = make_image(idea, m)
            except Exception as e:
                print("Image error [%s]: %s" % (m, type(e).__name__))
                data = None
            if data:
                source = "ai:" + m
                break
            print("AI cover failed with model %s." % m)
            time.sleep(10)
    else:
        print("IMAGE_MODEL or GapGPT key not set: using branded cover.")
    if not data:
        data = branded_cover(title, icon)
        source = "branded" if data else "none"
    if not data:
        return None, "", source
    small = compress(data)
    mime, ext = ("image/webp", "webp") if small[:4] == b"RIFF" else (("image/jpeg", "jpg") if small[:2] == b"\xff\xd8" else ("image/png", "png"))
    mid, _ = upload_media(small, "%s-cover.%s" % (slug, ext), mime, alt)
    print("Cover source: %s | media id: %s" % (source, mid))
    return mid, base64.b64encode(small).decode(), source


# ================= شروع =================
if __name__ == "__main__":
    try:
        r = wp("GET", WP + "/wp-json/wp/v2/users/me", tries=5, auth=AUTH, timeout=45)
    except Exception as e:
        sys.exit("اتصال به سایت برقرار نشد (%s). چند دقیقه بعد دوباره امتحان کنید." % type(e).__name__)
    print("WordPress:", r.status_code)
    if r.status_code != 200:
        sys.exit("اتصال وردپرس درست نیست.")

    with open("calendar.csv", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)
    row = next((x for x in rows if x["status"].strip().lower() == "ready"), None)
    if not row:
        sys.exit("ردیفی با وضعیت ready نیست.")
    kw = row["primary_keyword"]
    kw2 = row["secondary_keywords"].replace("|", "، ")
    SEED = int(re.sub(r"\D", "", row["id"]) or "0")
    set_palette(SEED)
    rnd = random.Random(SEED)
    print("Topic:", row["topic"], "| seed:", SEED)

    # طرح کلی
    o = ask("""موضوع: %s
کلمه‌ی کلیدی اصلی: %s
کلمات فرعی: %s

برای این مقاله یک عنوان جذاب (شامل کلمه‌ی کلیدی)، یک slug انگلیسی کوتاه و ۷ بخش طراحی کن. بخش اول مقدمه و بخش آخر جمع‌بندی است.
عنوان بخش‌ها: کوتاه، روشن و جذاب، نه کلی؛ دو یا سه تا از آن‌ها شامل کلمه‌ی کلیدی یا مفهوم اصلی باشند. هر بخش وظیفه‌ی جدا داشته باشد.
دقیقاً در این قالب و بدون هیچ توضیح دیگر:
TITLE: ...
SLUG: ...
H1: مقدمه | هدف بخش در یک جمله
H2: عنوان بخش | هدف بخش در یک جمله
H3: ...
H4: ...
H5: ...
H6: ...
H7: جمع‌بندی | هدف بخش در یک جمله""" % (row["topic"], kw, kw2), 900)
    title = grab(o, "TITLE") or row["topic"]
    slug = re.sub(r"[^a-z0-9-]", "", grab(o, "SLUG").lower().replace(" ", "-"))[:60].strip("-") or ("article-" + row["id"])
    heads = []
    for h in re.findall(r"^H\d\s*[:：]\s*(.+)$", o, re.M):
        name, _, goal = h.partition("|")
        heads.append((name.strip(), goal.strip() or name.strip()))
    if len(heads) < 5:
        print("Outline not parsed, using defaults.")
        heads = [("مقدمه", "مسئله را زنده کن"), ("موضوع دقیقاً چیست؟", "توضیح ساده"),
                 ("چرا بیشتر مردم اشتباه می‌کنند؟", "نکته‌ای که کمتر دیده می‌شود"),
                 ("یک نمونه‌ی فرضی", "مثال ملموس"), ("برنامه‌ی عملی قدم‌به‌قدم", "راهکار اجرایی"),
                 ("جمع‌بندی", "جمع‌بندی کوتاه")]
    heads = heads[:9]
    print("Title:", title, "| slug:", slug, "| sections:", len(heads))

    dup = wp("GET", WP + "/wp-json/wp/v2/posts", params={"slug": slug, "status": "any"}, auth=AUTH, timeout=60).json()
    if isinstance(dup, list) and dup:
        sys.exit("مقاله‌ای با این slug قبلاً هست: " + slug)

    # نوشتن بخش‌ها
    QUOTE_SECTION = 2
    parts = []
    names = " | ".join(n for n, _ in heads)
    for i, (name, goal) in enumerate(heads):
        prev = plain(" ".join(parts), 4000)[-400:]
        if i == 0:
            extra = "این بخش مقدمه است؛ مسئله را زنده کن و خواننده را وارد بحث کن."
        elif i == len(heads) - 1:
            extra = "این بخش جمع‌بندی است؛ کوتاه جمع‌بندی کن و با یک سؤال برای خواننده تمام کن."
        elif i == QUOTE_SECTION:
            extra = ("یک جمله‌ی کلیدی و ماندگار از دیدگاه خودت (نه نقل‌قول از شخص یا کتاب دیگر) را "
                     "در یک بلوک <blockquote><p>...</p></blockquote> بیاور.")
        else:
            extra = "اگر بخش بلند شد، یک یا دو زیرعنوان h3 بگذار."
        body = clean(ask("""مقاله: «%s» | کلمه‌ی کلیدی: %s
فهرست بخش‌ها: %s

حالا فقط بخش «%s» را بنویس. هدف این بخش: %s. %s
حدود ۲۸۰ تا ۳۵۰ کلمه بنویس (کوتاه‌تر نباشد)، با توضیح کافی، مثال یا جزئیات.
متن را پررنگ (bold) نکن.
فقط HTML ساده (p, ul, li, h3, blockquote). تیتر h2 نگذار و مطالب بخش‌های دیگر را تکرار نکن.
پایان متن قبلی (تکرارش نکن): %s""" % (title, kw, names, name, goal, extra, prev), 1800))
        head_html = "" if i == 0 else '<h2 id="mm-s%d" style="scroll-margin-top:90px">%s</h2>\n' % (i, esc(name))
        parts.append(head_html + body + "\n")
    words = len(plain(" ".join(parts), 10 ** 7).split())
    minutes = max(3, int(math.ceil(words / 180.0)))
    print("Word count:", words, "| reading minutes:", minutes)

    # سئو، نکات کلیدی و سؤال‌های متداول
    s = ask("""برای مقاله‌ی «%s» با کلمه‌ی کلیدی «%s» دقیقاً در این قالب بنویس، هر مورد در یک خط:
META_TITLE: حداکثر ۶۰ کاراکتر، بدون کلیشه
META_DESC: ۱۴۰ تا ۱۶۰ کاراکتر، جذاب و بدون عبارت کلیشه‌ای
EXCERPT: ۲ جمله
TAGS: ۴ تا ۵ برچسب جداشده با علامت |
ALT1: متن جایگزین تصویر شاخص به فارسی، یک جمله‌ی کوتاه شامل کلمه‌ی کلیدی
SUB: یک زیرعنوان جذاب و کوتاه (حداکثر ۱۸ کلمه) که وعده‌ی مقاله را بگوید
Q1: سؤال واقعی یک مدیر کسب‌وکار
A1: پاسخ ۲ تا ۳ جمله
Q2: ...
A2: ...
Q3: ...
A3: ...
Q4: ...
A4: ...""" % (title, kw), 1800)
    meta_title = grab(s, "META_TITLE")[:60] or title[:60]
    meta_desc = grab(s, "META_DESC")[:160]
    excerpt = grab(s, "EXCERPT")
    alt1 = grab(s, "ALT1") or title
    tags = [x.strip() for x in grab(s, "TAGS").split("|") if x.strip()] or [x.strip() for x in kw2.split("،") if x.strip()]
    subtitle = grab(s, "SUB") or (re.split(r"[.؟!]", excerpt)[0].strip() if excerpt else "")
    faq = [(grab(s, "Q%d" % i), grab(s, "A%d" % i)) for i in (1, 2, 3, 4)]
    faq = [(q, a) for q, a in faq if q and a]

    # منابع
    try:
        sources = pick_sources(title, kw, load_registry())
    except SystemExit:
        sources = []
    print("Sources:", [r["url"] for r in sources])

    # لینک‌سازی داخلی
    related = []
    try:
        related = pick_related(title, kw, fetch_published(), slug)
    except SystemExit:
        related = []
    except Exception as e:
        print("Related posts step failed (%s); skipping." % type(e).__name__)
    n_links = add_inline_links(parts, related) if related else 0
    print("Related posts:", [r["url"] for r in related], "| inline links:", n_links)

    # دسته و برچسب
    cat_ids = []
    try:
        cr = wp("GET", WP + "/wp-json/wp/v2/categories", tries=3, auth=AUTH, timeout=60,
                params={"search": row["category"].strip(), "per_page": 20, "_fields": "id,name"})
        cat_ids = [c["id"] for c in cr.json() if c.get("name", "").strip() == row["category"].strip()]
    except Exception as e:
        print("Category lookup failed (%s); continuing without category." % type(e).__name__)
    print("Category ids:", cat_ids)
    tag_ids = []
    for tg in tags[:5]:
        try:
            tr = wp("POST", WP + "/wp-json/wp/v2/tags", tries=3, auth=AUTH, json={"name": tg}, timeout=60)
            if tr.status_code in (200, 201):
                tag_ids.append(tr.json()["id"])
            elif tr.status_code == 400 and "term_id" in tr.text:
                tag_ids.append(tr.json()["data"]["term_id"])
        except Exception as e:
            print("Tag '%s' failed (%s); skipping." % (tg, type(e).__name__))

    # تصویر شاخص
    featured_id, cover_b64 = None, ""
    try:
        ctx = title + ". Sections: " + " | ".join(n for n, _ in heads) + ". " + plain(parts[0])
        featured_id, cover_b64, cover_src = make_cover(title, ctx, alt1, slug, kw)
    except Exception as e:
        print("Cover step failed (%s); continuing without cover." % type(e).__name__)

    # اینفوگرافیک‌ها (متنوع)
    for slot, kind in pick_slots(heads, rnd):
        try:
            if slot < len(parts):
                block = make_infographic(heads[slot][0], parts[slot], kind)
                if block:
                    parts[slot] += block
                    print("Infographic added after section %d (%s)" % (slot + 1, kind))
                else:
                    print("Infographic skipped for section %d" % (slot + 1))
        except SystemExit:
            print("Infographic failed for section %d; skipping." % (slot + 1))

    # مونتاژ
    faq_html = build_faq(faq) if faq else ""
    rel_html = build_related(related)
    src_html = build_sources(sources)
    core = justify("\n".join(parts)) + faq_html + rel_html + src_html

    toc_items = [("mm-s%d" % i, heads[i][0]) for i in range(1, len(heads))]
    if faq_html:
        toc_items.append(("mm-faq", "سوالات متداول"))
    if rel_html:
        toc_items.append(("mm-rel", "مقاله‌های مرتبط"))
    if src_html:
        toc_items.append(("mm-src", "برای مطالعه‌ی بیشتر (منابع)"))

    pdf_url = None
    if MAKE_PDF:
        pdf = make_pdf(pdf_document(title, cover_b64, core, minutes))
        if pdf:
            try:
                _, pdf_url = upload_media(pdf, "%s.pdf" % slug, "application/pdf", title + " (PDF)")
                print("PDF URL:", pdf_url)
            except Exception as e:
                print("PDF upload failed (%s); continuing without button." % type(e).__name__)
    btn = pdf_button(pdf_url) if pdf_url else ""

    hero = build_hero(title, subtitle)
    top_btn = ('<div style="margin:0 0 1.6em;text-align:right">%s</div>' % btn) if btn else ""
    end_btn = ('<div style="margin:1.6em 0;text-align:center">%s</div>' % btn) if btn else ""
    full = '<div class="mm-article">' + hero + build_toc(toc_items) + top_btn + core + end_btn + build_cta() + "</div>"

    focus = ", ".join([kw] + [x.strip() for x in kw2.split("،") if x.strip()][:2])
    payload = {"title": title, "slug": slug, "content": full, "excerpt": excerpt,
               "status": "draft", "categories": cat_ids, "tags": tag_ids,
               "meta": {"rank_math_title": meta_title, "rank_math_description": meta_desc,
                        "rank_math_focus_keyword": focus}}
    if featured_id:
        payload["featured_media"] = featured_id
    try:
        post = wp("POST", WP + "/wp-json/wp/v2/posts", tries=1, auth=AUTH, timeout=120, json=payload)
    except requests.exceptions.RequestException as e:
        print("Create post error %s; checking whether it was created..." % type(e).__name__)
        time.sleep(20)
        found = wp("GET", WP + "/wp-json/wp/v2/posts", params={"slug": slug, "status": "any"}, auth=AUTH, timeout=60).json()
        if isinstance(found, list) and found:
            class _P:
                status_code = 201

                def json(self):
                    return found[0]
            post = _P()
        else:
            post = wp("POST", WP + "/wp-json/wp/v2/posts", tries=2, auth=AUTH, timeout=120, json=payload)
    print("Create post:", post.status_code)
    if post.status_code not in (200, 201):
        sys.exit(post.text[:300])
    pid = post.json()["id"]
    print("Draft ID:", pid, "| edit:", "%s/wp-admin/post.php?post=%s&action=edit" % (WP, pid))
    try:
        chk = wp("GET", "%s/wp-json/wp/v2/posts/%s" % (WP, pid), tries=2, params={"context": "edit"}, auth=AUTH, timeout=60).json()
        m = chk.get("meta") or {}
        print("Rank Math saved:", bool(m.get("rank_math_title")), "| focus:", m.get("rank_math_focus_keyword"))
        if featured_id and chk.get("featured_media") != featured_id:
            wp("POST", "%s/wp-json/wp/v2/posts/%s" % (WP, pid), tries=3, auth=AUTH, json={"featured_media": featured_id}, timeout=60)
            print("Featured image re-attached.")
        print("Featured image on post:", chk.get("featured_media"))
    except Exception as e:
        print("Rank Math check skipped (%s)." % type(e).__name__)
    print("META_TITLE:", meta_title)
    print("META_DESC:", meta_desc)

    if "wp_id" not in fields:
        fields.append("wp_id")
    row["status"] = "draft"
    row["wp_id"] = str(pid)
    with open("calendar.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    notify("پیش‌نویس جدید در سایت منتشر شد و آماده‌ی بازبینی است.\n\nعنوان: %s\nزمان مطالعه: %s دقیقه\n\nویرایش:\n%s/wp-admin/post.php?post=%s&action=edit\n\nپیش‌نمایش:\n%s/?p=%s&preview=true"
           % (title, fa(minutes), WP, pid, WP, pid))
