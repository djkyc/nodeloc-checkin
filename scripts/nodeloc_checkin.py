import asyncio
import time
import os
import json
import random
import requests
from playwright.async_api import async_playwright

LOGIN_URL = "https://www.nodeloc.com/login"
HOME_URL = "https://www.nodeloc.com/"
CSRF_URL = "https://www.nodeloc.com/session/csrf.json"
CHECKIN_URL = "https://www.nodeloc.com/checkin"

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


def generate_nonce():
    """生成签到所需的 nonce"""
    part1 = ''.join(random.choices('0123456789abcdefghijklmnopqrstuvwxyz', k=13))
    part2 = ''.join(random.choices('0123456789abcdefghijklmnopqrstuvwxyz', k=13))
    return part1 + part2


async def main():
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    browser = None

    try:
        log("====== NodeLoc 自动签到启动 ======")

        async with async_playwright() as p:
            # 启动浏览器
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            # 步骤 1: 打开登录页
            log("打开登录页面 /login")
            await page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(2000)

            # 步骤 2: 等待登录表单
            log("等待登录表单加载")
            await page.wait_for_selector("#login-account-name", timeout=30000)
            await page.wait_for_selector("#login-account-password", timeout=30000)
            await page.wait_for_selector("#login-button", timeout=30000)

            # 步骤 3: 输入用户名和密码
            log(f"输入用户名: {NODELOC_USERNAME}")
            await page.fill("#login-account-name", NODELOC_USERNAME)
            await page.wait_for_timeout(500)

            log("输入密码")
            await page.fill("#login-account-password", NODELOC_PASSWORD)
            await page.wait_for_timeout(500)

            # 步骤 4: 点击登录
            log("点击登录按钮 #login-button")
            await page.click("#login-button")
            
            # 步骤 5: 等待登录完成
            log("等待登录成功...")
            try:
                # 等待页面跳转或签到按钮出现
                await page.wait_for_function(
                    """() => {
                        return document.querySelector('.checkin-button') !== null ||
                               window.location.href !== 'https://www.nodeloc.com/login';
                    }""",
                    timeout=30000
                )
                log("登录成功，页面已跳转")
            except Exception as e:
                log(f"等待登录超时，尝试手动导航: {e}")
                await page.goto(HOME_URL, wait_until="networkidle", timeout=60000)
            
            # 等待页面完全加载
            await page.wait_for_load_state("networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

            # 步骤 6: 获取 CSRF Token
            log("获取 CSRF Token...")
            csrf_response = await page.goto(CSRF_URL, wait_until="networkidle")
            csrf_text = await csrf_response.text()
            csrf_data = json.loads(csrf_text)
            csrf_token = csrf_data.get("csrf", "")
            log(f"CSRF Token: {csrf_token[:20]}...")

            # 步骤 7: 获取当前用户信息
            log("获取当前用户信息...")
            user_info = await page.evaluate('''() => {
                if (typeof Discourse !== 'undefined' && Discourse.currentUser) {
                    return {
                        id: Discourse.currentUser.id,
                        username: Discourse.currentUser.username
                    };
                }
                return null;
            }''')
            
            if not user_info:
                raise RuntimeError("无法获取当前用户信息，登录可能失败")
            
            log(f"当前用户: {user_info['username']} (ID: {user_info['id']})")

            # 步骤 8: 检查是否已签到
            log("检查今日签到状态...")
            today = time.strftime("%Y-%m-%d")
            checkin_key = f"checkin-{user_info['id']}-{today}"
            
            already_checked_in = await page.evaluate(f'''() => {{
                return localStorage.getItem("{checkin_key}") !== null;
            }}''')
            
            if already_checked_in:
                log("🟡 今日已签到")
                await context.close()
                await browser.close()
                send_tg(f"🟡 NodeLoc 今日已签到\n{now}")
                return 0

            # 步骤 9: 执行签到
            log("准备签到...")
            nonce = generate_nonce()
            timestamp = int(time.time() * 1000)
            
            log(f"Nonce: {nonce}")
            log(f"Timestamp: {timestamp}")

            # 获取所有 cookies
            cookies = await context.cookies()
            cookie_dict = {c['name']: c['value'] for c in cookies}
            
            # 构造签到请求
            log("发送签到请求到 /checkin")
            checkin_response = await page.evaluate(f'''async () => {{
                try {{
                    const response = await fetch('/checkin', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                            'X-Discourse-Checkin': 'true',
                            'X-Checkin-Nonce': '{nonce}',
                            'X-CSRF-Token': '{csrf_token}',
                            'X-Requested-With': 'XMLHttpRequest'
                        }},
                        body: new URLSearchParams({{
                            'nonce': '{nonce}',
                            'timestamp': '{timestamp}'
                        }})
                    }});
                    
                    const text = await response.text();
                    return {{
                        status: response.status,
                        ok: response.ok,
                        body: text
                    }};
                }} catch (error) {{
                    return {{
                        error: error.message
                    }};
                }}
            }}''')

            log(f"签到响应: {json.dumps(checkin_response, indent=2, ensure_ascii=False)}")

            # 步骤 10: 处理签到结果
            if checkin_response.get('error'):
                raise RuntimeError(f"签到请求失败: {checkin_response['error']}")
            
            if checkin_response.get('ok'):
                try:
                    result = json.loads(checkin_response['body'])
                    if result.get('success'):
                        points = result.get('points', 0)
                        log(f"✅ 签到成功！获得 {points} 积分")
                        
                        # 更新 localStorage
                        await page.evaluate(f'''() => {{
                            localStorage.setItem("{checkin_key}", "true");
                        }}''')
                        
                        await context.close()
                        await browser.close()
                        send_tg(f"✅ NodeLoc 签到成功\n{now}\n获得 {points} 积分")
                        return 0
                    else:
                        message = result.get('message', '未知错误')
                        log(f"⚠️ 签到失败: {message}")
                        
                        # 检查是否是已签到的提示
                        if 'already' in message.lower() or '已签' in message:
                            await page.evaluate(f'''() => {{
                                localStorage.setItem("{checkin_key}", "true");
                            }}''')
                            await context.close()
                            await browser.close()
                            send_tg(f"🟡 NodeLoc 今日已签到\n{now}")
                            return 0
                        
                        raise RuntimeError(message)
                except json.JSONDecodeError:
                    log(f"⚠️ 响应不是 JSON 格式: {checkin_response['body']}")
                    raise RuntimeError("签到响应格式错误")
            else:
                status = checkin_response.get('status', 'unknown')
                body = checkin_response.get('body', '')
                raise RuntimeError(f"签到请求失败 (HTTP {status}): {body}")

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
