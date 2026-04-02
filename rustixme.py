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
            page.goto(target_url, timeout=60000)
            print(f"打开服务器页面: {target_url}")

            page.wait_for_load_state('domcontentloaded')
            time.sleep(5) 
            
            # =========================================================
            # 【逻辑重构】基于 Старт 按钮的精准拉起与闭环验证
            # =========================================================
            print("正在查找「Старт」按钮进行状态判断...")
            
            # 定位 Start 按钮
            start_button = page.get_by_role("button", name="Старт", exact=True).first
            start_button.wait_for(state="visible", timeout=15000)
            
            action_taken = ""
            
            # 检查初始状态
            if start_button.is_disabled():
                print("✅ 检测到「Старт」按钮为 disabled (不可点击) 状态，说明服务器已在运行中。")
                action_taken = "无需操作 (已在运行)"
            else:
                print("⚠️ 检测到「Старт」按钮可点击，服务器处于停止状态。")
                print("准备执行点击拉起...")
                start_button.click(force=True)
                
                print("⏳ 正在等待 60 秒，让服务器执行启动过程...")
                time.sleep(60)
                
                print("🔄 正在刷新页面以获取最新状态...")
                page.reload()
                page.wait_for_load_state('domcontentloaded')
                time.sleep(5) # 给前端框架一点渲染时间
                
                print("正在验证拉起结果...")
                # 重新定位刷新后的 Start 按钮
                verify_button = page.get_by_role("button", name="Старт", exact=True).first
                verify_button.wait_for(state="visible", timeout=15000)
                
                if verify_button.is_disabled():
                    print("✅ 验证成功！「Старт」按钮已变为 disabled 状态，服务器拉起成功。")
                    action_taken = "执行拉起并验证成功"
                else:
                    # 如果一分钟后按钮依然可点击，说明拉起失败，主动抛出异常进入报错流程
                    raise Exception("等待60秒后，'Старт'按钮依然可点击，服务器拉起失败。")
            # =========================================================
            
            print("📸 正在截取最终状态全屏快照...")
            page.screenshot(path=screenshot_path, full_page=True)
            
            success_msg = (
                f"🎁 <b>Rustix.me 拉起报告</b>\n\n"
                f"✅ 成功: 1 ⏭ 跳过: 0 ❌ 失败: 0\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"✅ <b>Rustix 机器</b>\n"
                f"🖥 服务器: <code>{masked_id}</code>\n"
                f"⚙️ 动作: {action_taken}\n"
                f"⏳ 状态: 脚本执行完毕\n"
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
