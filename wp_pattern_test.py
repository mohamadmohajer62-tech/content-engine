import json, time, requests
import generate as g

H = {"User-Agent": "Mozilla/5.0 (compatible; ContentEngine/1.0; +https://mohammadmohajer.ir)"}
W = g.WP + "/wp-json/wp/v2"
S = requests.Session()
SENT = "فرآیند فروش مسیر مشخص از اولین تماس تا قرارداد است و هر مرحله باید برای تیم روشن و قابل اندازه‌گیری باشد. "


def plain_block(kb):
    out = ""
    while len(out.encode("utf-8")) < kb * 1024:
        out += "<p>" + SENT * 3 + "</p>\n"
    return out


def timed(label, url, body=None, json_obj=None, timeout=90):
    t = time.time()
    try:
        kw = {}
        if json_obj is not None:
            kw["json"] = json_obj
        else:
            kw["data"] = body
        r = S.post(url, auth=g.AUTH, headers=dict(H, **({"Content-Type": "application/json; charset=utf-8"} if body is not None else {})), timeout=timeout, **kw)
        print("%-46s HTTP %s | %5.1fs" % (label, r.status_code, time.time() - t))
        if r.status_code >= 400:
            print("    body:", r.text[:160].replace("\n", " "))
        return r.status_code
    except Exception as e:
        print("%-46s %s after %.1fs" % (label, type(e).__name__, time.time() - t))
        return None


r = S.post(W + "/posts", auth=g.AUTH, headers=H, json={"title": "PATTERNTEST", "status": "draft", "content": "<p>x</p>"}, timeout=60)
if r.status_code not in (200, 201):
    raise SystemExit("ساخت پیش‌نویس تست ناموفق: %s" % r.status_code)
pid = r.json()["id"]
U = "%s/posts/%s" % (W, pid)
base = plain_block(6)

tests = [
    ("A plain <p> 6KB", base),
    ("B plain <p> 40KB", plain_block(40)),
    ("C <p style=text-align:justify>", base.replace("<p>", '<p style="text-align:justify;text-justify:inter-word">')),
    ("D <div class=mm-article> wrapper", '<div class="mm-article">' + base + "</div>"),
    ("E <h2 id style=scroll-margin-top>", '<h2 id="mm-s1" style="scroll-margin-top:90px">تیتر</h2>' + base),
    ("F <a href=external link>", base + '<p><a href="https://en.wikipedia.org/wiki/Marketing_strategy" target="_blank" rel="noopener noreferrer">منبع</a></p>'),
    ("G <details><summary>", "<details open><summary>سؤال</summary><div>پاسخ</div></details>" + base),
    ("H <style> block", "<style>.mm-grid{display:grid;gap:12px}</style>" + base),
    ("I infographic-like inline CSS", '<div dir="rtl" style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;border:1px solid #dfe6d6;border-radius:14px;background:#f7f9f3">' + base + "</div>"),
]
print("=== JSON (requests default, escaped \\u) ===")
for label, content in tests:
    timed(label, U, json_obj={"content": content})
print("\n=== Raw UTF-8 JSON body (no \\u escapes) ===")
raw = json.dumps({"content": base.replace("<p>", '<p style="text-align:justify">')}, ensure_ascii=False).encode("utf-8")
timed("C-raw <p style> as raw UTF-8", U, body=raw)
print("\n=== Form-encoded body ===")
timed("C-form <p style> form-encoded", U, body=None, json_obj=None) if False else None
t = time.time()
try:
    rr = S.post(U, auth=g.AUTH, headers=H, data={"content": base.replace("<p>", '<p style="text-align:justify">')}, timeout=90)
    print("%-46s HTTP %s | %5.1fs" % ("C-form <p style> form-encoded", rr.status_code, time.time() - t))
except Exception as e:
    print("%-46s %s after %.1fs" % ("C-form <p style> form-encoded", type(e).__name__, time.time() - t))
try:
    S.delete(U, auth=g.AUTH, headers=H, params={"force": "true"}, timeout=60)
    print("\nپیش‌نویس تست حذف شد.")
except Exception:
    print("\nپیش‌نویس تست (PATTERNTEST) را دستی حذف کنید.")
