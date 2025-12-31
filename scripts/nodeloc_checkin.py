import asyncio
import os
import time
import requests
from playwright.async_api import async_playwright

BASE = "https://www.nodeloc.com"

NODELOC_COOKIE = os.getenv("NODELOC_COOKIE", "")
LOGIN_EMAIL = os.getenv("LOGIN_EMAIL", "")

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_USER_ID = os.getenv("TG_USER_ID")


# ===== 工具函数 =====
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

        # 注入 Cookie
        cookies = parse_cookies(NODELOC_COOKIE)
        log(f"注入 Cookie 数量: {len(cookies)}")
        await context.add_cookies(cookies)

        page = await context.new_page()

        log("访问首页")
        await page.goto(BASE, wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)

        # === 读取当前签到状态 ===
        title_before = await page.get_attribute(
            "button.checkin-button",
            "title"
        )
        log(f"当前按钮 title: {title_before}")

        if not title_before:
            log("未找到签到按钮，可能未登录")
            return

        if "今日签到" not in title_before:
            log("检测为已签到状态，跳过")
            send_tg(
                f"🟢 <b>NodeLoc 今日已签到</b>\n\n"
                f"账号：{mask_email(LOGIN_EMAIL)}"
            )
            return

        # === 关键：在页面上下文触发真实事件链 ===
        log("执行签到事件链")
        result = await page.evaluate("""
        () => {
            const btn = document.querySelector("button.checkin-button");
            if (!btn) return "NO_BUTTON";

            btn.dispatchEvent(new MouseEvent("mouseenter", { bubbles: true }));
            btn.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
            btn.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
            btn.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
            btn.dispatchEvent(new MouseEvent("click", { bubbles: true }));

            return "EVENT_SENT";
        }
        """)

        log(f"事件执行结果: {result}")

        await page.wait_for_timeout(4000)

        # === 再次读取状态 ===
        title_after = await page.get_attribute(
            "button.checkin-button",
            "title"
        )
        log(f"点击后按钮 title: {title_after}")

        await browser.close()

    send_tg(
        f"✅ <b>NodeLoc 已尝试执行签到</b>\n\n"
        f"账号：{mask_email(LOGIN_EMAIL)}\n"
        f"时间：{time.strftime('%Y-%m-%d %H:%M:%S')}"
    )


if __name__ == "__main__":
    asyncio.run(main())
