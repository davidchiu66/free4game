import os
import time
import requests
import json
import re
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync 

# 1. 从环境变量获取配置
SERVER_ID = os.environ.get("SERVER_ID", "未知服务器")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
USER_COOKIES = os.environ.get("USER_COOKIES")

# 2. 定义固定的 User-Agent
CUSTOM_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"

def parse_raw_cookies(raw_cookie_str: str, domain: str = ".gaming4free.net") -> list:
    """解析原生 Cookie 字符串"""
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
    """将字符串中间部分替换为星号进行脱敏，例如: 0ab73ff2 -> 0ab****f2"""
    if not s or len(s) <= 4:
        return s
    return f"{s[:3]}****{s[-2:]}"

def send_tg_report(caption_html: str, photo_path: str = None):
    """发送 Telegram 图文报告"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("未配置 Telegram Token 或 Chat ID，跳过通知。")
        return
    
    try:
        # 如果有图片路径且图片存在，则发送图片+描述
        if photo_path and os.path.exists(photo_path):
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
            data = {
                "chat_id": TG_CHAT_ID,
                "caption": caption_html,
                "parse_mode": "HTML" # 使用 HTML 模式支持加粗等富文本
            }
            with open(photo_path, "rb") as photo_file:
                files = {"photo": photo_file}
                response = requests.post(url, data=data, files=files)
        # 否则只发送文本消息
        else:
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
            data = {
                "chat_id": TG_CHAT_ID,
                "text": caption_html,
                "parse_mode": "HTML"
            }
            response = requests.post(url, data=data)
            
        response.raise_for_status()
        print("✅ TG推送成功")
    except Exception as e:
        print(f"❌ TG推送失败: {e}")

# ... [保留之前的环境变量获取、parse_raw_cookies、mask_string 和 send_tg_report 函数不变] ...

def run_automation():
    screenshot_path = "result.png"
    
    with sync_playwright() as p:
        # ---------------------------------------------------------
        # 【关键升级 1】注入允许广告自动播放的底层参数
        # ---------------------------------------------------------
        browser = p.chromium.launch(
            headless=False, 
            channel="chrome", 
            args=[
                "--disable-blink-features=AutomationControlled",
                "--autoplay-policy=no-user-gesture-required", # 强制允许视频广告自动播放
                "--mute-audio", # 静音（防止因为有声音被拦截）
                "--disable-features=IsolateOrigins,site-per-process" # 帮助处理跨域广告 iframe
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
        stealth_sync(page)
        
        masked_id = mask_string(SERVER_ID)

        try:
            target_url = f"https://panel.gaming4free.net/server/{SERVER_ID}/console"
            page.goto(target_url)
            print(f"打开服务器页面: {target_url}")

            max_retries = 3
            is_success = False

            for attempt in range(1, max_retries + 1):
                print(f"\n--- 开始第 {attempt} 次续期检查 ---")
                
                # 等待基础框架渲染
                time.sleep(5)
                
                renew_button = page.get_by_role("button", name=re.compile(r"add 90 minutes", re.IGNORECASE))
                
                # ---------------------------------------------------------
                # 【关键升级 2】严苛的成功校验逻辑 (防止白屏假阳性)
                # ---------------------------------------------------------
                # 检查页面是否真的加载出来了（有没有 Console 标题）
                console_header = page.get_by_role("heading", name="Console", exact=True)
                is_page_loaded = console_header.is_visible(timeout=5000)
                
                if not is_page_loaded:
                    print("⚠️ 警告：页面似乎是白屏或未完全加载！")
                elif not renew_button.is_visible():
                    # 只有页面正常加载，且找不到按钮，才是真成功
                    print("✅ 页面加载正常，且续期按钮不存在 (已成功续期)。")
                    is_success = True
                    break 
                
                # 如果没成功，继续点击流程
                print(f"发现续期按钮，正在执行点击 (当前尝试: {attempt}/{max_retries})...")
                renew_button.click(force=True)
                
                print("正在等待 90 秒 (让后台广告疯狂播放吧)...")
                time.sleep(90) 
                
                print("正在刷新页面以确认最终状态...")
                page.reload()
                page.wait_for_load_state('domcontentloaded')
                print("等待前端 React 框架渲染...")
                time.sleep(8) # 多等一会儿，防止截图截到还没渲染完的白屏

            if not is_success:
                raise Exception(f"已重试 {max_retries} 次，续期按钮依然存在或页面白屏崩溃。")

            # ---------------------------------------------------------
            # 【关键升级 3】精准提取剩余时长
            # ---------------------------------------------------------
            remaining_time = "未知"
            try:
                print("正在提取服务器剩余时长...")
                # 使用更宽容的正则寻找包含 "suspended" 的段落，并提取里面的 strong 标签
                time_locator = page.locator("p", has_text=re.compile(r"suspended", re.IGNORECASE)).locator("strong").first
                if time_locator.is_visible(timeout=5000):
                    remaining_time = time_locator.inner_text().strip()
                    print(f"✅ 成功获取剩余时长: {remaining_time}")
                else:
                    print("⚠️ 未找到包含时间的标签，可能页面结构有变。")
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
                f"📊 共 1 个账号\n"
                f"✅ 成功: 1 ⏭ 跳过: 0 ❌ 失败: 0\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"✅ <b>Game4Free 机器</b>\n"
                f"🖥 服务器: <code>{masked_id}</code>\n"
                f"⏳ 状态: 续期成功 (+90分钟)\n"
                f"⏱ 剩余: <b>{remaining_time}</b>\n"
                f"🔑 Cookie: 正常"
            )
            send_tg_report(success_msg, screenshot_path)

        except Exception as e:
            error_details = str(e).split('\n')[0] 
            print(f"\n❌ 自动化任务执行失败: {error_details}")
            
            error_screenshot = "error.png"
            try:
                # 失败时不要盲目滚动了，直接截取当前屏幕，看看卡在什么广告上了
                time.sleep(2)
                page.screenshot(path=error_screenshot, full_page=True)
            except:
                error_screenshot = None

            fail_msg = (
                f"🎁 <b>Game4Free 续期报告</b>\n\n"
                f"📊 共 1 个账号\n"
                f"✅ 成功: 0 ⏭ 跳过: 0 ❌ 失败: 1\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"❌ <b>Game4Free 机器</b>\n"
                f"🖥 服务器: <code>{masked_id}</code>\n"
                f"⚠️ 状态: 续期失败\n"
                f"📝 原因: <code>{error_details}</code>"
            )
            send_tg_report(fail_msg, error_screenshot)
            
        finally:
            browser.close()

if __name__ == "__main__":
    run_automation()
