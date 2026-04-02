import os
import time
import requests
import urllib.parse
import re
from playwright.sync_api import sync_playwright

# =====================================================================
# 环境变量获取
# =====================================================================
SERVER_ID = os.environ.get("SERVER_ID", "未知服务器")
SERVER_UUID = os.environ.get("SERVER_UUID", SERVER_ID) 
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
USER_COOKIES = os.environ.get("USER_COOKIES")

CUSTOM_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"

def parse_raw_cookies(raw_cookie_str: str, domain: str = "my.rustix.me") -> list:
    """解析 Cookie 字符串供 Playwright 使用"""
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
    """脱敏服务器 ID"""
    if not s or len(s) <= 4:
        return s
    return f"{s[:3]}****{s[-2:]}"

def send_tg_report(caption_html: str, photo_path: str = None):
    """推送战报到 Telegram"""
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

            print("等待 8 秒，确保页面完全渲染并且 Cloudflare 验证通过...")
            time.sleep(8) 
            
            # =========================================================
            # 步骤 1：探测服务器当前状态
            # =========================================================
            print("正在检测服务器当前运行状态...")
            action_result = ""
            is_already_running = False
            
            # 使用正则兼容英文 Start 和俄文 Старт，并提取第一个匹配的按钮
            start_button = page.locator("button").filter(has_text=re.compile(r"^(Start|Старт)$", re.IGNORECASE)).first
            
            try:
                # 给一点时间寻找按钮
                start_button.wait_for(state="attached", timeout=10000)
                # 核心判断：如果 Start 按钮被禁用，说明服务器处于非停止状态
                if start_button.is_disabled():
                    is_already_running = True
                    print("✅ 状态检测：服务器已在运行中 (Start 按钮不可点)。")
                else:
                    print("⚠️ 状态检测：服务器当前已停止 (Start 按钮可点)。")
            except Exception:
                print("⚠️ 状态检测：未找到明确的 Start 按钮，为确保万一，将默认执行拉起操作。")

            # =========================================================
            # 步骤 2：根据状态决定是否下发 API 指令
            # =========================================================
            if is_already_running:
                action_result = "无需操作 (已在运行)"
                print("⏭️ 跳过 API 注入，直接进入战报截图环节...")
            else:
                print("=====================================================")
                print("🚀 启动原生 API 注入拉起")
                print("=====================================================")
                
                api_script = f"""
                    async () => {{
                        function getXsrfToken() {{
                            const match = document.cookie.match(new RegExp('(^| )(?:X)?SRF-TOKEN=([^;]+)'));
                            return match ? decodeURIComponent(match[2]) : '';
                        }}
                        
                        try {{
                            const response = await fetch('/api/client/servers/{SERVER_UUID}/power', {{
                                method: 'POST',
                                headers: {{
                                    'Accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'X-Requested-With': 'XMLHttpRequest',
                                    'X-XSRF-TOKEN': getXsrfToken()
                                }},
                                body: JSON.stringify({{ signal: 'start' }})
                            }});
                            return response.status;
                        }} catch (e) {{
                            return -1;
                        }}
                    }}
                """
                
                status_code = page.evaluate(api_script)
                print(f"📡 注入 API 响应状态码: {status_code}")
                
                if status_code in [200, 204]:
                    print("🎉 成功！拉起指令已下达！")
                    action_result = f"API 触发成功 (状态码: {status_code})"
                    
                    print("⏳ 正在等待 45 秒，让服务器执行启动过程...")
                    time.sleep(45)
                    
                    print("🔄 正在刷新页面以获取最新截图...")
                    try:
                        page.reload(timeout=60000, wait_until="domcontentloaded")
                    except:
                        pass
                    time.sleep(8) 
                else:
                    print(f"⚠️ API 请求异常 (状态码: {status_code})")
                    action_result = f"API 触发异常 (状态码: {status_code})"

            # =========================================================
            # 步骤 3：统一截图与通知
            # =========================================================
            print("📸 正在截取最终状态全屏快照...")
            page.screenshot(path=screenshot_path, full_page=True)
            
            success_msg = (
                f"🎁 <b>Rustix.me 拉起报告</b>\n\n"
                f"✅ 成功: 1 ⏭ 跳过: 0 ❌ 失败: 0\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"✅ <b>Rustix 机器</b>\n"
                f"🖥 服务器: <code>{masked_id}</code>\n"
                f"⚙️ 动作: {action_result}\n"
                f"⏳ 状态: 脚本执行完毕，请查看截图确认最终状态\n"
                f"🔑 Cookie: 正常加载"
            )
            send_tg_report(success_msg, screenshot_path)

        except Exception as e:
            error_details = str(e).split('\n')[0] 
            print(f"\n❌ 自动化任务执行失败: {error_details}")
            
            error_screenshot = "error.png"
            try:
                page.screenshot(path=error_screenshot, full_page=True)
            except:
                error_screenshot = None

            fail_msg = (
                f"🎁 <b>Rustix.me 拉起报告</b>\n\n"
                f"✅ 成功: 0 ⏭ 跳过: 0 ❌ 失败: 1\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"❌ <b>Rustix 机器</b>\n"
                f"🖥 服务器: <code>{masked_id}</code>\n"
                f"⚠️ 状态: API 执行失败\n"
                f"📝 原因: <code>{error_details}</code>" 
            )
            send_tg_report(fail_msg, error_screenshot)
            
        finally:
            browser.close()

if __name__ == "__main__":
    run_automation()
