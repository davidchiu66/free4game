import os
import requests
from botasaurus.browser import browser, Driver

# ============================================================
# 1. 环境变量配置
# ============================================================
ACCOUNT = os.environ.get("SKYBOTS_ACCOUNT", "")
PASSWORD = os.environ.get("SKYBOTS_PASSWORD", "")
SKYBOTS_COOKIE = os.environ.get("SKYBOTS_USER_COOKIES", "")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")

# 新增代理环境变量获取 (如果没配置，默认留空)
PROXY_URL = os.environ.get("PROXY_URL", "")

LOGIN_URL = "https://dash.skybots.tech/login"
DASHBOARD_URL = "https://dash.skybots.tech/projects"

# ============================================================
# 2. 辅助函数：Telegram 图片推送 (已修复 NameError)
# ============================================================
def send_tg_message(text: str, photo_path: str = None):
    """无论成功与否，将执行结果和截图推送到 TG"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("⚠️ 未配置 Telegram Token 或 Chat ID，跳过推送。")
        return

    try:
        if photo_path and os.path.exists(photo_path):
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
            data = {
                "chat_id": TG_CHAT_ID,
                "caption": f"🤖 [Skybots 守护者]\n{text}",
                "parse_mode": "HTML",
            }
            with open(photo_path, "rb") as photo_file:
                requests.post(url, data=data, files={"photo": photo_file}, timeout=30)
            print("📨 Telegram 图文反馈发送成功！")
        else:
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
            data = {
                "chat_id": TG_CHAT_ID,
                "text": f"🤖 [Skybots 守护者]\n{text}",
                "parse_mode": "HTML",
            }
            requests.post(url, data=data, timeout=30)
            print("📨 Telegram 纯文本反馈发送成功！")
    except Exception as e:
        print(f"❌ Telegram 发送失败: {e}")

# ============================================================
# 3. 辅助函数：Cookie 注入
# ============================================================
def inject_cookies(driver: Driver, raw_cookie_str: str):
    if not raw_cookie_str:
        return
    print("🍪 正在解析并注入 Cookie...")
    driver.get("https://dash.skybots.tech/404_init_cookie")

    cookies_list = []
    for pair in raw_cookie_str.split(";"):
        if "=" in pair:
            name, value = pair.strip().split("=", 1)
            cookies_list.append(
                {
                    "name": name,
                    "value": value,
                    "domain": "dash.skybots.tech",
                    "path": "/",
                }
            )

    try:
        if hasattr(driver, "add_cookies"):
            driver.add_cookies(cookies_list)
        elif hasattr(driver, "set_cookies"):
            driver.set_cookies(cookies_list)
        else:
            for c in cookies_list:
                js_code = f"document.cookie = '{c['name']}={c['value']}; domain={c['domain']}; path={c['path']}';"
                driver.run_js(js_code)
        print("✅ Cookie 注入尝试完毕！")
    except Exception as e:
        print(f"⚠️ Cookie 注入部分遇到环境限制: {e}")

# ============================================================
# 4. 辅助函数：智能处理自定义验证码
# ============================================================
def handle_custom_captcha(driver: Driver):
    """
    专门针对类似 Cloudflare Turnstile 的验证码
    只用物理模拟点击，杜绝 JS 点击，避免被直接判定为 Bot
    """
    print("☑️ 尝试定位并智能处理验证码...")
    try:
        has_captcha = driver.run_js("return !!document.querySelector('.auth-captcha-inner');")
        if not has_captcha:
            print("ℹ️ 页面上未检测到验证码，跳过验证步骤。")
            return True

        print("⏳ 等待验证码防爬虫指纹收集...")
        driver.sleep(3) # 多等一会儿，让前置检测跑完

        print("👆 正在执行物理级模拟点击...")
        # 仅使用原生的 click()，它在 botasaurus 底层更接近真实点击
        driver.click(".auth-captcha-inner")

        max_wait = 20
        for i in range(max_wait):
            driver.sleep(1)
            is_checked = driver.run_js("""
                var el = document.querySelector('.auth-captcha-inner');
                return el ? el.getAttribute('aria-checked') === 'true' : false;
            """)
            if is_checked:
                print(f"✅ 验证码已成功绿灯！(耗时 {i+1} 秒)")
                driver.sleep(1)
                return True
                
        print(f"⚠️ 等待了 {max_wait} 秒，环境信誉可能太低被拦截。")
        return False
        
    except Exception as e:
        print(f"⚠️ 处理验证码时出错: {e}")
        return False

# ============================================================
# 5. 核心任务：续期监控与执行
# ============================================================
# 在装饰器中增加 proxy 参数。
# 如果 PROXY_URL 为空，Botasaurus 会自动忽略它；如果有值，则会自动挂载代理。
@browser(headless=True, window_size=(1920, 1080), proxy=PROXY_URL)
def skybots_renewal_task(driver: Driver, data):
    screenshot_name = "skybots_status.png"
    screenshot_real_path = os.path.join("output", "screenshots", screenshot_name)

    try:
        if SKYBOTS_COOKIE:
            inject_cookies(driver, SKYBOTS_COOKIE)

        print(f"🌐 访问控制台面板: {DASHBOARD_URL}")
        driver.get(DASHBOARD_URL)
        driver.sleep(8)

        current_url_lower = driver.current_url.lower()
        if "login" in current_url_lower or "setup-password" in current_url_lower:
            print("⚠️ Cookie 已失效或未配置，触发账号密码登录...")

            # --- 密码设置页面 ---
            if "setup-password" in current_url_lower:
                print("🔐 检测到密码设置页面...")
                password_inputs = driver.get_elements('input[type="password"]')
                for i, inp in enumerate(password_inputs):
                    if i < 2:  
                        inp.type(PASSWORD)
                        driver.sleep(1)
                
                handle_custom_captcha(driver)
                driver.click('button[type="submit"]')
                driver.sleep(10)
                current_url_lower = driver.current_url.lower()

            # --- 常规登录页面 ---
            if "login" in current_url_lower:
                print("🔐 正在输入凭据...")
                captcha_retry = 0
                max_captcha_retry = 3 # 减少无意义重试次数，避免账号被风控
                login_success = False

                while captcha_retry < max_captcha_retry and not login_success:
                    captcha_retry += 1
                    print(f"🔄 第 {captcha_retry}/{max_captcha_retry} 次尝试登录...")

                    driver.type('#username, input[name="username"]', ACCOUNT)
                    driver.sleep(0.5)
                    driver.type('#password, input[name="password"]', PASSWORD)
                    driver.sleep(0.5)
                    
                    handle_custom_captcha(driver)
                    
                    driver.click('button[type="submit"]')
                    driver.sleep(8)
                    current_url_lower = driver.current_url.lower()

                    if "login" not in current_url_lower and "setup-password" not in current_url_lower:
                        login_success = True
                        print("✅ 登录成功！")
                        break

                    print("⚠️ 登录受阻，准备刷新页面重试...")
                    driver.get(LOGIN_URL)
                    driver.sleep(5)

                if not login_success:
                    driver.save_screenshot(screenshot_name)
                    send_tg_message(
                        "🔴 <b>登录失败</b>\n\n数据中心 IP 可能被验证码严格拦截。建议在您的 PC 上重新获取 Cookie 并更新到 GitHub Secrets 中！",
                        screenshot_real_path,
                    )
                    return

        # ====================== 提取时间与续期逻辑 ======================
        print("✅ 成功进入面板，正在精准提取服务器时间信息...")
        driver.sleep(8)

        expire_time_text = "未知"
        try:
            expire_time_text = driver.get_text(".projects-expiry-value")
            if expire_time_text:
                print(f"⏱️ 剩余时间: {expire_time_text}")
                with open("next_time.txt", "w", encoding="utf-8") as f:
                    f.write(expire_time_text)
        except Exception as e:
            print(f"⚠️ 获取时间失败: {e}")

        page_text_lower = ""
        try:
            page_text_lower = driver.get_text("body").lower()
        except:
            pass

        if "2 heures avant" in page_text_lower or "2 hours before" in page_text_lower:
            driver.save_screenshot(screenshot_name)
            msg = f"⏰ <b>暂无续期资格</b>\n\n距离到期还有 2 小时以上。\n⏱️ <b>剩余时间：</b><code>{expire_time_text}</code>"
            send_tg_message(msg, screenshot_real_path)
            print("⏰ 未达到时间，任务结束。")
            return

        print("🔍 尝试点击续期按钮...")
        js_click_code = """
        var renewBtn = document.querySelector('.projects-card-expiry button.client-btn');
        if (renewBtn) {
            renewBtn.click();
            return true;
        }
        return false;
        """
        clicked = False
        try:
            clicked = driver.run_js(js_click_code)
        except Exception as e:
            print(f"⚠️ 点击续期报错: {e}")

        if clicked:
            print("⏳ 等待页面刷新...")
            driver.sleep(8)
            new_expire_time_text = expire_time_text
            try:
                new_time = driver.get_text(".projects-expiry-value")
                if new_time:
                    new_expire_time_text = new_time
                    with open("next_time.txt", "w", encoding="utf-8") as f:
                        f.write(new_expire_time_text)
            except Exception as e:
                pass

            driver.save_screenshot(screenshot_name)
            msg = (
                "🟢 <b>续期执行成功！</b>\n\n"
                f"⏱️ <b>操作前时间：</b><code>{expire_time_text}</code>\n"
                f"⏱️ <b>续期后时间：</b><code>{new_expire_time_text}</code>"
            )
            send_tg_message(msg, screenshot_real_path)
        else:
            driver.save_screenshot(screenshot_name)
            send_tg_message(f"🔴 <b>续期异常</b>\n未找到按钮！\n⏱️ <b>时间：</b><code>{expire_time_text}</code>", screenshot_real_path)

    except Exception as e:
        driver.save_screenshot(screenshot_name)
        send_tg_message(f"🔴 <b>代码意外报错</b>\n<code>{str(e)}</code>", screenshot_real_path)

if __name__ == "__main__":
    skybots_renewal_task()
