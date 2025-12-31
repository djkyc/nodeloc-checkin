import asyncio
import time
from playwright.async_api import async_playwright, TimeoutError

BASE = "https://www.nodeloc.com"
LOGIN_URL = "https://www.nodeloc.com/login"

# ===== 在这里填写账号密码 =====
NODELOC_USERNAME = "你的账号或邮箱"
NODELOC_PASSWORD = "你的密码"


def log(msg):
    print(time.strftime("[%Y-%m-%d %H:%M:%S]"), msg, flush=True)


async def main():
    log("====== NodeLoc 自动签到开始 ======")

    async with async_playwright() as p:
        log("启动 Chromium 浏览器（非 headless）")
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled"
            ]
        )

        log("创建浏览器上下文")
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800}
        )

        log("新建页面")
        page = await context.new_page()

        # ===== 1. 打开登录页 =====
        log("STEP 1/15：打开登录页面")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # ===== 2. 等待账号输入框 =====
        log("STEP 2/15：等待账号输入框")
        await page.wait_for_selector('input[name="login"]', timeout=15000)
        log("账号输入框已找到")

        # ===== 3. 等待密码输入框 =====
        log("STEP 3/15：等待密码输入框")
        await page.wait_for_selector('input[name="password"]', timeout=15000)
        log("密码输入框已找到")

        # ===== 4. 输入账号 =====
        log("STEP 4/15：输入账号")
        await page.fill('input[name="login"]', NODELOC_USERNAME)
        await page.wait_for_timeout(300)

        # ===== 5. 输入密码 =====
        log("STEP 5/15：输入密码")
        await page.fill('input[name="password"]', NODELOC_PASSWORD)
        await page.wait_for_timeout(300)

        # ===== 6. 点击登录 =====
        log("STEP 6/15：点击登录按钮")
        await page.click('button[type="submit"]')

        # ===== 7. 等待跳转首页 =====
        log("STEP 7/15：等待登录跳转到首页")
        try:
            await page.wait_for_url(BASE + "/", timeout=20000)
            log("已跳转到首页")
        except TimeoutError:
            log("❌ 登录未跳转首页，可能失败")
            await page.wait_for_timeout(5000)
            await browser.close()
            return

        await page.wait_for_timeout(4000)

        # ===== 8. 判断是否登录成功 =====
        log("STEP 8/15：确认登录状态")
        await page.wait_for_selector(
            'li.header-dropdown-toggle.current-user',
            timeout=15000
        )
        log("确认已登录")

        # ===== 9. 查找签到按钮 =====
        log("STEP 9/15：查找签到按钮")
        btn = await page.wait_for_selector(
            'button.checkin-button[title="每日签到"]',
            timeout=15000
        )
        log("签到按钮已找到")

        # ===== 10. 获取按钮坐标 =====
        log("STEP 10/15：获取签到按钮坐标")
        box = await btn.bounding_box()
        if not box:
            log("❌ 未获取到按钮坐标")
            await browser.close()
            return

        x = box["x"] + box["width"] / 2
        y = box["y"] + box["height"] / 2
        log(f"按钮中心坐标: ({int(x)}, {int(y)})")

        # ===== 11. 鼠标移动 =====
        log("STEP 11/15：鼠标移动到签到按钮")
        await page.mouse.move(x - 20, y - 10)
        await page.wait_for_timeout(300)
        await page.mouse.move(x, y)
        await page.wait_for_timeout(300)

        # ===== 12. 鼠标按下 =====
        log("STEP 12/15：鼠标按下")
        await page.mouse.down()
        await page.wait_for_timeout(120)

        # ===== 13. 鼠标抬起 =====
        log("STEP 13/15：鼠标抬起")
        await page.mouse.up()

        # ===== 14. 等待前端响应 =====
        log("STEP 14/15：等待前端响应（6 秒）")
        await page.wait_for_timeout(6000)

        # ===== 15. 结束 =====
        log("STEP 15/15：流程完成，保留浏览器 5 秒供观察")
        await page.wait_for_timeout(5000)

        await browser.close()

    log("====== NodeLoc 自动签到结束 ======")


if __name__ == "__main__":
    asyncio.run(main())
