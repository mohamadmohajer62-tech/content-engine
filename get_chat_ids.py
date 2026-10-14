import os, requests

SERVICES = [("Telegram", "https://api.telegram.org/bot%s/getUpdates", os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()),
            ("Bale", "https://tapi.bale.ai/bot%s/getUpdates", os.environ.get("BALE_BOT_TOKEN", "").strip())]
for name, url, tok in SERVICES:
    print("=== %s ===" % name)
    if not tok:
        print("توکن تنظیم نشده است.")
        continue
    try:
        r = requests.get(url % tok, timeout=30)
    except Exception as e:
        print("خطای اتصال:", type(e).__name__)
        continue
    print("status:", r.status_code)
    if r.status_code != 200:
        print(r.text[:200])
        continue
    seen = {}
    for u in r.json().get("result", []):
        m = u.get("message") or u.get("channel_post") or u.get("edited_message") or {}
        c = m.get("chat") or {}
        if c.get("id") is not None:
            seen[c["id"]] = (c.get("type"), c.get("first_name") or c.get("title") or c.get("username") or "")
    if not seen:
        print("هیچ پیامی پیدا نشد. اول در تلگرام/بله به ربات خودتان یک پیام (مثلاً /start) بفرستید و دوباره اجرا کنید.")
    for cid, (t, n) in seen.items():
        print("CHAT_ID:", cid, "| نوع:", t, "| نام:", n)
