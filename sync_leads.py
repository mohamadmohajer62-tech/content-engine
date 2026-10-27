"""
همگام‌سازی مشترکان نشریه: وردپرس -> گوگل شیت + اعلان تلگرام و بله
(اجرا با workflow «sync-leads»؛ اگر مشترک جدیدی نباشد، در چند ثانیه تمام می‌شود)
"""
import os
import sys
import requests
import generate as g

SHEETS_URL = os.environ.get("SHEETS_URL", "").strip()
SHEETS_SECRET = os.environ.get("SHEETS_SECRET", "").strip()
BASE = g.WP + "/wp-json/mm-magazine/v1"


def wp(method, path, **kw):
    return g.wp(method, BASE + path, tries=3, auth=g.AUTH, timeout=60, **kw)


def send(text):
    """ارسال به تلگرام و بله؛ تعداد پیام‌های تحویل‌شده را برمی‌گرداند."""
    targets = [("Telegram", "https://api.telegram.org/bot%s/sendMessage", g.TG_TOKEN, g.TG_CHAT),
               ("Bale", "https://tapi.bale.ai/bot%s/sendMessage", g.BALE_TOKEN, g.BALE_CHAT)]
    ok = 0
    for name, url, tok, chat in targets:
        if not (tok and chat):
            continue
        try:
            r = requests.post(url % tok, json={"chat_id": chat, "text": text, "disable_web_page_preview": True}, timeout=30)
            print("Notify %s: %s" % (name, r.status_code))
            ok += 1 if r.status_code == 200 else 0
        except Exception as e:
            print("Notify %s failed: %s" % (name, type(e).__name__))
    return ok


try:
    r = wp("GET", "/leads")
except requests.exceptions.RequestException as e:
    print("Cannot reach WordPress:", type(e).__name__)
    sys.exit(1)

if r.status_code != 200:
    print("Leads endpoint answered HTTP", r.status_code, r.text[:200])
    sys.exit(1)

leads = r.json().get("leads", [])
if not leads:
    print("No new leads.")
    sys.exit(0)
print("Leads to process:", len(leads))

notified, synced = [], []

# ۱) اعلان
for L in leads:
    if L.get("notified"):
        continue
    text = (
        "🆕 عضو جدید نشریه‌ی رشد کسب‌وکار\n"
        "نام: %s\nایمیل: %s\nموبایل: %s\nعلاقه‌مندی: %s\nجایگاه فرم: %s"
        % (L["name"], L["email"], L["phone"] or "—", L["interests"] or "—", L["source"] or "—")
    )
    if send(text) > 0:
        notified.append(L["id"])
    else:
        print("No channel delivered the message for lead", L["id"], "- will retry next run.")

# ۲) گوگل شیت
todo = [L for L in leads if not L.get("synced")]
if todo and SHEETS_URL and SHEETS_SECRET:
    rows = [{
        "id": L["id"], "date": L["date"], "name": L["name"], "phone": L["phone"],
        "email": L["email"], "interests": L["interests"], "source": L["source"], "page": L["page"],
    } for L in todo]
    try:
        resp = requests.post(SHEETS_URL, json={"secret": SHEETS_SECRET, "rows": rows}, timeout=90)
        data = resp.json()
        if data.get("ok"):
            synced = [int(i) for i in data.get("saved", []) if str(i).isdigit()]
            print("Sheet saved:", len(synced))
        else:
            print("Sheet error:", str(data)[:200])
    except Exception as e:
        print("Sheet request failed:", type(e).__name__)
elif todo:
    print("SHEETS_URL/SHEETS_SECRET not set; rows stay pending.")

# ۳) تأیید به وردپرس
if notified or synced:
    try:
        a = wp("POST", "/leads/ack", json={"notified": notified, "synced": synced})
        print("Ack HTTP", a.status_code)
    except requests.exceptions.RequestException as e:
        print("Ack failed:", type(e).__name__)
