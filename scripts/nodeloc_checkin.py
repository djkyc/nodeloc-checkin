import asyncio
import os
import time
import requests
from playwright.async_api import async_playwright

BASE = "https://www.nodeloc.com"

NODELOC_COOKIE = os.getenv("NODELOC_COOKIE", "")
LOGIN_EMAIL = os.getenv("NODELOC_LOGIN_EMAIL", "")

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_USER_ID = os.getenv("TG_USER_ID")


def send_tg(msg: str):
    if not TG_BOT_TOKEN or not TG_USER_ID:
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TG_USER_ID,
        "text": msg
    })


def mask_email(email: str) -> str:
    if "@" not in email:
        return "***"
    u, d = email.split("@", 1)
    if len(u) <= 2:
        return u[0] + "*@" + d
    return u[:2] + "*" * (len(u) - 2) + "@" + d


def beijing_time():
    t = time.gmtime(time.time() + 8 * 3600)
    return time.strftime("%Y:%m:%d:%H:%M", t)


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


async def main():
    if not NODELOC_COOKIE:
        send_tg("❌ NodeLoc Cookie 缺失")
        return

    account = mask_email(LOGIN_EMAIL) if LOGIN_EMAIL else "（邮箱未配置）"
    now = beijing_time()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,   # 如果还不稳，改成 False 试一次
            args=["--no-sandbox"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800}
        )

        await context.add_cookies(parse_cookies(NODELOC_COOKIE))
        page = await context.new_page()

        await page.goto(BASE, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        btn = await page.query_selector("button.checkin-button")
        if not btn:
            send_tg(f"⚠️ NodeLoc 未发现签到入口\n账号：{account}\n时间：{now}")
            await browser.close()
            return

        # 记录点击前状态（仅用于区分首次/重复）
        before = await btn.evaluate("""
            b => ({
                checked: b.classList.contains("checked-in"),
                disabled: b.disabled,
                text: (b.getAttribute("title") || "") + (b.getAttribute("aria-label") || "")
            })
        """)

        # === 关键：始终点击，让网站自己判断 ===
        await page.evaluate("""
            () => {
                const b = document.querySelector("button.checkin-button");
                if (b) b.click();
            }
        """)

        await page.wait_for_timeout(800)

        # 读取点击后的状态
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

        # === 严格按网站逻辑给结果 ===
        if not before["checked"] and not before["disabled"] and "已签到" not in before["text"]:
            if after and (after["checked"] or after["disabled"] or "已签到" in after["text"]):
                send_tg(f"✅ NodeLoc 签到成功\n账号：{account}\n时间：{now}")
                return

        if after and ("已签到" in after["text"] or before["checked"] or before["disabled"]):
            send_tg(f"🟢 NodeLoc 今日已签到\n账号：{account}\n时间：{now}")
            return

        send_tg(f"❌ NodeLoc 签到未触发\n账号：{account}\n时间：{now}")


if __name__ == "__main__":
    asyncio.run(main())
