"""
موتور مشترک رندر با هویت بصری سایت (سبز + نارنجی تراکوتا) برای استوری و اینفوگرافیک.
متن فارسی با HTML/CSS و مرورگر Playwright رندر می‌شود؛ پس حروف همیشه درست و خوانا است.
"""
import os, io, re, base64, json, html as htmllib

G, G2, GD, GX = "#386641", "#6A994E", "#2a4d31", "#1f3a24"      # سبزهای برند
T, T2 = "#CC6A45", "#A84F31"                                       # نارنجی تراکوتا
CREAM, INK, MUTED = "#F6F1E6", "#1d2a20", "#5f6c62"
FONT = "'Vazirmatn','Noto Sans Arabic','Noto Naskh Arabic','DejaVu Sans',sans-serif"
AUTHOR = "محمد مهاجر | استراتژیست رشد کسب‌وکار"
SITE = "mohammadmohajer.ir"


def esc(t):
    return htmllib.escape(str(t or ""), quote=True)


def fa(n):
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def fill(tpl, **kw):
    for k, v in kw.items():
        tpl = tpl.replace("@@%s@@" % k, str(v))
    return tpl


def logo_b64(height=96):
    try:
        from PIL import Image
        im = Image.open("logo.png").convert("RGBA")
        im = im.resize((int(im.width * height / im.height), height), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def logo_tag(height=96, on_dark=True):
    b = logo_b64(height)
    if not b:
        return ""
    # روی زمینه‌ی تیره، لوگو داخل یک کارت روشن می‌نشیند تا همیشه خوانا باشد
    img = '<img src="data:image/png;base64,%s" style="height:%dpx;display:block">' % (b, height)
    if on_dark:
        return '<div style="background:%s;padding:14px 20px;border-radius:26px;display:flex">%s</div>' % (CREAM, img)
    return img


def data_uri(img_bytes):
    if not img_bytes:
        return ""
    mime = "image/png" if img_bytes[:4] == b"\x89PNG" else ("image/webp" if img_bytes[:4] == b"RIFF" else "image/jpeg")
    return "data:%s;base64,%s" % (mime, base64.b64encode(img_bytes).decode())


def render(html_doc, width, height, out_path):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": width, "height": height})
        pg.set_content(html_doc, wait_until="load")
        pg.wait_for_timeout(500)          # صبر برای بارگذاری فونت و تصویر
        pg.screenshot(path=out_path, type="png")
        b.close()
    return out_path


def page(inner, w, h, bg):
    return fill(
        '<html lang="fa" dir="rtl"><head><meta charset="utf-8"></head><body style="margin:0">'
        '<div style="width:@@w@@px;height:@@h@@px;position:relative;overflow:hidden;box-sizing:border-box;'
        "font-family:@@font@@;background:@@bg@@\">@@inner@@</div></body></html>",
        w=w, h=h, font=FONT, bg=bg, inner=inner)


def fit(text, big, mid, small, a=70, b=110):
    n = len(text or "")
    return big if n <= a else (mid if n <= b else small)


# ------------------------------------------------------------------ استوری ۱: معرفی مقاله
def story_intro(title, hook, img_bytes, out_path, tag="مقاله‌ی جدید"):
    W, H = 1080, 1920
    img = data_uri(img_bytes)
    if img:
        photo = ('<img src="@@img@@" style="width:100%;height:100%;object-fit:cover;display:block">')
        photo = fill(photo, img=img)
    else:
        photo = ('<div style="width:100%;height:100%;background:linear-gradient(135deg,@@g2@@,@@g@@);display:flex;align-items:center;'
                 'justify-content:center;color:rgba(255,255,255,.35);font-size:240px">◆</div>')
        photo = fill(photo, g2=G2, g=G)
    tsize = fit(title, 78, 68, 58, 45, 80)
    inner = fill(
        '<div style="position:absolute;left:-220px;top:430px;width:640px;height:640px;border-radius:50%;background:@@t@@;opacity:.16"></div>'
        '<div style="position:absolute;right:-260px;bottom:-200px;width:760px;height:760px;border-radius:50%;background:@@g2@@;opacity:.2"></div>'
        '<div style="position:absolute;inset:0;padding:150px 70px 330px;display:flex;flex-direction:column;gap:34px">'
        '<div style="display:flex;align-items:center;justify-content:space-between">@@logo@@'
        '<div style="color:#e9efe3;font-size:30px;font-weight:600;text-align:left;line-height:1.7">@@author@@</div></div>'
        '<div style="display:flex"><span style="background:@@t@@;color:#fff;font-size:38px;font-weight:800;padding:10px 38px;border-radius:999px;'
        'box-shadow:0 10px 30px rgba(0,0,0,.25)">@@tag@@</span></div>'
        '<div style="flex:1;min-height:0;border-radius:44px;overflow:hidden;border:8px solid @@cream@@;box-shadow:0 30px 60px rgba(0,0,0,.35);position:relative">'
        '@@photo@@<div style="position:absolute;inset:auto 0 0 0;height:35%;background:linear-gradient(180deg,rgba(31,58,36,0),rgba(31,58,36,.65))"></div></div>'
        '<div style="color:#fff;font-size:@@ts@@px;font-weight:800;line-height:1.7">@@title@@</div>'
        '<div style="color:#dbe7d3;font-size:40px;line-height:1.8;font-weight:500">@@hook@@</div>'
        "</div>"
        '<div style="position:absolute;left:0;right:0;bottom:0;height:300px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px">'
        '<div style="background:@@t@@;color:#fff;font-size:44px;font-weight:800;padding:18px 62px;border-radius:999px;box-shadow:0 14px 34px rgba(0,0,0,.3)">'
        "مطالعه‌ی کامل مقاله  ←</div>"
        '<div style="color:#cfe0c9;font-size:32px;letter-spacing:.5px" dir="ltr">@@site@@</div></div>',
        t=T, g2=G2, logo=logo_tag(86), author=esc(AUTHOR), tag=esc(tag), cream=CREAM, photo=photo,
        ts=tsize, title=esc(title), hook=esc(hook), site=SITE)
    return render(page(inner, W, H, "linear-gradient(165deg,%s 0%%,%s 55%%,%s 100%%)" % (GD, G, GX)), W, H, out_path)


# ------------------------------------------------------------------ استوری ۲: نقل‌قول تیره
def story_quote_dark(quote, title, out_path, label="نکته‌ی مهم"):
    W, H = 1080, 1920
    qs = fit(quote, 84, 72, 60, 60, 100)
    inner = fill(
        '<div style="position:absolute;right:30px;top:230px;font-size:760px;line-height:1;color:@@t@@;opacity:.17;font-family:Georgia,serif">”</div>'
        '<div style="position:absolute;left:-240px;bottom:-240px;width:760px;height:760px;border-radius:50%;background:@@g2@@;opacity:.22"></div>'
        '<div style="position:absolute;inset:0;padding:150px 80px 330px;display:flex;flex-direction:column;justify-content:space-between">'
        '<div style="display:flex;align-items:center;justify-content:space-between">@@logo@@'
        '<div style="color:#e9efe3;font-size:30px;font-weight:600;line-height:1.7">@@author@@</div></div>'
        '<div><div style="width:150px;height:10px;border-radius:5px;background:@@t@@;margin-bottom:54px"></div>'
        '<div style="color:#fff;font-size:@@qs@@px;font-weight:800;line-height:1.85">«@@quote@@»</div>'
        '<div style="margin-top:60px;color:@@t@@;font-size:38px;font-weight:700">@@label@@</div></div>'
        '<div style="border-top:2px solid rgba(255,255,255,.25);padding-top:30px;color:#d8e6d2;font-size:34px;line-height:1.8">از مقاله‌ی «@@title@@»</div>'
        "</div>"
        '<div style="position:absolute;left:0;right:0;bottom:0;height:300px;display:flex;align-items:center;justify-content:center;color:#cfe0c9;font-size:34px" dir="ltr">@@site@@</div>',
        t=T, g2=G2, logo=logo_tag(80), author=esc(AUTHOR), qs=qs, quote=esc(quote), label=esc(label), title=esc(title), site=SITE)
    return render(page(inner, W, H, "linear-gradient(170deg,%s 0%%,%s 100%%)" % (G, GX)), W, H, out_path)


# ------------------------------------------------------------------ استوری ۳: نقل‌قول روشن
def story_quote_light(quote, title, out_path, label="یک جمله برای یادآوری"):
    W, H = 1080, 1920
    qs = fit(quote, 80, 68, 58, 60, 100)
    inner = fill(
        '<div style="position:absolute;right:0;top:0;bottom:0;width:34px;background:linear-gradient(180deg,@@g@@,@@g2@@)"></div>'
        '<div style="position:absolute;left:-180px;top:-180px;width:620px;height:620px;border-radius:50%;background:@@t@@;opacity:.14"></div>'
        '<div style="position:absolute;inset:0;padding:150px 90px 330px 110px;display:flex;flex-direction:column;justify-content:space-between">'
        '<div style="display:flex;align-items:center;justify-content:space-between"><div style="display:flex">@@logo@@</div>'
        '<div style="color:@@g@@;font-size:30px;font-weight:700;line-height:1.7">@@author@@</div></div>'
        '<div><div style="font-size:300px;line-height:.5;color:@@t@@;font-family:Georgia,serif;height:120px">“</div>'
        '<div style="color:@@gd@@;font-size:@@qs@@px;font-weight:800;line-height:1.85;margin-top:30px">@@quote@@</div>'
        '<div style="display:flex;align-items:center;gap:20px;margin-top:56px"><div style="width:90px;height:8px;border-radius:4px;background:@@t@@"></div>'
        '<div style="color:@@t2@@;font-size:38px;font-weight:700">@@label@@</div></div></div>'
        '<div style="background:#fff;border-radius:30px;padding:26px 34px;box-shadow:0 14px 30px rgba(42,77,49,.12);color:@@ink@@;font-size:34px;line-height:1.8">'
        '<span style="color:@@t@@;font-weight:800">مقاله:</span> @@title@@</div></div>'
        '<div style="position:absolute;left:0;right:0;bottom:0;height:300px;display:flex;align-items:center;justify-content:center;color:@@g@@;font-size:34px;font-weight:600" dir="ltr">@@site@@</div>',
        g=G, g2=G2, gd=GD, t=T, t2=T2, ink=INK, logo=logo_tag(80, on_dark=False), author=esc(AUTHOR),
        qs=qs, quote=esc(quote), label=esc(label), title=esc(title), site=SITE)
    return render(page(inner, W, H, CREAM), W, H, out_path)


# ------------------------------------------------------------------ اینفوگرافیک
def infographic(title, items, out_path, fmt="post"):
    W, H = (1080, 1350) if fmt == "post" else (1080, 1920)
    n = len(items)
    pad_bottom = 150 if fmt == "post" else 330
    tiles = []
    for i, it in enumerate(items):
        tiles.append(fill(
            '<div style="background:#fff;border-radius:30px;padding:28px 28px 26px;box-shadow:0 12px 28px rgba(42,77,49,.12);display:flex;flex-direction:column;gap:12px;'
            'border-top:8px solid @@c@@;min-height:0;overflow:hidden">'
            '<div style="display:flex;align-items:center;gap:16px"><div style="flex:0 0 62px;height:62px;border-radius:50%;background:@@c@@;color:#fff;font-size:34px;font-weight:800;'
            'display:flex;align-items:center;justify-content:center">@@n@@</div>'
            '<div style="font-size:34px;font-weight:800;color:@@gd@@;line-height:1.55">@@h@@</div></div>'
            '<div style="font-size:27px;color:@@ink@@;line-height:1.8;font-weight:500">@@t@@</div></div>',
            c=(T if i % 2 == 0 else G), n=fa(i + 1), gd=GD, ink=INK, h=esc(it.get("h", "")), t=esc(it.get("t", ""))))
    inner = fill(
        '<div style="position:absolute;inset:0;padding:@@pt@@px 60px @@pb@@px;display:flex;flex-direction:column;gap:30px">'
        '<div style="display:flex;align-items:center;justify-content:space-between;gap:24px"><div style="display:flex">@@logo@@</div>'
        '<div style="color:@@g@@;font-size:28px;font-weight:700;line-height:1.7">@@author@@</div></div>'
        '<div style="background:linear-gradient(135deg,@@gd@@,@@g@@);color:#fff;border-radius:34px;padding:34px 40px;font-size:@@ts@@px;font-weight:800;line-height:1.65;'
        'box-shadow:0 16px 34px rgba(42,77,49,.3)">@@title@@</div>'
        '<div style="flex:1;min-height:0;display:grid;grid-template-columns:1fr 1fr;grid-auto-rows:1fr;gap:22px">@@tiles@@</div>'
        '<div style="text-align:center;color:@@g@@;font-size:28px;font-weight:600" dir="ltr">@@site@@</div></div>',
        pt=70 if fmt == "post" else 150, pb=pad_bottom, g=G, gd=GD, logo=logo_tag(70, on_dark=False), author=esc(AUTHOR),
        ts=fit(title, 46, 40, 36, 40, 70), title=esc(title), tiles="".join(tiles), site=SITE)
    return render(page(inner, W, H, CREAM), W, H, out_path)


# ------------------------------------------------------------------ دریافت مقاله از وردپرس
def strip_html(h, n=6000):
    h = re.sub(r"(?is)<(script|style).*?</\1>", " ", h or "")
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    h = htmllib.unescape(h)
    return re.sub(r"\s+", " ", h).strip()[:n]


def fetch_article(g, post_id):
    """عنوان، متن و عکس شاخص یک مقاله (حتی پیش‌نویس) را از وردپرس می‌گیرد."""
    url = "%s/wp-json/wp/v2/posts/%s?_embed=1&context=edit" % (g.WP, post_id)
    r = g.wp("GET", url, tries=3, auth=g.AUTH, timeout=60)
    if r.status_code != 200:
        raise SystemExit("مقاله پیدا نشد (HTTP %s)." % r.status_code)
    j = r.json()
    title = strip_html((j.get("title") or {}).get("raw") or (j.get("title") or {}).get("rendered") or "", 300)
    content = (j.get("content") or {}).get("raw") or (j.get("content") or {}).get("rendered") or ""
    img = None
    try:
        src = j["_embedded"]["wp:featuredmedia"][0]["source_url"]
    except Exception:
        src = ""
    if not src and j.get("featured_media"):
        try:
            m = g.wp("GET", "%s/wp-json/wp/v2/media/%s" % (g.WP, j["featured_media"]), tries=3, auth=g.AUTH, timeout=60)
            src = m.json().get("source_url", "")
        except Exception:
            src = ""
    if src:
        try:
            img = g.S.get(src, timeout=90).content
        except Exception as e:
            print("Cover download failed:", type(e).__name__)
    return {"title": title, "text": strip_html(content, 7000), "image": img, "link": j.get("link", "")}


def ask_json(g, user, max_tokens=700):
    """از مدل پاسخ JSON می‌گیرد؛ در صورت خرابی None برمی‌گرداند."""
    try:
        out = g.ask(user + "\n\nفقط یک JSON معتبر بده؛ بدون هیچ توضیح یا بک‌تیک.", max_tokens,
                    "You are an editor for a Persian business-strategy blog. Reply with strict JSON only.", min_len=10)
    except SystemExit:
        return None
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def send_photo(g, path, caption=""):
    """ارسال به تلگرام و بله (چت شخصی شما)."""
    import requests
    ok = 0
    for name, base, tok, chat in (("Telegram", "https://api.telegram.org/bot%s/sendPhoto", g.TG_TOKEN, g.TG_CHAT),
                                  ("Bale", "https://tapi.bale.ai/bot%s/sendPhoto", g.BALE_TOKEN, g.BALE_CHAT)):
        if not (tok and chat):
            continue
        try:
            with open(path, "rb") as f:
                r = requests.post(base % tok, data={"chat_id": chat, "caption": caption[:900]}, files={"photo": f}, timeout=120)
            print("Send %s: %s" % (name, r.status_code))
            ok += 1 if r.status_code == 200 else 0
        except Exception as e:
            print("Send %s failed: %s" % (name, type(e).__name__))
    return ok
