import os, json, requests

TG = (os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(), os.environ.get("TELEGRAM_CHANNEL_ID", "").strip())
BALE = (os.environ.get("BALE_BOT_TOKEN", "").strip(), os.environ.get("BALE_CHANNEL_ID", "").strip())
EITAA = (os.environ.get("EITAA_TOKEN", "").strip(), os.environ.get("EITAA_CHANNEL_ID", "").strip())
TEST_TEXT = "✅ تست اتصال کانال (این پیام را می‌توانید حذف کنید)"


def hint(err):
    e = (err or "").lower()
    if "chat not found" in e:
        return "شناسه‌ی کانال اشتباه است یا ربات در کانال نیست (عمومی: @نام_کاربری | خصوصی: شناسه‌ی عددی)."
    if "not enough rights" in e or "have no rights" in e or "can't post" in e or "need administrator" in e:
        return "ربات مدیر است ولی اجازه‌ی «ارسال پیام» ندارد."
    if "not a member" in e or "forbidden" in e or "kicked" in e:
        return "ربات باید مدیر (Administrator) همان کانال باشد."
    if "unauthorized" in e or "invalid token" in e:
        return "توکن ربات اشتباه است."
    return ""


def call(base, token, method, **params):
    try:
        r = requests.post((base % token) + method, data=params, timeout=40)
        try:
            j = r.json()
        except Exception:
            j = {"raw": r.text[:200]}
        return r.status_code, j
    except Exception as e:
        return 0, {"error": type(e).__name__}


def check_bot_api(name, base, token, chat):
    print("\\n=== %s ===" % name)
    if not (token and chat):
        print("توکن یا شناسه‌ی کانال تنظیم نشده است.")
        return
    code, j = call(base, token, "getMe")
    print("getMe:", code, json.dumps(j, ensure_ascii=False)[:200])
    bot_id = ((j.get("result") or {}) if isinstance(j, dict) else {}).get("id")
    code, j = call(base, token, "getChat", chat_id=chat)
    print("getChat:", code, json.dumps(j, ensure_ascii=False)[:240])
    if bot_id:
        code, j = call(base, token, "getChatMember", chat_id=chat, user_id=bot_id)
        print("getChatMember (ربات):", code, json.dumps(j, ensure_ascii=False)[:300])
    code, j = call(base, token, "sendMessage", chat_id=chat, text=TEST_TEXT)
    ok = code == 200 and (j.get("ok", True) if isinstance(j, dict) else False)
    print("sendMessage:", code, json.dumps(j, ensure_ascii=False)[:240])
    print("RESULT[%s]: %s %s" % (name, "OK ✅ (پیام تست در کانال ارسال شد)" if ok else "FAILED ❌", "" if ok else hint(json.dumps(j, ensure_ascii=False))))


def check_eitaa(token, chat):
    print("\\n=== Eitaa ===")
    if not (token and chat):
        print("توکن یا شناسه‌ی کانال تنظیم نشده است.")
        return
    try:
        r = requests.post("https://eitaayar.ir/api/%s/getMe" % token, timeout=40)
        print("getMe:", r.status_code, r.text[:200])
        r = requests.post("https://eitaayar.ir/api/%s/sendMessage" % token, data={"chat_id": chat, "text": TEST_TEXT, "title": "test"}, timeout=60)
        print("sendMessage:", r.status_code, r.text[:300])
        try:
            ok = bool(r.json().get("ok"))
        except Exception:
            ok = False
        print("RESULT[Eitaa]: %s" % ("OK ✅ (پیام تست در کانال ارسال شد)" if ok else "FAILED ❌ (شناسه‌ی کانال را از پنل ایتایار کپی کنید و ربات/حساب ایتایار باید مدیر کانال باشد)"))
    except Exception as e:
        print("خطا:", type(e).__name__)


check_bot_api("Telegram", "https://api.telegram.org/bot%s/", *TG)
check_bot_api("Bale", "https://tapi.bale.ai/bot%s/", *BALE)
check_eitaa(*EITAA)
