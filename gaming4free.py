import os
import re
import requests
from botasaurus.browser import browser, Driver

# ============================================================
# 1. 环境变量配置
# ============================================================
G4FREE_COOKIE = os.environ.get("G4FREE_USER_COOKIE", "")
ACCOUNT = os.environ.get("G4FREE_ACCOUNT", "")
PASSWORD = os.environ.get("G4FREE_PASSWORD", "")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")

LOGIN_URL = "https://gaming4free.net/login"
DASHBOARD_URL = "https://gaming4free.net/dashboard"

# ============================================================
# 2. 辅助函数：Telegram 推送
# ============================================================
def send_tg_message(text: str, photo_path: str = None):
    """无论成功与否，将执行结果和截图推送到 TG"""
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
# 3. 辅助函数：Cookie 高可用注入
# ============================================================
def inject_cookies(driver: Driver, raw_cookie_str: str):
    if not raw_cookie_str: 
        return
    print("🍪 正在解析并注入 Cookie...")
    driver.get("https://gaming4free.net/404_init_cookie") # 初始化主站域名环境
    
    cookies_list = []
    for pair in raw_cookie_str.split(';'):
        if '=' in pair:
            name, value = pair.strip().split('=', 1)
            cookies_list.append({"name": name, "value": value, "domain": "gaming4free.net", "path": "/"})
            
    try:
        if hasattr(driver, 'add_cookies'): 
            driver.add_cookies(cookies_list)
        elif hasattr(driver, 'set_cookies'): 
            driver.set_cookies(cookies_list)
        else:
            for c in cookies_list:
                driver.run_js(f"document.cookie = '{c['name']}={c['value']}; domain={c['domain']}; path={c['path']}';")
        print("✅ Cookie 注入尝试完毕！")
    except Exception as e:
        print(f"⚠️ Cookie 注入异常: {e}")

# ============================================================
# 4. 核心任务：G4Free 续期逻辑
# ============================================================
@browser(headless=True, window_size=(1920, 1080))
def g4free_renewal_task(driver: Driver, data):
    screenshot_name = "g4free_status.png"
    screenshot_real_path = os.path.join("output", "screenshots", screenshot_name)
    
    try:
        # 【阶段一：主站智能登录】
        if G4FREE_COOKIE:
            inject_cookies(driver, G4FREE_COOKIE)

        print(f"🌐 访问控制台面板: {DASHBOARD_URL}")
        driver.get(DASHBOARD_URL)
        driver.sleep(5)

        # 兜底检测：如果 URL 被重定向到了 login
        if "login" in driver.current_url.lower():
            print("⚠️ 主站 Cookie 失效，启动账号密码自动兜底登录...")
            driver.type('input[type="email"], input[name="email"]', ACCOUNT)
            driver.type('input[type="password"], input[name="password"]', PASSWORD)
            driver.click('button[type="submit"]')
            driver.sleep(8)
            
            if "login" in driver.current_url.lower():
                driver.save_screenshot(screenshot_name)
                send_tg_message("🔴 <b>主站兜底登录失败</b>\n请检查账号密码或查看截图是否有严重拦截。", screenshot_real_path)
                return

        # 【阶段二：提取 Renew 链接并跳转 Console】
        print("🔍 正在扫描服务器续期链接...")
        js_find_link = """
        var links = document.querySelectorAll('a');
        for (var i = 0; i < links.length; i++) {
            var text = links[i].innerText || links[i].textContent;
            if (text && text.includes('Renew')) {
                return links[i].getAttribute('href');
            }
        }
        return null;
        """
        renew_href = driver.run_js(js_find_link)
        
        if not renew_href:
            driver.save_screenshot(screenshot_name)
            send_tg_message("🔴 <b>异常拦截</b>\n在 Dashboard 页面未找到 'Renew' 按键，面板可能已更改。", screenshot_real_path)
            return

        # 智能路径拼接
        renew_href = renew_href.rstrip('/') 
        if renew_href.startswith("http"):
            console_url = f"{renew_href}/console"
        else:
            clean_href = renew_href.lstrip('/')
            console_url = f"https://panel.gaming4free.net/{clean_href}/console"
            
        print(f"🚀 跳转至服务器控制台: {console_url}")
        driver.get(console_url)
        driver.sleep(8)

        # 【阶段三：处理控制台面板 (panel 子域名) 的二次独立登录】
        if "login" in driver.current_url.lower() or driver.is_element_present('input[type="password"]'):
            print("⚠️ 触发了控制台面板二次登录，正在自动填写凭证...")
            driver.type('input[type="text"], input[type="email"]', ACCOUNT)
            driver.type('input[type="password"]', PASSWORD)
            
            # 给予 Turnstile 验证盾加载和静默通过的时间
            print("🛡️ 等待可能的验证盾初始化...")
            driver.sleep(5) 
            
            driver.click('button[type="submit"], button:contains("LOGIN"), button:contains("Login")')
            print("⏳ 等待控制台面板登录跳转...")
            driver.sleep(10)
            
            if "login" in driver.current_url.lower() or driver.is_element_present('input[type="password"]'):
                driver.save_screenshot(screenshot_name)
                send_tg_message("🔴 <b>控制台面板登录失败</b>\n二次登录未能成功，可能是由于极强验证码拦截或密码不匹配，请检查截图。", screenshot_real_path)
                return

        # 【阶段四：点击加时与处理 Cloudflare 及广告】
        print("👆 准备查找并点击 'Add 90 Minutes' 按钮...")
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
        btn_clicked = driver.run_js(js_click_add)

        if btn_clicked:
            driver.sleep(3) 
            
            # 检测潜在的独立 CF 弹窗质询
            if driver.is_element_present("iframe[src*='turnstile'], iframe[src*='cloudflare']"):
                print("🛡️ 检测到 Cloudflare 验证盾，等待 Botasaurus 底层环境自动绕过...")
                driver.sleep(15) 
                
            print("📺 开始等待广告播放完毕 (安全硬等待 90 秒)...")
            driver.sleep(90)

            # 【阶段五：双重刷新与时间提取】
            print("🔄 广告结束，执行双重刷新同步最新状态...")
            driver.refresh()
            driver.sleep(6)
            driver.refresh()
            driver.sleep(8)
            
            # 从网页源码中精确提取时间
            html_source = driver.page_html
            match = re.search(r'suspended.*?in\s*<strong[^>]*>(.*?)</strong>', html_source, re.IGNORECASE | re.DOTALL)
            
            final_time = match.group(1).strip() if match else "未知 (正则未完全匹配到时长结构)"
            print(f"⏱️ 最终剩余时间: {final_time}")
            
            driver.save_screenshot(screenshot_name)
            msg = (
                "🟢 <b>G4Free 续期任务完成！</b>\n\n"
                "广告等待与双重刷新已执行完毕。\n"
                f"⏱️ <b>最新剩余时长：</b><code>{final_time}</code>"
            )
            send_tg_message(msg, screenshot_real_path)
            
        else:
            driver.save_screenshot(screenshot_name)
            send_tg_message("🔴 <b>异常拦截</b>\n在控制台未找到 'Add 90 Minutes' 按钮，页面可能仍在加载或结构已变，请查看截图。", screenshot_real_path)

    except Exception as e:
        driver.save_screenshot(screenshot_name)
        send_tg_message(f"🔴 <b>脚本发生严重报错</b>\n\n<b>错误详情：</b>\n<code>{str(e)}</code>", screenshot_real_path)

if __name__ == "__main__":
    g4free_renewal_task()
