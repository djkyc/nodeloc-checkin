import asyncio
import time
import os
from playwright.async_api import async_playwright

BASE = "https://www.nodeloc.com"
LOGIN_URL = "https://www.nodeloc.com/login"

NODELOC_USERNAME = os.getenv("NODELOC_USERNAME")
NODELOC_PASSWORD = os.getenv("NODELOC_PASSWORD")


def log(msg):
    print(time.strftime("[%Y-%m-%d %H:%M:%S]"), msg, flush=True)


async def main():
    log("====== NodeLoc 自动签到开始（VPS GUI） ======")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,   # 🔴 必须 false
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )

        context = await browser.new_context(
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        # 打开登录页
        log("打开登录页")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        # 登录
        log("输入账号")
        await page.fill("#login-account-name", NODELOC_USERNAME)

        log("输入密码")
        await page.fill("#login-account-password", NODELOC_PASSWORD)

        log("点击登录")
        await page.click("#login-button")

        log("等待进入首页")
        await page.wait_for_url(BASE + "/", timeout=30000)
        await page.wait_for_timeout(2000)

        # 点击签到按钮
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

    log("====== NodeLoc 自动签到结束 ======")


if __name__ == "__main__":
    asyncio.run(main())
