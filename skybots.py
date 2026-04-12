import os
import re
import requests
from botasaurus.browser import browser, Driver

# ============================================================
# 1. 环境变量配置 (保持不变)
# ============================================================
ACCOUNT = os.environ.get("SKYBOTS_ACCOUNT", "")
PASSWORD = os.environ.get("SKYBOTS_PASSWORD", "")
SKYBOTS_COOKIE = os.environ.get("SKYBOTS_USER_COOKIES", "")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")

LOGIN_URL = "https://dash.skybots.tech/login"
DASHBOARD_URL = "https://dash.skybots.tech/projects"

# ... [保留原本的 send_tg_message 和 inject_cookies 函数不变] ...

# ============================================================
# 新增辅助函数：智能处理自定义验证码 (加强防御版)
# ============================================================
def handle_custom_captcha(driver: Driver):
    """
    点击验证码并智能等待其通过验证
    增加拟人延迟、双重点击触发和超长等待机制
    """
    print("☑️ 尝试定位并智能处理验证码...")
    try:
        # 1. 检查验证码元素是否存在
        has_captcha = driver.run_js("return !!document.querySelector('.auth-captcha-inner');")
        if not has_captcha:
            print("ℹ️ 页面上未检测到验证码，跳过验证步骤。")
            return True

        # 2. 模拟人类行为：页面加载后稍微停顿，避免秒点被识别为机器人
        print("⏳ 正在等待验证码前端脚本初始化...")
        driver.sleep(2)

        # 3. 执行点击 (加入异常兜底策略)
        print("👆 正在模拟点击验证码...")
        try:
            # 尝试标准模拟点击
            driver.click(".auth-captcha-inner")
        except Exception as e:
            print(f"⚠️ 常规点击失效，触发 JS 强行点击: {e}")
            # 如果标准点击被遮挡或失效，使用 JS 直接点击 DOM
            driver.run_js("document.querySelector('.auth-captcha-inner').click();")

        # 4. 延长动态等待时间 (上限 25 秒)，应对 Actions 网络延迟和后台计算
        max_wait = 25
        for i in range(max_wait):
            driver.sleep(1) # 每次循环等待 1 秒
            
            # 使用健壮的 JS 脚本获取状态，避免元素刷新导致 None 报错
            is_checked = driver.run_js("""
                var el = document.querySelector('.auth-captcha-inner');
                return el ? el.getAttribute('aria-checked') === 'true' : false;
            """)
            
            if is_checked:
                print(f"✅ 验证码已成功勾选！(耗时约 {i+1} 秒)")
                driver.sleep(1) # 验证通过后再缓冲 1 秒，让页面完全接收状态
                return True
                
        print(f"⚠️ 等待了 {max_wait} 秒，验证码仍未变绿。可能是遇到了视觉拼图挑战或环境被严重拦截。")
        return False
        
    except Exception as e:
        print(f"⚠️ 处理验证码时发生意外错误: {e}")
        return False
        
# ============================================================
# 4. 核心任务：续期监控与执行 (修改后的逻辑)
# ============================================================
@browser(headless=True, window_size=(1920, 1080))
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
            print("⚠️ Cookie 已失效或需要设置密码，触发账号密码兜底登录...")

            # --- 密码设置页面逻辑 ---
            if "setup-password" in current_url_lower:
                print("🔐 检测到密码设置页面，正在输入密码...")
                password_inputs = driver.get_elements('input[type="password"]')
                for i, inp in enumerate(password_inputs):
                    if i < 2:  
                        inp.type(PASSWORD)
                        driver.sleep(1)
                
                # 【修改点】调用智能验证码处理函数
                handle_custom_captcha(driver)
                
                driver.click('button[type="submit"]')
                driver.sleep(10)
                current_url_lower = driver.current_url.lower()

            # --- 常规登录逻辑 ---
            if "login" in current_url_lower:
                print("🔐 检测到登录页面，正在输入凭据...")
                captcha_retry = 0
                max_captcha_retry = 6
                login_success = False

                while captcha_retry < max_captcha_retry and not login_success:
                    captcha_retry += 1
                    print(f"🔄 第 {captcha_retry}/{max_captcha_retry} 次尝试登录...")

                    driver.type('#username, input[name="username"]', ACCOUNT)
                    driver.sleep(0.5)
                    driver.type('#password, input[name="password"]', PASSWORD)
                    driver.sleep(0.5)
                    
                    # 【修改点】调用智能验证码处理函数
                    captcha_passed = handle_custom_captcha(driver)
                    
                    if not captcha_passed:
                        print("⚠️ 验证码未通过判定，但仍尝试提交碰碰运气...")
                    
                    driver.click('button[type="submit"]')
                    driver.sleep(10) # 等待登录结果跳转
                    
                    current_url_lower = driver.current_url.lower()

                    if "login" not in current_url_lower and "setup-password" not in current_url_lower:
                        login_success = True
                        print("✅ 登录成功！")
                        break

                    print("⚠️ 登录失败，刷新页面重新尝试...")
                    driver.get(LOGIN_URL)
                    driver.sleep(6)

                if not login_success:
                    driver.save_screenshot(screenshot_name)
                    send_tg_message(
                        "🔴 <b>chinamen登录失败</b>\n验证码尝试6次均失败，请检查截图确认是否遇到盾或网络问题。",
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
