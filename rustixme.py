import os
import time
import requests
import urllib.parse
from playwright.sync_api import sync_playwright

# =====================================================================
# 1. 环境变量获取 (包含新增的 SERVER_UUID)
# =====================================================================
SERVER_ID = os.environ.get("SERVER_ID", "未知服务器") # 用于 UI 访问的短 ID
SERVER_UUID = os.environ.get("SERVER_UUID", SERVER_ID) # 用于 API 访问的完整 UUID，默认回退为短 ID 防止报错
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
USER_COOKIES = os.environ.get("USER_COOKIES")

CUSTOM_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"

def parse_raw_cookies(raw_cookie_str: str, domain: str = "my.rustix.me") -> list:
    """解析并格式化 Cookie 字符串，供 Playwright 注入使用"""
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
    """脱敏敏感的服务器 ID，用于 TG 推送显示"""
    if not s or len(s) <= 4:
        return s
    return f"{s[:3]}****{s[-2:]}"

def send_tg_report(caption_html: str, photo_path: str = None):
    """将运行结果和截图推送到 Telegram"""
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

        # 注入用户配置的 Cookie
        if USER_COOKIES:
            formatted_cookies = parse_raw_cookies(USER_COOKIES)
            if formatted_cookies:
                context.add_cookies(formatted_cookies)

        page = context.new_page()

        try:
            # =====================================================================
            # 2. 预热页面并获取 XSRF-TOKEN
            # =====================================================================
            target_url = f"https://my.rustix.me/server/{SERVER_ID}/console"
            print(f"准备打开服务器页面以刷新 Token: {target_url}")

            try:
                # 只需等待基础 DOM 加载完毕，不再苦等脆弱的 UI 文本 (修复之前的 15000ms 超时)
                page.goto(target_url, timeout=60000, wait_until="domcontentloaded")
                print("✅ 页面加载成功，Cookie 环境已准备就绪！")
            except Exception as goto_err:
                print(f"⚠️ 页面加载超时，但仍将尝试执行 API: {goto_err}")

            time.sleep(3) # 简短等待，确保浏览器解析完响应头里的 Set-Cookie

            # 从当前会话的 Cookie 中提取出 XSRF-TOKEN 并解码
            xsrf_token = ""
            for cookie in context.cookies():
                if cookie["name"] == "XSRF-TOKEN":
                    xsrf_token = urllib.parse.unquote(cookie["value"])
                    break
            
            # =====================================================================
            # 3. 构建并发送底层 API 启动指令
            # =====================================================================
            print("=====================================================")
            print("🚀 启动 API 拉起模式")
            print("=====================================================")
            
            if not SERVER_UUID or len(SERVER_UUID) < 15:
                print("⚠️ 警告：检测到你似乎没有配置完整的 SERVER_UUID。API 请求可能会因为端点错误而失败！")

            if not xsrf_token:
                print("⚠️ 警告：未获取到 XSRF-TOKEN！")

            # 使用 SERVER_UUID 拼接正确的 API 端点
            power_api_url = f"https://my.rustix.me/api/client/servers/{SERVER_UUID}/power"
            print(f"正在向 {power_api_url} 发送启动指令...")
            
            # 通过 Playwright Context 发送 POST 请求，自动携带所有 Cookie
            api_response = context.request.post(
                power_api_url,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-XSRF-TOKEN": xsrf_token
                },
                data={
                    "signal": "start" # 核心启动信号
                }
            )

            status_code = api_response.status
            print(f"📡 API 响应状态码: {status_code}")
            
            action_result = ""
            # 翼龙面板 API 成功执行 power 指令通常返回 204 No Content，兼容 200
            if status_code in [200, 204]:
                print("🎉 成功！后端已确认接收拉起指令，服务器正在启动！")
                action_result = f"API 触发启动成功 (状态码: {status_code})"
            else:
                response_text = api_response.text()
                print(f"⚠️ API 请求返回异常: {response_text}")
                action_result = f"API 触发异常 (状态码: {status_code})"

            # =====================================================================
            # 4. 等待结果并截图反馈
            # =====================================================================
            print("⏳ 正在等待 45 秒，让服务器执行启动过程...")
            time.sleep(45)
            
            print("🔄 正在刷新页面以获取最终状态...")
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
