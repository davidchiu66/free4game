import os
import time
import requests
import json
import re
from playwright.sync_api import sync_playwright
# 【关键修改 1】删除了 from playwright_stealth import stealth_sync 

SERVER_ID = os.environ.get("SERVER_ID", "未知服务器")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
USER_COOKIES = os.environ.get("USER_COOKIES")

CUSTOM_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"

def parse_raw_cookies(raw_cookie_str: str, domain: str = ".gaming4free.net") -> list:
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
    screenshot_path = "result.png"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False, 
            channel="chrome", 
            args=[
                "--disable-blink-features=AutomationControlled",
                "--autoplay-policy=no-user-gesture-required", 
                "--mute-audio", 
                "--disable-features=IsolateOrigins,site-per-process",
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
        
        # ---------------------------------------------------------
        # 【关键修改 2】用干净的手动注入代替有 BUG 的 stealth_sync
        # ---------------------------------------------------------
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            window.chrome = {
                runtime: {}
            };
        """)
        
        # 依然保留日志监听，方便我们观察
        page.on("console", lambda msg: print(f"🖥️ [网页内部日志] {msg.type}: {msg.text}"))
        page.on("pageerror", lambda err: print(f"💥 [网页 JS 报错] {err}"))
        
        masked_id = mask_string(SERVER_ID)

        try:
            target_url = f"https://panel.gaming4free.net/server/{SERVER_ID}/console"
            page.goto(target_url, timeout=60000)
            print(f"打开服务器页面: {target_url}")

            max_retries = 3
            is_success = False

            for attempt in range(1, max_retries + 1):
                print(f"\n--- 开始第 {attempt} 次续期检查 ---")
                print(f"当前所处 URL: {page.url}")
                
                time.sleep(5)
                
                console_header = page.get_by_role("heading", name="Console", exact=True)
                is_page_loaded = console_header.is_visible(timeout=5000)
                
                if not is_page_loaded:
                    print("⚠️ 警告：未检测到 Console 标题。")
                    if page.get_by_text("Just a moment", exact=False).is_visible() or page.get_by_text("Cloudflare", exact=False).is_visible():
                        print("🛡️ 检测到 Cloudflare 安全拦截，等待 15 秒...")
                        time.sleep(15)
                    
                    print("🔄 尝试刷新页面以恢复白屏...")
                    page.reload()
                    page.wait_for_load_state('domcontentloaded')
                    continue 
                
                renew_button = page.get_by_role("button", name=re.compile(r"add 90 minutes", re.IGNORECASE))
                
                if not renew_button.is_visible(timeout=5000):
                    fallback_button = page.locator("button:has-text('90')").filter(has_text=re.compile(r"minutes", re.IGNORECASE)).first
                    if fallback_button.is_visible():
                        renew_button = fallback_button
                    else:
                        print("✅ 页面加载正常，且续期按钮不存在 (已成功续期)。")
                        is_success = True
                        break 
                
                print(f"发现续期按钮，准备点击...")
                try:
                    renew_button.click(force=True, timeout=5000)
                    print("✅ 点击动作已触发！")
                except Exception as click_err:
                    print(f"⚠️ 点击按钮时出错: {str(click_err).split('Call log:')[0]}")
                    continue
                
                print("⏳ 开始等待 90 秒的广告播放时间...")
                for wait_step in range(3):
                    time.sleep(30)
                    print(f"   - 广告等待中 ({ (wait_step + 1) * 30 }/90秒)，当前 URL: {page.url}")
                    page.screenshot(path=f"debug_ad_wait_{attempt}_{wait_step}.png")
                
                print("🔄 广告等待结束，正在刷新页面以确认最终状态...")
                page.reload()
                page.wait_for_load_state('domcontentloaded')
                time.sleep(8) 

            if not is_success:
                raise Exception(f"已重试 {max_retries} 次，续期按钮依然存在或页面一直白屏。")

            remaining_time = "未知"
            try:
                print("正在提取服务器剩余时长...")
                time_locator = page.locator("p", has_text=re.compile(r"suspended", re.IGNORECASE)).locator("strong").first
                if time_locator.is_visible(timeout=5000):
                    remaining_time = time_locator.inner_text().strip()
            except Exception as e:
                print(f"⚠️ 提取时长时发生错误: {e}")

            print("\n尝试安全地转移焦点，并定位底部图表区域进行截图...")
            try:
                console_header.click(timeout=3000)
            except:
                page.mouse.click(1270, 400)
            
            try:
                cpu_label = page.get_by_text("CPU Load", exact=False)
                cpu_label.scroll_into_view_if_needed(timeout=3000)
            except:
                page.mouse.wheel(delta_x=0, delta_y=2000)

            time.sleep(3) 
            page.screenshot(path=screenshot_path, full_page=True)
            
            success_msg = (
                f"🎁 <b>Game4Free 续期报告</b>\n\n"
                f"✅ 成功: 1 ⏭ 跳过: 0 ❌ 失败: 0\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"✅ <b>Game4Free 机器</b>\n"
                f"🖥 服务器: <code>{masked_id}</code>\n"
                f"⏳ 状态: 续期成功 (+90分钟)\n"
                f"⏱ 剩余: <b>{remaining_time}</b>"
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
                f"🎁 <b>Game4Free 续期报告</b>\n\n"
                f"✅ 成功: 0 ⏭ 跳过: 0 ❌ 失败: 1\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"❌ <b>Game4Free 机器</b>\n"
                f"🖥 服务器: <code>{masked_id}</code>\n"
                f"⚠️ 状态: 续期失败\n"
                f"📝 原因: <code>{error_details}</code>\n"
                f"🔗 最终 URL: <code>{page.url}</code>" 
            )
            send_tg_report(fail_msg, error_screenshot)
            
        finally:
            browser.close()

if __name__ == "__main__":
    run_automation()
