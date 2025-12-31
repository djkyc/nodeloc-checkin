import asyncio
import os
import time
import requests
from playwright.async_api import async_playwright

BASE = "https://www.nodeloc.com"

# ===== 配置 =====
NODELOC_COOKIE = os.getenv("NODELOC_COOKIE", "")
LOGIN_EMAIL = os.getenv("NODELOC_LOGIN_EMAIL", "")

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_USER_ID = os.getenv("TG_USER_ID")


# ===== 日志 =====
def log(msg: str):
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"[{now}] {msg}", flush=True)


# ===== Telegram =====
def send_tg(msg: str):
    if not TG_BOT_TOKEN or not TG_USER_ID:
        return
    requests.post(
        f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
        json={
            "chat_id": TG_USER_ID,
            "text": msg,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        },
        timeout=10
    )


def mask_email(email: str) -> str:
    if "@" not in email:
        return "***"
    u, d = email.split("@", 1)
    return u[:2] + "***@" + d


def beijing_time():
    return time.strftime(
        "%Y-%m-%d %H:%M:%S",
        time.gmtime(time.time() + 8 * 3600)
    )


def parse_cookies(cookie_str: str):
    cookies = []
    for part in cookie_str.split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            cookies.append({
                "name": k,
                "value": v,
                "domain": "www.nodeloc.com",
                "path": "/"
            })
    return cookies


# ===== 主流程 =====
async def main():
    account = mask_email(LOGIN_EMAIL)
    now = beijing_time()

    log("====== NodeLoc 签到任务开始 ======")
    log(f"账号: {account}")

    # 记录接口返回文本
    checkin_message = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox"]
        )

        context = await browser.new_context(
            viewport={"width": 1280, "height": 800}
        )

        # 注入 Cookie
        await context.add_cookies(parse_cookies(NODELOC_COOKIE))
        page = await context.new_page()

        # 监听签到接口
        async def on_response(response):
            nonlocal checkin_message
            if "/checkin" not in response.url:
                return
            try:
                data = await response.json()
                msg = (
                    data.get("message")
                    or data.get("msg")
                    or data.get("notice")
                    or ""
                )
                checkin_message = str(msg)
                log(f"签到接口返回: {checkin_message}")
            except Exception:
                checkin_message = "接口返回异常"

        page.on("response", on_response)

        # 打开首页
        log("访问 NodeLoc 首页")
        await page.goto(BASE, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # ===== 核心：只做一件事 → 点签到图标 =====
        log("激活签到下拉菜单")
        toggle = await page.wait_for_selector(
            "li.header-dropdown-toggle.checkin-icon",
            timeout=8000
        )
        box = await toggle.bounding_box()
        await page.mouse.move(
            box["x"] + box["width"] / 2,
            box["y"] + box["height"] / 2
        )
        await page.wait_for_timeout(300)

        log("点击签到 SVG 图标")
        icon = await page.wait_for_selector(
            "li.header-dropdown-toggle.checkin-icon svg.d-icon-calendar-check",
            timeout=5000
        )
        ibox = await icon.bounding_box()
        await page.mouse.move(
            ibox["x"] + ibox["width"] / 2,
            ibox["y"] + ibox["height"] / 2
        )
        await page.mouse.down()
        await page.wait_for_timeout(50)
        await page.mouse.up()

        log("等待签到结果")
        await page.wait_for_timeout(4000)

        await browser.close()

    # ===== 最终业务判断（只按你给的三条规则）=====
    msg = checkin_message or ""

    if any(k in msg for k in ["签到成功", "获得", "能量"]):
        send_tg(
            f"✅ <b>NodeLoc 签到成功</b>\n\n"
            f"账号：{account}\n时间：{now}\n\n"
            f"{msg}"
        )
        return

    if any(k in msg for k in [
        "今日已签到",
        "已签到",
        "系统繁忙",
        "无效的请求",
        "尝试次数过多"
    ]):
        send_tg(
            f"🟢 <b>NodeLoc 今日已签到</b>\n\n"
            f"账号：{account}\n时间：{now}"
        )
        return

    # 理论上不会走到这里
    send_tg(
        f"⚠️ <b>NodeLoc 签到状态未知</b>\n\n"
        f"账号：{account}\n时间：{now}\n\n"
        f"{msg}"
    )


if __name__ == "__main__":
    asyncio.run(main())
