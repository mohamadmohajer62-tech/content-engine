import os, re, io, json, sys, time
import requests
import generate as g

STATE = "announced.json"
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TG_CH = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
BALE_TOKEN = os.environ.get("BALE_BOT_TOKEN", "").strip()
BALE_CH = os.environ.get("BALE_CHANNEL_ID", "").strip()
EITAA_TOKEN = os.environ.get("EITAA_TOKEN", "").strip()
EITAA_CH = os.environ.get("EITAA_CHANNEL_ID", "").strip()
MAX_PER_RUN = 3
BRAND = "مجله رشد کسب‌وکار"
HANDLE = os.environ.get("CHANNEL_HANDLE", "@fcmo_mohajer").strip() or "@fcmo_mohajer"
SIG_NAME = "محمد مهاجر | استراتژیست رشد کسب‌وکار"
FOLLOW_GAP = int(os.environ.get("FOLLOW_GAP_MIN", "120") or 120) * 60      # فاصله‌ی پیام‌های پیاپی (دقیقه)
FOLLOW_MIN_GAP = int(os.environ.get("FOLLOW_MIN_GAP_MIN", "45") or 45) * 60   # حداقل فاصله بین دو پیام پیاپی، حتی اگر زمان‌بندی عقب افتاده باشد
TEST_FOLLOW_ID = os.environ.get("TEST_FOLLOW_ID", "").strip()               # آزمایش: فقط به چت شخصی شما
ASSESS_URL = getattr(g, "ASSESS_URL", "https://mohammadmohajer.ir/growth-assessment/")
CONSULT_URL = getattr(g, "CONSULT_URL", "https://mohammadmohajer.ir/request-a-consultation/")
BTN_ASSESS = "سنجش رایگان رشد کسب‌وکار"
BTN_CONSULT = "درخواست مشاوره"


def pdf_buttons(link, btn):
    """سه کلید شیشه‌ای پست PDF: مطالعه‌ی آنلاین (ردیف اول)، سنجش رشد و مشاوره (ردیف دوم)."""
    return [[{"text": btn, "url": link}],
            [{"text": BTN_ASSESS, "url": ASSESS_URL}, {"text": BTN_CONSULT, "url": CONSULT_URL}]]


STAGE_NAMES = {1: "پیام بلند محتوا", 2: "اقدامات امروز", 3: "نسخه‌ی PDF مقاله"}


def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_state(st):
    st["ids"] = st["ids"][-300:]
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def fetch_recent():
    r = g.wp("GET", g.WP + "/wp-json/wp/v2/posts", tries=4, auth=g.AUTH,
             params={"status": "publish", "per_page": 30, "orderby": "date", "order": "desc",
                     "context": "edit", "_fields": "id,link,title,excerpt,featured_media,tags,date_gmt"})
    if r.status_code != 200:
        sys.exit("دریافت مقاله‌ها ناموفق بود: %s" % r.status_code)
    out = []
    for p in r.json():
        t = p.get("title") or {}
        e = p.get("excerpt") or {}
        out.append({"id": p["id"], "link": p.get("link", ""),
                    "title": g.plain(t.get("raw") or t.get("rendered") or "", 300),
                    "excerpt": g.plain(e.get("raw") or e.get("rendered") or "", 2000),
                    "media": p.get("featured_media") or 0, "tags": p.get("tags") or [],
                    "date": p.get("date_gmt", "")})
    return out


def to_jpeg(raw):
    from PIL import Image
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def cover_bytes(post_id, media_id):
    """خروجی: (بایت‌های JPEG یا None، آدرس تصویر برای ارسال مستقیم یا '')"""
    local = os.path.join("covers", "%s.jpg" % post_id)
    if os.path.exists(local):
        print("Cover from repo:", local)
        return open(local, "rb").read(), ""
    if not media_id:
        print("Cover: post has no featured image (featured_media=0).")
        return None, ""
    url = ""
    try:
        r = g.wp("GET", "%s/wp-json/wp/v2/media/%s" % (g.WP, media_id), tries=3, auth=g.AUTH, params={"_fields": "source_url"})
        print("Cover media lookup: HTTP", r.status_code)
        url = (r.json() or {}).get("source_url") or ""
    except Exception as e:
        print("Cover media lookup failed:", type(e).__name__)
    if not url:
        return None, ""
    try:
        resp = g.S.get(url, timeout=60)
        ctype = resp.headers.get("content-type", "")
        print("Cover download: HTTP %s | %s | %d bytes" % (resp.status_code, ctype, len(resp.content)))
        if resp.status_code == 200 and "image" in ctype:
            return to_jpeg(resp.content), url
    except Exception as e:
        print("Cover download failed:", type(e).__name__, str(e)[:100])
    return None, url


def tag_names(ids):
    if not ids:
        return []
    try:
        r = g.wp("GET", g.WP + "/wp-json/wp/v2/tags", tries=3, auth=g.AUTH,
                 params={"include": ",".join(str(i) for i in ids[:14]), "per_page": 20, "_fields": "name"})
        # برچسب‌های فنی step-1 تا step-17 هشتگ نشوند
        return [t["name"] for t in r.json() if not re.match(r"^step-\d+$", t["name"].strip())][:6]
    except Exception:
        return []


def short_excerpt(text, n=260):
    t = text.strip()
    if len(t) <= n:
        return t
    cut = t[:n]
    m = max(cut.rfind("."), cut.rfind("؟"), cut.rfind("!"))
    return cut[:m + 1] if m > 120 else cut.rsplit(" ", 1)[0] + "…"


def hashtags(names):
    tags = []
    for n in names[:4]:
        h = re.sub(r"[^\w\u200c]+", "_", n.strip()).strip("_")
        if h:
            tags.append("#" + h)
    return " ".join(tags)


def build_captions(p, names):
    tags = hashtags(names)
    sig_plain = "✍️ %s\n\n🆔️ %s" % (SIG_NAME, HANDLE)
    sig_html = "✍️ <b>%s</b>\n\n🆔️ %s" % (g.esc(SIG_NAME), g.esc(HANDLE))
    fixed = "%s\n\n\n\n🔗 مطالعه‌ی کامل مقاله:\n%s\n\n%s\n\n%s" % (p["title"], p["link"], tags, sig_plain)
    room = max(0, 960 - len(fixed))
    ex = short_excerpt(p["excerpt"], min(260, room)) if (p["excerpt"] and room > 60) else ""
    plain_cap = "%s\n\n%s\n\n🔗 مطالعه‌ی کامل مقاله:\n%s\n\n%s\n\n%s" % (p["title"], ex, p["link"], tags, sig_plain)
    html_cap = "<b>%s</b>\n\n%s\n\n🔗 مطالعه‌ی کامل مقاله:\n%s\n\n%s\n\n%s" % (
        g.esc(p["title"]), g.esc(ex), g.esc(p["link"]), g.esc(tags), sig_html)
    return plain_cap.strip(), html_cap.strip()


def hint(err):
    e = (err or "").lower()
    if "chat not found" in e:
        return "شناسه‌ی کانال اشتباه است یا ربات در کانال نیست (کانال عمومی: @نام_کاربری، کانال خصوصی: شناسه‌ی عددی)."
    if "not enough rights" in e or "have no rights" in e or "can't post" in e or "need administrator" in e:
        return "ربات مدیر کانال است ولی اجازه‌ی «ارسال پیام» ندارد."
    if "not a member" in e or "forbidden" in e or "kicked" in e:
        return "ربات باید مدیر (Administrator) همان کانال باشد."
    if "unauthorized" in e or "invalid token" in e or "401" in e:
        return "توکن ربات اشتباه است."
    if "parse entities" in e:
        return "قالب‌بندی کپشن مشکل دارد."
    return ""


def small_jpeg(jpg):
    """نسخه‌ی کوچک‌تر عکس برای وقتی که آپلود نسخه‌ی اصلی در سرور پیام‌رسان خطا می‌دهد."""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(jpg)).convert("RGB")
        im.thumbnail((1100, 1100))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=78, optimize=True)
        return buf.getvalue()
    except Exception as e:
        print("small_jpeg failed:", type(e).__name__)
        return None


def send_bot_api(name, base, token, chat, jpg, plain_cap, html_cap, link, photo_url=""):
    """تلگرام و بله: عکس + کپشن + دکمه‌ی لینک. زنجیره‌ی جایگزین: آپلود عکس ← آپلود نسخه‌ی کوچک ← ارسال با آدرس عکس ← فقط متن.
    خروجی: (موفق؟، متن خطا یا توضیح)"""
    markup = json.dumps({"inline_keyboard": [[{"text": "مطالعه‌ی مقاله", "url": link}]]})
    use_html = (name == "Telegram")
    cap = html_cap if use_html else plain_cap
    plans = []
    if jpg:
        plans.append(("sendPhoto", "upload", jpg))
        sm = small_jpeg(jpg)
        if sm and len(sm) < len(jpg):
            plans.append(("sendPhoto", "upload-small", sm))
    if photo_url:
        plans.append(("sendPhoto", "url", photo_url))
    plans.append(("sendMessage", "text", None))
    last_err, had_image = "", bool(jpg or photo_url)
    for method, kind, payload in plans:
        for with_markup in (True, False):
            d = {"chat_id": chat}
            files = None
            if with_markup:
                d["reply_markup"] = markup
            if method == "sendPhoto":
                d["caption"] = cap
                if kind == "url":
                    d["photo"] = payload
                else:
                    files = {"photo": ("cover.jpg", payload, "image/jpeg")}
            else:
                d["text"] = cap
            if use_html:
                d["parse_mode"] = "HTML"
            try:
                r = requests.post((base % token) + method, data=d, files=files, timeout=90)
            except Exception as e:
                last_err = type(e).__name__
                print("%s %s/%s error: %s" % (name, method, kind, last_err))
                continue
            print("%s %s/%s (markup=%s): %s %s" % (name, method, kind, with_markup, r.status_code, "" if r.status_code == 200 else r.text[:200]))
            if r.status_code == 200:
                return True, ("(بدون تصویر؛ آپلود عکس در %s خطا داد)" % name) if (kind == "text" and had_image) else ""
            last_err = r.text[:200]
        if kind.startswith("upload"):
            time.sleep(4)          # خطای ۵۰۰ آپلود معمولاً موقتی است؛ کمی صبر قبل از روش بعدی
    return False, last_err


def eitaa_call(token, method, data, files=None):
    """ایتایار: موفقیت یعنی ok=true در JSON (نه فقط کد ۲۰۰)."""
    try:
        r = requests.post("https://eitaayar.ir/api/%s/%s" % (token, method), data=data, files=files, timeout=120)
        try:
            j = r.json()
        except Exception:
            j = {}
        ok = bool(j.get("ok")) if isinstance(j, dict) else False
        print("Eitaa %s: HTTP %s ok=%s %s" % (method, r.status_code, ok, "" if ok else r.text[:200]))
        return ok, ("" if ok else r.text[:200])
    except Exception as e:
        print("Eitaa %s error: %s" % (method, type(e).__name__))
        return False, type(e).__name__


def send_eitaa(token, chat, jpg, plain_cap, title):
    err = ""
    if jpg:
        for method in ("sendFile", "sendDocument"):
            ok, err = eitaa_call(token, method, {"chat_id": chat, "caption": plain_cap, "title": title[:60]},
                                 {"file": ("cover.jpg", jpg, "image/jpeg")})
            if ok:
                return True, ""
    ok, err2 = eitaa_call(token, "sendMessage", {"chat_id": chat, "text": plain_cap, "title": title[:60]})
    return ok, ("" if ok else (err2 or err))


# ---------------------------------------------------------------- پیام‌های پیاپی بعد از معرفی مقاله
def post_full(post_id):
    r = g.wp("GET", "%s/wp-json/wp/v2/posts/%s" % (g.WP, post_id), tries=3, auth=g.AUTH, timeout=90,
             params={"context": "edit", "_fields": "id,link,title,content"})
    if r.status_code != 200:
        return None
    j = r.json()
    t, c = j.get("title") or {}, j.get("content") or {}
    html = c.get("raw") or c.get("rendered") or ""
    return {"id": post_id, "link": j.get("link", ""), "html": html,
            "title": g.plain(t.get("raw") or t.get("rendered") or "", 300), "text": g.plain(html, 7000)}


def ask_json(prompt, max_tokens=900):
    try:
        out = g.ask(prompt + "\n\nفقط یک JSON معتبر بده؛ بدون توضیح و بدون بک‌تیک.", max_tokens,
                    "You write Persian channel posts for a business-growth strategist. Reply with strict JSON only.", min_len=10)
    except SystemExit:
        return None
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2190-\u21FF\u2300-\u23FF\u2460-\u27BF\u2900-\u297F\u2B00-\u2BFF\uFE0E\uFE0F\u200d]")
POINT_EMOJIS = ["🔹", "📌", "💡", "🎯", "🧭"]


def strip_emoji(t):
    """همه‌ی ایموجی‌ها از متن حذف می‌شود؛ ایموجی فقط توسط کد و فقط اول پاراگراف نکته‌ها گذاشته می‌شود."""
    t = EMOJI_RE.sub("", str(t or ""))
    t = re.sub(r"[ \t]{2,}", " ", t)
    return re.sub(r"\s+([.،؛:!؟?])", r"\1", t).strip()


def build_long(intro, points, outro):
    """چیدمان قطعی پیام بلند: مقدمه، هر نکته در پاراگراف جدا با ایموجی اول سطر، جمع‌بندی؛ بین همه خط خالی."""
    paras = [strip_emoji(intro)]
    for i, pt in enumerate(points):
        paras.append("%s %s" % (POINT_EMOJIS[i % len(POINT_EMOJIS)], strip_emoji(pt)))
    paras.append(strip_emoji(outro))
    return "\n\n".join(x for x in paras if x)


def normalize_long(text):
    """اگر مدل به‌جای ساختار، یک متن پیوسته داد: متن را به جمله‌ها بشکن و همان چیدمان قطعی را بساز."""
    t = str(text or "").replace("\r", "").strip()
    sents = [strip_emoji(x) for x in re.split(r"(?<=[.!؟?])\s+|\n+", t) if strip_emoji(x)]
    if len(sents) < 5:
        return ""
    intro, outro, mid = sents[0], sents[-1], sents[1:-1]
    n = min(4, max(3, len(mid) // 2)) if len(mid) >= 6 else min(4, len(mid))
    size = -(-len(mid) // n)            # بالا گرد
    points = [" ".join(mid[i:i + size]) for i in range(0, len(mid), size)][:4]
    return build_long(intro, points, outro)


def gen_long(title, text):
    for _ in range(3):
        j = ask_json(
            "عنوان مقاله: %s\n\nمتن مقاله:\n%s\n\n"
            "از همین متن یک پیام بلند و جذاب برای کانال بنویس؛ اول‌شخص و صمیمی با صدای محمد مهاجر (استراتژیست رشد کسب‌وکار). "
            "خروجی سه بخش جدا باشد: intro یک پاراگراف کوتاه با یک جمله‌ی کنجکاوبرانگیز (۶۰ تا ۲۵۰ نویسه)؛ "
            "points فهرستی از ۳ یا ۴ نکته‌ی کلیدی خودِ مقاله، هر نکته یک پاراگراف مستقل ۱۲۰ تا ۴۰۰ نویسه؛ "
            "outro یک جمله‌ی دعوت به مطالعه‌ی کامل مقاله (۳۰ تا ۲۰۰ نویسه). "
            "در هیچ‌کدام ایموجی، بولد، هشتگ، شماره‌گذاری یا لینک ننویس؛ ایموجی‌ها را خود سیستم می‌گذارد. فقط از محتوای مقاله استفاده کن.\n"
            'خروجی: {"intro": "...", "points": ["...", "...", "..."], "outro": "..."}' % (title, text[:5500]), 1500)
        if not j:
            continue
        if isinstance(j.get("points"), list) and j.get("intro"):
            pts = [str(x).strip() for x in j["points"] if isinstance(x, str) and len(strip_emoji(x)) >= 60][:4]
            t = build_long(j.get("intro", ""), pts, j.get("outro", "")) if len(pts) >= 3 else ""
        else:                                  # قالب قدیمی {"text": "..."}
            t = normalize_long(j.get("text", ""))
        if 450 <= len(t) <= 3200 and g.latin_ratio(t) <= 0.12:
            return t
    return ""


def gen_actions(title, text):
    for _ in range(2):
        j = ask_json(
            "عنوان مقاله: %s\n\nمتن مقاله:\n%s\n\n"
            "برای پیام «اقدامات امروز» کانال بنویس: intro یک جمله‌ی کوتاه و انگیزه‌بخش (حداکثر ۱۱۰ نویسه)، و actions فهرستی از ۳ تا ۵ اقدام "
            "عملی و مشخص که مدیر همین امروز می‌تواند بر اساس این مقاله انجام دهد؛ هر اقدام یک جمله‌ی فعلی ۴۰ تا ۱۷۰ نویسه و قابل اجرا در یک روز. "
            "فقط بر پایه‌ی محتوای مقاله؛ بدون بولد، بدون شماره‌گذاری در متن.\n"
            'خروجی: {"intro": "...", "actions": ["...", "..."]}' % (title, text[:5500]), 900)
        if not j:
            continue
        intro = str(j.get("intro", "")).strip()
        acts = [a.strip() for a in (j.get("actions") or []) if isinstance(a, str) and 25 <= len(a.strip()) <= 230][:5]
        if len(acts) >= 3 and g.latin_ratio(" ".join(acts)) <= 0.12:
            return intro, acts
    return "", []


def compose(head, body, link):
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    sp = "✍️ %s\n\n🆔️ %s" % (SIG_NAME, HANDLE)
    sh = "✍️ <b>%s</b>\n\n🆔️ %s" % (g.esc(SIG_NAME), g.esc(HANDLE))
    plain = "%s\n\n%s\n\n🔗 متن کامل مقاله:\n%s\n\n%s" % (head, body, link, sp)
    html = "<b>%s</b>\n\n%s\n\n🔗 متن کامل مقاله:\n%s\n\n%s" % (g.esc(head), g.esc(body), g.esc(link), sh)
    return plain, html


def dest(owner=False):
    if owner:   # آزمایش: فقط چت شخصی شما
        d = [("Telegram", "https://api.telegram.org/bot%s/", TG_TOKEN, g.TG_CHAT), ("Bale", "https://tapi.bale.ai/bot%s/", BALE_TOKEN, g.BALE_CHAT)]
    else:
        d = [("Telegram", "https://api.telegram.org/bot%s/", TG_TOKEN, TG_CH), ("Bale", "https://tapi.bale.ai/bot%s/", BALE_TOKEN, BALE_CH),
             ("Eitaa", None, EITAA_TOKEN, EITAA_CH)]
    return [x for x in d if x[2] and x[3]]


def send_text_all(plain, html, link, title, owner=False):
    res = {}
    for name, base, tok, chat in dest(owner):
        if name == "Eitaa":
            res[name] = send_eitaa(tok, chat, None, plain, title)[0]
        else:
            res[name] = send_bot_api(name, base, tok, chat, None, plain, html, link)[0]
    return res


def send_doc_bot_api(name, base, token, chat, data, filename, plain, html, link, btn="مطالعه‌ی آنلاین مقاله"):
    markup = json.dumps({"inline_keyboard": pdf_buttons(link, btn)})
    use_html = (name == "Telegram") and len(html) <= 1000
    cap = html if use_html else plain[:1000]
    for with_markup in (True, False):
        d = {"chat_id": chat, "caption": cap}
        if use_html:
            d["parse_mode"] = "HTML"
        if with_markup:
            d["reply_markup"] = markup
        try:
            r = requests.post((base % token) + "sendDocument", data=d, files={"document": (filename, data, "application/pdf")}, timeout=240)
        except Exception as e:
            print("%s sendDocument error: %s" % (name, type(e).__name__))
            continue
        print("%s sendDocument (markup=%s): %s %s" % (name, with_markup, r.status_code, "" if r.status_code == 200 else r.text[:200]))
        if r.status_code == 200:
            return True
    # فایل آپلود نشد: پیام متنی با همان کلیدهای شیشه‌ای، تا مخاطب بی‌خبر نماند
    try:
        d = {"chat_id": chat, "text": cap + "\n\n(فایل PDF در این پیام‌رسان آپلود نشد؛ از لینک مقاله استفاده کنید.)", "reply_markup": markup}
        if use_html:
            d["parse_mode"] = "HTML"
        r = requests.post((base % token) + "sendMessage", data=d, timeout=60)
        print("%s sendMessage (no file): %s" % (name, r.status_code))
        if r.status_code == 200:
            return True
    except Exception as e:
        print("%s sendMessage fallback error: %s" % (name, type(e).__name__))
    return False


def send_doc_all(data, filename, plain, html, link, title, owner=False, btn="مطالعه‌ی آنلاین مقاله", eitaa_plain=None):
    res = {}
    for name, base, tok, chat in dest(owner):
        if name == "Eitaa":
            ok = False
            for method in ("sendFile", "sendDocument"):
                ok, _ = eitaa_call(tok, method, {"chat_id": chat, "caption": (eitaa_plain or plain)[:1000], "title": title[:60]},
                                   {"file": (filename, data, "application/pdf")})
                if ok:
                    break
            res[name] = ok
        else:
            res[name] = send_doc_bot_api(name, base, tok, chat, data, filename, plain, html, link, btn)
    return res


def do_stage(post_id, stage, owner=False, late=0):
    """یک مرحله از سه پیام پیاپی. خروجی: (انجام شد یا رها شد؟، خلاصه‌ی نتیجه)."""
    p = post_full(post_id)
    if not p or not p["text"]:
        return False, "متن مقاله در دسترس نیست"
    title = p["title"]
    if stage == 1:
        body = gen_long(title, p["text"])
        if not body:
            return False, "مدل زبانی متن بلند معتبر نساخت"
        plain, html = compose("📖 " + title, body, p["link"])
        res = send_text_all(plain, html, p["link"], title, owner)
    elif stage == 2:
        intro, acts = gen_actions(title, p["text"])
        if not acts:
            return False, "مدل زبانی فهرست اقدامات معتبر نساخت"
        lines = "\n\n".join("%s) %s" % (g.fa(i + 1), a) for i, a in enumerate(acts))
        body = (intro + "\n\n" if intro else "") + lines
        plain, html = compose("✅ اقدامات امروز | " + title, body, p["link"])
        res = send_text_all(plain, html, p["link"], title, owner)
    else:
        m = re.search(r'href="([^"]+\.pdf)"', p["html"], re.I)
        if not m:
            return True, "این مقاله PDF ندارد؛ مرحله‌ی PDF رد شد"
        try:
            data = g.S.get(m.group(1), timeout=150).content
        except Exception as e:
            return False, "دانلود PDF ناموفق: " + type(e).__name__
        if data[:4] != b"%PDF":
            return False, "فایل PDF معتبر نبود"
        short = title[:120]
        body = "برای مطالعه‌ی آفلاین، نگهداری و ارسال برای همکارانتان."
        sp = "✍️ %s\n\n🆔️ %s" % (SIG_NAME, HANDLE)
        sh = "✍️ <b>%s</b>\n\n🆔️ %s" % (g.esc(SIG_NAME), g.esc(HANDLE))
        plain = "📄 نسخه‌ی PDF مقاله: %s\n\n%s\n\n🔗 مطالعه‌ی آنلاین:\n%s\n\n%s" % (short, body, p["link"], sp)
        html = "<b>📄 نسخه‌ی PDF مقاله: %s</b>\n\n%s\n\n🔗 مطالعه‌ی آنلاین:\n%s\n\n%s" % (g.esc(short), g.esc(body), g.esc(p["link"]), sh)
        fname = (re.sub(r"[^\w\-]+", "-", title).strip("-")[:50] or "article") + ".pdf"
        # ایتا کلید شیشه‌ای ندارد؛ دو لینک داخل متن کپشن می‌آید (قبل از امضا)
        eitaa_plain = ("📄 نسخه‌ی PDF مقاله: %s\n\n%s\n\n🔗 مطالعه‌ی آنلاین:\n%s\n\n"
                       "📊 %s:\n%s\n\n💬 %s:\n%s\n\n%s"
                       % (short, body, p["link"], BTN_ASSESS, ASSESS_URL, BTN_CONSULT, CONSULT_URL, sp))
        res = send_doc_all(data, fname, plain, html, p["link"], title, owner, eitaa_plain=eitaa_plain)
    line = " | ".join("%s %s" % (k, "✅" if v else "❌") for k, v in res.items()) or "هیچ مقصدی تنظیم نیست"
    ok = any(res.values())
    if not owner:
        g.notify("📨 %s ارسال شد:\n%s\n\n%s%s" % (STAGE_NAMES[stage], title, line,
                 ("\n⏱ تأخیر نسبت به زمان‌بندی: %d دقیقه" % late) if late >= 10 else ""))
    return ok, line


def process_follow(st):
    now = int(time.time())
    done_runs = 0
    for key, f in list(st.get("follow", {}).items()):
        if f.get("done", 0) >= 3:
            if now - f.get("t0", now) > 3 * 86400:
                del st["follow"][key]
            continue
        stage = f.get("done", 0) + 1
        # زمان‌بندی از لحظه‌ی اعلان (t0) حساب می‌شود، نه از ارسال قبلی؛ پس تأخیر اجراها روی هم جمع نمی‌شود.
        planned = f.get("t0", now) + stage * FOLLOW_GAP
        due = max(planned, f.get("last", now) + FOLLOW_MIN_GAP)
        if now < due or done_runs >= 3:
            continue
        late = (now - planned) // 60
        ok, info = do_stage(int(key), stage, late=late)
        done_runs += 1
        print("Follow-up %s stage %d: %s (%s) | late %d min" % (key, stage, "OK" if ok else "FAIL", info, late))
        if ok:
            f["done"], f["last"], f["tries"] = stage, now, 0
        else:
            f["tries"] = f.get("tries", 0) + 1
            if f["tries"] >= 3:
                f["done"], f["last"], f["tries"] = stage, now, 0
                g.notify("⚠️ مرحله‌ی «%s» برای مقاله‌ی %s بعد از ۳ تلاش انجام نشد و رد شد: %s" % (STAGE_NAMES[stage], key, info))
        save_state(st)


def run_test(post_id):
    """آزمایش بدون ارسال به کانال: هر سه پیام به چت شخصی شما (تلگرام و بله) می‌آید."""
    print("TEST: sending 3 follow-up messages for post", post_id, "to the owner chat only.")
    for stage in (1, 2, 3):
        ok, info = do_stage(post_id, stage, owner=True)
        print("Stage %d: %s | %s" % (stage, "OK" if ok else "FAIL", info))
    g.notify("🧪 آزمایش سه پیام پیاپی برای مقاله‌ی %s تمام شد (به کانال‌ها چیزی ارسال نشد)." % post_id)


def log_run(st):
    """ثبت زمان هر اجرای زمان‌بندی‌شده؛ اگر گیت‌هاب اجراها را دیر می‌رساند (میانگین فاصله بیش از ۳۵ دقیقه به‌جای ۱۵)، یک‌بار در ۱۲ ساعت هشدار می‌دهد."""
    if os.environ.get("GITHUB_EVENT_NAME", "") != "schedule":
        return
    now = int(time.time())
    runs = (st.get("runs") or [])[-11:] + [now]
    st["runs"] = runs
    if len(runs) >= 6:
        gaps = [(b - a) / 60 for a, b in zip(runs, runs[1:])]
        avg, worst = sum(gaps) / len(gaps), max(gaps)
        print("Scheduler check: average gap %.0f min, worst %.0f min over last %d runs (expected 15)." % (avg, worst, len(gaps)))
        if avg > 35 and now - st.get("warn_t", 0) > 12 * 3600:
            st["warn_t"] = now
            g.notify("⏱ زمان‌بندی گیت‌هاب دیر می‌رسد: در %d اجرای اخیر فاصله‌ی دو اجرای announce به‌طور میانگین %.0f دقیقه "
                     "(بیشترین %.0f دقیقه) بوده، نه ۱۵ دقیقه. ارسال‌ها به همین اندازه عقب می‌افتند." % (len(gaps), avg, worst))


def retry_missed(st, posts):
    """مقصدهایی که در اعلان اولیه خطا دادند (مثلاً بله) در اجراهای بعدی، فقط برای همان مقصد، دوباره امتحان می‌شوند."""
    by_id = {str(p["id"]): p for p in posts}
    for key, m in list(st.get("missed", {}).items()):
        p = by_id.get(key)
        if not p:
            del st["missed"][key]
            continue
        names = m.get("names", [])
        jpg, photo_url = cover_bytes(p["id"], p["media"])
        plain_cap, html_cap = build_captions(p, tag_names(p["tags"]))
        for name in list(names):
            if name == "Bale" and BALE_TOKEN and BALE_CH:
                ok, note = send_bot_api("Bale", "https://tapi.bale.ai/bot%s/", BALE_TOKEN, BALE_CH, jpg, plain_cap, html_cap, p["link"], photo_url)
            elif name == "Telegram" and TG_TOKEN and TG_CH:
                ok, note = send_bot_api("Telegram", "https://api.telegram.org/bot%s/", TG_TOKEN, TG_CH, jpg, plain_cap, html_cap, p["link"], photo_url)
            elif name == "Eitaa" and EITAA_TOKEN and EITAA_CH:
                ok, note = send_eitaa(EITAA_TOKEN, EITAA_CH, jpg, plain_cap, p["title"])
            else:
                ok, note = True, ""
            if ok:
                names.remove(name)
                g.notify("🔁 ارسال دوباره‌ی مقاله در %s انجام شد:\n%s" % (name, p["title"]))
        m["tries"] = m.get("tries", 0) + 1
        if not names:
            del st["missed"][key]
        elif m["tries"] >= 4:
            g.notify("⚠️ مقاله‌ی «%s» بعد از ۴ تلاش دوباره در این مقصدها ارسال نشد: %s" % (p["title"], "، ".join(names)))
            del st["missed"][key]
        save_state(st)


def main():
    if TEST_FOLLOW_ID.isdigit():
        return run_test(int(TEST_FOLLOW_ID))
    channels = [("Telegram", TG_TOKEN and TG_CH), ("Bale", BALE_TOKEN and BALE_CH), ("Eitaa", EITAA_TOKEN and EITAA_CH)]
    if not any(c[1] for c in channels):
        sys.exit("هیچ کانالی تنظیم نشده است (Secretهای کانال را بسازید).")
    posts = fetch_recent()
    st = load_state()
    if st is not None:
        log_run(st)
    if st is None:
        st = {"ids": [p["id"] for p in posts], "attempts": {}}
        save_state(st)
        print("Initialized with %d existing posts; nothing sent." % len(posts))
        g.notify("📣 اعلان خودکار کانال‌ها فعال شد. %d مقاله‌ی موجود علامت خورد و از این به بعد هر مقاله‌ی تازه‌منتشرشده ارسال می‌شود." % len(posts))
        return
    force = {int(x) for x in re.findall(r"\d+", os.environ.get("FORCE_IDS", ""))}
    new = [p for p in posts if p["id"] not in st["ids"] or p["id"] in force]
    for p in new:
        if p["id"] in force:
            st["attempts"][str(p["id"])] = 0
            if p["id"] in st["ids"]:
                st["ids"].remove(p["id"])
    new.sort(key=lambda p: p["date"])
    print("New published posts:", [p["id"] for p in new])
    for p in new[:MAX_PER_RUN]:
        names = tag_names(p["tags"])
        jpg, photo_url = cover_bytes(p["id"], p["media"])
        plain_cap, html_cap = build_captions(p, names)
        res, errs = {}, {}
        if TG_TOKEN and TG_CH:
            res["Telegram"], errs["Telegram"] = send_bot_api("Telegram", "https://api.telegram.org/bot%s/", TG_TOKEN, TG_CH, jpg, plain_cap, html_cap, p["link"], photo_url)
        if BALE_TOKEN and BALE_CH:
            res["Bale"], errs["Bale"] = send_bot_api("Bale", "https://tapi.bale.ai/bot%s/", BALE_TOKEN, BALE_CH, jpg, plain_cap, html_cap, p["link"], photo_url)
        if EITAA_TOKEN and EITAA_CH:
            res["Eitaa"], errs["Eitaa"] = send_eitaa(EITAA_TOKEN, EITAA_CH, jpg, plain_cap, p["title"])
        key = str(p["id"])
        st["attempts"][key] = st["attempts"].get(key, 0) + 1
        if any(res.values()) or st["attempts"][key] >= 3:
            st["ids"].append(p["id"])
        failed = [k for k, v in res.items() if not v]
        if failed and any(res.values()):
            st.setdefault("missed", {})[key] = {"names": failed, "tries": 0}
        if any(res.values()):
            st.setdefault("follow", {})[key] = {"t0": int(time.time()), "last": int(time.time()), "done": 0, "tries": 0}
        line = " | ".join("%s %s" % (k, "✅" if v else "❌") for k, v in res.items())
        details = "\n".join("• %s: %s" % (k, (hint(errs[k]) or errs[k][:120])) for k, v in res.items() if (not v) or errs.get(k))
        print("Announced post %s: %s" % (p["id"], line))
        g.notify("📣 اعلان مقاله در کانال‌ها:\n%s\n\n%s%s" % (p["title"], line, ("\n\n" + details) if details else ""))
        save_state(st)
    retry_missed(st, posts)
    process_follow(st)
    save_state(st)


if __name__ == "__main__":
    main()
