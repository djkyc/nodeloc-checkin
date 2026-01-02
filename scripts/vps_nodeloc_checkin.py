import asyncio
import time
import os
import requests
from playwright.async_api import async_playwright

LOGIN_URL = "https://www.nodeloc.com/login"

NODELOC_USERNAME = os.getenv("NODELOC_USERNAME")
NODELOC_PASSWORD = os.getenv("NODELOC_PASSWORD")
DISPLAY = os.getenv("DISPLAY", ":99")

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")


def log(msg):
    print(time.strftime("[%Y-%m-%d %H:%M:%S]"), msg, flush=True)


def send_tg(msg):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    requests.post(
        f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
        json={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "HTML"},
        timeout=10,
    )


async def main():
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    try:
        log("NodeLoc systemd 签到启动")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            page = await browser.new_page()

            # 打开登录页（只等 DOM）
            await page.goto(LOGIN_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(1500)

            # 登录
            await page.fill("#login-account-name", NODELOC_USERNAME)
            await page.fill("#login-account-password", NODELOC_PASSWORD)
            await page.click("#login-button")

            # ⭐⭐ 关键：只等签到按钮出现，绝不等 URL ⭐⭐
            btn = await page.wait_for_selector(
                "li.header-dropdown-toggle.checkin-icon > button.checkin-button",
                timeout=90000
            )

            cls = await btn.get_attribute("class") or ""
            if "checked-in" in cls:
                await browser.close()
                send_tg(f"🟡 NodeLoc 今日已签到\n{now}")
                return 0

            # 执行签到
            await btn.hover()
            await page.wait_for_timeout(300)
            await btn.click()
            await page.wait_for_timeout(2000)

            cls2 = await btn.get_attribute("class") or ""
            await browser.close()

            if "checked-in" in cls2:
                send_tg(f"✅ NodeLoc 签到成功\n{now}")
                return 0

            raise RuntimeError("签到状态未变化")

    except Exception as e:
        send_tg(f"❌ NodeLoc 签到失败\n{now}\n{e}")
        log(f"签到失败: {e}")
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
