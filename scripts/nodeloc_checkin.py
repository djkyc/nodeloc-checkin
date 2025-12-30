import asyncio
import os
import time
import requests
from playwright.async_api import async_playwright

BASE = "https://www.nodeloc.com"

# ====== Secrets ======
NODELOC_COOKIE = os.getenv("NODELOC_COOKIE", "")
NODELOC_USERNAME = os.getenv("NODELOC_USERNAME", "")  # 邮箱/用户名
NODELOC_PASSWORD = os.getenv("NODELOC_PASSWORD", "")  # 密码
LOGIN_EMAIL = os.getenv("NODELOC_LOGIN_EMAIL", "")

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_USER_ID = os.getenv("TG_USER_ID")


# ====== Utils ======
def send_tg(msg: str):
    if not TG_BOT_TOKEN or not TG_USER_ID:
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TG_USER_ID,
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }, timeout=15)


def mask_email(email: str) -> str:
    if "@" not in email:
        return "***"
    u, d = email.split("@", 1)
    if len(u) <= 2:
        return u[0] + "*@" + d
    return u[:2] + "*" * (len(u) - 2) + "@" + d


def beijing_time():
    t = time.gmtime(time.time() + 8 * 3600)
    return time.strftime("%Y-%m-%d %H:%M:%S", t)


def parse_cookies(cookie_str: str):
    cookies = []
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            cookies.append({
                "name": k,
                "value": v,
                "domain": "www.nodeloc.com",
                "path": "/"
            })
    return cookies


# ====== Login & Fetch New Cookie ======
async def login_and_get_new_cookie(context, page):
    if not NODELOC_USERNAME or not NODELOC_PASSWORD:
        return None

    await page.goto(f"{BASE}/login", wait_until="domcontentloaded")
    await page.wait_for_timeout(1500)

    # ⚠️ 如登录页有变化，这里的 selector 可能需要微调
    await page.fill("input[name='email']", NODELOC_USERNAME)
    await page.fill("input[name='password']", NODELOC_PASSWORD)
    await page.click("button[type='submit']")

    # 等待跳转
    await page.wait_for_timeout(5000)

    # 若仍在 login 页面，视为失败（可能有验证码）
    if "login" in page.url:
        return None

    cookies = await context.cookies(BASE)
    if not cookies:
        return None

    cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
    return cookie_str


async def main():
    account = mask_email(LOGIN_EMAIL) if LOGIN_EMAIL else "（邮箱未配置）"
    now = beijing_time()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800}
        )

        # 先尝试使用已有 Cookie
        if NODELOC_COOKIE:
            await context.add_cookies(parse_cookies(NODELOC_COOKIE))

        page = await context.new_page()
        await page.goto(BASE, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        btn = await page.query_selector("button.checkin-button")

        # ====== Cookie 失效分支 ======
        if not btn:
            # 尝试账号密码登录，获取新 Cookie
            new_cookie = await login_and_get_new_cookie(context, page)
            await browser.close()

            if new_cookie:
                send_tg(
                    "🚨 <b>NodeLoc Cookie 已失效，已自动获取新 Cookie</b>\n\n"
                    f"📧 账号：<a href=\"mailto:{account}\">{account}</a>\n"
                    f"🕒 时间：{now}\n\n"
                    "📎 <b>新的 Cookie（请手动更新 GitHub Secrets）</b>\n"
                    f"<code>{new_cookie}</code>\n\n"
                    "👉 操作：复制以上 Cookie → GitHub → Secrets → "
                    "<b>NODELOC_COOKIE</b> 覆盖保存"
                )
            else:
                send_tg(
                    "❌ <b>NodeLoc Cookie 失效，自动登录失败</b>\n\n"
                    f"📧 账号：<a href=\"mailto:{account}\">{account}</a>\n"
                    f"🕒 时间：{now}\n\n"
                    "⚠️ 可能原因：验证码 / 风控\n"
                    "👉 请手动登录网站并更新 Cookie"
                )
            return

        # ====== 正常签到流程 ======
        before = await btn.evaluate("""
            b => ({
                checked: b.classList.contains("checked-in"),
                disabled: b.disabled,
                text: (b.getAttribute("title") || "") + (b.getAttribute("aria-label") || "")
            })
        """)

        await page.evaluate("""
            () => {
                const b = document.querySelector("button.checkin-button");
                if (b) b.click();
            }
        """)
        await page.wait_for_timeout(800)

        after = await page.evaluate("""
            () => {
                const b = document.querySelector("button.checkin-button");
                if (!b) return null;
                const text = (b.getAttribute("title") || "") + (b.getAttribute("aria-label") || "");
                return {
                    checked: b.classList.contains("checked-in"),
                    disabled: b.disabled,
                    text
                };
            }
        """)

        await browser.close()

        if not before["checked"] and not before["disabled"] and "已签到" not in before["text"]:
            if after and (after["checked"] or after["disabled"] or "已签到" in after["text"]):
                send_tg(
                    "✅ <b>NodeLoc 签到成功</b>\n\n"
                    f"📧 账号：<a href=\"mailto:{account}\">{account}</a>\n"
                    f"🕒 时间：{now}"
                )
                return

        if after and ("已签到" in after["text"] or before["checked"] or before["disabled"]):
            send_tg(
                "🟢 <b>NodeLoc 今日已签到</b>\n\n"
                f"📧 账号：<a href=\"mailto:{account}\">{account}</a>\n"
                f"🕒 时间：{now}"
            )
            return

        send_tg(
            "❌ <b>NodeLoc 签到未触发</b>\n\n"
            f"📧 账号：<a href=\"mailto:{account}\">{account}</a>\n"
            f"🕒 时间：{now}"
        )


if __name__ == "__main__":
    asyncio.run(main())
