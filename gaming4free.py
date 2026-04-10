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
# 3. 辅助函数：Cookie 注入
# ============================================================
def inject_cookies(driver: Driver, raw_cookie_str: str, target_domain: str):
    """将原生 Cookie 字符串转化为 Botasaurus 支持的格式并注入指定域名"""
    if not raw_cookie_str: 
        return
    print(f"🍪 正在解析并注入 {target_domain} 的 Cookie...")
    
    # 访问目标域名下的无效路径，以初始化该域名的 Cookie 环境
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
        print(f"✅ {target_domain} Cookie 注入完毕！")
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
        # 【阶段一：主站智能登录】
        if G4FREE_COOKIE:
            inject_cookies(driver, G4FREE_COOKIE, "gaming4free.net")

        print(f"🌐 访问主站控制台面板: {DASHBOARD_URL}")
        driver.get(DASHBOARD_URL)
        driver.sleep(5)

        if "login" in driver.current_url.lower():
            print("⚠️ 主站 Cookie 失效，启动账号密码自动兜底登录...")
            driver.type('input[type="email"], input[name="email"]', ACCOUNT)
            driver.type('input[type="password"], input[name="password"]', PASSWORD)
            driver.click('button[type="submit"]')
            driver.sleep(8)
            
            if "login" in driver.current_url.lower():
                driver.save_screenshot(screenshot_name)
                send_tg_message("🔴 <b>主站兜底登录失败</b>\n请检查账号密码或查看截图。", screenshot_real_path)
                return

        # 【阶段二：拟人化点击 Renew 按钮】
        print("🔍 正在扫描并尝试自然点击 'Renew' 按钮...")
        
        # 核心优化：使用 JS 找到按钮，移除新标签页属性，并触发真实的点击事件
        js_click_renew = """
        var links = document.querySelectorAll('a');
        for (var i = 0; i < links.length; i++) {
            var text = links[i].innerText || links[i].textContent;
            if (text && text.includes('Renew')) {
                // 关键防拦截技巧：移除 target="_blank"，迫使链接在当前标签页打开
                links[i].removeAttribute('target');
                links[i].click();
                return true;
            }
        }
        return false;
        """
        renew_clicked = driver.run_js(js_click_renew)
        
        if not renew_clicked:
            driver.save_screenshot(screenshot_name)
            send_tg_message("🔴 <b>异常拦截</b>\n在 Dashboard 未找到 'Renew' 按键，或页面未加载完成。", screenshot_real_path)
            return
            
        print("🚀 已模拟真实用户点击 Renew，等待页面自然跳转至服务器总览...")
        # 给予充足的时间等待页面自然加载完成
        driver.sleep(10)

        # 【阶段三：在总览页面拟人化点击 Console 进入终端】
        print("🖥️ 正在寻找并自然点击 Console 终端入口...")
        
        # 同样使用 JS 触发真实点击
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
        console_clicked = driver.run_js(js_click_console)
        
        if not console_clicked:
            # 加入双重判定，防止页面加载慢导致的误判
            driver.save_screenshot(screenshot_name)
            send_tg_message("🔴 <b>页面结构异常</b>\n跳转后未能找到 Console 按钮，可能是遇到了二次验证拦截，请核实截图。", screenshot_real_path)
            return
            
        print("⏳ 已触发 Console 点击，等待终端面板加载...")
        driver.sleep(8)

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
            
            if driver.is_element_present("iframe[src*='turnstile'], iframe[src*='cloudflare']"):
                print("🛡️ 检测到 Cloudflare 验证盾，等待底层环境自动绕过...")
                driver.sleep(15) 
                
            print("📺 开始等待广告播放完毕 (安全硬等待 90 秒)...")
            driver.sleep(90)

            # 【阶段五：双重刷新与时间提取】
            print("🔄 广告结束，执行双重刷新同步最新状态...")
            driver.refresh()
            driver.sleep(6)
            driver.refresh()
            driver.sleep(8)
            
            html_source = driver.page_html
            match = re.search(r'suspended.*?in\s*<strong[^>]*>(.*?)</strong>', html_source, re.IGNORECASE | re.DOTALL)
            
            final_time = match.group(1).strip() if match else "未知 (正则未完全匹配)"
            print(f"⏱️ 最终剩余时间: {final_time}")
            
            driver.save_screenshot(screenshot_name)
            msg = (
                "🟢 <b>G4Free 续期任务完成！</b>\n\n"
                "通过标准流程安全进入控制台，广告等待与刷新已执行完毕。\n"
                f"⏱️ <b>最新剩余时长：</b><code>{final_time}</code>"
            )
            send_tg_message(msg, screenshot_real_path)
            
        else:
            driver.save_screenshot(screenshot_name)
            send_tg_message("🔴 <b>异常拦截</b>\n在终端未找到 'Add 90 Minutes' 按钮，请查看截图。", screenshot_real_path)

    except Exception as e:
        driver.save_screenshot(screenshot_name)
        send_tg_message(f"🔴 <b>脚本发生严重报错</b>\n\n<b>错误详情：</b>\n<code>{str(e)}</code>", screenshot_real_path)

if __name__ == "__main__":
    g4free_renewal_task()
