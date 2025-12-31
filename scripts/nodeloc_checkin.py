import asyncio
import time
import os
from playwright.async_api import async_playwright, TimeoutError

BASE = "https://www.nodeloc.com"
LOGIN_URL = "https://www.nodeloc.com/login"

# GitHub Actions Secrets
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

        # 1️⃣ 打开登录页
        log("打开登录页面 /login")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        # 2️⃣ 等账号输入框（基于你给的 F12，唯一正确）
        log("等待账号输入框 #login-account-name")
        await page.wait_for_selector("#login-account-name", timeout=30000)

        log("输入账号")
        await page.fill("#login-account-name", NODELOC_USERNAME)

        # 3️⃣ 等密码输入框
        log("等待密码输入框 #login-account-password")
        await page.wait_for_selector("#login-account-password", timeout=30000)

        log("输入密码")
        await page.fill("#login-account-password", NODELOC_PASSWORD)

        # 4️⃣ 点击登录
        log("点击登录按钮 #login-button")
        await page.click("#login-button")

        # 5️⃣ 等回到首页（这是登录成功的铁证）
        log("等待跳转回首页")
        await page.wait_for_url(BASE + "/", timeout=30000)
        log("登录成功，已进入首页")

        # 6️⃣ 查找【真正的签到按钮：日历图片按钮本体】
        log("查找签到按钮（图片按钮本体）")
        btn = await page.wait_for_selector(
            "li.header-dropdown-toggle.checkin-icon > button.checkin-button",
            timeout=30000
        )

        # —— 点击前状态
        title_before = await btn.get_attribute("title")
        aria_before = await btn.get_attribute("aria-label")
        log(f"签到前状态: title={title_before}, aria-label={aria_before}")

        # 7️⃣ 点击签到（就是你截图里那个日历图标）
        log("点击签到按钮")
        await btn.click(delay=120)

        # 等前端处理
        await page.wait_for_timeout(2000)

        # —— 点击后状态
        btn_after = await page.query_selector(
            "li.header-dropdown-toggle.checkin-icon > button.checkin-button"
        )

        if not btn_after:
            log("✅ 签到后：按钮消失（判定签到成功）")
        else:
            title_after = await btn_after.get_attribute("title")
            aria_after = await btn_after.get_attribute("aria-label")
            log(f"签到后状态: title={title_after}, aria-label={aria_after}")

            if title_before != title_after or aria_before != aria_after:
                log("✅ 签到状态发生变化（判定签到成功）")
            else:
                log("⚠️ 签到按钮状态未变化（可能已签到或当日无变化）")

        await page.wait_for_timeout(2000)
        await browser.close()

    log("====== NodeLoc 自动签到结束 ======")


if __name__ == "__main__":
    asyncio.run(main())
