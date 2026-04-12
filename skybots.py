import os
import re
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

LOGIN_URL = "https://dash.skybots.tech/login"
DASHBOARD_URL = "https://dash.skybots.tech/projects"


# ============================================================
# 2. 辅助函数：Telegram 图片推送
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
            print("📨 Telegram 图文状态反馈发送成功！")
        else:
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
            data = {
                "chat_id": TG_CHAT_ID,
                "text": f"🤖 [Skybots 守护者]\n{text}",
                "parse_mode": "HTML",
            }
            requests.post(url, data=data, timeout=30)
            print("📨 Telegram 纯文本状态反馈发送成功！")
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
# 4. 核心任务：续期监控与执行
# ============================================================
@browser(headless=True, window_size=(1920, 1080))
def skybots_renewal_task(driver: Driver, data):
    screenshot_name = "skybots_status.png"
    screenshot_real_path = os.path.join("output", "screenshots", screenshot_name)

    try:
        # 第一阶段：注入 Cookie 并访问
        if SKYBOTS_COOKIE:
            inject_cookies(driver, SKYBOTS_COOKIE)

        print(f"🌐 访问控制台面板: {DASHBOARD_URL}")
        driver.get(DASHBOARD_URL)
        driver.sleep(8)

        # 第二阶段：Cookie 失效兜底判定
        current_url_lower = driver.current_url.lower()
        if "login" in current_url_lower or "setup-password" in current_url_lower:
            print("⚠️ Cookie 已失效或需要设置密码，触发账号密码兜底登录...")

            # 检查是否是 setup-password 页面（首次登录或密码过期）
            if "setup-password" in current_url_lower:
                print("🔐 检测到密码设置页面，正在输入密码...")
                # 在两个密码框输入相同密码
                password_inputs = driver.get_elements('input[type="password"]')
                for i, inp in enumerate(password_inputs):
                    if i < 2:  # 只处理前两个密码框
                        inp.type(PASSWORD)
                        driver.sleep(1)
                driver.sleep(2)
                # 点击验证码复选框（如果存在）
                try:
                    captcha = driver.get_element(
                        ".auth-captcha-box, .auth-captcha-inner"
                    )
                    if captcha:
                        driver.click(".auth-captcha-box, .auth-captcha-inner")
                        driver.sleep(2)
                except:
                    pass
                # 点击提交按钮
                driver.click('button[type="submit"]')
                driver.sleep(10)
                # 检查跳转后的 URL
                current_url_lower = driver.current_url.lower()
            # 常规登录流程
            if "login" in current_url_lower:
                print("🔐 检测到登录页面，正在输入凭据...")
                captcha_retry = 0
                max_captcha_retry = 6
                login_success = False

                while captcha_retry < max_captcha_retry and not login_success:
                    captcha_retry += 1
                    print(f"☑️ 尝试点击验证码 ({captcha_retry}/{max_captcha_retry})...")

                    # 输入用户名
                    driver.type('#username, input[name="username"]', ACCOUNT)
                    driver.sleep(0.5)
                    # 输入密码
                    driver.type('#password, input[name="password"]', PASSWORD)
                    driver.sleep(0.5)
                    # 点击验证码复选框
                    driver.click(".auth-captcha-box, .auth-captcha-inner")
                    driver.sleep(3)
                    # 点击提交按钮
                    driver.click('button[type="submit"]')
                    driver.sleep(10)
                    current_url_lower = driver.current_url.lower()

                    # 检查是否成功登录（不再在 login 页面）
                    if (
                        "login" not in current_url_lower
                        and "setup-password" not in current_url_lower
                    ):
                        login_success = True
                        print("✅ 登录成功！")
                        break

                    print(f"⚠️ 验证码尝试 {captcha_retry} 失败，重试中...")
                    # 刷新页面重新尝试
                    driver.get(LOGIN_URL)
                    driver.sleep(6)

                if not login_success:
                    driver.save_screenshot(screenshot_name)
                    send_tg_message(
                        "🔴 <b>登录失败</b>\n验证码尝试 6 次均失败，请检查截图。",
                        screenshot_real_path,
                    )
                    return

        # 第三阶段：利用精确的 CSS 类名提取时间信息
        print("✅ 成功进入面板，正在精准提取服务器时间信息...")
        driver.sleep(8)

        expire_time_text = "未知"
        try:
            # 直接通过源码中的 class 名称精准提取，无需正则！
            expire_time_text = driver.get_text(".projects-expiry-value")
            if expire_time_text:
                print(f"⏱️ 精准抓取到的剩余时间: {expire_time_text}")
                with open("next_time.txt", "w", encoding="utf-8") as f:
                    f.write(expire_time_text)
        except Exception as e:
            print(f"⚠️ 无法通过精确选择器获取时间: {e}")

        # 第四阶段：续期业务逻辑判定
        # 获取页面所有文本用于判断警告提示
        page_text_lower = ""
        try:
            page_text_lower = driver.get_text("body").lower()
        except:
            pass

        # 检查是否包含法语 "2 heures avant" 或英语 "2 hours before"
        if "2 heures avant" in page_text_lower or "2 hours before" in page_text_lower:
            driver.save_screenshot(screenshot_name)
            msg = f"⏰ <b>暂无续期资格</b>\n\n提示：距离到期还有 2 小时以上。\n⏱️ <b>剩余时间：</b><code>{expire_time_text}</code>"
            send_tg_message(msg, screenshot_real_path)
            print("⏰ 尚未达到续期时间条件，任务正常结束。")
            return

        # 状态 B：时间已到，利用源码特征精准查找并点击
        print("🔍 正在通过精确 CSS 结构锁定续期按钮...")

        # 使用基于你提供的 HTML 结构编写的精准点击脚本
        js_click_code = """
        // 直接寻找 .projects-card-expiry 容器下的 .client-btn 按钮
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
            print(f"⚠️ 执行精准点击脚本时发生小意外: {e}")

        if clicked:
            print("⏳ 等待续期请求处理与页面刷新...")
            # 给足 8 秒钟等待网页前端完成异步数据请求和 DOM 更新
            driver.sleep(8)

            # --- 核心优化点：重新抓取刷新后的最新时间 ---
            print("🔄 正在获取续期后的最新时间...")
            new_expire_time_text = expire_time_text  # 默认使用旧时间兜底
            try:
                new_time = driver.get_text(".projects-expiry-value")
                if new_time:
                    new_expire_time_text = new_time
                    print(f"⏱️ 续期后最新时间已更新为: {new_expire_time_text}")
                    # 将续期后的最新时间覆盖写入文件，供 Actions 后续可能的使用
                    with open("next_time.txt", "w", encoding="utf-8") as f:
                        f.write(new_expire_time_text)
            except Exception as e:
                print(f"⚠️ 无法获取刷新后的最新时间: {e}")
            # --------------------------------------------

            driver.save_screenshot(screenshot_name)
            # 消息模板更新：同时展示操作前后对比
            msg = (
                "🟢 <b>续期执行成功！</b>\n\n"
                "按键已被精确锁定并成功点击。\n"
                f"⏱️ <b>操作前时间：</b><code>{expire_time_text}</code>\n"
                f"⏱️ <b>续期后时间：</b><code>{new_expire_time_text}</code>"
            )
            send_tg_message(msg, screenshot_real_path)
        else:
            driver.save_screenshot(screenshot_name)
            msg = f"🔴 <b>续期操作异常</b>\n\n未能通过结构定位到按钮，页面结构可能发生了改变，请核实截图！\n⏱️ <b>剩余时间：</b><code>{expire_time_text}</code>"
            send_tg_message(msg, screenshot_real_path)

    except Exception as e:
        driver.save_screenshot(screenshot_name)
        send_tg_message(
            f"🔴 <b>脚本发生意外报错</b>\n\n<b>错误详情：</b>\n<code>{str(e)}</code>",
            screenshot_real_path,
        )


if __name__ == "__main__":
    skybots_renewal_task()
