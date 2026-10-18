"""推送：把 alerts.json 里的异动发到 Telegram / 邮件。

设计原则：
  - **没配就静默跳过**，不报错。这样这个脚本可以永远留在流水线里，
    你哪天配了 secret，第二天就自动开始收消息，不用改代码。
  - **没有警报就不发**。不制造「今天没事」的噪音——那种消息发三天你就
    会把 bot 静音，然后真正的警报也收不到。
  - 多个渠道都配了就都发，一个失败不影响另一个。

需要的环境变量（在 GitHub 仓库 Settings → Secrets and variables → Actions 里配）：

  Telegram（推荐，最简单）：
    TELEGRAM_BOT_TOKEN   从 @BotFather 拿
    TELEGRAM_CHAT_ID     你的 chat id（给 bot 发条消息后访问
                         https://api.telegram.org/bot<TOKEN>/getUpdates 可查到）

  邮件（可选）：
    SMTP_HOST            如 smtp.qq.com / smtp.gmail.com
    SMTP_PORT            465（SSL）或 587（STARTTLS）
    SMTP_USER            发件邮箱
    SMTP_PASS            邮箱授权码（不是登录密码）
    MAIL_TO              收件邮箱

用法：
    python notify.py            # 发 alerts.json 里的异动
    python notify.py --test     # 发一条测试消息（验证配置对不对）
"""
import json
import os
import smtplib
import ssl
import sys
import urllib.parse
import urllib.request
from email.mime.text import MIMEText
from email.header import Header

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ALERTS_PATH = os.path.normpath(
    os.path.join(HERE, "..", "public", "data", "alerts.json")
)
SITE = os.environ.get("SITE_URL", "https://chasebig.xyz")

LEVEL_ICON = {"warn": "⚠️", "info": "🔔"}


def env(name):
    v = os.environ.get(name, "").strip()
    return v or None


# ---------------- Telegram ----------------


def tg_configured():
    return bool(env("TELEGRAM_BOT_TOKEN") and env("TELEGRAM_CHAT_ID"))


def tg_send(text):
    """返回 True/False；长消息自动按 Telegram 4096 字符上限切分。"""
    token = env("TELEGRAM_BOT_TOKEN")
    chat = env("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return None

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    # Telegram 上限 4096，保守切 3800
    chunks = []
    while text:
        if len(text) <= 3800:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, 3800)
        if cut < 1000:
            cut = 3800
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")

    ok = True
    for c in chunks:
        data = urllib.parse.urlencode(
            {
                "chat_id": chat,
                "text": c,
                "disable_web_page_preview": "true",
            }
        ).encode()
        try:
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=20) as r:
                body = json.loads(r.read().decode("utf-8", "replace"))
            if not body.get("ok"):
                print(f"  Telegram 返回失败：{body}")
                ok = False
        except Exception as e:
            print(f"  Telegram 发送异常：{e}")
            ok = False
    return ok


# ---------------- 邮件 ----------------


def mail_configured():
    return all(
        env(k)
        for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS", "MAIL_TO")
    )


def mail_send(subject, body):
    if not mail_configured():
        return None

    host = env("SMTP_HOST")
    user = env("SMTP_USER")
    pw = env("SMTP_PASS")
    to = env("MAIL_TO")
    port = int(env("SMTP_PORT") or 465)

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = user
    msg["To"] = to

    try:
        if port == 465:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as s:
                s.login(user, pw)
                s.sendmail(user, [to], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=30) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(user, pw)
                s.sendmail(user, [to], msg.as_string())
        return True
    except Exception as e:
        print(f"  邮件发送异常：{e}")
        return False


# ---------------- 组装文本 ----------------


def build_text(payload):
    alerts = payload.get("alerts") or []
    n = len(alerts)
    upd = (payload.get("nowUpdated") or "")[:16].replace("T", " ")

    lines = [f"📊 美股代币 LP 异动 {n} 条", f"数据时间 {upd}", ""]

    for a in alerts:
        icon = LEVEL_ICON.get(a.get("level"), "•")
        lines.append(f"{icon} {a['title']}")
        lines.append(f"   {a['detail']}")
    lines.append("")
    lines.append(f"看板：{SITE}")
    return "\n".join(lines)


def main():
    if "--test" in sys.argv:
        text = (
            "✅ 通知测试\n\n"
            "如果你看到这条消息，说明异动推送已经配好了。\n"
            "以后只在**真的检测到异动**时才发，不会天天打扰你。\n\n"
            f"看板：{SITE}"
        )
        results = []
        if tg_configured():
            results.append(("Telegram", tg_send(text)))
        if mail_configured():
            results.append(("邮件", mail_send("LP 看板通知测试", text)))
        if not results:
            print("没有配置任何推送渠道（TELEGRAM_BOT_TOKEN / SMTP_* 都没设置）")
            return 1
        for name, ok in results:
            print(f"  {name}: {'OK' if ok else '失败'}")
        return 0 if all(ok for _, ok in results) else 1

    try:
        # utf-8-sig：容忍手工编辑时产生的 BOM
        with open(ALERTS_PATH, encoding="utf-8-sig") as f:
            payload = json.load(f)
    except Exception as e:
        print(f"读不到 alerts.json（{e}），跳过推送")
        return 0

    alerts = payload.get("alerts") or []
    if not alerts:
        print("本次无异动，不推送")
        return 0

    if not payload.get("baseline"):
        print("首次运行无基线，不推送（只建基线）")
        return 0

    text = build_text(payload)
    print(f"准备推送 {len(alerts)} 条异动")
    print("--- 消息内容 ---")
    print(text)
    print("---------------")

    results = []
    if tg_configured():
        results.append(("Telegram", tg_send(text)))
    if mail_configured():
        subject = f"LP 异动 {len(alerts)} 条 · {payload.get('nowUpdated','')[:10]}"
        results.append(("邮件", mail_send(subject, text)))

    if not results:
        print("没有配置任何推送渠道，异动已写入 alerts.json（看板上可见）")
        return 0

    for name, ok in results:
        print(f"  {name}: {'OK' if ok else '失败'}")

    # 推送失败不算流水线失败——数据本身是好的，别因为渠道问题让 Actions 红
    return 0


if __name__ == "__main__":
    sys.exit(main())
