import os
import time
import requests
from http.cookies import SimpleCookie

BASE = "https://www.nodeloc.com"
CHECKIN_API = f"{BASE}/checkin"

# 你已经在 GitHub Actions 里提供的 cookie
NODELOC_COOKIE = os.getenv("NODELOC_COOKIE")


def log(msg):
    print(time.strftime("[%Y-%m-%d %H:%M:%S]"), msg, flush=True)


def build_cookiejar(cookie_str: str):
    jar = requests.cookies.RequestsCookieJar()
    sc = SimpleCookie()
    sc.load(cookie_str)
    for k, v in sc.items():
        jar.set(
            k,
            v.value,
            domain="www.nodeloc.com",
            path="/"
        )
    return jar


def extract_csrf(jar):
    for cookie in jar:
        if cookie.name == "csrf_token":
            return cookie.value
    return None


def main():
    log("====== NodeLoc 自动签到开始（直接使用 cookie） ======")

    if not NODELOC_COOKIE:
        log("❌ 未提供 NODELOC_COOKIE")
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
    log(f"已加载 Cookie 数量: {len(session.cookies)}")

    csrf = extract_csrf(session.cookies)
    if not csrf:
        log("❌ Cookie 中未找到 csrf_token，请确认 cookie 是否完整")
        return

    log(f"已获取 csrf_token: {csrf[:6]}***")
    session.headers["X-CSRF-Token"] = csrf

    log("发送签到请求 /checkin")
    resp = session.post(CHECKIN_API, timeout=10)

    log(f"HTTP 状态码: {resp.status_code}")
    log(f"返回内容: {resp.text}")

    log("====== NodeLoc 自动签到结束 ======")


if __name__ == "__main__":
    main()
