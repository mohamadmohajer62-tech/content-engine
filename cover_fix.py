import os, re, sys
import generate as g

pid = os.environ.get("POST_ID", "").strip()
if not pid.isdigit():
    sys.exit("شناسه‌ی مقاله (POST_ID) باید یک عدد باشد.")
g.set_palette(int(pid))
r = g.wp("GET", "%s/wp-json/wp/v2/posts/%s" % (g.WP, pid), tries=4, auth=g.AUTH,
         params={"context": "edit", "_fields": "id,title,content,slug,featured_media"})
if r.status_code != 200:
    sys.exit("مقاله پیدا نشد: %s %s" % (r.status_code, r.text[:150]))
j = r.json()
title = (j["title"].get("raw") or j["title"].get("rendered") or "").strip()
content = j["content"].get("raw") or ""
slug = j.get("slug") or ("post-" + pid)
heads = [g.plain(h, 80) for h in re.findall(r"<h2[^>]*>(.*?)</h2>", content, re.S)][:8]
ctx = title + ". Sections: " + " | ".join(heads) + ". " + g.plain(content, 700)
print("Post:", pid, "|", title, "| current featured:", j.get("featured_media"))
mid, b64, src = g.make_cover(title, ctx, title, slug, title)
if not mid:
    sys.exit("ساخت یا آپلود تصویر شاخص ناموفق بود.")
u = g.wp("POST", "%s/wp-json/wp/v2/posts/%s" % (g.WP, pid), tries=3, auth=g.AUTH, json={"featured_media": mid}, timeout=60)
print("Set featured image:", u.status_code, "| source:", src, "| media:", mid)
