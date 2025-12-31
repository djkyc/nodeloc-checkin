import asyncio
import time
import os
import requests
from playwright.async_api import async_playwright
from http.cookies import SimpleCookie

BASE = "https://www.nodeloc.com"
LOGIN_URL = "https://www.nodeloc.com/login"
CHECKIN_API = f"{BASE}/checkin"

NODELOC_USERNAME = os.getenv("NODELOC_USERNAME")
NODELOC_PASSWORD = os.getenv("NODELOC_PASSWORD")


def log(msg):
    print(time.strftime("[%Y-%m-%d %H:%M:%S]"), msg, flush=True)


def cookies_to_jar(cookies):
    jar = requests.cookies.RequestsCookieJar()
    for c in cookies:
        jar.set(
            c["name"],
            c["value"],
            domain=c.get("domain", "www.nodeloc.com"),
            path=c.get("path", "/")
        )
    return jar


def extract_csrf(jar):
    for k in jar:
        if k.lower() == "csrf_token":
            return jar[k]
    return None


async def main():
    log("====== NodeLoc 自动签到开始（最终稳定方案） ======")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context()
        page = await context.new_page()

        # 登录
        log("打开登录页面")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await page.wait_for_selector("#login-account-name")

        log("输入账号")
        await page.fill("#login-account-name", NODELOC_USERNAME)

        log("输入密码")
        await page.fill("#login-account-password", NODELOC_PASSWORD)

        log("提交登录")
        await page.click("#login-button")

        log("等待进入首页")
        await page.wait_for_url(BASE + "/", timeout=30000)
        log("登录成功")

        # 取 cookie
        cookies = await context.cookies()
        log(f"获取 Cookie 数量: {len(cookies)}")

        await browser.close()

    # ===== 后端签到 =====
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Referer": BASE,
        "Origin": BASE,
        "Accept": "application/json"
    })

    jar = cookies_to_jar(cookies)
    session.cookies.update(jar)

    csrf = extract_csrf(session.cookies)
    if not csrf:
        log("❌ 未找到 csrf_token，无法签到")
        return

    session.headers["X-CSRF-Token"] = csrf

    log("发送签到请求 /checkin")
    resp = session.post(CHECKIN_API, timeout=10)

    log(f"HTTP 状态码: {resp.status_code}")
    log(f"返回内容: {resp.text}")

    log("====== NodeLoc 自动签到结束 ======")


if __name__ == "__main__":
    asyncio.run(main())
