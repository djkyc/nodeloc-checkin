import asyncio
import time
import os
import requests
from playwright.async_api import async_playwright, TimeoutError

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


def extract_csrf(cookiejar):
    for k in cookiejar:
        if k.lower() == "csrf_token":
            return cookiejar[k]
    return None


async def login_and_get_cookies():
    log("启动 headless 浏览器（仅用于登录）")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )

        context = await browser.new_context()
        page = await context.new_page()

        log("打开登录页面（domcontentloaded）")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)

        # ⚠️ Discourse 登录弹层是异步渲染的，给它时间
        await page.wait_for_timeout(2000)

        log("等待账号输入框 #login-account-name")
        try:
            await page.wait_for_selector("#login-account-name", timeout=20000)
        except TimeoutError:
            log("❌ 未找到账号输入框（可能被 Cloudflare / 登录方式变化）")
            await browser.close()
            return None

        log("输入账号")
        await page.fill("#login-account-name", NODELOC_USERNAME)

        log("等待密码输入框")
        await page.wait_for_selector("#login-account-password", timeout=10000)

        log("输入密码")
        await page.fill("#login-account-password", NODELOC_PASSWORD)

        log("点击登录按钮")
        await page.click("button.login-button")

        log("等待跳转首页")
        try:
            await page.wait_for_url(BASE + "/", timeout=30000)
            log("登录成功")
        except TimeoutError:
            log("❌ 登录失败，未跳转首页")
            await browser.close()
            return None

        cookies = await context.cookies()
        log(f"获取到 Cookie 数量: {len(cookies)}")

        await browser.close()
        return cookies


def do_checkin(cookies):
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Referer": BASE,
        "Origin": BASE
    })

    jar = cookies_to_jar(cookies)
    session.cookies.update(jar)

    csrf = extract_csrf(session.cookies)
    if not csrf:
        log("❌ 未找到 csrf_token")
        return

    session.headers["X-CSRF-Token"] = csrf
    log("CSRF Token 已设置")

    log("发送签到请求")
    resp = session.post(CHECKIN_API, timeout=10)

    log(f"HTTP 状态码: {resp.status_code}")

    if resp.status_code != 200:
        log(resp.text)
        return

    try:
        data = resp.json()
    except Exception:
        log("❌ 返回非 JSON")
        log(resp.text)
        return

    msg = (
        data.get("message")
        or data.get("msg")
        or data.get("notice")
        or str(data)
    )

    log(f"接口返回: {msg}")


async def main():
    log("====== NodeLoc 自动签到开始（账号密码登录） ======")

    if not NODELOC_USERNAME or not NODELOC_PASSWORD:
        log("❌ 未设置账号或密码")
        return

    cookies = await login_and_get_cookies()
    if not cookies:
        return

    do_checkin(cookies)

    log("====== NodeLoc 自动签到结束 ======")


if __name__ == "__main__":
    asyncio.run(main())
