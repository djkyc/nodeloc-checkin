import asyncio
import os
import time
import requests
from playwright.async_api import async_playwright

BASE = "https://www.nodeloc.com"

# ===== Secrets =====
NODELOC_COOKIE = os.getenv("NODELOC_COOKIE", "")
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
        log("TG 未配置，跳过通知")
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


# ===== 主流程 =====
async def main():
    account = mask_email(LOGIN_EMAIL) if LOGIN_EMAIL else "（邮箱未配置）"
    now = beijing_time()

    log("====== NodeLoc 签到任务开始 ======")
    log(f"账号：{account}")

    checkin = {
        "hit": False,
        "status": None,
        "message": ""
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

        # ===== 接口监听（权威判定）=====
        async def on_response(response):
            if "/checkin" not in response.url:
                return

            log(f"捕获到签到接口：{response.url}")
            checkin["hit"] = True

            try:
                data = await response.json()
            except Exception:
                checkin["status"] = "failed"
                checkin["message"] = "接口返回非 JSON"
                return

            msg = (
                data.get("message")
                or data.get("msg")
                or data.get("notice")
                or ""
            )
            msg = str(msg)
            checkin["message"] = msg

            log(f"签到接口 message：{msg}")

            if any(k in msg for k in [
                "签到成功", "成功", "获得", "能量"
            ]):
                checkin["status"] = "success"
            elif any(k in msg for k in [
                "已签到", "今天已经签到", "无效", "系统繁忙", "尝试次数过多"
            ]):
                checkin["status"] = "already"
            else:
                checkin["status"] = "failed"

        page.on("response", on_response)

        # ===== 打开首页 =====
        log("访问 NodeLoc 首页")
        await page.goto(BASE, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # ===== 查找签到按钮 =====
        log("查找签到按钮")
        btn = await page.wait_for_selector(
            "li.header-dropdown-toggle.checkin-icon button.checkin-button",
            timeout=8000
        )

        if not btn:
            log("未找到签到按钮")
            await browser.close()
            send_tg(
                "❌ <b>NodeLoc 未找到签到按钮</b>\n\n"
                f"📧 账号：<a href=\"mailto:{account}\">{account}</a>\n"
                f"🕒 时间：{now}"
            )
            return

        # ===== 真实鼠标点击（核心）=====
        log("准备使用真实鼠标事件点击签到按钮")

        await btn.scroll_into_view_if_needed()
        box = await btn.bounding_box()
        if not box:
            raise RuntimeError("无法获取签到按钮位置")

        x = box["x"] + box["width"] / 2
        y = box["y"] + box["height"] / 2

        await page.mouse.move(x, y)
        await page.wait_for_timeout(300)
        await page.mouse.down()
        await page.wait_for_timeout(50)
        await page.mouse.up()

        log("已发送真实鼠标点击事件")

        # ===== 等待接口 =====
        log("等待签到接口响应")
        await page.wait_for_timeout(4000)

        await browser.close()
        log("浏览器已关闭")

        # ===== 最终判定 =====
        if not checkin["hit"]:
            send_tg(
                "❌ <b>NodeLoc 签到未触发</b>\n\n"
                f"📧 账号：<a href=\"mailto:{account}\">{account}</a>\n"
                f"🕒 时间：{now}\n\n"
                "⚠️ 未捕获到 /checkin 接口"
            )
            return

        if checkin["status"] == "success":
            send_tg(
                "✅ <b>NodeLoc 今日签到成功</b>\n\n"
                f"📧 账号：<a href=\"mailto:{account}\">{account}</a>\n"
                f"🕒 时间：{now}\n\n"
                f"🎁 {checkin['message']}"
            )
            return

        if checkin["status"] == "already":
            send_tg(
                "🟢 <b>NodeLoc 今日已签到</b>\n\n"
                f"📧 账号：<a href=\"mailto:{account}\">{account}</a>\n"
                f"🕒 时间：{now}"
            )
            return

        send_tg(
            "⚠️ <b>NodeLoc 签到失败</b>\n\n"
            f"📧 账号：<a href=\"mailto:{account}\">{account}</a>\n"
            f"🕒 时间：{now}\n\n"
            f"<code>{checkin['message']}</code>"
        )


if __name__ == "__main__":
    asyncio.run(main())
