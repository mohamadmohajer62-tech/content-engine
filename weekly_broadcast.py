"""
ارسال هفتگی PDF نشریه: شنبه ساعت ۱۰ صبح (وقت تهران) به کانال‌های تلگرام، بله و ایتا، با توضیح، امضا و آیدی کانال.
اجرا از ۹:۳۰ شروع می‌شود و دقیقاً تا ۱۰:۰۰ صبر می‌کند. فقط شنبه‌ها (وقت تهران) و فقط برای آخرین شماره‌ی ارسال‌نشده؛ اجرای زودهنگام یا تکراری چیزی نمی‌فرستد.
TEST_OWNER=1  -> فقط به چت شخصی شما می‌فرستد (آزمایش) و علامت «ارسال‌شده» نمی‌زند.
"""
import os, sys, re, time
from datetime import datetime
from zoneinfo import ZoneInfo
import generate as g
import announce as a

API = g.WP + "/wp-json/mm-magazine/v1"
MAG_URL = os.environ.get("MAGAZINE_PAGE_URL", "https://mohammadmohajer.ir/business-growth-magazine/")
ISSUE_NO = os.environ.get("ISSUE_NO", "").strip()
TEST_OWNER = os.environ.get("TEST_OWNER", "0").strip().lower() in ("1", "true", "yes")
FORCE = os.environ.get("FORCE", "0").strip().lower() in ("1", "true", "yes")


def wait_until_ten():
    """تا ساعت ۱۰ تهران صبر می‌کند. اگر بیش از ۶۵ دقیقه مانده باشد، ارسال نمی‌شود (اجرای زودهنگام اشتباه)."""
    tz = ZoneInfo("Asia/Tehran")
    now = datetime.now(tz)
    target = now.replace(hour=10, minute=0, second=0, microsecond=0)
    if now >= target:
        print("Already past 10:00 Tehran; sending now.")
        return True
    delta = (target - now).total_seconds()
    if delta > 65 * 60:
        print("Too early (%.0f min to 10:00 Tehran); not sending." % (delta / 60))
        return False
    print("Waiting %.0f seconds until 10:00 Tehran..." % delta)
    time.sleep(delta)
    return True


def fetch_issues():
    # پارامتر nc جلوی کش شدن پاسخ (CDN یا افزونه‌ی کش) را می‌گیرد تا پرچم «ارسال‌شده» همیشه تازه خوانده شود
    r = g.wp("GET", API + "/issues?nc=%d" % int(time.time()), tries=3, timeout=90)
    if r.status_code != 200:
        sys.exit("فهرست شماره‌ها در دسترس نیست (HTTP %s)." % r.status_code)
    return r.json().get("issues", [])


def pick_issue():
    """فقط «آخرین شماره‌ی بسته‌شده‌ی دارای PDF» انتخاب می‌شود، نه شماره‌های قدیمی؛ و اگر قبلاً ارسال شده باشد، ارسال نمی‌شود."""
    items = fetch_issues()
    if ISSUE_NO:
        sel = [i for i in items if str(i["no"]) == ISSUE_NO]
        issue = sel[0] if sel else None
    else:
        ready = [i for i in items if (not i["open"]) and i.get("pdf")]
        issue = max(ready, key=lambda i: int(i["no"])) if ready else None
    if issue and issue.get("sent") and not (FORCE or TEST_OWNER):
        print("شماره‌ی %s قبلاً ارسال شده است؛ چیزی ارسال نمی‌شود." % issue["no"])
        return None
    return issue


def mark_sent(no):
    """ثبت «ارسال‌شده» با تأیید؛ اگر ثبت نشود، اجرای بعدی دوباره همان شماره را می‌فرستد."""
    for k in range(3):
        try:
            mr = g.wp("POST", API + "/asset", tries=3, auth=g.AUTH, timeout=90, json={"no": no, "sent": 1})
            print("Mark sent: HTTP", mr.status_code)
            if mr.status_code == 200:
                chk = [i for i in fetch_issues() if str(i["no"]) == str(no)]
                if chk and chk[0].get("sent"):
                    return True
        except Exception as e:
            print("Mark sent error:", type(e).__name__)
        time.sleep(5)
    return False


def titles_of(ids):
    url = "%s/wp-json/wp/v2/posts?include=%s&per_page=20&orderby=include&_fields=id,title" % (g.WP, ",".join(str(i) for i in ids))
    r = g.wp("GET", url, tries=3, timeout=90)
    out = []
    if r.status_code == 200:
        for p in r.json():
            out.append(g.plain((p.get("title") or {}).get("rendered", ""), 200))
    return out


def build_caption(issue, titles):
    no = issue["no"]
    link = "%s?issue=%s" % (MAG_URL, no)
    sp = "✍️ %s\n\n🆔️ %s" % (a.SIG_NAME, a.HANDLE)
    sh = "✍️ <b>%s</b>\n\n🆔️ %s" % (g.esc(a.SIG_NAME), g.esc(a.HANDLE))
    head_p = "📘 نشریه‌ی هفتگی رشد کسب‌وکار | شماره‌ی %s\n🗓 %s" % (g.fa(no), issue["range"])
    head_h = "<b>📘 نشریه‌ی هفتگی رشد کسب‌وکار | شماره‌ی %s</b>\n🗓 %s" % (g.fa(no), g.esc(issue["range"]))
    tail_p = ("\n\n📥 دانلود PDF و مطالعه‌ی آنلاین:\n%s\n\nاین نشریه را برای کسی که لازمش دارد بفرستید و شماره‌ی بعد را هر شنبه از دست ندهید.\n\n%s" % (link, sp))
    tail_h = ("\n\n📥 دانلود PDF و مطالعه‌ی آنلاین:\n%s\n\nاین نشریه را برای کسی که لازمش دارد بفرستید و شماره‌ی بعد را هر شنبه از دست ندهید.\n\n%s" % (g.esc(link), sh))
    lines_p, lines_h = [], []
    for i, t in enumerate(titles[:7]):
        t = t if len(t) <= 80 else t[:78].rsplit(" ", 1)[0] + "…"
        lines_p.append("%s) %s" % (g.fa(i + 1), t))
        lines_h.append("%s) %s" % (g.fa(i + 1), g.esc(t)))
        # کپشن تلگرام حداکثر ۱۰۲۴ نویسه است
        if len(head_h + "\n\nدر این شماره:\n" + "\n".join(lines_h) + tail_h) > 960:
            lines_p.pop()
            lines_h.pop()
            break
    body_p = ("\n\nدر این شماره:\n" + "\n".join(lines_p)) if lines_p else ""
    body_h = ("\n\nدر این شماره:\n" + "\n".join(lines_h)) if lines_h else ""
    return head_p + body_p + tail_p, head_h + body_h + tail_h, link


def main():
    manual = bool(ISSUE_NO or FORCE or TEST_OWNER)
    if not manual:
        now = datetime.now(ZoneInfo("Asia/Tehran"))
        if now.weekday() != 5:          # شنبه
            print("امروز شنبه نیست (وقت تهران)؛ ارسال هفتگی انجام نمی‌شود.")
            return
    issue = pick_issue()
    if not issue:
        print("شماره‌ی آماده‌ی ارسال وجود ندارد (PDF ساخته نشده یا قبلاً ارسال شده).")
        return
    no = issue["no"]
    print("Issue to send:", no, issue["range"])
    pdf_url = issue.get("pdf_url", "")
    if not pdf_url:
        sys.exit("آدرس PDF شماره‌ی %s ثبت نشده است." % no)
    data = g.S.get(pdf_url, timeout=180).content
    if data[:4] != b"%PDF":
        sys.exit("فایل PDF معتبر نیست.")
    titles = titles_of(issue["ids"])
    plain, html, link = build_caption(issue, titles)
    print("Caption length:", len(plain), len(html))

    if not manual:
        if not wait_until_ten():
            return
        issue = pick_issue()            # بعد از انتظار دوباره بررسی می‌شود؛ شاید اجرای دیگری فرستاده باشد
        if not issue or str(issue["no"]) != str(no):
            print("در فاصله‌ی انتظار وضعیت عوض شد؛ ارسال لغو شد.")
            return
    fname = "نشریه-رشد-کسب-وکار-شماره-%02d.pdf" % int(no)
    res = a.send_doc_all(data, fname, plain, html, link, "نشریه‌ی هفتگی رشد کسب‌وکار — شماره‌ی %s" % g.fa(no),
                         owner=TEST_OWNER, btn="مطالعه‌ی نشریه")
    line = " | ".join("%s %s" % (k, "✅" if v else "❌") for k, v in res.items()) or "هیچ مقصدی تنظیم نیست"
    print("Result:", line)
    if TEST_OWNER:
        g.notify("🧪 آزمایش ارسال هفتگی شماره‌ی %s (فقط به شما):\n%s" % (g.fa(no), line))
        return
    note = ""
    if any(res.values()):
        if not mark_sent(no):
            note = "\n\n⚠️ ثبت «ارسال‌شده» در وردپرس انجام نشد؛ ممکن است اجرای بعدی دوباره بفرستد. افزونه و پاسخ /issues را بررسی کنید."
    g.notify("📘 PDF شماره‌ی %s نشریه در کانال‌ها ارسال شد:\n%s\n\n(ایمیل اعضا: هنوز به سامانه‌ی ایمیل وصل نشده است)%s" % (g.fa(no), line, note))


if __name__ == "__main__":
    main()
