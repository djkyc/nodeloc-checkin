import asyncio
import time
import os
import requests
from playwright.async_api import async_playwright

BASE = "https://www.nodeloc.com"
LOGIN_URL = "https://www.nodeloc.com/login"

NODELOC_USERNAME = os.getenv("NODELOC_USERNAME")
NODELOC_PASSWORD = os.getenv("NODELOC_PASSWORD")
DISPLAY = os.getenv("DISPLAY", ":99")

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")


def log(msg):
    print(time.strftime("[%Y-%m-%d %H:%M:%S]"), msg, flush=True)


def send_telegram(message):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        log("⚠️ 未配置 Telegram，跳过通知")
        return

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        log(f"Telegram 发送失败: {e}")


async def main():
    start_time = time.strftime("%Y-%m-%d %H:%M:%S")

    try:
        log("====== NodeLoc 自动签到开始 (VPS GUI) ======")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )

            context = await browser.new_context(
                viewport={"width": 1280, "height": 800}
            )
            page = await context.new_page()

            log("打开登录页")
            await page.goto(LOGIN_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            log("输入账号")
            await page.fill("#login-account-name", NODELOC_USERNAME)

            log("输入密码")
            await page.fill("#login-account-password", NODELOC_PASSWORD)

            log("点击登录")
            await page.click("#login-button")

            log("等待进入首页")
            await page.wait_for_url(BASE + "/", timeout=30000)
            await page.wait_for_timeout(2000)

            log("查找签到按钮（日历图标）")
            btn = await page.wait_for_selector(
                "li.header-dropdown-toggle.checkin-icon > button.checkin-button",
                timeout=20000
            )

            log("执行签到点击")
            await btn.hover()
            await page.wait_for_timeout(300)
            await btn.click()

            log("等待签到反馈")
            await page.wait_for_timeout(3000)

            await browser.close()

        msg = (
            f"✅ <b>NodeLoc 签到成功</b>\n\n"
            f"账号：{NODELOC_USERNAME}\n"
            f"时间：{start_time}"
        )

        send_telegram(msg)
        log("Telegram 已发送成功通知")

    except Exception as e:
        err_msg = (
            f"❌ <b>NodeLoc 签到失败</b>\n\n"
            f"账号：{NODELOC_USERNAME}\n"
            f"时间：{start_time}\n\n"
            f"<code>{str(e)}</code>"
        )
        send_telegram(err_msg)
        log(f"发生异常: {e}")

    log("====== NodeLoc 自动签到结束 ======")


if __name__ == "__main__":
    asyncio.run(main())
