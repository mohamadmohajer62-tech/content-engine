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
TEST_FOLLOW_ID = os.environ.get("TEST_FOLLOW_ID", "").strip()               # آزمایش: فقط به چت شخصی شما
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
                 params={"include": ",".join(str(i) for i in ids[:6]), "per_page": 10, "_fields": "name"})
        return [t["name"] for t in r.json()]
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


def send_bot_api(name, base, token, chat, jpg, plain_cap, html_cap, link, photo_url=""):
    """تلگرام و بله (API سازگار): عکس + کپشن + دکمه‌ی لینک. خروجی: (موفق؟، متن خطا)"""
    markup = json.dumps({"inline_keyboard": [[{"text": "مطالعه‌ی مقاله", "url": link}]]})
    use_html = (name == "Telegram")
    cap = html_cap if use_html else plain_cap
    last_err = ""
    for with_markup in (True, False):
        d = {"chat_id": chat}
        if with_markup:
            d["reply_markup"] = markup
        if jpg:
            d["caption"] = cap
            if use_html:
                d["parse_mode"] = "HTML"
            files, method = {"photo": ("cover.jpg", jpg, "image/jpeg")}, "sendPhoto"
        elif photo_url:
            d["caption"] = cap
            d["photo"] = photo_url
            if use_html:
                d["parse_mode"] = "HTML"
            files, method = None, "sendPhoto"
        else:
            d["text"] = cap
            if use_html:
                d["parse_mode"] = "HTML"
            files, method = None, "sendMessage"
        try:
            r = requests.post((base % token) + method, data=d, files=files, timeout=90)
        except Exception as e:
            last_err = type(e).__name__
            print("%s error: %s" % (name, last_err))
            continue
        print("%s %s (markup=%s): %s %s" % (name, method, with_markup, r.status_code, "" if r.status_code == 200 else r.text[:200]))
        if r.status_code == 200:
            return True, ""
        last_err = r.text[:200]
    if photo_url and not jpg:
        d = {"chat_id": chat, "text": cap}
        if use_html:
            d["parse_mode"] = "HTML"
        try:
            r = requests.post((base % token) + "sendMessage", data=d, timeout=60)
            print("%s sendMessage (no image): %s" % (name, r.status_code))
            if r.status_code == 200:
                return True, "(بدون تصویر)"
        except Exception:
            pass
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


def gen_long(title, text):
    for _ in range(2):
        j = ask_json(
            "عنوان مقاله: %s\n\nمتن مقاله:\n%s\n\n"
            "از همین متن یک پیام بلند و جذاب برای کانال بنویس: ۱۰۰۰ تا ۱۶۰۰ نویسه؛ اول‌شخص و صمیمی با صدای محمد مهاجر (استراتژیست رشد کسب‌وکار)؛ "
            "شروع با یک جمله‌ی کنجکاوبرانگیز؛ سه یا چهار نکته‌ی کلیدی خودِ مقاله که هرکدام با یک ایموجی ساده شروع شود؛ "
            "بدون بولد، بدون هشتگ، بدون لینک؛ پایان با یک جمله‌ی دعوت به مطالعه‌ی کامل. فقط از محتوای مقاله استفاده کن.\n"
            'خروجی: {"text": "..."}' % (title, text[:5500]), 1400)
        t = str((j or {}).get("text", "")).strip()
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
    markup = json.dumps({"inline_keyboard": [[{"text": btn, "url": link}]]})
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
    return False


def send_doc_all(data, filename, plain, html, link, title, owner=False, btn="مطالعه‌ی آنلاین مقاله"):
    res = {}
    for name, base, tok, chat in dest(owner):
        if name == "Eitaa":
            ok = False
            for method in ("sendFile", "sendDocument"):
                ok, _ = eitaa_call(tok, method, {"chat_id": chat, "caption": plain[:1000], "title": title[:60]},
                                   {"file": (filename, data, "application/pdf")})
                if ok:
                    break
            res[name] = ok
        else:
            res[name] = send_doc_bot_api(name, base, tok, chat, data, filename, plain, html, link, btn)
    return res


def do_stage(post_id, stage, owner=False):
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
        res = send_doc_all(data, fname, plain, html, p["link"], title, owner)
    line = " | ".join("%s %s" % (k, "✅" if v else "❌") for k, v in res.items()) or "هیچ مقصدی تنظیم نیست"
    ok = any(res.values())
    if not owner:
        g.notify("📨 %s ارسال شد:\n%s\n\n%s" % (STAGE_NAMES[stage], title, line))
    return ok, line


def process_follow(st):
    now = int(time.time())
    done_runs = 0
    for key, f in list(st.get("follow", {}).items()):
        if f.get("done", 0) >= 3:
            if now - f.get("t0", now) > 3 * 86400:
                del st["follow"][key]
            continue
        if now < f.get("last", now) + FOLLOW_GAP or done_runs >= 3:
            continue
        stage = f.get("done", 0) + 1
        ok, info = do_stage(int(key), stage)
        done_runs += 1
        print("Follow-up %s stage %d: %s (%s)" % (key, stage, "OK" if ok else "FAIL", info))
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


def main():
    if TEST_FOLLOW_ID.isdigit():
        return run_test(int(TEST_FOLLOW_ID))
    channels = [("Telegram", TG_TOKEN and TG_CH), ("Bale", BALE_TOKEN and BALE_CH), ("Eitaa", EITAA_TOKEN and EITAA_CH)]
    if not any(c[1] for c in channels):
        sys.exit("هیچ کانالی تنظیم نشده است (Secretهای کانال را بسازید).")
    posts = fetch_recent()
    st = load_state()
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
        if any(res.values()):
            st.setdefault("follow", {})[key] = {"t0": int(time.time()), "last": int(time.time()), "done": 0, "tries": 0}
        line = " | ".join("%s %s" % (k, "✅" if v else "❌") for k, v in res.items())
        details = "\n".join("• %s: %s" % (k, (hint(errs[k]) or errs[k][:120])) for k, v in res.items() if not v)
        print("Announced post %s: %s" % (p["id"], line))
        g.notify("📣 اعلان مقاله در کانال‌ها:\n%s\n\n%s%s" % (p["title"], line, ("\n\n" + details) if details else ""))
        save_state(st)
    process_follow(st)
    save_state(st)


if __name__ == "__main__":
    main()
