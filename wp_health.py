import time, random, requests
import generate as g

S = requests.Session()
UA_BOT = {"User-Agent": "Mozilla/5.0 (compatible; ContentEngine/1.0; +https://mohammadmohajer.ir)"}
UA_BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def timed(label, method, url, headers=UA_BOT, timeout=150, **kw):
    t = time.time()
    try:
        r = S.request(method, url, auth=g.AUTH, headers=headers, timeout=timeout, **kw)
        dt = time.time() - t
        print("%-40s HTTP %s | %5.1fs | server=%s | %d bytes" % (label, r.status_code, dt, r.headers.get("server", "?"), len(r.content)))
        if r.status_code >= 400:
            print("    body:", r.text[:200].replace("\\n", " "))
        return r
    except Exception as e:
        print("%-40s %s after %.1fs" % (label, type(e).__name__, time.time() - t))
        return None


def fake_article(kb):
    sent = "فرآیند فروش مسیر مشخص از اولین تماس تا قرارداد است و هر مرحله باید برای تیم روشن و قابل اندازه‌گیری باشد. "
    html = ""
    while len(html.encode("utf-8")) < kb * 1024:
        html += '<p style="text-align:justify;text-justify:inter-word">' + sent * 4 + "</p>\\n"
    return '<div class="mm-article">' + html + "</div>"


W = g.WP + "/wp-json/wp/v2"
print("=== Read tests ===")
timed("GET /wp-json/ (index)", "GET", g.WP + "/wp-json/", timeout=60)
timed("GET users/me", "GET", W + "/users/me", timeout=60)
timed("GET posts?per_page=1", "GET", W + "/posts", timeout=60, params={"per_page": 1, "_fields": "id"})

print("\\n=== Write tests (a temporary draft titled HEALTHCHECK) ===")
r = timed("POST create tiny draft", "POST", W + "/posts", json={"title": "HEALTHCHECK", "status": "draft", "content": "<p>x</p>"}, timeout=150)
pid = None
if r is not None and r.status_code in (200, 201):
    pid = r.json()["id"]
    for kb in (20, 60, 120):
        timed("POST update content %d KB" % kb, "POST", "%s/posts/%s" % (W, pid), json={"content": fake_article(kb)}, timeout=200)
    timed("POST update 60 KB (browser UA)", "POST", "%s/posts/%s" % (W, pid), headers=UA_BROWSER, json={"content": fake_article(60)}, timeout=200)
    timed("POST update meta (Rank Math)", "POST", "%s/posts/%s" % (W, pid), json={"meta": {"rank_math_title": "t", "rank_math_description": "d", "rank_math_focus_keyword": "k"}}, timeout=120)
    timed("DELETE the test draft", "DELETE", "%s/posts/%s" % (W, pid), params={"force": "true"}, timeout=120)
else:
    print("ساخت پیش‌نویس تست ممکن نشد؛ نوشتن در سایت از این سرور مشکل دارد.")
print("\\nراهنما: اگر خواندن‌ها سریع و نوشتن‌ها (به‌خصوص حجم‌های بزرگ) timeout شدند، مشکل از تنظیمات هاست/فایروال است.")
