import os
import re
import requests
from botasaurus.browser import browser, Driver

# ============================================================
# 1. 环境变量配置
# ============================================================
G4FREE_COOKIE = os.environ.get("G4FREE_USER_COOKIE", "")
# 【恢复】控制台面板专属 Cookie，必须重新添加回 Secrets
G4FREE_PANEL_COOKIE = os.environ.get("G4FREE_PANEL_COOKIE", "") 
ACCOUNT = os.environ.get("G4FREE_ACCOUNT", "")
PASSWORD = os.environ.get("G4FREE_PASSWORD", "")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")

DASHBOARD_URL = "https://gaming4free.net/dashboard"

# ============================================================
# 2. 辅助函数：Telegram 推送
# ============================================================
def send_tg_message(text: str, photo_path: str = None):
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

# ============================================================
# 3. 辅助函数：跨域 Cookie 注入
# ============================================================
def inject_cookies(driver: Driver, raw_cookie_str: str, target_domain: str):
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

# ============================================================
# 4. 核心任务：G4Free 续期逻辑
# ============================================================
@browser(headless=True, window_size=(1920, 1080))
def g4free_renewal_task(driver: Driver, data):
    screenshot_name = "g4free_status.png"
    screenshot_real_path = os.path.join("output", "screenshots", screenshot_name)
    
    try:
        # 【阶段〇：全域 Cookie 前置预加载】
        # 必须在进入工作流之前，把两个域名的门票都买好
        if G4FREE_PANEL_COOKIE:
            inject_cookies(driver, G4FREE_PANEL_COOKIE, "panel.gaming4free.net")
        else:
            print("⚠️ 警告：未配置 G4FREE_PANEL_COOKIE，稍后跨域时极大概率被图形验证码拦截！")

        if G4FREE_COOKIE:
            inject_cookies(driver, G4FREE_COOKIE, "gaming4free.net")

        # 【阶段一：进入主站与状态核验】
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

        # 【阶段二：拟人化点击 Renew 前往过渡页】
        print("🔍 正在扫描并自然点击 'Renew' 按钮...")
        js_click_renew = """
        var links = document.querySelectorAll('a');
        for (var i = 0; i < links.length; i++) {
            var text = links[i].innerText || links[i].textContent;
            if (text && text.includes('Renew')) {
                links[i].removeAttribute('target');
                links[i].click();
                return true;
            }
        }
        return false;
        """
        if not driver.run_js(js_click_renew):
            driver.save_screenshot(screenshot_name)
            send_tg_message("🔴 <b>异常拦截</b>\n在 Dashboard 未找到 Renew 按钮。", screenshot_real_path)
            return
            
        print("🚀 已点击 Renew，等待过渡页加载...")
        driver.sleep(10)

        # 【阶段三：拟人化点击 Panel 前往真实面板】
        print("🔗 正在寻找并自然点击 'Panel' 按钮...")
        js_click_panel = """
        var links = document.querySelectorAll('a');
        for (var i = 0; i < links.length; i++) {
            var text = links[i].innerText || links[i].textContent;
            if (text && text.trim().toLowerCase() === 'panel') {
                links[i].removeAttribute('target');
                links[i].click();
                return true;
            }
        }
        return false;
        """
        if not driver.run_js(js_click_panel):
            driver.save_screenshot(screenshot_name)
            send_tg_message("🔴 <b>页面结构异常</b>\n未找到 Panel 按钮。", screenshot_real_path)
            return
            
        print("🚀 已点击 Panel，等待 Pterodactyl 面板加载...")
        driver.sleep(10)

        # 【阶段三点五：核验是否成功带状态跨域】
        if "login" in driver.current_url.lower():
            driver.save_screenshot(screenshot_name)
            send_tg_message("🔴 <b>面板跨域认证失败</b>\n虽已模拟点击，但面板 Cookie 失效或未配置，被二次登录/验证码拦截。", screenshot_real_path)
            return

        # 【阶段四：点击 Console 进入终端】
        print("🖥️ 正在寻找并自然点击 Console 终端入口...")
        js_click_console = """
        var links = document.querySelectorAll('a');
        for (var i = 0; i < links.length; i++) {
            var text = links[i].innerText || links[i].textContent;
            var href = links[i].getAttribute('href') || "";
            if ((text && text.includes('Console')) || href.endsWith('/console')) {
                links[i].click();
                return true;
            }
        }
        return false;
        """
        if not driver.run_js(js_click_console):
            driver.save_screenshot(screenshot_name)
            send_tg_message("🔴 <b>页面异常</b>\n在 Panel 页面未找到 Console。", screenshot_real_path)
            return
            
        print("⏳ 等待终端加载...")
        driver.sleep(8)

        # 【阶段五：点击加时与处理广告】
        print("👆 准备点击 'Add 90 Minutes'...")
        js_click_add = """
        var btns = document.querySelectorAll('button');
        for (var i = 0; i < btns.length; i++) {
            var text = btns[i].innerText || btns[i].textContent;
            if (text && text.includes('Add 90 Minutes')) {
                btns[i].click();
                return true;
            }
        }
        return false;
        """
        if driver.run_js(js_click_add):
            driver.sleep(3) 
            if driver.is_element_present("iframe[src*='turnstile'], iframe[src*='cloudflare']"):
                print("🛡️ 检测到验证盾，等待底层自动绕过...")
                driver.sleep(15) 
                
            print("📺 开始等待广告播放 (90 秒)...")
            driver.sleep(90)

            print("🔄 广告结束，执行双重刷新...")
            driver.refresh()
            driver.sleep(6)
            driver.refresh()
            driver.sleep(8)
            
            html_source = driver.page_html
            match = re.search(r'suspended.*?in\s*<strong[^>]*>(.*?)</strong>', html_source, re.IGNORECASE | re.DOTALL)
            final_time = match.group(1).strip() if match else "未知"
            
            driver.save_screenshot(screenshot_name)
            msg = f"🟢 <b>G4Free 续期完成！</b>\n\n安全通过自然流跨域并看守广告。\n⏱️ <b>最新时长：</b><code>{final_time}</code>"
            send_tg_message(msg, screenshot_real_path)
            
        else:
            driver.save_screenshot(screenshot_name)
            send_tg_message("🔴 <b>异常拦截</b>\n未找到加时按钮。", screenshot_real_path)

    except Exception as e:
        driver.save_screenshot(screenshot_name)
        send_tg_message(f"🔴 <b>脚本严重报错</b>\n<code>{str(e)}</code>", screenshot_real_path)

if __name__ == "__main__":
    g4free_renewal_task()
