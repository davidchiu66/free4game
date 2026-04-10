import os
import re
import requests
from botasaurus.browser import browser, Driver

# ============================================================
# 1. 环境变量配置 (关联 GitHub Secrets)
# ============================================================
G4FREE_COOKIE = os.environ.get("G4FREE_USER_COOKIE", "")
G4FREE_PANEL_COOKIE = os.environ.get("G4FREE_PANEL_COOKIE", "") 
ACCOUNT = os.environ.get("G4FREE_ACCOUNT", "")
PASSWORD = os.environ.get("G4FREE_PASSWORD", "")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")

DASHBOARD_URL = "https://gaming4free.net/dashboard"

# ============================================================
# 2. 辅助函数合集
# ============================================================
def send_tg_message(text: str, photo_path: str = None):
    """发送图文消息至 Telegram 进行实时监控"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("⚠️ 未配置 Telegram Token 或 Chat ID，跳过消息推送。")
        return
    try:
        if photo_path and os.path.exists(photo_path):
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
            data = {"chat_id": TG_CHAT_ID, "caption": f"🎮 [G4Free 助手]\n{text}", "parse_mode": "HTML"}
            with open(photo_path, "rb") as f:
                requests.post(url, data=data, files={"photo": f}, timeout=30)
        else:
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
            data = {"chat_id": TG_CHAT_ID, "text": f"🎮 [G4Free 助手]\n{text}", "parse_mode": "HTML"}
            requests.post(url, data=data, timeout=30)
        print("📨 Telegram 状态反馈发送成功！")
    except Exception as e:
        print(f"❌ Telegram 发送失败: {e}")

def inject_cookies(driver: Driver, raw_cookie_str: str, target_domain: str):
    """跨域 Cookie 预热与注入，打通会话隔离"""
    if not raw_cookie_str: 
        return
    print(f"🍪 正在初始化并预加载 {target_domain} 的环境...")
    driver.get(f"https://{target_domain}/404_init_cookie") 
    
    cookies_list = []
    for pair in raw_cookie_str.split(';'):
        if '=' in pair:
            name, value = pair.strip().split('=', 1)
            cookies_list.append({"name": name, "value": value, "domain": target_domain, "path": "/"})
            
    try:
        if hasattr(driver, 'add_cookies'): 
            driver.add_cookies(cookies_list)
        elif hasattr(driver, 'set_cookies'): 
            driver.set_cookies(cookies_list)
        else:
            for c in cookies_list:
                driver.run_js(f"document.cookie = '{c['name']}={c['value']}; domain={c['domain']}; path={c['path']}';")
        print(f"✅ {target_domain} Cookie 预加载完毕！")
    except Exception as e:
        print(f"⚠️ {target_domain} Cookie 注入异常: {e}")

def get_total_minutes(time_str: str) -> int:
    """将文本时间转换为纯数字总分钟数以便数学运算"""
    if not time_str or time_str == "未知":
        return 0
    h_match = re.search(r'(\d+)\s*hour', time_str, re.IGNORECASE)
    m_match = re.search(r'(\d+)\s*minute', time_str, re.IGNORECASE)
    
    hours = int(h_match.group(1)) if h_match else 0
    minutes = int(m_match.group(1)) if m_match else 0
    
    return hours * 60 + minutes

# ============================================================
# 3. 核心业务流程：G4Free 续期任务
# ============================================================
@browser(headless=True, window_size=(1920, 1080))
def g4free_renewal_task(driver: Driver, data):
    screenshot_name = "g4free_status.png"
    screenshot_real_path = os.path.join("output", "screenshots", screenshot_name)
    
    try:
        # 【前置】全域 Cookie 预加载
        if G4FREE_PANEL_COOKIE:
            inject_cookies(driver, G4FREE_PANEL_COOKIE, "panel.gaming4free.net")
        if G4FREE_COOKIE:
            inject_cookies(driver, G4FREE_COOKIE, "gaming4free.net")

        # 【步骤一】登录主站
        print(f"🌐 访问主站 Dashboard: {DASHBOARD_URL}")
        driver.get(DASHBOARD_URL)
        driver.sleep(6)

        if "login" in driver.current_url.lower():
            print("⚠️ 主站 Cookie 失效，启动账号密码兜底登录...")
            driver.type('input[type="email"], input[name="email"]', ACCOUNT)
            driver.type('input[type="password"], input[name="password"]', PASSWORD)
            driver.click('button[type="submit"]')
            driver.sleep(8)
            if "login" in driver.current_url.lower():
                driver.save_screenshot(screenshot_name)
                send_tg_message("🔴 <b>主站兜底登录失败</b>\n请检查账号密码。", screenshot_real_path)
                return

        # 【步骤二】拟人化过渡
        print("🔍 尝试自然点击 'Renew' 按钮...")
        js_click_renew = """
        var links = document.querySelectorAll('a');
        for (var i = 0; i < links.length; i++) {
            if ((links[i].innerText || links[i].textContent).includes('Renew')) {
                links[i].removeAttribute('target');
                links[i].click(); return true;
            }
        } return false;
        """
        if not driver.run_js(js_click_renew):
            driver.save_screenshot(screenshot_name)
            send_tg_message("🔴 <b>异常拦截</b>\n在 Dashboard 未找到 Renew 按钮。", screenshot_real_path)
            return
        driver.sleep(10)

        # 【步骤三】面板过渡
        print("🔗 尝试自然点击 'Panel' 按钮...")
        js_click_panel = """
        var links = document.querySelectorAll('a');
        for (var i = 0; i < links.length; i++) {
            if ((links[i].innerText || links[i].textContent).trim().toLowerCase() === 'panel') {
                links[i].removeAttribute('target');
                links[i].click(); return true;
            }
        } return false;
        """
        if not driver.run_js(js_click_panel):
            driver.save_screenshot(screenshot_name)
            send_tg_message("🔴 <b>页面结构异常</b>\n未找到 Panel 按钮。", screenshot_real_path)
            return
        driver.sleep(10)

        if "login" in driver.current_url.lower():
            driver.save_screenshot(screenshot_name)
            send_tg_message("🔴 <b>面板跨域认证失败</b>\n虽已模拟点击，但面板 Cookie 失效或被图形验证码拦截。", screenshot_real_path)
            return

        # 【步骤四】终端过渡
        print("🖥️ 尝试自然点击 Console 终端入口...")
        js_click_console = """
        var links = document.querySelectorAll('a');
        for (var i = 0; i < links.length; i++) {
            var text = links[i].innerText || links[i].textContent;
            var href = links[i].getAttribute('href') || "";
            if ((text && text.includes('Console')) || href.endsWith('/console')) {
                links[i].click(); return true;
            }
        } return false;
        """
        if not driver.run_js(js_click_console):
            driver.save_screenshot(screenshot_name)
            send_tg_message("🔴 <b>页面异常</b>\n在 Panel 页面未找到 Console。", screenshot_real_path)
            return
        driver.sleep(8)

        # 【步骤五】防欺骗续期核心逻辑
        print("⏱️ 正在获取加时前的初始时间...")
        html_source_before = driver.page_html
        match_before = re.search(r'suspended.*?in\s*<strong[^>]*>(.*?)</strong>', html_source_before, re.IGNORECASE | re.DOTALL)
        time_before = match_before.group(1).strip() if match_before else "未知"
        minutes_before = get_total_minutes(time_before)
        
        print("👆 准备查找并点击 'Add 90 Minutes'...")
        js_click_add = """
        var btns = document.querySelectorAll('button');
        for (var i = 0; i < btns.length; i++) {
            if ((btns[i].innerText || btns[i].textContent).toLowerCase().includes('add 90 minutes')) {
                btns[i].click(); return true;
            }
        } return false;
        """
        
        if driver.run_js(js_click_add):
            driver.sleep(3) 
            if driver.is_element_present("iframe[src*='turnstile'], iframe[src*='recaptcha'], iframe[src*='cloudflare']"):
                print("🛡️ 检测到图形验证码盾！如果机房 IP 信誉差极可能导致加时失败...")
                driver.sleep(15) 
                
            print("📺 开始等待广告播放或验证码处理 (90 秒)...")
            driver.sleep(90)

            print("🔄 等待结束，执行原生底层双重刷新...")
            driver.run_js("location.reload(true);")
            driver.sleep(6)
            driver.run_js("location.reload(true);")
            driver.sleep(8)
            
            html_source_after = driver.page_html
            match_after = re.search(r'suspended.*?in\s*<strong[^>]*>(.*?)</strong>', html_source_after, re.IGNORECASE | re.DOTALL)
            time_after = match_after.group(1).strip() if match_after else "未知"
            minutes_after = get_total_minutes(time_after)
            
            driver.save_screenshot(screenshot_name)
            
            # 【最终审判】计算时差
            if minutes_after > minutes_before + 30:
                msg = (
                    "🟢 <b>G4Free 续期成功！</b>\n\n"
                    "时间已发生真实增长，加时操作成功生效！\n"
                    f"⏱️ <b>操作前：</b><code>{time_before}</code>\n"
                    f"⏱️ <b>最新时长：</b><code>{time_after}</code>"
                )
            else:
                msg = (
                    "🔴 <b>假成功警告 (被验证码拦截)</b>\n\n"
                    "代码已成功点击加时按钮，但服务器未生效(极大概率是底层弹出了无法绕过的图形验证码)。\n"
                    f"⏱️ <b>操作前：</b><code>{time_before}</code>\n"
                    f"⏱️ <b>操作后：</b><code>{time_after}</code>"
                )
            send_tg_message(msg, screenshot_real_path)
            
        else:
            driver.save_screenshot(screenshot_name)
            send_tg_message("🔴 <b>异常拦截</b>\n未找到加时按钮，请检查截图核实。", screenshot_real_path)

    except Exception as e:
        driver.save_screenshot(screenshot_name)
        send_tg_message(f"🔴 <b>脚本严重报错</b>\n<code>{str(e)}</code>", screenshot_real_path)

if __name__ == "__main__":
    g4free_renewal_task()
