"""
ساخت PDF واقعی هر شماره‌ی هفتگی نشریه + «سخن سردبیر» خودکار.
  python build_issue.py check   -> فقط می‌سنجد کاری لازم است یا نه (سریع)
  python build_issue.py         -> می‌سازد، در وردپرس بارگذاری و ثبت می‌کند، به شما خبر می‌دهد
PDF هر مقاله همان PDF خودش است (از دکمه‌ی دانلود مقاله)؛ اگر نبود، همان‌جا ساخته می‌شود.
"""
import os, sys, re, io, json, base64, time
import requests
import generate as g
import brand_render as b

MODE = sys.argv[1] if len(sys.argv) > 1 else "build"
ISSUE_NO = os.environ.get("ISSUE_NO", "").strip()
FORCE = os.environ.get("FORCE", "").strip().lower() in ("1", "true", "yes")
ED_OVERRIDE = os.environ.get("EDITORIAL", "").strip()
API = g.WP + "/wp-json/mm-magazine/v1"
os.makedirs("out", exist_ok=True)

TG_URL = os.environ.get("TG_URL", "https://t.me/fcmo_mohajer")
BALE_URL = os.environ.get("BALE_URL", "https://ble.ir/fcmo_mohajer")
EITAA_URL = os.environ.get("EITAA_URL", "https://eitaa.com/fcmo_mohajer")
HANDLE = os.environ.get("CHANNEL_HANDLE", "@fcmo_mohajer")
MAG_URL = os.environ.get("MAGAZINE_PAGE_URL", "https://mohammadmohajer.ir/business-growth-magazine/")

GOLD, GOLD2, EM0, EM1, EM2, PAPER = "#C9A24B", "#E8CF8A", "#07150c", "#0f2a1b", "#173b25", "#f9f4e7"
FONT = b.FONT


# ------------------------------------------------------------------ انتخاب شماره‌ها
def issue_list():
    r = g.wp("GET", API + "/issues", tries=3, timeout=90)
    if r.status_code != 200:
        sys.exit("فهرست شماره‌ها در دسترس نیست (HTTP %s). افزونه‌ی نشریه به‌روز است؟" % r.status_code)
    return r.json().get("issues", [])


def pick_targets():
    items = issue_list()
    if ISSUE_NO:
        return [i for i in items if str(i["no"]) == ISSUE_NO]
    todo = [i for i in items if (not i["open"]) and i["count"] > 0 and (FORCE or not i["pdf"])]
    return todo[:2]                      # حداکثر دو شماره (قدیمی‌ترین اول) در هر اجرا


if MODE == "check":
    t = pick_targets()
    print("Targets:", [x["no"] for x in t])
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write("need=%s\n" % ("true" if t else "false"))
    sys.exit(0)


# ------------------------------------------------------------------ مقاله‌ها
def fetch_posts(ids):
    url = "%s/wp-json/wp/v2/posts?include=%s&per_page=20&orderby=include&_embed=wp:featuredmedia" % (g.WP, ",".join(str(i) for i in ids))
    r = g.wp("GET", url, tries=3, timeout=120)
    if r.status_code != 200:
        sys.exit("دریافت مقاله‌ها ناموفق بود (HTTP %s)." % r.status_code)
    by = {p["id"]: p for p in r.json()}
    posts = []
    for i in ids:
        p = by.get(i)
        if not p:
            continue
        content = (p.get("content") or {}).get("rendered", "")
        try:
            img_url = p["_embedded"]["wp:featuredmedia"][0]["source_url"]
        except Exception:
            img_url = ""
        m = re.search(r'href="([^"]+\.pdf)"', content, re.I)
        posts.append({
            "id": i,
            "title": b.strip_html((p.get("title") or {}).get("rendered", ""), 300),
            "excerpt": b.strip_html((p.get("excerpt") or {}).get("rendered", ""), 260),
            "content": content,
            "link": p.get("link", ""),
            "img_url": img_url,
            "pdf_url": m.group(1) if m else "",
        })
    return posts


def download(url):
    try:
        return g.S.get(url, timeout=150).content
    except Exception as e:
        print("Download failed:", type(e).__name__, url[-60:])
        return None


def webp_b64(img_bytes):
    if not img_bytes:
        return ""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        im.thumbnail((1400, 1400))
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=80)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def core_html(content):
    """فقط ساختار متنی (تیتر، پاراگراف، فهرست، نقل‌قول) برای PDFِ جایگزین."""
    keep = []
    for m in re.finditer(r"<(h2|h3|p|ul|ol|blockquote)\b[^>]*>.*?</\1>", content, flags=re.S | re.I):
        keep.append(re.sub(r'\sstyle="[^"]*"', "", m.group(0)))
    return "\n".join(keep)


def article_pdf(p, img_bytes):
    """PDF مقاله: اول نسخه‌ی موجود؛ اگر نبود، بسازد."""
    if p["pdf_url"]:
        data = download(p["pdf_url"])
        if data and data[:4] == b"%PDF":
            return data
    print("Article %s has no PDF; generating." % p["id"])
    words = len(b.strip_html(p["content"], 10 ** 6).split())
    doc = g.pdf_document(p["title"], webp_b64(img_bytes), core_html(p["content"]), max(1, round(words / 180)))
    return g.make_pdf(doc)


# ------------------------------------------------------------------ سخن سردبیر
def make_editorial(no, posts):
    if ED_OVERRIDE:
        return ED_OVERRIDE
    items = "\n".join("- %s: %s" % (p["title"], p["excerpt"][:160]) for p in posts)
    prompt = (
        "شماره‌ی %s نشریه‌ی هفتگی «رشد کسب‌وکار» شامل این مقاله‌هاست:\n%s\n\n"
        "برای «سخن سردبیر» همین شماره یک متن ۹۰ تا ۱۳۰ کلمه‌ای بنویس:\n"
        "- اول‌شخص و صمیمی، با صدای محمد مهاجر (استراتژیست رشد کسب‌وکار) که با مدیران حرف می‌زند\n"
        "- دو پاراگراف کوتاه؛ اولی درباره‌ی رشته‌ی مشترک مقاله‌های این هفته، دومی یک پیشنهاد عملی برای هفته‌ی پیش‌رو\n"
        "- بدون بولد، بدون فهرست، بدون تیتر، بدون اشاره به محصول یا خدمات، بدون کلمه‌ی انگلیسی\n"
        "فقط خود متن را بنویس." % (b.fa(no), items))
    for _ in range(3):
        try:
            t = g.ask(prompt, 700, "تو سردبیر یک نشریه‌ی تخصصی فارسی برای مدیران هستی. روان، دقیق و صمیمی می‌نویسی.", min_len=200).strip()
        except SystemExit:
            break
        if 300 <= len(t) <= 1100 and g.latin_ratio(t) <= 0.1:
            return t
    return ("در این شماره، مقاله‌های هفته را کنار هم گذاشته‌ایم تا ببینید رشد از تصمیم‌های کوچک و پیوسته ساخته می‌شود. "
            "هر مقاله یک قطعه از همین تصویر است.\n\nپیشنهاد من برای این هفته ساده است: فقط یکی از این مقاله‌ها را انتخاب کنید "
            "و یک اقدام کوچک از آن را تا آخر هفته در کسب‌وکارتان اجرا کنید.")


# ------------------------------------------------------------------ صفحه‌های سفارشی PDF
def css_base():
    return ("@page{size:210mm 297mm;margin:0}*{box-sizing:border-box}body{margin:0;font-family:%s}"
            ".pg{width:210mm;height:297mm;position:relative;overflow:hidden;page-break-after:always}" % FONT)


def wrap(inner):
    return '<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><style>%s</style></head><body>%s</body></html>' % (css_base(), inner)


def cover_html(no, range_label, titles, img_bytes):
    img = b.data_uri(img_bytes)
    bg = ('<img src="%s" style="position:absolute;inset:0;width:100%%;height:100%%;object-fit:cover">' % img) if img else \
         '<div style="position:absolute;inset:0;background:linear-gradient(135deg,#6A994E,#386641)"></div>'
    heads = "".join('<div style="position:relative;padding-right:7mm;margin-bottom:2.4mm;font-size:15pt;line-height:1.6;color:#fff">'
                    '<span style="position:absolute;right:0;color:%s;font-size:9pt;top:1.6mm">◆</span>%s</div>' % (GOLD, b.esc(t)) for t in titles[:4])
    return fill_page(
        '<div class="pg" style="background:%s">%s'
        '<div style="position:absolute;inset:0;background:linear-gradient(180deg,rgba(6,20,12,.92) 0%%,rgba(6,20,12,.55) 22%%,rgba(6,20,12,0) 42%%,rgba(6,20,12,.35) 58%%,rgba(6,20,12,.95) 100%%)"></div>'
        '<div style="position:absolute;inset:9mm;border:1.1mm solid %s"></div><div style="position:absolute;inset:12mm;border:.35mm solid rgba(232,207,138,.55)"></div>'
        '<div style="position:absolute;top:24mm;left:0;right:0;text-align:center"><div style="color:%s;font-size:15pt;font-weight:700">نشریه‌ی هفتگی</div>'
        '<div style="color:%s;font-size:66pt;font-weight:900;line-height:1.25">رشد کسب‌وکار</div>'
        '<div style="display:inline-block;margin-top:3mm;color:#fff;font-size:14pt;padding:1mm 9mm;border-top:.4mm solid %s;border-bottom:.4mm solid %s">شماره‌ی %s</div></div>'
        '<div style="position:absolute;left:24mm;bottom:96mm;width:34mm;height:34mm;border-radius:50%%;background:radial-gradient(circle at 30%% 25%%,#fff1bf,#c9a24b 55%%,#8f6b1e);'
        'color:#2a1c05;text-align:center;box-shadow:0 2mm 5mm rgba(0,0,0,.5)"><div style="font-size:11pt;font-weight:700;padding-top:5mm">شماره</div>'
        '<div style="font-size:28pt;font-weight:900;line-height:1">%s</div></div>'
        '<div style="position:absolute;left:24mm;right:24mm;bottom:26mm"><div style="color:%s;font-size:14pt;font-weight:700;margin-bottom:4mm">%s</div>%s</div></div>'
        % (EM1, bg, GOLD2, GOLD2, GOLD2, GOLD, GOLD, b.fa(no), b.fa(no), GOLD2, b.esc(range_label), heads))


def fill_page(s):
    return s


def editorial_html(no, text, custom):
    paras = "".join('<p style="margin:0 0 5mm">%s</p>' % b.esc(x.strip()) for x in re.split(r"\n{2,}|\n", text) if x.strip())
    sig = ('<div style="margin-top:8mm;color:#386641;font-weight:800;font-size:15pt">محمد مهاجر<div style="color:#5f6c62;font-weight:400;font-size:11pt">استراتژیست رشد کسب‌وکار</div></div>')
    return ('<div class="pg" style="background:%s"><div style="position:absolute;inset:14mm;border:.35mm solid #e7dfc9"></div>'
            '<div style="position:absolute;left:26mm;right:26mm;top:30mm"><div style="font-size:30pt;color:%s;font-weight:800">سخن سردبیر</div>'
            '<div style="width:34mm;height:1.2mm;background:%s;margin:3mm 0 10mm"></div>'
            '<div style="font-size:60pt;color:%s;line-height:.5;height:14mm;font-family:Georgia,serif">“</div>'
            '<div style="font-size:15pt;line-height:2.15;color:#1b261e;text-align:justify">%s</div>%s</div>'
            '<div style="position:absolute;bottom:16mm;left:0;right:0;text-align:center;color:#5f6c62;font-size:10pt">— %s —</div></div>'
            % (PAPER, EM1, GOLD, GOLD, paras, sig, b.fa(2)))


def toc_html(no, rows, folio):
    li = "".join(
        '<div style="display:flex;align-items:baseline;gap:4mm;margin-bottom:7mm"><span style="color:%s;font-weight:900;font-size:20pt;min-width:12mm">%s</span>'
        '<span style="font-size:15pt;line-height:1.7;color:#1b261e">%s</span><span style="flex:1;border-bottom:.5mm dotted #cdbf9b;transform:translateY(-1.5mm)"></span>'
        '<span style="color:#5f6c62;font-size:12pt">%s</span></div>' % (GOLD, b.fa(i + 1), b.esc(t), b.fa(pg)) for i, (t, pg) in enumerate(rows))
    return ('<div class="pg" style="background:%s"><div style="position:absolute;inset:14mm;border:.35mm solid #e7dfc9"></div>'
            '<div style="position:absolute;left:26mm;right:26mm;top:30mm"><div style="font-size:30pt;color:%s;font-weight:800">در این شماره</div>'
            '<div style="width:34mm;height:1.2mm;background:%s;margin:3mm 0 12mm"></div>%s</div>'
            '<div style="position:absolute;bottom:16mm;left:0;right:0;text-align:center;color:#5f6c62;font-size:10pt">— %s —</div></div>'
            % (PAPER, EM1, GOLD, li, b.fa(folio)))


def back_html():
    def chip(name, url):
        return ('<a href="%s" style="flex:1;display:block;text-decoration:none;color:#fff;border:.4mm solid %s;border-radius:4mm;padding:5mm 3mm;text-align:center">'
                '<div style="color:%s;font-weight:800;font-size:15pt">%s</div>'
                '<div style="font-size:11pt;direction:ltr;margin-top:1mm;color:#e9efe5">%s</div></a>') % (url, GOLD2, GOLD2, name, HANDLE)
    socials = '<div style="display:flex;gap:5mm">%s%s%s</div>' % (chip("تلگرام", TG_URL), chip("بله", BALE_URL), chip("ایتا", EITAA_URL))
    return (
        '<div class="pg" style="background:linear-gradient(160deg,%s,%s)"><div style="position:absolute;inset:9mm;border:.9mm solid %s"></div>'
        '<div style="position:absolute;inset:12mm;border:.3mm solid rgba(232,207,138,.5)"></div>'
        '<div style="position:absolute;left:26mm;right:26mm;top:34mm;text-align:center;color:#fff">'
        '<div style="color:%s;font-size:24pt">◆</div>'
        '<div style="color:%s;font-size:27pt;font-weight:900;line-height:1.6;margin:5mm 0 4mm">نشریه‌های بعدی را از دست ندهید</div>'
        '<div style="font-size:14.5pt;line-height:2.1;color:#e3eedd">نشریه‌ی هفتگی «رشد کسب‌وکار» هر شنبه، منظم و به‌روز برای شما ارسال می‌شود. '
        'برای دریافت شماره‌ی بعد، در نشریه عضو شوید.</div>'
        '<a href="%s" style="display:inline-block;margin:8mm 0 12mm;text-decoration:none;background:linear-gradient(115deg,#8f6b1e,#e8cf8a 45%%,#c9a24b);'
        'color:#2a1c05;font-weight:900;font-size:15pt;padding:3.5mm 14mm;border-radius:99mm">عضویت در نشریه</a>'
        '<div style="color:%s;font-size:14pt;font-weight:800;margin-bottom:5mm">ما را در این شبکه‌ها دنبال کنید</div>%s'
        '<div style="margin-top:14mm;font-size:14pt;line-height:2.1;color:#e3eedd">اگر این نشریه برایتان مفید بود، آن را برای کسی که به آن نیاز دارد بفرستید.</div>'
        '<div style="margin-top:12mm;color:%s;font-size:16pt;font-weight:800">محمد مهاجر</div>'
        '<div style="font-size:12pt;color:#cfe0c9">استراتژیست رشد کسب‌وکار</div>'
        '<div style="font-size:11pt;color:#cfe0c9;margin-top:2mm;direction:ltr">mohammadmohajer.ir</div></div></div>'
        % (EM2, EM0, GOLD2, GOLD, GOLD2, MAG_URL, GOLD2, socials, GOLD2))


def render_pdf(inner):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br = p.chromium.launch()
        pg = br.new_page()
        pg.set_content(wrap(inner), wait_until="load")
        pg.wait_for_timeout(400)
        data = pg.pdf(width="210mm", height="297mm", print_background=True, prefer_css_page_size=True,
                      margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        br.close()
    return data


def merge(parts, title, bookmarks):
    """parts: فهرست بایت‌های PDF؛ bookmarks: (نام، شماره‌ی صفحه‌ی اول از صفر)."""
    from pypdf import PdfReader, PdfWriter
    w = PdfWriter()
    for data in parts:
        for page in PdfReader(io.BytesIO(data)).pages:
            w.add_page(page)
    for name, idx in bookmarks:
        w.add_outline_item(name, idx)
    w.add_metadata({"/Title": title, "/Author": "محمد مهاجر"})
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def page_count(data):
    from pypdf import PdfReader
    return len(PdfReader(io.BytesIO(data)).pages)


# ------------------------------------------------------------------ ساخت یک شماره
def build(issue):
    no = issue["no"]
    print("== Building issue", no, issue.get("range"), "==")
    posts = fetch_posts(issue["ids"])
    if not posts:
        print("No posts; skipped.")
        return
    imgs = {p["id"]: (download(p["img_url"]) if p["img_url"] else None) for p in posts}
    lead = next((imgs[p["id"]] for p in posts if imgs.get(p["id"])), None)

    arts = []
    for p in posts:
        data = article_pdf(p, imgs.get(p["id"]))
        if data:
            arts.append((p, data, page_count(data)))
        else:
            print("Skipped article", p["id"], "(no PDF)")
    if not arts:
        print("No article PDFs; skipped.")
        return

    editorial = make_editorial(no, posts)
    print("Editorial:", editorial[:120].replace("\n", " "), "...")

    # شماره‌ی صفحه‌ها: جلد ۱، سخن سردبیر ۲، فهرست ۳، مقاله‌ها از ۴
    rows, cur = [], 4
    for p, _, n in arts:
        rows.append((p["title"], cur))
        cur += n
    cover = render_pdf(cover_html(no, issue.get("range", ""), [p["title"] for p, _, _ in arts], lead))
    ed = render_pdf(editorial_html(no, editorial, bool(ED_OVERRIDE)))
    toc = render_pdf(toc_html(no, rows, 3))
    back = render_pdf(back_html())

    parts = [cover, ed, toc] + [d for _, d, _ in arts] + [back]
    marks = [("جلد", 0), ("سخن سردبیر", 1), ("فهرست", 2)] + [(t, pg - 1) for t, pg in rows]
    title = "نشریه‌ی هفتگی رشد کسب‌وکار — شماره‌ی %s" % b.fa(no)
    pdf = merge(parts, title, marks)
    path = "out/mm-issue-%s.pdf" % no
    open(path, "wb").write(pdf)
    print("PDF: %d KB, %d pages" % (len(pdf) // 1024, page_count(pdf)))

    mid, url = g.upload_media(pdf, "rushd-kasbokar-weekly-issue-%02d.pdf" % int(no), "application/pdf", title)
    if not url:
        g.notify("⚠️ PDF شماره‌ی %s ساخته شد ولی بارگذاری در وردپرس ناموفق بود. فایل در Artifacts همین اجرا هست." % no)
        return
    r = g.wp("POST", API + "/asset", tries=3, auth=g.AUTH, timeout=90, json={"no": no, "pdf": url, "editorial": editorial})
    print("Register asset: HTTP", r.status_code)
    g.notify("📘 شماره‌ی %s نشریه آماده شد (%s)\nPDF: %s\n\nسخن سردبیر:\n%s" % (no, issue.get("range", ""), url, editorial))


targets = pick_targets()
if not targets:
    print("Nothing to build.")
    sys.exit(0)
for t in targets:
    build(t)
print("Done.")
