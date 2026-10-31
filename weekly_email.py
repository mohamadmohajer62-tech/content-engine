"""ساخت ایمیل هفتگی نشریه (HTML سازگار با ایمیل‌کلاینت‌ها، راست‌به‌چپ، با هویت سبز-طلایی)."""
import html as _h

GOLD, GOLD2, EM1, EM2, PAPER = "#C9A24B", "#E8CF8A", "#0f2a1b", "#173b25", "#f9f4e7"
FONT = "Tahoma,'Segoe UI',Arial,sans-serif"


def e(t):
    return _h.escape(str(t or ""), quote=True)


def fa(n):
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def btn(text, url, bg, fg):
    return ('<a href="%s" style="display:inline-block;background:%s;color:%s;text-decoration:none;font-weight:bold;font-size:15px;padding:12px 28px;border-radius:30px">%s</a>'
            % (e(url), bg, fg, e(text)))


def build(issue_no, range_label, posts, editorial, pdf_url, read_url, links, cover_url=""):
    """posts: فهرست {title, link, excerpt}؛ links: {telegram, bale, eitaa, handle}."""
    subject = "📘 نشریه‌ی هفتگی رشد کسب‌وکار | شماره‌ی %s" % fa(issue_no)
    items = "".join(
        '<tr><td style="padding:14px 0;border-bottom:1px solid #e7dfc9">'
        '<div style="font-size:12px;color:#C8643C;font-weight:bold">%s</div>'
        '<a href="%s" style="color:#0f2a1b;text-decoration:none;font-size:17px;font-weight:bold;line-height:1.9">%s</a>'
        '<div style="color:#5f6c62;font-size:13px;line-height:1.9;margin-top:2px">%s</div></td></tr>'
        % (fa(i + 1), e(p["link"]), e(p["title"]), e(p.get("excerpt", "")[:150])) for i, p in enumerate(posts))
    cover = ('<tr><td><a href="%s"><img src="%s" width="600" alt="" style="display:block;width:100%%;max-width:600px;height:auto;border:0"></a></td></tr>'
             % (e(read_url), e(cover_url))) if cover_url else ""
    ed = ""
    if editorial:
        ed = ('<tr><td style="padding:22px 28px 6px"><div style="color:%s;font-size:18px;font-weight:bold;margin-bottom:8px">سخن سردبیر</div>'
              '<div style="font-size:15px;line-height:2.1;color:#1b261e;text-align:justify">%s</div></td></tr>'
              % (EM1, "<br><br>".join(e(x.strip()) for x in editorial.split("\n") if x.strip())))
    soc = " &nbsp;|&nbsp; ".join('<a href="%s" style="color:%s;text-decoration:none;font-weight:bold">%s</a>' % (e(links[k]), GOLD2, n)
                                  for k, n in (("telegram", "تلگرام"), ("bale", "بله"), ("eitaa", "ایتا")) if links.get(k))
    body = (
        '<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>'
        '<body style="margin:0;padding:0;background:#efe9d9;font-family:%s;direction:rtl">'
        '<div style="display:none;max-height:0;overflow:hidden;color:#efe9d9">%s</div>'
        '<table role="presentation" width="100%%" cellpadding="0" cellspacing="0" style="background:#efe9d9"><tr><td align="center" style="padding:18px 8px">'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%%;max-width:600px;background:%s;direction:rtl;text-align:right">'
        '<tr><td align="center" style="background:%s;padding:26px 20px;border-bottom:3px solid %s">'
        '<div style="color:%s;font-size:13px">نشریه‌ی هفتگی</div><div style="color:%s;font-size:34px;font-weight:bold;line-height:1.5">رشد کسب‌وکار</div>'
        '<div style="color:#fff;font-size:14px;margin-top:4px">شماره‌ی %s &nbsp;·&nbsp; %s</div></td></tr>'
        '%s%s'
        '<tr><td style="padding:18px 28px 0"><div style="color:%s;font-size:18px;font-weight:bold">در این شماره</div></td></tr>'
        '<tr><td style="padding:0 28px"><table role="presentation" width="100%%" cellpadding="0" cellspacing="0">%s</table></td></tr>'
        '<tr><td align="center" style="padding:26px 20px 8px">%s</td></tr>'
        '<tr><td align="center" style="padding:6px 20px 24px">%s</td></tr>'
        '<tr><td align="center" style="background:%s;padding:20px;color:#cfe0c9;font-size:13px;line-height:2">'
        'ما را دنبال کنید: %s<br>این نشریه را برای کسی که لازمش دارد بفرستید.<br>'
        '<span style="color:%s;font-weight:bold">محمد مهاجر | استراتژیست رشد کسب‌وکار</span><br>%s</td></tr>'
        '<tr><td align="center" style="padding:14px;color:#8b8f86;font-size:11px;line-height:1.9">'
        'این ایمیل را چون در نشریه‌ی رشد کسب‌وکار عضو شده‌اید دریافت کرده‌اید. '
        '<a href="{$unsubscribe}" style="color:#8b8f86">لغو عضویت</a></td></tr>'
        '</table></td></tr></table></body></html>'
    ) % (FONT, e("در این شماره: " + "؛ ".join(p["title"] for p in posts[:3])), PAPER, EM1, GOLD, GOLD2, GOLD2,
         fa(issue_no), e(range_label), cover, ed, EM1, items,
         btn("دانلود PDF شماره‌ی %s" % fa(issue_no), pdf_url, GOLD, "#2a1c05"),
         btn("ورق زدن آنلاین", read_url, "#386641", "#ffffff"),
         EM1, soc, GOLD2, e(links.get("handle", "")))
    return subject, body
