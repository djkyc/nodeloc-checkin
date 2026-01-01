import asyncio
import time
import os
import requests
from http.cookies import SimpleCookie
from playwright.async_api import async_playwright

BASE = "https://www.nodeloc.com"
LOGIN_URL = "https://www.nodeloc.com/login"
CHECKIN_API = f"{BASE}/checkin"

NODELOC_USERNAME = os.getenv("NODELOC_USERNAME")
NODELOC_PASSWORD = os.getenv("NODELOC_PASSWORD")
NODELOC_COOKIE = os.getenv("NODELOC_COOKIE")


def log(msg):
    print(time.strftime("[%Y-%m-%d %H:%M:%S]"), msg, flush=True)


def build_cookiejar(cookie_str: str):
    jar = requests.cookies.RequestsCookieJar()
    sc = SimpleCookie()
    sc.load(cookie_str)
    for k, v in sc.items():
        jar.set(k, v.value, domain="www.nodeloc.com", path="/")
    return jar


def extract_csrf(jar):
    for cookie in jar:
        if cookie.name == "csrf_token":
            return cookie.value
    return None


def api_checkin():
    log("➡️ 使用 Cookie 接口方式签到")

    if not NODELOC_COOKIE:
        log("❌ 未提供 NODELOC_COOKIE，接口签到不可用")
        return

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Referer": BASE,
        "Origin": BASE,
    })

    jar = build_cookiejar(NODELOC_COOKIE)
    session.cookies.update(jar)

    csrf = extract_csrf(session.cookies)
    if not csrf:
        log("❌ Cookie 中未找到 csrf_token，无法接口签到")
        return

    session.headers["X-CSRF-Token"] = csrf
    log("CSRF Token 已设置")

    resp = session.post(CHECKIN_API, timeout=10)
    log(f"接口返回状态码: {resp.status_code}")
    log(f"接口返回内容: {resp.text}")


async def main():
    log("====== NodeLoc 自动签到开始 ======")

    ui_success = False

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

        # 2️⃣ 登录
        log("等待账号输入框 #login-account-name")
        await page.wait_for_selector("#login-account-name", timeout=30000)
        log("输入账号")
        await page.fill("#login-account-name", NODELOC_USERNAME)

        log("等待密码输入框 #login-account-password")
        await page.wait_for_selector("#login-account-password", timeout=30000)
        log("输入密码")
        await page.fill("#login-account-password", NODELOC_PASSWORD)

        log("点击登录按钮 #login-button")
        await page.click("#login-button")

        log("等待跳转回首页")
        await page.wait_for_url(BASE + "/", timeout=30000)
        log("登录成功，已进入首页")

        # 3️⃣ UI 尝试签到
        log("查找签到按钮（图片按钮本体）")
        btn = await page.wait_for_selector(
            "li.header-dropdown-toggle.checkin-icon > button.checkin-button",
            timeout=30000
        )

        title_before = await btn.get_attribute("title")
        log(f"签到前状态: {title_before}")

        log("点击签到按钮（UI）")
        await btn.click(delay=120)
        await page.wait_for_timeout(2000)

        title_after = await btn.get_attribute("title")
        log(f"签到后状态: {title_after}")

        if title_before != title_after:
            log("✅ UI 签到成功")
            ui_success = True
        else:
            log("⚠️ UI 签到未生效")

        await browser.close()

    # 4️⃣ UI 不成功 → 接口兜底
    if not ui_success:
        log("➡️ UI 未生效，切换接口签到")
        api_checkin()

    log("====== NodeLoc 自动签到结束 ======")


if __name__ == "__main__":
    asyncio.run(main())
