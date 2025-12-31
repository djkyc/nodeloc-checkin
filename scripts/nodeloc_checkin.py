import asyncio
import time
import os
from playwright.async_api import async_playwright, TimeoutError

BASE = "https://www.nodeloc.com"
LOGIN_URL = "https://www.nodeloc.com/login"

NODELOC_USERNAME = os.getenv("NODELOC_USERNAME")
NODELOC_PASSWORD = os.getenv("NODELOC_PASSWORD")


def log(msg):
    print(time.strftime("[%Y-%m-%d %H:%M:%S]"), msg, flush=True)


async def main():
    log("====== NodeLoc 自动签到开始 ======")

    async with async_playwright() as p:
        log("启动 headless Chromium（GitHub Actions）")
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )

        context = await browser.new_context()
        page = await context.new_page()

        # 1️⃣ 打开登录页（⚠️ 不能用 networkidle）
        log("打开登录页面")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        # 2️⃣ 等登录框（Discourse 标准 ID）
        log("等待账号输入框")
        await page.wait_for_selector("#login-account-name", timeout=20000)

        log("输入账号")
        await page.fill("#login-account-name", NODELOC_USERNAME)

        log("输入密码")
        await page.fill("#login-account-password", NODELOC_PASSWORD)

        log("提交登录")
        await page.click("button.login-button")

        # 3️⃣ 等跳回首页
        log("等待跳转首页")
        await page.wait_for_url(BASE + "/", timeout=30000)
        log("登录成功")

        # 4️⃣ 直接点签到按钮
        log("查找签到按钮")
        btn = await page.wait_for_selector(
            'button.checkin-button',
            timeout=20000
        )

        log("点击签到")
        await btn.click(delay=100)

        log("签到点击完成，等待 3 秒")
        await page.wait_for_timeout(3000)

        await browser.close()

    log("====== NodeLoc 自动签到结束 ======")


if __name__ == "__main__":
    asyncio.run(main())
