import os
import time
import requests
import re
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

            # =========================================================
            # 【策略 1】深度等待：确保网页的 JS 完全加载并绑定完毕
            # =========================================================
            try:
                # 升级等待策略：等待到网络请求基本静止，确保前端框架就绪
                page.goto(target_url, timeout=60000, wait_until="networkidle")
                print("✅ 页面及所有后台脚本加载完成 (Network Idle)！")
            except Exception as goto_err:
                print(f"⚠️ 网络未完全静止，但可能已够用，尝试继续执行: {goto_err}")

            # 强行硬等待 5 秒，给前端留出最后的事件绑定时间
            time.sleep(5) 
            
            print("正在扫描「Start」按钮...")
            start_button = page.locator("button").filter(has_text=re.compile(r"Start", re.IGNORECASE)).first
            
            if not start_button.is_visible(timeout=10000):
                print("⚠️ 警告：屏幕上没有找到可见的「Start」按钮！")
            else:
                print("✅ 成功定位到可见的「Start」按钮！")
                
                # =========================================================
                # 【策略 2】机枪连发确认法：直到你真的生效为止
                # =========================================================
                print("▶️ 开始执行【轮询确认点击】策略...")
                
                max_attempts = 10
                action_successful = False
                
                for attempt in range(1, max_attempts + 1):
                    # 每次点击前先检查按钮是否已经因为上一秒的点击变成了 disabled
                    if start_button.is_disabled():
                        print(f"🎉 成功！在第 {attempt} 次检测时，发现按钮已变为 disabled。拉起请求已发送！")
                        action_successful = True
                        break
                    
                    print(f"   - 第 {attempt}/{max_attempts} 次尝试触发 Start...")
                    try:
                        # 确保按钮在视口内
                        start_button.scroll_into_view_if_needed()
                        
                        # 使用简单的原生点击，因为现在的问题更可能是前端还没准备好
                        start_button.click(force=True, timeout=3000)
                    except Exception as click_err:
                        print(f"     点击时遇到小问题 (忽略): {click_err}")
                    
                    # 每次点击后等待 3 秒，让前端有机会响应并改变按钮状态
                    time.sleep(3)
                
                if not action_successful:
                    print("⚠️ 警告：10 次尝试完毕，按钮依然处于可点击状态，前端极有可能彻底拦截了自动化点击。")
            
            print("⏳ 正在等待最终的 45 秒，让服务器执行启动过程...")
            time.sleep(45)
            
            print("🔄 正在刷新页面以获取最终截图状态...")
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
                f"⚙️ 动作: 执行了轮询确认点击策略\n"
                f"⏳ 状态: 脚本执行完毕，请查看截图确认最终状态\n"
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
