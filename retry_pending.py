import os, sys, json, glob, time
import requests
import generate as g

MAX_RUNS = 6        # بعد از این تعداد اجرای ناموفق برای یک پیش‌نویس، دیگر تلاش نمی‌کند (و یک‌بار خبر می‌دهد)
BUDGET = 12 * 60    # سقف زمان کل اجرا (ثانیه) تا دقیقه‌های GitHub هدر نرود
ATT = os.path.join("pending", "_attempts.json")

files = sorted(f for f in glob.glob(os.path.join("pending", "*.json"))
               if os.path.basename(f)[:-5].isdigit())
if not files:
    print("No pending drafts.")
    sys.exit(0)

try:
    attempts = json.load(open(ATT, encoding="utf-8"))
except Exception:
    attempts = {}

t0 = time.time()
done = 0
for path in files:
    pid = os.path.basename(path).split(".")[0]
    if attempts.get(pid, 0) >= MAX_RUNS:
        print("Pending %s skipped (already failed %d runs)." % (pid, attempts[pid]))
        continue
    if time.time() - t0 > BUDGET:
        print("Time budget reached; remaining drafts wait for the next run.")
        break
    try:
        update = json.load(open(path, encoding="utf-8"))
        r = g.wp("POST", "%s/wp-json/wp/v2/posts/%s" % (g.WP, pid), tries=2, auth=g.AUTH, timeout=120, json=update)
        print("Pending %s: HTTP %s" % (pid, r.status_code))
        if r.status_code in (200, 201):
            os.remove(path)
            attempts.pop(pid, None)
            done += 1
            g.notify("✅ محتوای کامل پیش‌نویس %s در سایت ذخیره شد.\n%s/wp-admin/post.php?post=%s&action=edit" % (pid, g.WP, pid))
            continue
        print(r.text[:200])
    except requests.exceptions.RequestException as e:
        print("Pending %s failed: %s" % (pid, type(e).__name__))
    attempts[pid] = attempts.get(pid, 0) + 1
    if attempts[pid] == MAX_RUNS:
        g.notify("⚠️ ذخیره‌ی پیش‌نویس %s بعد از %d اجرا موفق نشد؛ تلاش خودکار متوقف شد. دستی بررسی کنید.\n%s/wp-admin/post.php?post=%s&action=edit"
                 % (pid, MAX_RUNS, g.WP, pid))

os.makedirs("pending", exist_ok=True)
with open(ATT, "w", encoding="utf-8") as f:
    json.dump(attempts, f)
print("Completed: %d of %d" % (done, len(files)))
