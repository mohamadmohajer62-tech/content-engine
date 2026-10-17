import os, re, io, json, sys
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


def cover_bytes(media_id):
    if not media_id:
        return None
    try:
        r = g.wp("GET", "%s/wp-json/wp/v2/media/%s" % (g.WP, media_id), tries=3, auth=g.AUTH, params={"_fields": "source_url"})
        url = r.json().get("source_url")
        if not url:
            return None
        img = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"}).content
        from PIL import Image
        im = Image.open(io.BytesIO(img)).convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=88)
        return buf.getvalue()
    except Exception as e:
        print("Cover fetch failed:", type(e).__name__)
        return None


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
    ex = short_excerpt(p["excerpt"]) if p["excerpt"] else ""
    tags = hashtags(names)
    plain_cap = "%s\n\n%s\n\n🔗 مطالعه‌ی کامل مقاله:\n%s\n\n%s\n%s" % (p["title"], ex, p["link"], tags, BRAND)
    html_cap = "<b>%s</b>\n\n%s\n\n🔗 مطالعه‌ی کامل مقاله:\n%s\n\n%s\n<b>%s</b>" % (
        g.esc(p["title"]), g.esc(ex), g.esc(p["link"]), g.esc(tags), BRAND)
    return plain_cap.strip()[:1000], html_cap.strip()[:1000]


def send_bot_api(name, base, token, chat, jpg, plain_cap, html_cap, link):
    """تلگرام و بله (API سازگار): عکس + کپشن + دکمه‌ی لینک."""
    markup = json.dumps({"inline_keyboard": [[{"text": "مطالعه‌ی مقاله", "url": link}]]})
    use_html = (name == "Telegram")
    cap = html_cap if use_html else plain_cap
    for with_markup in (True, False):
        d = {"chat_id": chat}
        if with_markup:
            d["reply_markup"] = markup
        if jpg:
            d["caption"] = cap
            if use_html:
                d["parse_mode"] = "HTML"
            files, method = {"photo": ("cover.jpg", jpg, "image/jpeg")}, "sendPhoto"
        else:
            d["text"] = cap
            if use_html:
                d["parse_mode"] = "HTML"
            files, method = None, "sendMessage"
        try:
            r = requests.post((base % token) + method, data=d, files=files, timeout=90)
        except Exception as e:
            print("%s error: %s" % (name, type(e).__name__))
            continue
        print("%s %s (markup=%s): %s %s" % (name, method, with_markup, r.status_code, "" if r.status_code == 200 else r.text[:160]))
        if r.status_code == 200:
            return True
    return False


def send_eitaa(token, chat, jpg, plain_cap, title):
    base = "https://eitaayar.ir/api/%s/" % token
    if jpg:
        try:
            r = requests.post(base + "sendFile", data={"chat_id": chat, "caption": plain_cap, "title": title[:60]},
                              files={"file": ("cover.jpg", jpg, "image/jpeg")}, timeout=120)
            print("Eitaa sendFile:", r.status_code, "" if r.status_code == 200 else r.text[:160])
            if r.status_code == 200:
                return True
        except Exception as e:
            print("Eitaa sendFile error:", type(e).__name__)
    try:
        r = requests.post(base + "sendMessage", data={"chat_id": chat, "text": plain_cap, "title": title[:60]}, timeout=60)
        print("Eitaa sendMessage:", r.status_code, "" if r.status_code == 200 else r.text[:160])
        return r.status_code == 200
    except Exception as e:
        print("Eitaa sendMessage error:", type(e).__name__)
        return False


def main():
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
    new = [p for p in posts if p["id"] not in st["ids"]]
    new.sort(key=lambda p: p["date"])
    print("New published posts:", [p["id"] for p in new])
    for p in new[:MAX_PER_RUN]:
        names = tag_names(p["tags"])
        jpg = cover_bytes(p["media"])
        plain_cap, html_cap = build_captions(p, names)
        res = {}
        if TG_TOKEN and TG_CH:
            res["Telegram"] = send_bot_api("Telegram", "https://api.telegram.org/bot%s/", TG_TOKEN, TG_CH, jpg, plain_cap, html_cap, p["link"])
        if BALE_TOKEN and BALE_CH:
            res["Bale"] = send_bot_api("Bale", "https://tapi.bale.ai/bot%s/", BALE_TOKEN, BALE_CH, jpg, plain_cap, html_cap, p["link"])
        if EITAA_TOKEN and EITAA_CH:
            res["Eitaa"] = send_eitaa(EITAA_TOKEN, EITAA_CH, jpg, plain_cap, p["title"])
        key = str(p["id"])
        st["attempts"][key] = st["attempts"].get(key, 0) + 1
        if any(res.values()) or st["attempts"][key] >= 3:
            st["ids"].append(p["id"])
        line = " | ".join("%s %s" % (k, "✅" if v else "❌") for k, v in res.items())
        print("Announced post %s: %s" % (p["id"], line))
        g.notify("📣 اعلان مقاله در کانال‌ها:\n%s\n\n%s" % (p["title"], line))
        save_state(st)
    save_state(st)


if __name__ == "__main__":
    main()
