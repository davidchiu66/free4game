import os
import time
import requests
from playwright.sync_api import sync_playwright

# 获取环境变量
SERVER_ID = os.environ.get("SERVER_ID", "未知服务器")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
USER_COOKIES = os.environ.get("USER_COOKIES")

CUSTOM_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"

def parse_raw_cookies(raw_cookie_str: str, domain: str = "my.rustix.me") -> list:
    cookies_list = []
    if not raw_cookie_str:
        return cookies_list
    pairs = raw_cookie_str.split(';')
    for pair in pairs:
        if '=' in pair:
            name, value = pair.strip().split('=', 1)
            cookies_list.append({"name": name, "value": value, "domain": domain, "path": "/"})
    return cookies_list

def mask_string(s: str) -> str:
    if not s or len(s) <= 4:
        return s
    return f"{s[:3]}****{s[-2:]}"

def send_tg_report(caption_html: str, photo_path: str = None):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("未配置 Telegram Token 或 Chat ID，跳过通知。")
        return
    try:
        if photo_path and os.path.exists(photo_path):
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
            data = {"chat_id": TG_CHAT_ID, "caption": caption_html, "parse_mode": "HTML"}
            with open(photo_path, "rb") as photo_file:
                files = {"photo": photo_file}
                response = requests.post(url, data=data, files=files)
        else:
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
            data = {"chat_id": TG_CHAT_ID, "text": caption_html, "parse_mode": "HTML"}
            response = requests.post(url, data=data)
        response.raise_for_status()
        print("✅ TG推送成功")
    except Exception as e:
        print(f"❌ TG推送失败: {e}")

def run_automation():
    screenshot_path = "rustix_result.png"
    masked_id = mask_string(SERVER_ID)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage", 
                "--disable-gpu",           
                "--no-sandbox"             
            ] 
        )
        context = browser.new_context(
            user_agent=CUSTOM_USER_AGENT,
            viewport={'width': 1280, 'height': 800}
        )

        if USER_COOKIES:
            formatted_cookies = parse_raw_cookies(USER_COOKIES)
            if formatted_cookies:
                context.add_cookies(formatted_cookies)

        page = context.new_page()

        try:
            target_url = f"https://my.rustix.me/server/{SERVER_ID}/console"
            print(f"准备打开服务器页面: {target_url}")

            try:
                page.goto(target_url, timeout=60000, wait_until="domcontentloaded")
                print("✅ 页面基础结构加载成功！")
            except Exception as goto_err:
                print(f"⚠️ 页面加载超时，尝试继续执行: {goto_err}")

            # 等待服务器状态文本出现，确保 WebSocket 和会话已完全就绪
            print("等待获取当前服务器状态...")
            page.locator("text=Offline").wait_for(state="visible", timeout=15000)
            
            # =========================================================
            # 【终极魔法】Pterodactyl 面板底层 API 直连注入
            # =========================================================
            print("▶️ UI点击被前端拦截，启动终极方案：直连底层 API 发送拉起指令...")
            
            # 编写要在浏览器内部执行的 JS 代码
            api_script = f"""
                async () => {{
                    // 1. 从浏览器原生环境中提取防伪造请求令牌 (XSRF-TOKEN)
                    function getXsrfToken() {{
                        const match = document.cookie.match(new RegExp('(^| )XSRF-TOKEN=([^;]+)'));
                        return match ? decodeURIComponent(match[2]) : '';
                    }}
                    
                    // 2. 直接调用 Pterodactyl 的官方电源管理 API
                    const response = await fetch('/api/client/servers/{SERVER_ID}/power', {{
                        method: 'POST',
                        headers: {{
                            'Accept': 'application/json',
                            'Content-Type': 'application/json',
                            'X-XSRF-TOKEN': getXsrfToken()
                        }},
                        body: JSON.stringify({{ signal: 'start' }})
                    }});
                    
                    // 3. 返回 HTTP 状态码
                    return response.status;
                }}
            """
            
            # 执行 JS 代码并获取返回的状态码
            status_code = page.evaluate(api_script)
            
            if status_code == 204 or status_code == 200:
                print(f"🎉 成功！底层 API 指令已下达，服务器正在拉起！(状态码: {status_code})")
            else:
                print(f"⚠️ API 指令已发送，但返回了异常状态码: {status_code}。请留意后续截图。")
            
            # =========================================================
            
            print("⏳ 正在等待 60 秒，让服务器执行启动过程...")
            time.sleep(60)
            
            print("🔄 正在刷新页面以获取最新状态...")
            try:
                page.reload(timeout=60000, wait_until="domcontentloaded")
            except:
                pass
            
            time.sleep(8)
            
            print("📸 正在截取最终状态全屏快照...")
            page.screenshot(path=screenshot_path, full_page=True)
            
            success_msg = (
                f"🎁 <b>Rustix.me 拉起报告</b>\n\n"
                f"✅ 成功: 1 ⏭ 跳过: 0 ❌ 失败: 0\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"✅ <b>Rustix 机器</b>\n"
                f"🖥 服务器: <code>{masked_id}</code>\n"
                f"⚙️ 动作: 底层 API 直连拉起 (状态码: {status_code})\n"
                f"⏳ 状态: 脚本执行完毕，请查看截图确认状态\n"
                f"🔑 Cookie: 正常加载"
            )
            send_tg_report(success_msg, screenshot_path)

        except Exception as e:
            error_details = str(e).split('\n')[0] 
            print(f"\n❌ 自动化任务执行失败: {error_details}")
            
            error_screenshot = "error.png"
            try:
                time.sleep(2)
                page.screenshot(path=error_screenshot, full_page=True)
            except:
                error_screenshot = None

            fail_msg = (
                f"🎁 <b>Rustix.me 拉起报告</b>\n\n"
                f"✅ 成功: 0 ⏭ 跳过: 0 ❌ 失败: 1\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"❌ <b>Rustix 机器</b>\n"
                f"🖥 服务器: <code>{masked_id}</code>\n"
                f"⚠️ 状态: 执行失败\n"
                f"📝 原因: <code>{error_details}</code>" 
            )
            send_tg_report(fail_msg, error_screenshot)
            
        finally:
            browser.close()

if __name__ == "__main__":
    run_automation()
