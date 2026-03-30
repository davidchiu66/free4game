import os
import time
import requests
from playwright.sync_api import sync_playwright

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

def run_automation():
    screenshot_path = "result.png"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=CUSTOM_USER_AGENT,
            viewport={'width': 1280, 'height': 800}
        )

        # 注入 Cookie
        if USER_COOKIES:
            formatted_cookies = parse_raw_cookies(USER_COOKIES)
            if formatted_cookies:
                context.add_cookies(formatted_cookies)

        page = context.new_page()
        masked_id = mask_string(SERVER_ID)

        try:
            target_url = f"https://panel.gaming4free.net/server/{SERVER_ID}/console"
            page.goto(target_url)
            print(f"打开服务器页面: {target_url}")

            # ---------------------------------------------------------
            # 【全新逻辑】引入最多 3 次的重试验证机制
            # ---------------------------------------------------------
            max_retries = 3
            is_success = False

            for attempt in range(1, max_retries + 1):
                print(f"\n--- 开始第 {attempt} 次续期检查 ---")
                
                # 查找续期按钮
                renew_button = page.get_by_role("button", name="Add 90 Minutes", exact=True)
                
                # 给页面 5 秒钟时间确认按钮是否真的存在（避免因为页面刚加载完而误判）
                try:
                    renew_button.wait_for(state="visible", timeout=5000)
                except:
                    pass # 如果 5 秒后没找到，什么都不做，继续往下走
                
                # 校验状态：按钮是否还在？
                if not renew_button.is_visible():
                    print("✅ 确认「Add 90 Minutes」按钮已消失，续期成功生效！")
                    is_success = True
                    break # 成功了！直接跳出重试循环，去执行后面的截图操作
                
                # 如果按钮还在，说明需要续期（或者上一次续期没成功）
                print(f"发现续期按钮，正在执行点击 (当前尝试: {attempt}/{max_retries})...")
                renew_button.click()
                
                print("正在等待 45 秒 (等待广告/后台处理)...")
                time.sleep(45) 
                
                print("正在刷新页面以确认状态...")
                page.reload()
                page.wait_for_load_state('networkidle')
                # 刷新完成后，循环会回到开头，再次检查按钮是否存在

            # 循环结束后，检查最终状态
            if not is_success:
                # 如果执行了 3 次还没成功，抛出异常，触发失败通知
                raise Exception(f"已重试 {max_retries} 次，但续期按钮依然存在，可能是广告加载失败或被拦截。")

            # ---------------------------------------------------------
            # 以下为成功后的滑动截屏与通知逻辑 (只有 is_success 为 True 才会执行到这里)
            # ---------------------------------------------------------
            print("\n尝试安全地转移焦点，并定位底部图表区域进行截图...")
            
            try:
                console_header = page.get_by_role("heading", name="Console", exact=True)
                console_header.click(timeout=5000)
                print("✅ 已点击 Console 标题，成功安全移除终端焦点。")
            except Exception as e:
                page.mouse.click(1270, 400)
            
            try:
                cpu_label = page.get_by_text("CPU Load", exact=False)
                cpu_label.scroll_into_view_if_needed(timeout=5000)
                print("✅ 成功滚动到底部图表区域！")
            except Exception as e:
                page.mouse.wheel(delta_x=0, delta_y=2000)

            time.sleep(2) 
            page.screenshot(path=screenshot_path, full_page=True)
            
            success_msg = (
                f"🎁 <b>Game4Free 续期报告</b>\n\n"
                f"📊 共 1 个账号\n"
                f"✅ 成功: 1 ⏭ 跳过: 0 ❌ 失败: 0\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"✅ <b>Game4Free 机器</b>\n"
                f"🖥 服务器: <code>{masked_id}</code>\n"
                f"⏳ 状态: 续期成功 (+90分钟)\n"
                f"🔑 Cookie: 正常"
            )
            send_tg_report(success_msg, screenshot_path)

        except Exception as e:
            error_details = str(e).split('\n')[0] 
            print(f"\n❌ 自动化任务执行失败: {error_details}")
            
            error_screenshot = "error.png"
            try:
                page.get_by_role("heading", name="Console", exact=True).click(timeout=3000)
                page.mouse.wheel(delta_x=0, delta_y=2000)
                time.sleep(1)
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
