import os
import sys
import time
import socket
import urllib.parse
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# =====================================================================
# 1. 环境变量获取
# =====================================================================
SERVER_ID = os.environ.get("LEME_SERVER_ID", "未知服务器")
SERVER_UUID = os.environ.get("LEME_SERVER_UUID", SERVER_ID) 
SERVER_IP = os.environ.get("SERVER_IP", "28.lemehost.com")
SERVER_PORT = int(os.environ.get("SERVER_PORT", 17868))

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
USER_COOKIES = os.environ.get("LEME_USER_COOKIES")

# =====================================================================

CUSTOM_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"

def parse_raw_cookies(raw_cookie_str: str, domain: str = "lemehost.com") -> list:
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

# =====================================================================
# 2. 前置 TCP 连通性探测
# =====================================================================
def check_server_port_status(ip: str, port: int, timeout: int = 5) -> bool:
    """使用原生 Socket 探测端口，避免开启沉重的浏览器"""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False

# =====================================================================
# 3. 核心 Playwright 自动化流程
# =====================================================================
def run_automation():
    masked_id = mask_string(SERVER_ID)
    
    # ---------------------------------------------------------
    # 阶段一：健康检查
    # ---------------------------------------------------------
    print(f"🔍 正在探测游戏服务器连通性: {SERVER_IP}:{SERVER_PORT}")
    is_online = check_server_port_status(SERVER_IP, SERVER_PORT)
    
    if is_online:
        print("🟢 服务器当前运行正常，端口已开放。准备发送在线通知并退出。")
        online_msg = (
            f"🎁 <b>Lemehost 运行状态报告</b>\n\n"
            f"✅ <b>Lemehost 机器</b>\n"
            f"🖥 服务器: <code>{masked_id}</code>\n"
            f"⚙️ 动作: TCP 探测正常 (免登录)\n"
            f"🟢 状态: <b>运行中</b>"
        )
        send_tg_report(online_msg)
        sys.exit(0) # 正常退出，不消耗后续的计算资源
        
    print("🔴 探测失败，服务器处于停机状态！准备启动自动化拉起流程...")

    # ---------------------------------------------------------
    # 阶段二：启动浏览器并登录
    # ---------------------------------------------------------
    screenshot_path = "lemehost_result.png"
    
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
            target_url = f"https://lemehost.com/server/{SERVER_ID}/console"
            print(f"🌐 准备打开服务器控制台: {target_url}")

            try:
                page.goto(target_url, timeout=60000, wait_until="domcontentloaded")
            except PlaywrightTimeoutError:
                print("⚠️ 页面 DOM 加载超时，尝试继续强行注入...")

            print("等待 5 秒，让 Cloudflare 盾牌可能存在的重定向完成...")
            time.sleep(5) 
            
            # ---------------------------------------------------------
            # 阶段三：抗跳转重试注入
            # ---------------------------------------------------------
            print("=====================================================")
            print("🚀 启动原生 API 注入 (带有重试装甲)")
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
            
            max_retries = 3
            status_code = -1
            action_result = ""
            
            for attempt in range(max_retries):
                try:
                    print(f"尝试第 {attempt + 1}/{max_retries} 次注入拉起指令...")
                    status_code = page.evaluate(api_script)
                    
                    if status_code in [200, 204]:
                        print("🎉 成功！拉起指令已下达！")
                        action_result = f"API 触发成功 (状态码: {status_code})"
                        break # 成功则跳出循环
                    else:
                        print(f"⚠️ API 返回异常状态码: {status_code}")
                        action_result = f"API 触发异常 (状态码: {status_code})"
                        break # 返回了明确的状态码，说明注入没被销毁，不需要重试，直接跳出
                        
                except Exception as e:
                    # 捕获 Execution context was destroyed 等异常
                    print(f"⚠️ 第 {attempt + 1} 次注入失败，页面可能正在跳转。原因: {str(e).splitlines()[0]}")
                    if attempt < max_retries - 1:
                        print("等待 3 秒后重试...")
                        time.sleep(3)
                    else:
                        action_result = "API 注入彻底失败 (上下文多次被销毁)"
            
            # ---------------------------------------------------------
            # 阶段四：强行截图与推送
            # ---------------------------------------------------------
            print("⏳ 等待 30 秒，让服务器执行启动日志输出...")
            time.sleep(30)
            
            try:
                print("📸 正在强行截取当前可视区域...")
                # 修复超时点：去掉 full_page=True，并设置独立的强制 10 秒超时机制
                page.screenshot(path=screenshot_path, timeout=10000)
            except Exception as ss_err:
                print(f"⚠️ 截图步骤被跳过或超时: {ss_err}")
                screenshot_path = None # 如果截图失败，依然发送文字战报
            
            success_msg = (
                f"🎁 <b>Lemehost 拉起报告</b>\n\n"
                f"✅ <b>Lemehost 机器</b>\n"
                f"🖥 服务器: <code>{masked_id}</code>\n"
                f"⚙️ 动作: {action_result}\n"
                f"⏳ 状态: 脚本执行完毕，请查看截图确认最终状态"
            )
            send_tg_report(success_msg, screenshot_path)

        except Exception as e:
            error_details = str(e).split('\n')[0] 
            print(f"\n❌ 自动化任务发生致命崩溃: {error_details}")
            
            error_screenshot = "error.png"
            try:
                page.screenshot(path=error_screenshot, timeout=10000)
            except:
                error_screenshot = None

            fail_msg = (
                f"🎁 <b>Lemehost 严重异常报告</b>\n\n"
                f"❌ <b>Lemehost 机器</b>\n"
                f"🖥 服务器: <code>{masked_id}</code>\n"
                f"📝 原因: <code>{error_details}</code>" 
            )
            send_tg_report(fail_msg, error_screenshot)
            
        finally:
            browser.close()

if __name__ == "__main__":
    run_automation()
