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


def log(msg: str):
    print(time.strftime("[%Y-%m-%d %H:%M:%S] "), msg, flush=True)


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


def mask_email(email: str):
    if "@" not in email:
        return "***"
    u, d = email.split("@", 1)
    return u[:2] + "***@" + d


def parse_cookies(cookie_str):
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


async def main():
    log("====== NodeLoc 签到开始 ======")
    log(f"账号: {mask_email(LOGIN_EMAIL)}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox"]
        )

        context = await browser.new_context(
            viewport={"width": 1280, "height": 800}
        )

        cookies = parse_cookies(NODELOC_COOKIE)
        log(f"注入 Cookie 数量: {len(cookies)}")
        await context.add_cookies(cookies)

        page = await context.new_page()
        log("访问首页")
        await page.goto(BASE, wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)

        # === 找到签到 button ===
        log("查找签到按钮")
        btn = await page.wait_for_selector(
            "li.header-dropdown-toggle.checkin-icon button.checkin-button",
            timeout=8000
        )

        box = await btn.bounding_box()
        x = box["x"] + box["width"] / 2
        y = box["y"] + box["height"] / 2

        log("模拟真实鼠标点击（down/up）")
        await page.mouse.move(x, y)
        await page.wait_for_timeout(200)
        await page.mouse.down()
        await page.wait_for_timeout(120)
        await page.mouse.up()

        log("鼠标事件已发送，等待前端处理")
        await page.wait_for_timeout(4000)

        await browser.close()

    send_tg(
        "✅ <b>NodeLoc 已执行签到点击</b>\n\n"
        f"账号：{mask_email(LOGIN_EMAIL)}\n"
        f"时间：{time.strftime('%Y-%m-%d %H:%M:%S')}"
    )


if __name__ == "__main__":
    asyncio.run(main())
