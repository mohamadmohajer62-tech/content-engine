import os, sys, time, json, base64, hashlib
import requests

WP = "https://mohammadmohajer.ir"
AUTH = (os.environ["WP_USER"], os.environ["WP_APP_PASSWORD"])
T = int(os.environ.get("REQ_TIMEOUT", "45"))
S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (compatible; ContentEngine/1.0; +https://mohammadmohajer.ir)"})


def call(label, method, path, **kw):
    t = time.time()
    try:
        r = S.request(method, WP + path, auth=AUTH, timeout=T, **kw)
        _ = r.content
        print("%-46s HTTP %s in %5.1fs" % (label, r.status_code, time.time() - t), flush=True)
        return r
    except Exception as e:
        print("%-46s %s after %.1fs" % (label, type(e).__name__, time.time() - t), flush=True)
        return None


def latin(n):
    return "<p>" + ("lorem ipsum dolor sit amet " * (n // 27 + 1))[: n - 7] + "</p>"


def persian(n_chars):
    base = "این یک جمله‌ی آزمایشی برای سنجش ذخیره‌ی محتوای فارسی در وردپرس است. "
    return "<p>" + (base * (n_chars // len(base) + 1))[:n_chars] + "</p>"


def realistic():
    parts = ['<div class="mm-article" style="direction:rtl">']
    for i in range(8):
        parts.append('<h2 id="s%d" style="scroll-margin-top:90px">بخش %d</h2>' % (i, i))
        parts.append('<p style="text-align:justify">' + ("متن نمونه‌ی مقاله برای آزمایش. " * 90) + "</p>")
        parts.append('<details><summary>سؤال %d</summary><p>پاسخ کوتاه.</p></details>' % i)
    parts.append("</div>")
    return "\n".join(parts)


print("=== 0. ping snippet ===")
r = call("GET /mm/v1/ping", "GET", "/wp-json/mm/v1/ping")
bridge = bool(r is not None and r.status_code == 200)
print("bridge snippet active:", bridge, flush=True)

print("\n=== 1. create draft with tiny content ===")
r = call("create draft (tiny content)", "POST", "/wp-json/wp/v2/posts",
         json={"title": "wp-size-test (auto delete)", "status": "draft", "content": "<p>x</p>"})
if r is None or r.status_code not in (200, 201):
    sys.exit("cannot create draft")
pid = r.json()["id"]
print("draft id:", pid, flush=True)

try:
    if bridge:
        print("\n=== 2. echo: does the request BODY itself get through? (nothing saved) ===")
        for label, data in (("echo plain 1KB", latin(1000)), ("echo plain 6KB", latin(6000)),
                            ("echo plain 40KB", latin(40000)),
                            ("echo base64 6KB", base64.b64encode(latin(4500).encode()).decode()),
                            ("echo base64 40KB", base64.b64encode(realistic().encode()).decode())):
            call(label, "POST", "/wp-json/mm/v1/echo", json={"data": data})

    print("\n=== 3. standard REST: content size ladder (UTF-8 latin) ===")
    for n in (200, 500, 1000, 2000, 4000, 6000):
        call("content latin %d B" % n, "POST", "/wp-json/wp/v2/posts/%d" % pid, json={"content": latin(n)})

    print("\n=== 4. standard REST: other fields / persian ===")
    call("excerpt latin 6KB (not content)", "POST", "/wp-json/wp/v2/posts/%d" % pid, json={"excerpt": latin(6000)})
    call("content persian 1500 chars", "POST", "/wp-json/wp/v2/posts/%d" % pid, json={"content": persian(1500)})

    if bridge:
        print("\n=== 5. bridge: chunk + commit (base64 -> $wpdb) ===")
        for label, html in (("6KB latin", latin(6000)), ("realistic article", realistic())):
            raw = html.encode("utf-8")
            b64 = base64.b64encode(raw).decode()
            size = int(os.environ.get("CHUNK", "3000"))
            chunks = [b64[i:i + size] for i in range(0, len(b64), size)]
            ok = True
            for i, c in enumerate(chunks):
                rr = call("  chunk %d/%d (%s)" % (i + 1, len(chunks), label), "POST", "/wp-json/mm/v1/chunk",
                          json={"id": pid, "i": i, "data": c})
                if rr is None or rr.status_code != 200:
                    ok = False
                    break
            if not ok:
                print("  -> chunk upload failed, skip commit")
                continue
            rr = call("  commit (%s, %d bytes)" % (label, len(raw)), "POST", "/wp-json/mm/v1/commit",
                      json={"id": pid, "n": len(chunks), "md5": hashlib.md5(raw).hexdigest()})
            if rr is not None and rr.status_code == 200:
                chk = call("  verify read-back", "GET", "/wp-json/wp/v2/posts/%d" % pid, params={"context": "edit", "_fields": "content"})
                if chk is not None and chk.status_code == 200:
                    got = chk.json().get("content", {}).get("raw", "")
                    print("  read-back identical:", got == html, "(len %d vs %d)" % (len(got), len(html)), flush=True)
            elif rr is not None:
                print("  commit answer:", rr.text[:200], flush=True)
finally:
    print("\n=== cleanup ===")
    call("delete test draft", "DELETE", "/wp-json/wp/v2/posts/%d" % pid, params={"force": "true"})
