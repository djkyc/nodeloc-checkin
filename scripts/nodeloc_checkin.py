import asyncio
import os
import time
import requests
from playwright.async_api import async_playwright

BASE = "https://www.nodeloc.com"

# ===== 配置 =====
NODELOC_COOKIE = os.getenv("NODELOC_COOKIE", "")
LOGIN_EMAIL = os.getenv("NODELOC_LOGIN_EMAIL", "")

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_USER_ID = os.getenv("TG_USER_ID")


# ===== 工具 =====
def log(msg: str):
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"[{now}] {msg}", flush=True)


def send_tg(msg: str):
    if not TG_BOT_TOKEN or not TG_USER_ID:
        return
    requests.post(
        f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
        json={
            "chat_id": TG_USER_ID,
            "text": msg,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        },
        timeout=10
    )


def mask_email(email: str) -> str:
    if "@" not in email:
        return "***"
    u, d = email.split("@", 1)
    return u[:2] + "***@" + d


def beijing_time():
    return time.strftime(
        "%Y-%m-%d %H:%M:%S",
        time.gmtime(time.time() + 8 * 3600)
    )


def parse_cookies(cookie_str: str):
    cookies = []
    for part in cookie_str.split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            cookies.append({
                "name": k,
                "value": v,
                "domain": "www.nodeloc.com",
                "path": "/"
            })
    return cookies


# ===== 主流程 =====
async def main():
    account = mask_email(LOGIN_EMAIL)
    now = beijing_time()

    log("====== NodeLoc 签到开始 ======")
    log(f"账号: {account}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox"]
        )

        context = await browser.new_context(
            viewport={"width": 1280, "height": 800}
        )

        # 注入 Cookie
        await context.add_cookies(parse_cookies(NODELOC_COOKIE))
        page = await context.new_page()

        log("访问首页")
        await page.goto(BASE, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # === 只做一件事：点击签到图标 ===
        log("定位签到按钮")
        icon = await page.wait_for_selector(
            "li.header-dropdown-toggle.checkin-icon svg.d-icon-calendar-check",
            timeout=8000
        )

        box = await icon.bounding_box()
        await page.mouse.move(
            box["x"] + box["width"] / 2,
            box["y"] + box["height"] / 2
        )
        await page.mouse.down()
        await page.wait_for_timeout(80)
        await page.mouse.up()

        log("签到点击完成")
        await page.wait_for_timeout(3000)

        await browser.close()

    # === 结果判断（前端已执行即视为成功）===
    send_tg(
        f"✅ <b>NodeLoc 已执行签到</b>\n\n"
        f"账号：{account}\n"
        f"时间：{now}"
    )


if __name__ == "__main__":
    asyncio.run(main())
