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
            
            # 等待登录成功跳转
            log("等待登录响应...")
            try:
                # 等待 URL 变化或特定元素出现
                await page.wait_for_function(
                    "() => window.location.href === 'https://www.nodeloc.com/' || document.querySelector('.checkin-button') || document.querySelector('#current-user')",
                    timeout=30000
                )
            except Exception:
                log("登录跳转等待超时，尝试直接访问首页")
                await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
            
            log("登录成功，正在加载首页数据...")
            # 关键：多等一会儿，确保 Discourse 核心对象加载完成
            await page.wait_for_timeout(5000)
            
            # 2. 获取 CSRF Token
            log("获取 CSRF Token...")
            csrf_token = ""
            try:
                # 优先从 API 获取，这样最准确
                res = await page.request.get(CSRF_URL)
                csrf_data = await res.json()
                csrf_token = csrf_data.get("csrf", "")
            except Exception as e:
                log(f"API 获取 CSRF 失败: {e}，尝试从页面提取")
                csrf_token = await page.evaluate('document.querySelector("meta[name=\'csrf-token\']")?.content')
            
            if not csrf_token:
                raise RuntimeError("无法获取 CSRF Token")
            
            # 3. 获取用户信息 (增强版)
            log("正在提取用户信息...")
            user_info = await page.evaluate('''() => {
                // 方式 1: Discourse 全局对象
                if (typeof Discourse !== 'undefined' && Discourse.currentUser) {
                    return { id: Discourse.currentUser.id, username: Discourse.currentUser.username, source: 'discourse' };
                }
                
                // 方式 2: 从 body 属性获取 (Discourse 常用)
                const body = document.querySelector('body');
                const uid = body?.getAttribute('data-current-user-id');
                if (uid) {
                    return { id: uid, username: 'User', source: 'body-attr' };
                }
                
                // 方式 3: 从页面 JSON 数据获取
                const dataElement = document.querySelector('#data-discourse-setup');
                if (dataElement) {
                    try {
                        const data = JSON.parse(dataElement.getAttribute('data-preloaded'));
                        const currentUser = JSON.parse(data['current_user']);
                        if (currentUser) {
                            return { id: currentUser.id, username: currentUser.username, source: 'preloaded-data' };
                        }
                    } catch (e) {}
                }
                
                return null;
            }''')
            
            if not user_info:
                # 方式 4: 最后的挣扎，尝试从 API 获取当前用户信息
                log("尝试通过 API 获取用户信息...")
                try:
                    res = await page.request.get("https://www.nodeloc.com/session/current.json")
                    current_data = await res.json()
                    if current_data.get('current_user'):
                        user_info = {
                            'id': current_data['current_user']['id'],
                            'username': current_data['current_user']['username'],
                            'source': 'api'
                        }
                except:
                    pass

            if not user_info:
                # 记录页面内容以便调试
                content = await page.content()
                log(f"页面内容片段: {content[:500]}...")
                raise RuntimeError("无法获取用户信息，请确认是否登录成功")
            
            log(f"用户信息获取成功: {user_info['username']} (ID: {user_info['id']}, 来源: {user_info['source']})")

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
                        body: new URLSearchParams({{ 'nonce': '{nonce}', 'timestamp': '{timestamp}' }})
                    }});
                    return await response.json();
                } catch (e) {
                    return { success: false, message: e.message };
                }
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
                wait_time = (i + 1) * 15
                log(f"等待 {wait_time} 秒后重试...")
                await asyncio.sleep(wait_time)
            else:
                send_tg(f"❌ NodeLoc 签到最终失败\n{time.strftime('%Y-%m-%d %H:%M:%S')}\n{e}")
                return 1

if __name__ == "__main__":
    exit(asyncio.run(main()))
