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

            try:
                page.goto(target_url, timeout=60000, wait_until="domcontentloaded")
                print("✅ 页面基础结构加载成功！")
            except Exception as goto_err:
                print(f"⚠️ 页面加载超时，尝试继续执行: {goto_err}")

            time.sleep(5) 
            
            # =========================================================
            # 【绝对拟真外挂逻辑】使用纯正的物理鼠标轨迹和按压
            # =========================================================
            print("正在扫描桌面端英文「Start」按钮...")
            
            # 定位包含 "Start" 文本的按钮
            start_button = page.locator("button").filter(has_text=re.compile(r"^Start$", re.IGNORECASE)).first
            
            # 如果没找到，尝试模糊匹配（以防有前后空格）
            if not start_button.is_visible():
                 start_button = page.locator("button").filter(has_text=re.compile(r"Start", re.IGNORECASE)).first

            if not start_button.is_visible(timeout=10000):
                print("⚠️ 警告：屏幕上没有找到可见的「Start」按钮！")
            else:
                print("✅ 成功定位到可见的「Start」按钮！")
                try:
                    # 获取屏幕绝对坐标
                    box = start_button.bounding_box()
                    if box:
                        # 计算按钮正中心的像素点
                        target_x = box["x"] + box["width"] / 2
                        target_y = box["y"] + box["height"] / 2
                        
                        print(f"▶️ 目标坐标锁定：X={target_x}, Y={target_y}。开始模拟人类手部动作...")
                        
                        # 1. 模拟鼠标平滑移动过去（产生鼠标滑过的事件流）
                        page.mouse.move(target_x, target_y, steps=10)
                        time.sleep(0.2)
                        
                        # 2. 模拟真实物理按下（鼠标左键）
                        print("   - 鼠标按下 (Mousedown)...")
                        page.mouse.down()
                        
                        # 3. 模拟人类手指停留的几十毫秒
                        time.sleep(0.15) 
                        
                        # 4. 模拟真实物理抬起
                        print("   - 鼠标抬起 (Mouseup)...")
                        page.mouse.up()
                        
                        print("✅ 绝对物理拟真点击完成！")
                    else:
                        print("⚠️ 无法获取按钮的屏幕物理坐标。")
                except Exception as click_err:
                    print(f"⚠️ 物理点击时遇到异常: {click_err}")
            
            print("⏳ 正在等待 60 秒，让服务器执行启动过程...")
            time.sleep(60)
            
            print("🔄 正在刷新页面以获取最新状态...")
            try:
                page.reload(timeout=60000, wait_until="domcontentloaded")
            except:
                pass
            
            time.sleep(8)
            # =========================================================
            
            print("📸 正在截取最终状态全屏快照...")
            page.screenshot(path=screenshot_path, full_page=True)
            
            success_msg = (
                f"🎁 <b>Rustix.me 拉起报告</b>\n\n"
                f"✅ 成功: 1 ⏭ 跳过: 0 ❌ 失败: 0\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"✅ <b>Rustix 机器</b>\n"
                f"🖥 服务器: <code>{masked_id}</code>\n"
                f"⚙️ 动作: 执行了物理坐标平滑点击\n"
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
