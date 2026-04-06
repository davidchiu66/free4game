import os
import sys
import time
import socket
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# =====================================================================
# 1. 环境变量获取
# =====================================================================
SERVER_ID = os.environ.get("LEME_SERVER_ID", "未知服务器")
# 注意：UI 点击不再需要 SERVER_UUID，我们只需 SERVER_ID
SERVER_IP = os.environ.get("SERVER_IP", "28.lemehost.com")
SERVER_PORT = int(os.environ.get("SERVER_PORT", 17868))

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
USER_COOKIES = os.environ.get("LEME_USER_COOKIES")

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
                requests.post(url, data=data, files=files).raise_for_status()
        else:
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
            data = {"chat_id": TG_CHAT_ID, "text": caption_html, "parse_mode": "HTML"}
            requests.post(url, data=data).raise_for_status()
        print("✅ TG推送成功")
    except Exception as e:
        print(f"❌ TG推送失败: {e}")

# =====================================================================
# 2. 前置 TCP 连通性探测
# =====================================================================
def check_server_port_status(ip: str, port: int, timeout: int = 5) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False

# =====================================================================
# 3. 核心 Playwright 自动化流程 (UI 点击模式)
# =====================================================================
def run_automation():
    masked_id = mask_string(SERVER_ID)
    
    print(f"🔍 正在探测游戏服务器连通性: {SERVER_IP}:{SERVER_PORT}")
    if check_server_port_status(SERVER_IP, SERVER_PORT):
        print("🟢 服务器当前运行正常，端口已开放。准备发送在线通知并退出。")
        online_msg = (
            f"🎁 <b>Lemehost 运行状态报告</b>\n\n"
            f"✅ <b>Lemehost 机器</b>\n"
            f"🖥 服务器: <code>{masked_id}</code>\n"
            f"⚙️ 动作: TCP 探测正常 (免登录)\n"
            f"🟢 状态: <b>运行中</b>"
        )
        send_tg_report(online_msg)
        sys.exit(0)
        
    print("🔴 探测失败，服务器处于停机状态！准备启动自动化拉起流程...")

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
                print("⚠️ 页面 DOM 加载超时，尝试继续强行寻找按钮...")

            print("等待 8 秒，让页面完全渲染...")
            time.sleep(8) 
            
            # =========================================================
            # 阶段三：UI 物理点击启动 (废弃 404 API)
            # =========================================================
            print("=====================================================")
            print("🚀 启动纯 UI 模拟点击模式")
            print("=====================================================")
            
            action_result = ""
            
            # 精确锁定源码中的启动按钮
            start_button = page.locator('button[data-state="start"]')
            
            try:
                # 给一点时间等待按钮出现在 DOM 中
                start_button.wait_for(state="attached", timeout=10000)
                
                # 检查按钮是否被禁用 (如果已经在运行或启动中，按钮通常是不可点击的)
                if start_button.is_disabled():
                    print("✅ 状态检测：服务器已在运行中或正在启动 (Start 按钮不可点)。")
                    action_result = "无需操作 (Start按钮已禁用)"
                else:
                    print("🖱️ 发现 Start 按钮处于可点状态，正在执行鼠标左键物理点击...")
                    start_button.click(force=True)
                    action_result = "UI 点击 Start 按钮成功"
                    print("🎉 成功！点击指令已下达！")
            except Exception as e:
                print(f"⚠️ 未能找到可用的 Start 按钮或点击失败: {e}")
                action_result = "UI 触发异常 (未找到Start按钮)"

            # 等待启动过程
            print("⏳ 等待 30 秒，准备获取执行结果...")
            time.sleep(30)
            
            try:
                print("📸 正在强行截取当前可视区域...")
                page.screenshot(path=screenshot_path, timeout=10000)
            except Exception as ss_err:
                print(f"⚠️ 截图步骤被跳过或超时: {ss_err}")
                screenshot_path = None
            
            success_msg = (
                f"🎁 <b>Lemehost 拉起报告</b>\n\n"
                f"✅ <b>Lemehost 机器</b>\n"
                f"🖥 服务器: <code>{masked_id}</code>\n"
                f"⚙️ 动作: {action_result}\n"
                f"⏳ 状态: 脚本执行完毕，请查看截图确认"
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
