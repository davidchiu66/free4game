import os
import re
import requests
from botasaurus.browser import browser, Driver

# [1. 环境变量配置] (保持不变)
G4FREE_COOKIE = os.environ.get("G4FREE_USER_COOKIE", "")
G4FREE_PANEL_COOKIE = os.environ.get("G4FREE_PANEL_COOKIE", "") 
ACCOUNT = os.environ.get("G4FREE_ACCOUNT", "")
PASSWORD = os.environ.get("G4FREE_PASSWORD", "")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")
DASHBOARD_URL = "https://gaming4free.net/dashboard"

# [2. 辅助函数] (保持不变)
def send_tg_message(text: str, photo_path: str = None):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    try:
        if photo_path and os.path.exists(photo_path):
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
            data = {"chat_id": TG_CHAT_ID, "caption": f"🎮 [G4Free 助手]\n{text}", "parse_mode": "HTML"}
            with open(photo_path, "rb") as f: requests.post(url, data=data, files={"photo": f}, timeout=30)
        else:
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
            data = {"chat_id": TG_CHAT_ID, "text": f"🎮 [G4Free 助手]\n{text}", "parse_mode": "HTML"}
            requests.post(url, data=data, timeout=30)
    except Exception as e:
        print(f"❌ Telegram 发送失败: {e}")

def inject_cookies(driver: Driver, raw_cookie_str: str, target_domain: str):
    if not raw_cookie_str: return
    driver.get(f"https://{target_domain}/404_init_cookie") 
    cookies_list = [{"name": pair.strip().split('=', 1)[0], "value": pair.strip().split('=', 1)[1], "domain": target_domain, "path": "/"} for pair in raw_cookie_str.split(';') if '=' in pair]
    try:
        if hasattr(driver, 'add_cookies'): driver.add_cookies(cookies_list)
        else:
            for c in cookies_list: driver.run_js(f"document.cookie = '{c['name']}={c['value']}; domain={c['domain']}; path={c['path']}';")
    except Exception as e: print(f"⚠️ Cookie 注入异常: {e}")

def get_total_minutes(time_str: str) -> int:
    if not time_str or time_str == "未知": return 0
    h_match = re.search(r'(\d+)\s*hour', time_str, re.IGNORECASE)
    m_match = re.search(r'(\d+)\s*minute', time_str, re.IGNORECASE)
    return (int(h_match.group(1)) if h_match else 0) * 60 + (int(m_match.group(1)) if m_match else 0)

# ============================================================
# 3. 核心业务流程：G4Free 续期任务 (带 Buster 破盾能力)
# ============================================================
# 🚨 核心改动：必须关闭 headless，并挂载解压后的 Buster 插件目录
@browser(
    headless=False, 
    window_size=(1920, 1080),
    extensions=["extensions/buster/unpacked"] 
)
def g4free_renewal_task(driver: Driver, data):
    screenshot_name = "g4free_status.png"
    screenshot_real_path = os.path.join("output", "screenshots", screenshot_name)
    
    try:
        # 【全域预加载与登录过渡】
        if G4FREE_PANEL_COOKIE: inject_cookies(driver, G4FREE_PANEL_COOKIE, "panel.gaming4free.net")
        if G4FREE_COOKIE: inject_cookies(driver, G4FREE_COOKIE, "gaming4free.net")

        driver.get(DASHBOARD_URL)
        driver.sleep(6)

        if "login" in driver.current_url.lower():
            driver.type('input[type="email"], input[name="email"]', ACCOUNT)
            driver.type('input[type="password"], input[name="password"]', PASSWORD)
            driver.click('button[type="submit"]')
            driver.sleep(8)
            if "login" in driver.current_url.lower():
                driver.save_screenshot(screenshot_name)
                send_tg_message("🔴 <b>主站兜底登录失败</b>\n请检查账号密码。", screenshot_real_path)
                return

        js_click_renew = """var links = document.querySelectorAll('a'); for (var i=0; i<links.length; i++) { if ((links[i].innerText || links[i].textContent).includes('Renew')) { links[i].removeAttribute('target'); links[i].click(); return true; } } return false;"""
        if not driver.run_js(js_click_renew):
            driver.save_screenshot(screenshot_name)
            send_tg_message("🔴 <b>异常拦截</b>\n在 Dashboard 未找到 Renew 按钮。", screenshot_real_path)
            return
        driver.sleep(10)

        js_click_panel = """var links = document.querySelectorAll('a'); for (var i=0; i<links.length; i++) { if ((links[i].innerText || links[i].textContent).trim().toLowerCase() === 'panel') { links[i].removeAttribute('target'); links[i].click(); return true; } } return false;"""
        if not driver.run_js(js_click_panel): return
        driver.sleep(10)

        js_click_console = """var links = document.querySelectorAll('a'); for (var i=0; i<links.length; i++) { var text = links[i].innerText || links[i].textContent; var href = links[i].getAttribute('href') || ""; if ((text && text.includes('Console')) || href.endsWith('/console')) { links[i].click(); return true; } } return false;"""
        if not driver.run_js(js_click_console): return
        driver.sleep(8)

        # 【防欺骗续期与 Buster 音频破解】
        html_source_before = driver.page_html
        match_before = re.search(r'suspended.*?in\s*<strong[^>]*>(.*?)</strong>', html_source_before, re.IGNORECASE | re.DOTALL)
        time_before = match_before.group(1).strip() if match_before else "未知"
        minutes_before = get_total_minutes(time_before)
        
        js_click_add = """var btns = document.querySelectorAll('button'); for (var i=0; i<btns.length; i++) { if ((btns[i].innerText || btns[i].textContent).toLowerCase().includes('add 90 minutes')) { btns[i].click(); return true; } } return false;"""
        
        if driver.run_js(js_click_add):
            driver.sleep(3) 
            
            # 🚨 核心改动：Buster 交互逻辑
            bframe_sel = "iframe[src*='bframe']"
            if driver.is_element_present(bframe_sel):
                print("🛡️ 检测到图形验证码弹窗！启动 Buster 音频破解方案...")
                try:
                    driver.sleep(2)
                    # 1. 跨越 iframe 点击原生的“耳机”音频挑战图标
                    print("🎧 切换至音频挑战模式...")
                    driver.click("#recaptcha-audio-button", iframe=bframe_sel)
                    driver.sleep(3)
                    
                    # 2. 跨越 iframe 点击 Buster 插件注入的破解按钮
                    print("🤖 触发 Buster AI 破解...")
                    driver.click("#solver-button", iframe=bframe_sel)
                    
                    # 给予充分的时间听取音频并完成自动输入
                    print("⏳ 正在等待 Buster 请求 API 并完成破解...")
                    driver.sleep(15)
                except Exception as e:
                    print(f"⚠️ Buster 破解交互发生异常: {e}")
            else:
                print("✅ 未检测到验证码弹窗，直接进入等待阶段。")
                
            print("📺 开始等待广告播放 (90 秒)...")
            driver.sleep(90)

            print("🔄 等待结束，执行双重刷新...")
            driver.run_js("location.reload(true);")
            driver.sleep(6)
            driver.run_js("location.reload(true);")
            driver.sleep(8)
            
            html_source_after = driver.page_html
            match_after = re.search(r'suspended.*?in\s*<strong[^>]*>(.*?)</strong>', html_source_after, re.IGNORECASE | re.DOTALL)
            time_after = match_after.group(1).strip() if match_after else "未知"
            minutes_after = get_total_minutes(time_after)
            
            driver.save_screenshot(screenshot_name)
            
            if minutes_after > minutes_before + 30:
                msg = f"🟢 <b>G4Free 续期成功！</b>\n\nBuster 语音破盾与加时操作生效！\n⏱️ <b>操作前：</b><code>{time_before}</code>\n⏱️ <b>最新时长：</b><code>{time_after}</code>"
            else:
                msg = f"🔴 <b>假成功警告 (破盾失败)</b>\n\n尝试了 Buster 破解，但未能成功加时。\n⏱️ <b>操作前：</b><code>{time_before}</code>\n⏱️ <b>操作后：</b><code>{time_after}</code>"
            send_tg_message(msg, screenshot_real_path)
            
        else:
            driver.save_screenshot(screenshot_name)
            send_tg_message("🔴 <b>异常拦截</b>\n未找到加时按钮，请检查截图核实。", screenshot_real_path)

    except Exception as e:
        driver.save_screenshot(screenshot_name)
        send_tg_message(f"🔴 <b>脚本严重报错</b>\n<code>{str(e)}</code>", screenshot_real_path)

if __name__ == "__main__":
    g4free_renewal_task()
