import os, sys, random
import generate as g

title = os.environ.get("TITLE", "").strip()
kw = os.environ.get("KEYWORD", "").strip() or title
variants = [v.strip() for v in os.environ.get("VARIANTS", "").split(",") if v.strip()] or \
    ["gpt-image-2:low", "gpt-image-2:medium", "gpt-image-1-mini:medium", "gapgpt/qwen-image-2.1"]
if not title:
    sys.exit("عنوان مقاله (TITLE) خالی است.")
if not g.GAP:
    sys.exit("GAPGPT_API_KEY تنظیم نشده است.")

rnd = random.Random()
hint, _icon = g.pick_metaphor(title, kw, rnd)
print("Scene:", hint)
try:
    brief = g.art_brief(title, title, hint) or hint
except SystemExit:
    brief = hint
print("Brief:", brief)

made = 0
for v in variants:
    model, _, quality = v.partition(":")
    label = v.replace("/", "_").replace(":", "_")
    print("\n=== Variant: model=%s quality=%s ===" % (model, quality or "default"))
    data = g.make_image(brief, model, quality if quality else None)
    if not data:
        print("RESULT[%s]: no image (credit, quality param or model problem)." % v)
        continue
    open("cover_test_%s_raw.png" % label, "wb").write(data)
    small = g.compress(data)
    open("cover_test_%s.webp" % label, "wb").write(small)
    print("RESULT[%s]: image OK | raw %d KB -> web %d KB" % (v, len(data) // 1024, len(small) // 1024))
    made += 1
print("\nمصرف هر مدل را در پنل گپ‌جی‌پی‌تی بخش «لاگ درخواست‌ها» ببینید.")
if not made:
    sys.exit("هیچ تصویری ساخته نشد.")
