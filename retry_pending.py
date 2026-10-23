import os, sys, json, glob
import requests
import generate as g

files = sorted(glob.glob(os.path.join("pending", "*.json")))
if not files:
    print("No pending drafts.")
    sys.exit(0)
done = 0
for path in files:
    pid = os.path.basename(path).split(".")[0]
    try:
        update = json.load(open(path, encoding="utf-8"))
        r = g.wp("POST", "%s/wp-json/wp/v2/posts/%s" % (g.WP, pid), tries=4, auth=g.AUTH, timeout=240, json=update)
        print("Pending %s: HTTP %s" % (pid, r.status_code))
        if r.status_code in (200, 201):
            os.remove(path)
            done += 1
            g.notify("✅ محتوای کامل پیش‌نویس %s در سایت ذخیره شد.\\n%s/wp-admin/post.php?post=%s&action=edit" % (pid, g.WP, pid))
        else:
            print(r.text[:200])
    except requests.exceptions.RequestException as e:
        print("Pending %s failed: %s" % (pid, type(e).__name__))
print("Completed: %d of %d" % (done, len(files)))
