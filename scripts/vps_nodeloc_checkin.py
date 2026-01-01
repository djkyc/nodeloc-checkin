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


def tg_send(msg):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
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


def is_checked_in(btn):
    """判断按钮是否处于‘已签到’状态"""
    # disabled 或 checked-in class 都算
    return (
        btn.get_attribute("disabled") is not None
        or "checked-in" in (btn.get_attribute("class") or "")
    )


async def main():
    start_time = time.strftime("%Y-%m-%d %H:%M:%S")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )

            context = await browser.new_context(
                viewport={"width": 1280, "height": 800}
            )
            page = await context.new_page()

            # 登录
            await page.goto(LOGIN_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            await page.fill("#login-account-name", NODELOC_USERNAME)
            await page.fill("#login-account-password", NODELOC_PASSWORD)
            await page.click("#login-button")

            await page.wait_for_url(BASE + "/", timeout=30000)
            await page.wait_for_timeout(2000)

            btn = await page.wait_for_selector(
                "li.header-dropdown-toggle.checkin-icon > button.checkin-button",
                timeout=20000
            )

            # ===== ① 运行前判断 =====
            pre_disabled = await btn.get_attribute("disabled")
            pre_class = await btn.get_attribute("class") or ""

            if pre_disabled is not None or "checked-in" in pre_class:
                # 今天已经签到过
                await browser.close()
                tg_send(
                    f"🟡 <b>NodeLoc 今日已签到</b>\n\n"
                    f"账号：{NODELOC_USERNAME}\n"
                    f"时间：{start_time}"
                )
                log("今日已签到（运行前状态）")
                return 0

            # ===== ② 执行点击 =====
            await btn.hover()
            await page.wait_for_timeout(300)
            await btn.click()
            await page.wait_for_timeout(2000)

            # ===== ③ 点击后判断 =====
            post_disabled = await btn.get_attribute("disabled")
            post_class = await btn.get_attribute("class") or ""

            await browser.close()

            if post_disabled is not None or "checked-in" in post_class:
                tg_send(
                    f"✅ <b>NodeLoc 签到成功</b>\n\n"
                    f"账号：{NODELOC_USERNAME}\n"
                    f"时间：{start_time}"
                )
                log("签到成功（刚刚完成）")
                return 0

            raise RuntimeError("点击后仍未进入已签到状态")

    except Exception as e:
        tg_send(
            f"❌ <b>NodeLoc 签到失败</b>\n\n"
            f"账号：{NODELOC_USERNAME}\n"
            f"时间：{start_time}\n\n"
            f"<code>{e}</code>"
        )
        log(f"签到失败: {e}")
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
