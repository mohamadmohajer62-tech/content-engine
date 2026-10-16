import os, sys, random, base64
import generate as g

title = os.environ.get("TITLE", "").strip()
kw = os.environ.get("KEYWORD", "").strip() or title
count = int(os.environ.get("COUNT", "2") or 2)
if not title:
    sys.exit("عنوان مقاله (TITLE) خالی است.")
if not (g.GAP and g.IMG_MODEL):
    sys.exit("GAPGPT_API_KEY یا IMAGE_MODEL تنظیم نشده است.")

rnd = random.Random()
models = [g.IMG_MODEL] + [m.strip() for m in os.environ.get("IMAGE_FALLBACKS", "gapgpt/qwen-image-2.1,gpt-image-1-mini").split(",") if m.strip()]
made = 0
for n in range(1, count + 1):
    hint, _icon = g.pick_metaphor(title, kw, rnd)
    print("\\n=== Variant %d ===" % n)
    print("Scene:", hint)
    try:
        brief = g.art_brief(title, title, hint) or hint
    except SystemExit:
        brief = hint
    print("Brief:", brief)
    data, used = None, ""
    for m in models:
        try:
            data = g.make_image(brief, m)
        except Exception as e:
            print("error", m, type(e).__name__)
            data = None
        if data:
            used = m
            break
    if not data:
        print("RESULT: no image (credit or model problem).")
        continue
    open("cover_test_%d_raw.png" % n, "wb").write(data)
    small = g.compress(data)
    open("cover_test_%d.webp" % n, "wb").write(small)
    print("RESULT: image OK | model: %s | raw %d KB -> web %d KB" % (used, len(data) // 1024, len(small) // 1024))
    made += 1
if not made:
    sys.exit("هیچ تصویری ساخته نشد.")
