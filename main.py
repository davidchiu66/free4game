import os
import time
import json
import requests
from playwright.sync_api import sync_playwright

# 1. 从环境变量获取配置
SERVER_ID = os.environ.get("SERVER_ID")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
USER_COOKIES = os.environ.get("USER_COOKIES")

# 2. 定义固定的 User-Agent
CUSTOM_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"

def send_tg_message(message: str):
    """发送 Telegram 消息"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("未配置 Telegram Token 或 Chat ID，跳过通知。")
        return
    
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print("TG推送成功")
    except Exception as e:
        print(f"TG推送失败: {e}")

def run_automation():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # ---------------------------------------------------------
        # 关键更新：在创建上下文时，注入自定义的 User-Agent
        # ---------------------------------------------------------
        print(f"创建浏览器上下文，使用 User-Agent: {CUSTOM_USER_AGENT}")
        context = browser.new_context(user_agent=CUSTOM_USER_AGENT)

        # 解析并注入 Cookie
        if USER_COOKIES:
            try:
                print("正在解析并注入 Cookie...")
                cookies_list = json.loads(USER_COOKIES)
                context.add_cookies(cookies_list)
                print("✅ Cookie 注入成功！")
            except json.JSONDecodeError:
                print("❌ Cookie 解析失败！请确保 USER_COOKIES 是合法的 JSON 格式。")
            except Exception as e:
                print(f"❌ 注入 Cookie 时发生未知错误: {e}")
        else:
            print("⚠️ 未找到 USER_COOKIES 环境变量，将尝试以未登录状态访问。")

        # 使用已配置好的上下文创建新页面
        page = context.new_page()

        try:
            target_url = f"https://panel.gaming4free.net/server/{SERVER_ID}/console"
            page.goto(target_url)
            print(f"打开服务器页面: {target_url}")

            print("查找续期按钮...")
            renew_button = page.get_by_role("button", name="Add 90 Minutes", exact=True)
            
            # 等待按钮在页面上变为可见状态
            renew_button.wait_for(state="visible", timeout=15000)
            
            print("点击「Add 90 Minutes」按钮...")
            renew_button.click()
            
            print("正在等待 45 秒...")
            time.sleep(45) 
            
            print("时间到，正在刷新页面以确认状态...")
            page.reload()
            page.wait_for_load_state('networkidle')
            print("页面刷新完成！")

            send_tg_message(f"✅ 服务器 `{SERVER_ID}` 续期任务执行完成。")

        except Exception as e:
            error_msg = f"❌ 自动化任务执行失败: {str(e)}"
            print(error_msg)
            send_tg_message(error_msg)
            
        finally:
            browser.close()

if __name__ == "__main__":
    run_automation()
