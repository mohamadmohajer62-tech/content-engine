"""
آزمایشگاه استوری اینستاگرام: از یک مقاله، ۳ استوری با هویت سایت می‌سازد
(۱ معرفی مقاله + ۲ نقل‌قول). نتیجه در تلگرام و بله برای شما فرستاده می‌شود و در Artifacts هم می‌ماند.
"""
import os, re, sys
import generate as g
import brand_render as b

POST_ID = os.environ.get("POST_ID", "").strip()
TITLE = os.environ.get("TITLE", "").strip()
HOOK = os.environ.get("HOOK", "").strip()
QUOTES = [q.strip() for q in (os.environ.get("QUOTE1", ""), os.environ.get("QUOTE2", "")) if q.strip()]
WHICH = os.environ.get("WHICH", "all").strip() or "all"
os.makedirs("out", exist_ok=True)


def fallback_quotes(text):
    """اگر مدل پاسخ ندهد: دو جمله‌ی مناسب از خود متن."""
    sents = [s.strip() for s in re.split(r"(?<=[.!؟?])\s+", text or "") if 60 <= len(s.strip()) <= 140]
    mid = len(sents) // 3
    pick = sents[mid:mid + 2] or sents[:2]
    return pick


art = {"title": TITLE, "text": "", "image": None, "link": ""}
if POST_ID:
    art = b.fetch_article(g, POST_ID)
    if TITLE:
        art["title"] = TITLE
if not art["title"]:
    sys.exit("شماره‌ی مقاله (post_id) یا عنوان را وارد کنید.")
print("Article:", art["title"], "| text chars:", len(art["text"]), "| image:", bool(art["image"]))

hook = HOOK
quotes = list(QUOTES)
need_hook = not hook and WHICH in ("all", "intro")
need_q = len(quotes) < 2 and WHICH in ("all", "quotes")

if need_hook or need_q:
    j = None
    if art["text"]:
        j = b.ask_json(g, (
            "عنوان مقاله: %s\n\nمتن مقاله:\n%s\n\n"
            "برای استوری اینستاگرام این‌ها را بنویس:\n"
            "۱) hook: یک جمله‌ی کوتاه و کنجکاوبرانگیز (حداکثر ۹۰ نویسه) که مقاله را معرفی کند و عنوان را تکرار نکند.\n"
            "۲) quotes: دو نقل‌قول مستقل و ماندگار از همین متن، هرکدام بین ۶۰ تا ۱۲۰ نویسه، کامل و قابل فهم بدون زمینه، "
            "بدون نام و بدون علامت نقل‌قول، با فارسی روان.\n"
            'خروجی: {"hook": "...", "quotes": ["...", "..."]}' % (art["title"], art["text"][:5500])))
    if j:
        if need_hook and isinstance(j.get("hook"), str):
            hook = j["hook"].strip()
        if need_q and isinstance(j.get("quotes"), list):
            quotes = [q.strip().strip("«»\"") for q in j["quotes"] if isinstance(q, str) and 20 < len(q.strip()) < 170][:2]
    if need_q and len(quotes) < 2:
        quotes = (quotes + fallback_quotes(art["text"]))[:2]
    if need_hook and not hook:
        hook = (art["text"][:110] + "…") if art["text"] else ""

print("Hook:", hook)
print("Quotes:", quotes)

made = []
if WHICH in ("all", "intro"):
    made.append(("استوری ۱ — معرفی مقاله", b.story_intro(art["title"], hook, art["image"], "out/story-1-intro.png")))
if WHICH in ("all", "quotes"):
    if quotes:
        made.append(("استوری ۲ — نقل‌قول (تیره)", b.story_quote_dark(quotes[0], art["title"], "out/story-2-quote-dark.png")))
    if len(quotes) > 1:
        made.append(("استوری ۳ — نقل‌قول (روشن)", b.story_quote_light(quotes[1], art["title"], "out/story-3-quote-light.png")))

for cap, path in made:
    print("Rendered:", path)
    b.send_photo(g, path, "%s\n%s" % (cap, art["title"]))
print("Done: %d stories." % len(made))
