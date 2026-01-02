import asyncio
import time
import os
import json
import random
import requests
from playwright.async_api import async_playwright, TimeoutError

# 配置
LOGIN_URL = "https://www.nodeloc.com/login"
HOME_URL = "https://www.nodeloc.com/"
CSRF_URL = "https://www.nodeloc.com/session/csrf.json"

NODELOC_USERNAME = os.getenv("NODELOC_USERNAME")
NODELOC_PASSWORD = os.getenv("NODELOC_PASSWORD")
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

def generate_nonce():
    return ''.join(random.choices('0123456789abcdefghijklmnopqrstuvwxyz', k=26))

async def run_checkin():
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        try:
            # 1. 登录
            log("正在打开登录页面...")
            await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)
            
            log(f"正在输入账号: {NODELOC_USERNAME}")
            await page.fill("#login-account-name", NODELOC_USERNAME)
            await page.fill("#login-account-password", NODELOC_PASSWORD)
            await page.click("#login-button")
            
            # 等待登录成功
            log("等待登录响应...")
            await page.wait_for_function(
                "() => (typeof Discourse !== 'undefined' && Discourse.currentUser) || document.querySelector('.checkin-button')",
                timeout=30000
            )
            log("登录成功！")
            await page.wait_for_timeout(2000)
            
            # 2. 获取 CSRF Token
            log("获取 CSRF Token...")
            csrf_token = ""
            try:
                # 尝试从 API 获取
                res = await page.request.get(CSRF_URL)
                csrf_data = await res.json()
                csrf_token = csrf_data.get("csrf", "")
            except:
                # 备选：从页面 meta 获取
                csrf_token = await page.evaluate('document.querySelector("meta[name=\'csrf-token\']")?.content')
            
            if not csrf_token:
                raise RuntimeError("无法获取 CSRF Token")
            
            # 3. 获取用户信息
            user_info = await page.evaluate('''() => {
                if (typeof Discourse !== 'undefined' && Discourse.currentUser) {
                    return { id: Discourse.currentUser.id, username: Discourse.currentUser.username };
                }
                return null;
            }''')
            
            if not user_info:
                # 备选：从 body 属性获取
                uid = await page.evaluate('document.querySelector("body").getAttribute("data-current-user-id")')
                if uid:
                    user_info = {"id": uid, "username": "User"}
                else:
                    raise RuntimeError("无法获取用户信息")

            # 4. 检查是否已签到
            today = time.strftime("%Y-%m-%d")
            checkin_key = f"checkin-{user_info['id']}-{today}"
            is_checked = await page.evaluate(f'localStorage.getItem("{checkin_key}")')
            if is_checked:
                log("🟡 今日已签到 (localStorage 记录)")
                send_tg(f"🟡 NodeLoc 今日已签到\n{now}")
                return True

            # 5. 发送签到请求
            log("发送签到请求...")
            nonce = generate_nonce()
            timestamp = int(time.time() * 1000)
            
            result = await page.evaluate(f'''async () => {{
                const response = await fetch('/checkin', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                        'X-Discourse-Checkin': 'true',
                        'X-Checkin-Nonce': '{nonce}',
                        'X-CSRF-Token': '{csrf_token}',
                        'X-Requested-With': 'XMLHttpRequest'
                    }},
                    body: new URLSearchParams({{ 'nonce': '{nonce}', 'timestamp': '{timestamp}' }})
                }});
                return await response.json();
            }}''')
            
            log(f"签到结果: {json.dumps(result, ensure_ascii=False)}")
            
            if result.get('success'):
                log(f"✅ 签到成功！获得 {result.get('points', 0)} 积分")
                await page.evaluate(f'localStorage.setItem("{checkin_key}", "true")')
                send_tg(f"✅ NodeLoc 签到成功\n{now}\n获得 {result.get('points', 0)} 积分")
                return True
            elif 'already' in result.get('message', '').lower() or '已签' in result.get('message', ''):
                log("🟡 今日已签到 (服务器返回)")
                await page.evaluate(f'localStorage.setItem("{checkin_key}", "true")')
                send_tg(f"🟡 NodeLoc 今日已签到\n{now}")
                return True
            else:
                raise RuntimeError(result.get('message', '未知错误'))

        finally:
            await browser.close()

async def main():
    max_retries = 3
    for i in range(max_retries):
        try:
            if await run_checkin():
                return 0
        except Exception as e:
            log(f"第 {i+1} 次尝试失败: {e}")
            if i < max_retries - 1:
                wait_time = (i + 1) * 10
                log(f"等待 {wait_time} 秒后重试...")
                await asyncio.sleep(wait_time)
            else:
                send_tg(f"❌ NodeLoc 签到最终失败\n{time.strftime('%Y-%m-%d %H:%M:%S')}\n{e}")
                return 1

if __name__ == "__main__":
    exit(asyncio.run(main()))
