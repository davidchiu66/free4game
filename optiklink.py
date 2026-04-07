import os
import requests
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ============================================================
# 1. 从 GitHub Secrets (环境变量) 读取敏感配置
# ============================================================
OPTIK_COOKIE = os.environ.get("OPTIK_COOKIE", "")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")

TARGET_URL = "https://optiklink.net/index"
# 使用与抓包数据完全一致的 User-Agent 以降低风控概率
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"

# ============================================================
# 2. 辅助函数：Telegram 推送模块
# ============================================================
def send_tg_message(text: str, photo_path: str = None):
    """
    负责将结果发送到 Telegram。如果有截图路径，则发送图片+文字；否则只发送文字。
    """
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("未配置 Telegram Token 或 Chat ID，无法发送通知。")
        return

    try:
        if photo_path and os.path.exists(photo_path):
            # 发送图片和说明文字
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
            data = {"chat_id": TG_CHAT_ID, "caption": text, "parse_mode": "HTML"}
            with open(photo_path, "rb") as photo_file:
                files = {"photo": photo_file}
                requests.post(url, data=data, files=files, timeout=15)
        else:
            # 仅发送文字
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
            data = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}
            requests.post(url, data=data, timeout=15)
        print("✅ Telegram 通知发送成功！")
    except Exception as e:
        print(f"❌ Telegram 通知发送失败: {e}")

# ============================================================
# 3. 辅助函数：Cookie 解析模块
# ============================================================
def parse_raw_cookies(raw_cookie_str: str) -> list:
    """
    将原生字符串格式的 Cookie 转换为 Playwright 需要的列表字典格式。
    """
    cookies_list = []
    if not raw_cookie_str:
        return cookies_list
    
    # 按照分号拆分多个 cookie 键值对
    for pair in raw_cookie_str.split(';'):
        if '=' in pair:
            name, value = pair.strip().split('=', 1)
            cookies_list.append({
                "name": name, 
                "value": value, 
                "domain": "optiklink.net", 
                "path": "/"
            })
    return cookies_list

# ============================================================
# 4. 主流程：Playwright 自动化测试
# ============================================================
def main():
    # 检查必要的环境变量
    if not OPTIK_COOKIE:
        send_tg_message("❌ <b>登录任务中止</b>\n原因：未在环境变量中读取到 OPTIK_COOKIE。")
        return

    screenshot_file = "result_screenshot.png"

    with sync_playwright() as p:
        # 启动无头浏览器
        browser = p.chromium.launch(headless=True)
        # 创建一个独立的浏览器上下文，并设置 User-Agent
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={'width': 1920, 'height': 1080}
        )

        # 注入我们解析好的 Cookie
        formatted_cookies = parse_raw_cookies(OPTIK_COOKIE)
        context.add_cookies(formatted_cookies)

        page = context.new_page()

        try:
            print(f"🌐 正在访问目标网址: {TARGET_URL}")
            
            # --- 修复点 1：放宽等待条件，并延长最大超时时间到 60 秒 ---
            page.goto(TARGET_URL, timeout=60000, wait_until="load")
            
            # --- 修复点 2：页面加载触发后，额外硬性等待 3 秒，确保现代网页的 JS 渲染出画面 ---
            page.wait_for_timeout(3000)

            # 无论成败先截取屏幕
            page.screenshot(path=screenshot_file)
            
            # --- 校验登录是否成功 ---
            current_url = page.url
            if "login" in current_url.lower():
                # 判定为失败
                fail_msg = (
                    "🔴 <b>Optiklink 登录失败</b>\n\n"
                    "<b>原因</b>：Cookie 可能已过期，页面被重定向到了登录页。\n"
                    f"<b>当前 URL</b>：<code>{current_url}</code>\n"
                    "<b>详情</b>：请查看附带的错误截图。"
                )
                send_tg_message(fail_msg, screenshot_file)
            else:
                # 判定为成功
                success_msg = (
                    "🟢 <b>Optiklink 登录成功</b>\n\n"
                    "<b>状态</b>：Cookie 依然有效，成功进入目标页面。\n"
                    f"<b>当前 URL</b>：<code>{current_url}</code>\n"
                    "<b>详情</b>：请查看附带的网页截图确认运行状态。"
                )
                send_tg_message(success_msg, screenshot_file)

        except PlaywrightTimeoutError:
            # 捕获页面加载超时的特定异常
            try:
                page.screenshot(path=screenshot_file)
            except:
                pass
            timeout_msg = (
                "🔴 <b>Optiklink 登录失败</b>\n\n"
                "<b>原因</b>：页面加载依然超时（超过 60 秒）。\n"
                "<b>详情</b>：请查看附带的超时截图。"
            )
            send_tg_message(timeout_msg, screenshot_file if os.path.exists(screenshot_file) else None)

        except Exception as e:
            # 捕获其他任何未预料的系统错误
            try:
                page.screenshot(path=screenshot_file)
            except:
                pass 
                
            error_msg = (
                "🔴 <b>Optiklink 登录发生严重异常</b>\n\n"
                f"<b>原因</b>：脚本执行报错\n"
                f"<b>错误信息</b>：<code>{str(e)}</code>"
            )
            send_tg_message(error_msg, screenshot_file if os.path.exists(screenshot_file) else None)

        finally:
            # 确保脚本结束时关闭浏览器释放资源
            browser.close()

if __name__ == "__main__":
    main()
