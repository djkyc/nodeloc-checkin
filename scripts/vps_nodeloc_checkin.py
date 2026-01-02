import asyncio
import time
import os
import requests
from playwright.async_api import async_playwright, TimeoutError

BASE = "https://www.nodeloc.com"
LOGIN_URL = "https://www.nodeloc.com/login"

NODELOC_USERNAME = os.getenv("NODELOC_USERNAME")
NODELOC_PASSWORD = os.getenv("NODELOC_PASSWORD")
DISPLAY = os.getenv("DISPLAY", ":99")

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")


def log(msg: str):
    print(time.strftime("[%Y-%m-%d %H:%M:%S]"), msg, flush=True)


def send_telegram(msg: str):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        log("Telegram 未配置，跳过通知")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TG_CHAT_ID,
                "text": msg,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
    except Exception as e:
        log(f"Telegram 发送失败: {e}")


async def main() -> int:
    start_time = time.strftime("%Y-%m-%d %H:%M:%S")

    try:
        log("NodeLoc systemd 签到启动")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )

            context = await browser.new_context(
                viewport={"width": 1280, "height": 800}
            )
            page = await context.new_page()

            # 打开登录页
            await page.goto(LOGIN_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            # 登录
            await page.fill("#login-account-name", NODELOC_USERNAME)
            await page.fill("#login-account-password", NODELOC_PASSWORD)
            await page.click("#login-button")

            # ⚠️ 关键修正点：
            # 只等 DOM 就绪，不等 load
            await page.wait_for_url(
                BASE + "/",
                wait_until="domcontentloaded",
                timeout=60000
            )

            # 等签到按钮出现（这是我们真正关心的）
            btn = await page.wait_for_selector(
                "li.header-dropdown-toggle.checkin-icon > button.checkin-button",
                timeout=60000
            )

            # ===== ① 运行前判断：是否已签到 =====
            pre_disabled = await btn.get_attribute("disabled")
            pre_class = await btn.get_attribute("class") or ""

            if pre_disabled is not None or "checked-in" in pre_class:
                await browser.close()
                send_telegram(
                    f"🟡 <b>NodeLoc 今日已签到</b>\n\n"
                    f"账号：{NODELOC_USERNAME}\n"
                    f"时间：{start_time}"
                )
                log("今日已签到（运行前状态）")
                return 0

            # ===== ② 执行签到点击 =====
            await btn.hover()
            await page.wait_for_timeout(300)
            await btn.click()
            await page.wait_for_timeout(2000)

            # ===== ③ 点击后判断 =====
            post_disabled = await btn.get_attribute("disabled")
            post_class = await btn.get_attribute("class") or ""

            await browser.close()

            if post_disabled is not None or "checked-in" in post_class:
                send_telegram(
                    f"✅ <b>NodeLoc 签到成功</b>\n\n"
                    f"账号：{NODELOC_USERNAME}\n"
                    f"时间：{start_time}"
                )
                log("签到成功（刚刚完成）")
                return 0

            raise RuntimeError("点击后未进入已签到状态")

    except Exception as e:
        send_telegram(
            f"❌ <b>NodeLoc 签到失败</b>\n\n"
            f"账号：{NODELOC_USERNAME}\n"
            f"时间：{start_time}\n\n"
            f"<code>{str(e)}</code>"
        )
        log(f"签到失败: {e}")
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
