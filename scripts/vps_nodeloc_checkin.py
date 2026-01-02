import asyncio
import time
import os
import requests
from playwright.async_api import async_playwright

LOGIN_URL = "https://www.nodeloc.com/login"
HOME_URL = "https://www.nodeloc.com/"

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
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        log(f"Telegram 通知发送失败: {e}")


async def main():
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    browser = None

    try:
        log("NodeLoc 自动签到启动")

        async with async_playwright() as p:
            # 启动浏览器（headless 模式）
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
            )
            
            # 创建浏览器上下文，设置更真实的 User-Agent
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )
            page = await context.new_page()

            log("打开登录页面 /login")
            # 打开登录页，等待网络空闲
            await page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(2000)

            log("等待登录表单加载")
            # 等待登录表单元素出现
            await page.wait_for_selector("#login-account-name", timeout=30000)
            await page.wait_for_selector("#login-account-password", timeout=30000)
            await page.wait_for_selector("#login-button", timeout=30000)

            log("输入用户名")
            await page.fill("#login-account-name", NODELOC_USERNAME)
            await page.wait_for_timeout(500)

            log("输入密码")
            await page.fill("#login-account-password", NODELOC_PASSWORD)
            await page.wait_for_timeout(500)

            log("点击登录按钮 #login-button")
            await page.click("#login-button")
            
            # 等待登录完成，监听导航或签到按钮出现
            log("等待登录成功，已进入首页")
            try:
                # 方案1：等待签到按钮出现（说明已登录成功）
                await page.wait_for_selector(
                    "li.header-dropdown-toggle.checkin-icon > button.checkin-button",
                    timeout=30000
                )
                log("签到按钮已出现（图片按钮体）")
            except Exception as e:
                log(f"等待签到按钮超时: {e}")
                # 方案2：尝试导航到首页
                log("尝试手动导航到首页")
                await page.goto(HOME_URL, wait_until="networkidle", timeout=60000)
                await page.wait_for_timeout(3000)
                await page.wait_for_selector(
                    "li.header-dropdown-toggle.checkin-icon > button.checkin-button",
                    timeout=30000
                )
                log("签到按钮已出现（图片按钮体）")

            # 等待页面完全加载，确保 Cookie 和 CSRF Token 都已设置
            log("等待页面完全加载（包括 Cookie 接收）")
            await page.wait_for_load_state("networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

            # 获取签到按钮
            btn = await page.query_selector("li.header-dropdown-toggle.checkin-icon > button.checkin-button")
            if not btn:
                raise RuntimeError("未找到签到按钮")

            # 检查是否已签到
            cls = await btn.get_attribute("class") or ""
            log(f"签到按钮状态: {cls}")
            
            if "checked-in" in cls:
                log("今日已签到")
                await context.close()
                await browser.close()
                send_tg(f"🟡 NodeLoc 今日已签到\n{now}")
                return 0

            # 执行签到
            log("准备签到，悬停按钮")
            await btn.hover()
            await page.wait_for_timeout(500)
            
            log("点击签到按钮")
            await btn.click()
            
            # 等待签到请求完成
            log("等待签到请求完成")
            await page.wait_for_timeout(5000)
            
            # 再次检查按钮状态
            cls2 = await btn.get_attribute("class") or ""
            log(f"签到后按钮状态: {cls2}")

            await context.close()
            await browser.close()

            if "checked-in" in cls2:
                log("✅ 签到成功")
                send_tg(f"✅ NodeLoc 签到成功\n{now}")
                return 0
            else:
                # 可能签到成功但状态未立即更新，检查页面内容
                log("⚠️ 签到状态未变化，但可能已成功")
                send_tg(f"⚠️ NodeLoc 签到状态未变化\n{now}\n请手动检查")
                return 0

    except Exception as e:
        error_msg = str(e)
        log(f"❌ 签到失败: {error_msg}")
        send_tg(f"❌ NodeLoc 签到失败\n{now}\n{error_msg}")
        
        if browser:
            try:
                await browser.close()
            except:
                pass
        
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
