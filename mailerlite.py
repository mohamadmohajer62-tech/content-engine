"""
اتصال به MailerLite (API نسخه‌ی جدید): گروه‌ها، افزودن مشترک، و ساخت و ارسال کمپین.
توجه: ارسال کمپین با HTML دلخواه فقط در پلن Advanced مجاز است؛ هم‌گام‌سازی مشترکان در پلن رایگان هم کار می‌کند.
ML_DRY=1 : درخواست‌ها را فقط چاپ می‌کند و چیزی ارسال نمی‌کند.
"""
import os, time
import requests

BASE = "https://connect.mailerlite.com/api"
KEY = os.environ.get("MAILERLITE_API_KEY", "").strip()
DRY = os.environ.get("ML_DRY", "0").strip() in ("1", "true", "yes")
ALL_GROUP = "نشریه رشد کسب‌وکار — همه‌ی اعضا"
INTEREST_PREFIX = "علاقه‌مندی: "


def enabled():
    return bool(KEY)


def call(method, path, body=None, tries=3):
    headers = {"Authorization": "Bearer " + KEY, "Accept": "application/json", "Content-Type": "application/json"}
    if DRY and method != "GET":
        print("[DRY] %s %s %s" % (method, path, str(body)[:300]))
        return None
    for i in range(tries):
        try:
            r = requests.request(method, BASE + path, headers=headers, json=body, timeout=60)
        except Exception as e:
            print("MailerLite error:", type(e).__name__)
            time.sleep(3 * (i + 1))
            continue
        if r.status_code == 429:                      # سقف تعداد درخواست
            time.sleep(10 * (i + 1))
            continue
        return r
    return None


def ensure_groups(labels):
    """گروه‌های «همه‌ی اعضا» و «علاقه‌مندی: ...» را می‌سازد؛ نقشه‌ی نام ← شناسه را برمی‌گرداند."""
    wanted = [ALL_GROUP] + [INTEREST_PREFIX + l for l in labels]
    ids = {}
    r = call("GET", "/groups?limit=100")
    if r is not None and r.status_code == 200:
        for gr in r.json().get("data", []):
            ids[gr.get("name")] = str(gr.get("id"))
    elif r is not None:
        print("List groups failed:", r.status_code, r.text[:200])
    for name in wanted:
        if name in ids:
            continue
        c = call("POST", "/groups", {"name": name})
        if c is not None and c.status_code in (200, 201):
            ids[name] = str(c.json()["data"]["id"])
            print("Group created:", name)
        elif c is not None:
            print("Group create failed:", name, c.status_code, c.text[:200])
        else:
            ids.setdefault(name, "dry-" + name)
    return ids


def upsert(lead, group_ids):
    """مشترک را می‌سازد یا به‌روز می‌کند و در گروه‌ها می‌گذارد. True اگر موفق بود."""
    body = {"email": lead["email"], "fields": {"name": lead["name"]}, "groups": group_ids}
    if lead.get("phone"):
        body["fields"]["phone"] = lead["phone"]
    r = call("POST", "/subscribers", body)
    if r is None:
        return DRY
    if r.status_code in (200, 201):
        return True
    print("Subscriber failed:", lead["email"], r.status_code, r.text[:200])
    return False


def create_and_send(name, subject, html, group_ids, from_email, from_name):
    """کمپین می‌سازد و بلافاصله ارسال می‌کند. شناسه‌ی کمپین یا None."""
    body = {"name": name, "type": "regular", "groups": group_ids,
            "emails": [{"subject": subject, "from_name": from_name, "from": from_email, "content": html}]}
    r = call("POST", "/campaigns", body)
    if r is None:
        return "dry" if DRY else None
    if r.status_code not in (200, 201):
        print("Create campaign failed:", r.status_code, r.text[:300])
        return None
    cid = str(r.json()["data"]["id"])
    s = call("POST", "/campaigns/%s/schedule" % cid, {"delivery": "instant"})
    if s is None or s.status_code not in (200, 201):
        print("Schedule failed:", getattr(s, "status_code", None), getattr(s, "text", "")[:300])
        return None
    print("Campaign sent:", cid)
    return cid
