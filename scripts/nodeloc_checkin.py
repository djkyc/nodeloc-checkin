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

    # 用于保存接口判定结果
    checkin = {
        "hit": False,      # 是否捕获到 /checkin
        "status": None,   # success / already / failed
        "message": ""     # 接口 message（权威）
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

        # ===== 只监听真正的签到接口 =====
        async def on_response(response):
            if "/checkin" not in response.url:
                return

            log(f"捕获到签到接口：{response.url}")
            checkin["hit"] = True

            try:
                data = await response.json()
            except Exception:
                log("签到接口返回非 JSON")
                checkin["status"] = "failed"
                return

            # NodeLoc / Discourse 插件：message 才是唯一权威
            msg = (
                data.get("message")
                or data.get("msg")
                or data.get("notice")
                or ""
            )
            msg = str(msg)
            checkin["message"] = msg

            log(f"签到接口 message：{msg}")

            # ===== 严格判断顺序（非常重要）=====
            if "已签到" in msg or "今天已经签到" in msg:
                checkin["status"] = "already"
            elif "签到成功" in msg or "成功" in msg:
                checkin["status"] = "success"
            else:
                checkin["status"] = "failed"

        page.on("response", on_response)

        log("访问 NodeLoc 首页")
        await page.goto(BASE, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        log("查找签到按钮")
        btn = await page.query_selector("button.checkin-button")

        if not btn:
            log("未找到签到按钮，Cookie 可能失效")
            await browser.close()
            send_tg(
                "❌ <b>NodeLoc Cookie 可能已失效</b>\n\n"
                f"📧 账号：<a href=\"mailto:{account}\">{account}</a>\n"
                f"🕒 时间：{now}\n\n"
                "👉 请重新登录 NodeLoc 并更新 Cookie"
            )
            return

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

        # ===== 最终判定（只基于接口 message）=====
        if not checkin["hit"]:
            send_tg(
                "❌ <b>NodeLoc 签到未触发</b>\n\n"
                f"📧 账号：<a href=\"mailto:{account}\">{account}</a>\n"
                f"🕒 时间：{now}\n\n"
                "⚠️ 未捕获到 /checkin 接口"
            )
            return

        if checkin["status"] == "already":
            send_tg(
                "🟢 <b>NodeLoc 今日已签到</b>\n\n"
                f"📧 账号：<a href=\"mailto:{account}\">{account}</a>\n"
                f"🕒 时间：{now}"
            )
            return

        if checkin["status"] == "success":
            send_tg(
                "✅ <b>NodeLoc 今日签到成功</b>\n\n"
                f"📧 账号：<a href=\"mailto:{account}\">{account}</a>\n"
                f"🕒 时间：{now}"
            )
            return

        # 兜底：接口返回但语义未知
        send_tg(
            "⚠️ <b>NodeLoc 签到状态未知</b>\n\n"
            f"📧 账号：<a href=\"mailto:{account}\">{account}</a>\n"
            f"🕒 时间：{now}\n\n"
            f"<code>{checkin['message']}</code>"
        )


if __name__ == "__main__":
    asyncio.run(main())
