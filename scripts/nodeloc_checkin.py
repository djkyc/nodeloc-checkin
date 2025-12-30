import asyncio
import os
import time
import requests
from playwright.async_api import async_playwright

BASE = "https://www.nodeloc.com"

# ===== Secrets =====
NODELOC_COOKIE = os.getenv("NODELOC_COOKIE", "")
NODELOC_USERNAME = os.getenv("NODELOC_USERNAME", "")
NODELOC_PASSWORD = os.getenv("NODELOC_PASSWORD", "")
LOGIN_EMAIL = os.getenv("NODELOC_LOGIN_EMAIL", "")

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_USER_ID = os.getenv("TG_USER_ID")


# ===== Logging =====
def log(msg: str):
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"[{now}] {msg}", flush=True)


# ===== Utils =====
def send_tg(msg: str):
    if not TG_BOT_TOKEN or not TG_USER_ID:
        log("TG 未配置，跳过发送通知")
        return

    log("发送 TG 通知")
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    requests.post(
        url,
        json={
            "chat_id": TG_USER_ID,
            "text": msg,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        },
        timeout=15
    )


def mask_email(email: str) -> str:
    if "@" not in email:
        return "***"
    u, d = email.split("@", 1)
    if len(u) <= 2:
        return u[0] + "*@" + d
    return u[:2] + "*" * (len(u) - 2) + "@" + d


def beijing_time():
    t = time.gmtime(time.time() + 8 * 3600)
    return time.strftime("%Y-%m-%d %H:%M:%S", t)


def parse_cookies(cookie_str: str):
    cookies = []
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            cookies.append({
                "name": k,
                "value": v,
                "domain": "www.nodeloc.com",
                "path": "/"
            })
    return cookies


# ===== 自动登录并获取新 Cookie =====
async def login_and_get_new_cookie(context, page):
    if not NODELOC_USERNAME or not NODELOC_PASSWORD:
        log("未配置账号密码，无法自动登录")
        return None

    log("Cookie 失效，尝试账号密码自动登录")

    await page.goto(f"{BASE}/login", wait_until="domcontentloaded")
    await page.wait_for_timeout(1500)

    await page.fill("input[name='email']", NODELOC_USERNAME)
    await page.fill("input[name='password']", NODELOC_PASSWORD)
    await page.click("button[type='submit']")

    await page.wait_for_timeout(5000)

    if "login" in page.url:
        log("仍停留在登录页，登录失败（可能验证码/风控）")
        return None

    cookies = await context.cookies(BASE)
    if not cookies:
        log("登录成功但未读取到 Cookie")
        return None

    cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
    log("成功获取新的 Cookie")
    return cookie_str


# ===== 主流程 =====
async def main():
    account = mask_email(LOGIN_EMAIL) if LOGIN_EMAIL else "（邮箱未配置）"
    now = beijing_time()

    log("====== NodeLoc 签到任务开始 ======")
    log(f"账号：{account}")

    # 用于记录接口监听结果
    checkin_result = {
        "hit": False,
        "responses": []
    }

    async with async_playwright() as p:
        log("启动 Chromium")
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox"]
        )

        context = await browser.new_context(
            viewport={"width": 1280, "height": 800}
        )

        if NODELOC_COOKIE:
            log("注入已有 Cookie")
            await context.add_cookies(parse_cookies(NODELOC_COOKIE))
        else:
            log("未配置 NODELOC_COOKIE")

        page = await context.new_page()

        # ===== 接口监听（核心）=====
        async def on_response(response):
            url = response.url
            if any(k in url.lower() for k in ["check", "sign", "attendance"]):
                try:
                    text = await response.text()
                except:
                    text = "(no body)"
                checkin_result["hit"] = True
                checkin_result["responses"].append(f"{url} -> {text}")
                log(f"捕获到签到相关接口：{url}")

        page.on("response", on_response)

        log("访问 NodeLoc 首页")
        await page.goto(BASE, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        log("查找签到按钮")
        btn = await page.query_selector("button.checkin-button")

        # ===== Cookie 失效 =====
        if not btn:
            log("未找到签到按钮，判定 Cookie 失效")
            new_cookie = await login_and_get_new_cookie(context, page)
            await browser.close()

            if new_cookie:
                send_tg(
                    "🚨 <b>NodeLoc Cookie 已失效，已自动获取新 Cookie</b>\n\n"
                    f"📧 账号：<a href=\"mailto:{account}\">{account}</a>\n"
                    f"🕒 时间：{now}\n\n"
                    "📎 <b>新的 Cookie（请手动更新 GitHub Secrets）</b>\n"
                    f"<code>{new_cookie}</code>"
                )
            else:
                send_tg(
                    "❌ <b>NodeLoc Cookie 失效，自动登录失败</b>\n\n"
                    f"📧 账号：<a href=\"mailto:{account}\">{account}</a>\n"
                    f"🕒 时间：{now}\n\n"
                    "⚠️ 可能原因：验证码 / 风控"
                )
            return

        # ===== 点击签到 =====
        log("滚动并点击签到按钮")
        await page.evaluate(
            """
            () => {
                const b = document.querySelector("button.checkin-button");
                if (b) {
                    b.scrollIntoView({behavior: "instant", block: "center"});
                    b.click();
                }
            }
            """
        )

        log("等待签到接口响应")
        await page.wait_for_timeout(3000)

        await browser.close()
        log("浏览器已关闭")

        # ===== 基于接口的最终判定 =====
        if checkin_result["hit"]:
            log("判定：已捕获签到接口请求")
            send_tg(
                "✅ <b>NodeLoc 签到请求已触发</b>\n\n"
                f"📧 账号：<a href=\"mailto:{account}\">{account}</a>\n"
                f"🕒 时间：{now}\n\n"
                "📡 <b>接口响应摘要</b>\n"
                f"<code>{checkin_result['responses'][0][:1000]}</code>"
            )
            return

        log("未捕获到任何签到接口，请求可能被拦截")
        send_tg(
            "❌ <b>NodeLoc 签到未触发（未检测到接口请求）</b>\n\n"
            f"📧 账号：<a href=\"mailto:{account}\">{account}</a>\n"
            f"🕒 时间：{now}\n\n"
            "⚠️ 按钮已点击，但未产生网络请求"
        )


if __name__ == "__main__":
    asyncio.run(main())
