import os
import re
import time
import requests
from botasaurus.browser import browser, Driver

G4FREE_PANEL_COOKIE = os.environ.get("G4FREE_PANEL_COOKIE", "")
ACCOUNT = os.environ.get("G4FREE_ACCOUNT", "")
PASSWORD = os.environ.get("G4FREE_PASSWORD", "")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")
BUSTER_EXTENSION_PATH = os.environ.get("BUSTER_EXTENSION_PATH", "")

PANEL_URL = "https://panel.gaming4free.net/"
LOGIN_URL = "https://panel.gaming4free.net/auth/login"
SCREENSHOT_NAME = "g4free_status.png"
SCREENSHOT_PATH = os.path.join("output", "screenshots", SCREENSHOT_NAME)
POST_SOLVE_WAIT_SECONDS = 18
MAX_CAPTCHA_WAIT_SECONDS = 30
MAX_RECAPTCHA_RETRIES = 3


def log(message: str):
    print(f"[G4FREE] {message}", flush=True)


def send_tg_message(text: str, photo_path: str | None = None):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        log("Telegram is not configured, skipping notification.")
        return

    try:
        if photo_path and os.path.exists(photo_path):
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
            data = {
                "chat_id": TG_CHAT_ID,
                "caption": text,
                "parse_mode": "HTML",
            }
            with open(photo_path, "rb") as photo_file:
                requests.post(
                    url,
                    data=data,
                    files={"photo": photo_file},
                    timeout=30,
                )
        else:
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
            data = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}
            requests.post(url, data=data, timeout=30)
        log("Telegram notification sent.")
    except Exception as exc:
        log(f"Telegram notification failed: {exc}")


def normalize_stage_name(stage: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "_", stage.strip().lower())
    return normalized.strip("_") or "status"


def save_status_screenshot(driver: Driver, stage: str = "status") -> str | None:
    filename = f"{normalize_stage_name(stage)}.png"
    screenshot_path = os.path.join("output", "screenshots", filename)

    try:
        os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
        driver.save_screenshot(screenshot_path)
        try:
            driver.save_screenshot(SCREENSHOT_PATH)
        except Exception:
            pass
        log(f"Saved screenshot: {screenshot_path}")
        return screenshot_path
    except Exception as exc:
        log(f"Failed to save screenshot to {screenshot_path}: {exc}")

    try:
        driver.save_screenshot(SCREENSHOT_NAME)
        return SCREENSHOT_NAME
    except Exception as exc:
        log(f"Failed to save fallback screenshot: {exc}")
        return None


def inject_cookies(driver: Driver, raw_cookie_str: str, target_domain: str):
    if not raw_cookie_str:
        return

    log(f"Injecting cookies for {target_domain}")
    driver.get(f"https://{target_domain}/404_init_cookie")

    cookies_list = []
    for pair in raw_cookie_str.split(";"):
        if "=" not in pair:
            continue
        name, value = pair.strip().split("=", 1)
        cookies_list.append(
            {"name": name, "value": value, "domain": target_domain, "path": "/"}
        )

    try:
        if hasattr(driver, "add_cookies"):
            driver.add_cookies(cookies_list)
        else:
            for cookie in cookies_list:
                driver.run_js(
                    f"document.cookie = '{cookie['name']}={cookie['value']}; domain={cookie['domain']}; path={cookie['path']}';"
                )
        log(f"Cookie injection finished for {target_domain}")
    except Exception as exc:
        log(f"Cookie injection failed for {target_domain}: {exc}")


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def get_page_text(driver: Driver) -> str:
    try:
        return clean_text(
            driver.run_js("return document.body ? document.body.innerText : '';")
        )
    except Exception:
        return ""


def get_total_minutes(time_str: str) -> int:
    if not time_str or time_str == "Unknown":
        return 0

    h_match = re.search(r"(\d+)\s*hour", time_str, re.IGNORECASE)
    m_match = re.search(r"(\d+)\s*minute", time_str, re.IGNORECASE)
    hours = int(h_match.group(1)) if h_match else 0
    minutes = int(m_match.group(1)) if m_match else 0
    return hours * 60 + minutes


def is_login_page(driver: Driver) -> bool:
    try:
        current_url = driver.current_url.lower()
    except Exception:
        current_url = ""

    if "/auth/login" in current_url:
        return True

    try:
        return bool(
            driver.run_js(
                """
                const username = document.querySelector(
                    "input[type='email'], input[name='email'], input[name='username'], input[name='user'], input[autocomplete='username']"
                );
                const password = document.querySelector("input[type='password']");
                const loginButton = Array.from(
                    document.querySelectorAll("button, input[type='submit']")
                ).some((element) => {
                    const text = (element.innerText || element.textContent || element.value || "").trim().toLowerCase();
                    return text.includes("login") || text.includes("sign in");
                });
                return !!(username && password && loginButton);
                """
            )
        )
    except Exception:
        return False


def wait_for_recaptcha_frame(driver: Driver, selector: str, timeout_seconds: int = 20) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if driver.is_element_present(selector):
            return True
        driver.sleep(1)
    return False


def has_recaptcha_anchor_frame(driver: Driver) -> bool:
    return wait_for_recaptcha_frame(driver, "iframe[src*='recaptcha/api2/anchor']", 4)


def has_recaptcha_challenge_frame(driver: Driver) -> bool:
    return wait_for_recaptcha_frame(driver, "iframe[src*='recaptcha/api2/bframe']", 4)


def find_recaptcha_anchor_frame(driver: Driver):
    return driver.select_iframe("iframe[src*='recaptcha/api2/anchor']")


def find_recaptcha_challenge_frame(driver: Driver):
    return driver.select_iframe("iframe[src*='recaptcha/api2/bframe']")


def is_recaptcha_solved(driver: Driver) -> bool:
    try:
        anchor = find_recaptcha_anchor_frame(driver)
        checked = anchor.run_js(
            "return document.querySelector('#recaptcha-anchor')?.getAttribute('aria-checked') === 'true';"
        )
        if checked:
            return True
    except Exception:
        pass

    try:
        token = driver.run_js(
            "return document.querySelector(\"textarea[name='g-recaptcha-response']\")?.value || '';"
        )
        return bool(token and len(token) > 20)
    except Exception:
        return False


def is_audio_challenge_visible(driver: Driver) -> bool:
    if not has_recaptcha_challenge_frame(driver):
        return False

    try:
        challenge = find_recaptcha_challenge_frame(driver)
        return bool(challenge.run_js("return !!document.querySelector('#audio-response');"))
    except Exception:
        return False


def is_visual_challenge_visible(driver: Driver) -> bool:
    if not has_recaptcha_challenge_frame(driver):
        return False

    try:
        challenge = find_recaptcha_challenge_frame(driver)
        return bool(
            challenge.run_js(
                """
                const selectors = [
                    ".rc-imageselect-instructions",
                    ".rc-imageselect-desc-wrapper",
                    ".rc-imageselect-target",
                    ".rc-image-tile-wrapper",
                    "#rc-imageselect"
                ];
                return selectors.some((selector) => !!document.querySelector(selector));
                """
            )
        )
    except Exception:
        return False


def click_recaptcha_checkbox(driver: Driver) -> bool:
    if not wait_for_recaptcha_frame(driver, "iframe[src*='recaptcha/api2/anchor']", 25):
        log("reCAPTCHA anchor frame not found.")
        return False

    try:
        anchor = find_recaptcha_anchor_frame(driver)
        anchor.click("#recaptcha-anchor")
        driver.sleep(3)
        return True
    except Exception as exc:
        log(f"Failed to click reCAPTCHA checkbox: {exc}")
        return False


def switch_recaptcha_to_audio(driver: Driver) -> bool:
    if not wait_for_recaptcha_frame(driver, "iframe[src*='recaptcha/api2/bframe']", 20):
        log("reCAPTCHA challenge frame not found.")
        return False

    for attempt in range(1, 5):
        try:
            challenge = find_recaptcha_challenge_frame(driver)
            if is_audio_challenge_visible(driver):
                log("reCAPTCHA is already in audio mode.")
                return True

            try:
                challenge.click("#recaptcha-audio-button")
            except Exception:
                clicked = challenge.run_js(
                    """
                    const selectors = [
                        "#recaptcha-audio-button",
                        "button[aria-label*='audio' i]",
                        "button[title*='audio' i]",
                        ".rc-button-audio"
                    ];
                    for (const selector of selectors) {
                        const element = document.querySelector(selector);
                        if (element) {
                            element.click();
                            return true;
                        }
                    }

                    const buttons = Array.from(document.querySelectorAll("button"));
                    for (const button of buttons) {
                        const text = (button.innerText || button.textContent || "").toLowerCase();
                        if (text.includes("audio")) {
                            button.click();
                            return true;
                        }
                    }
                    return false;
                    """
                )
                if not clicked:
                    raise RuntimeError("Audio button was not found.")

            driver.sleep(3)
            if is_audio_challenge_visible(driver):
                log(f"Switched reCAPTCHA to audio mode on attempt {attempt}.")
                return True
        except Exception as exc:
            log(f"Audio mode switch attempt {attempt} failed: {exc}")
            if not is_visual_challenge_visible(driver) and not is_audio_challenge_visible(driver):
                driver.sleep(2)
        driver.sleep(2)

    return False


def trigger_buster_solver(driver: Driver) -> bool:
    for attempt in range(1, 9):
        try:
            challenge = find_recaptcha_challenge_frame(driver)
            try:
                challenge.click("#solver-button")
                log("Buster solver button clicked.")
                driver.sleep(POST_SOLVE_WAIT_SECONDS)
                return True
            except Exception:
                clicked = challenge.run_js(
                    """
                    const solver = document.querySelector("#solver-button");
                    if (solver) {
                        solver.click();
                        return true;
                    }
                    const alt = document.querySelector("[title*='Buster'], [aria-label*='Buster']");
                    if (alt) {
                        alt.click();
                        return true;
                    }
                    return false;
                    """
                )
                if clicked:
                    log("Buster solver button clicked through JS fallback.")
                    driver.sleep(POST_SOLVE_WAIT_SECONDS)
                    return True
        except Exception as exc:
            log(f"Buster solver attempt {attempt} failed: {exc}")
        driver.sleep(2)

    log("Buster solver button was not available.")
    return False


def solve_recaptcha_with_buster_once(driver: Driver) -> bool:
    if is_recaptcha_solved(driver):
        return True

    if has_recaptcha_anchor_frame(driver) and not click_recaptcha_checkbox(driver):
        return False

    driver.sleep(4)
    if is_recaptcha_solved(driver):
        log("reCAPTCHA solved by checkbox only.")
        return True

    if has_recaptcha_challenge_frame(driver) or wait_for_recaptcha_frame(
        driver, "iframe[src*='recaptcha/api2/bframe']", 10
    ):
        if is_visual_challenge_visible(driver) and not switch_recaptcha_to_audio(driver):
            log("Failed to switch visual challenge to audio mode.")
            return False
        if not is_audio_challenge_visible(driver):
            log("Audio challenge is not visible after switch attempt.")
            return False
        if not trigger_buster_solver(driver):
            return False

        deadline = time.time() + MAX_CAPTCHA_WAIT_SECONDS
        while time.time() < deadline:
            if is_recaptcha_solved(driver):
                log("reCAPTCHA solved by Buster.")
                return True
            driver.sleep(2)
        log("Timed out waiting for Buster to solve reCAPTCHA.")
        return False

    return is_recaptcha_solved(driver)


def solve_recaptcha_with_retries(driver: Driver, stage: str, reset_action=None) -> bool:
    for attempt in range(1, MAX_RECAPTCHA_RETRIES + 1):
        if attempt > 1 and reset_action:
            log(f"Resetting page state for {stage}, attempt {attempt}.")
            if not reset_action():
                save_status_screenshot(driver, f"{stage}_reset_failed_attempt_{attempt}")
                return False

        log(f"Starting reCAPTCHA solve for {stage}, attempt {attempt}/{MAX_RECAPTCHA_RETRIES}.")
        save_status_screenshot(driver, f"{stage}_recaptcha_attempt_{attempt}_before")

        solved = solve_recaptcha_with_buster_once(driver)
        if solved:
            save_status_screenshot(driver, f"{stage}_recaptcha_attempt_{attempt}_after")
            log(f"reCAPTCHA solved for {stage} on attempt {attempt}.")
            return True

        save_status_screenshot(driver, f"{stage}_recaptcha_attempt_{attempt}_failed")
        log(f"reCAPTCHA solve failed for {stage} on attempt {attempt}.")

    return False


def type_first_matching(driver: Driver, selectors: list[str], value: str) -> bool:
    for selector in selectors:
        try:
            if driver.is_element_present(selector):
                driver.type(selector, value)
                return True
        except Exception:
            continue
    return False


def click_login_button(driver: Driver) -> bool:
    try:
        return bool(
            driver.run_js(
                """
                const selectors = [
                    "button[type='submit']",
                    "input[type='submit']"
                ];

                for (const selector of selectors) {
                    const element = document.querySelector(selector);
                    if (element) {
                        element.click();
                        return true;
                    }
                }

                const buttons = Array.from(document.querySelectorAll("button, a, [role='button']"));
                for (const button of buttons) {
                    const text = (button.innerText || button.textContent || button.value || "").trim().toLowerCase();
                    if (text === "login" || text.includes("login") || text.includes("sign in")) {
                        button.click();
                        return true;
                    }
                }

                const form = document.querySelector("form");
                if (form) {
                    form.submit();
                    return true;
                }
                return false;
                """
            )
        )
    except Exception as exc:
        log(f"Failed to submit login form: {exc}")
        return False


def prepare_login_form(driver: Driver, stage: str = "login_page_loaded") -> bool:
    driver.get(LOGIN_URL)
    driver.sleep(4)
    save_status_screenshot(driver, stage)

    username_selectors = [
        "input[type='email']",
        "input[name='email']",
        "input[name='username']",
        "input[name='user']",
        "input[autocomplete='username']",
        "form input:not([type='password'])",
    ]
    password_selectors = [
        "input[type='password']",
        "input[name='password']",
        "input[autocomplete='current-password']",
    ]

    if not type_first_matching(driver, username_selectors, ACCOUNT):
        log("Username/email input was not found.")
        save_status_screenshot(driver, "login_missing_username_input")
        return False
    if not type_first_matching(driver, password_selectors, PASSWORD):
        log("Password input was not found.")
        save_status_screenshot(driver, "login_missing_password_input")
        return False

    save_status_screenshot(driver, "login_credentials_filled")
    return True


def login_with_account_password(driver: Driver) -> bool:
    if not ACCOUNT or not PASSWORD:
        log("Account/password are not configured, cannot fall back to form login.")
        return False

    log("Falling back to account/password login.")
    if not prepare_login_form(driver):
        return False

    recaptcha_present = has_recaptcha_anchor_frame(driver) or has_recaptcha_challenge_frame(driver)
    if recaptcha_present:
        log("reCAPTCHA detected on login page, switching to audio mode and invoking Buster.")
        if not solve_recaptcha_with_retries(
            driver,
            "login",
            reset_action=lambda: prepare_login_form(driver, "login_page_reloaded"),
        ):
            log("Failed to solve login reCAPTCHA.")
            save_status_screenshot(driver, "login_recaptcha_failed")
            return False

    if not click_login_button(driver):
        log("Login button was not found.")
        save_status_screenshot(driver, "login_button_not_found")
        return False

    save_status_screenshot(driver, "login_submitted")
    driver.sleep(8)
    save_status_screenshot(driver, "login_after_submit")

    if is_login_page(driver) and (has_recaptcha_anchor_frame(driver) or has_recaptcha_challenge_frame(driver)):
        log("Still on login page after submit, retrying once with reCAPTCHA solve flow.")
        save_status_screenshot(driver, "login_still_on_login_page")
        if not solve_recaptcha_with_retries(
            driver,
            "login_post_submit",
            reset_action=lambda: prepare_login_form(driver, "login_post_submit_reloaded"),
        ):
            return False
        if not click_login_button(driver):
            save_status_screenshot(driver, "login_retry_button_not_found")
            return False
        save_status_screenshot(driver, "login_retry_submitted")
        driver.sleep(8)
        save_status_screenshot(driver, "login_retry_after_submit")

    return not is_login_page(driver)


def ensure_panel_logged_in(driver: Driver) -> bool:
    if G4FREE_PANEL_COOKIE:
        inject_cookies(driver, G4FREE_PANEL_COOKIE, "panel.gaming4free.net")
    else:
        log("G4FREE_PANEL_COOKIE is empty, cookie login will be skipped.")

    log(f"Opening panel: {PANEL_URL}")
    driver.get(PANEL_URL)
    driver.sleep(6)
    save_status_screenshot(driver, "panel_opened")

    if not is_login_page(driver):
        log("Panel cookie login succeeded.")
        save_status_screenshot(driver, "panel_cookie_login_success")
        return True

    log("Panel cookie login failed, panel redirected to login page.")
    save_status_screenshot(driver, "panel_cookie_login_failed")
    return login_with_account_password(driver)


def click_first_matching_link(driver: Driver, snippets: list[str], exact_match: bool = False) -> bool:
    snippets_js = "[" + ", ".join(repr(item.lower()) for item in snippets) + "]"
    matcher = "text === snippet" if exact_match else "text.includes(snippet)"
    js = f"""
    const snippets = {snippets_js};
    const links = Array.from(document.querySelectorAll('a, button, [role="button"]'));
    for (const link of links) {{
        const text = (link.innerText || link.textContent || '').trim().toLowerCase();
        if (!text) continue;
        if (snippets.some((snippet) => {matcher})) {{
            link.removeAttribute('target');
            link.click();
            return true;
        }}
    }}
    return false;
    """
    try:
        return bool(driver.run_js(js))
    except Exception:
        return False


def click_console_entry(driver: Driver) -> bool:
    if "/console" in driver.current_url.lower():
        save_status_screenshot(driver, "console_already_open")
        return True

    for attempt in range(1, 5):
        if click_first_matching_link(driver, ["console"], exact_match=False):
            driver.sleep(6)
            save_status_screenshot(driver, f"console_entry_clicked_attempt_{attempt}")
            return True

        try:
            found = bool(
                driver.run_js(
                    """
                    const links = Array.from(document.querySelectorAll("a"));
                    for (const link of links) {
                        const href = link.getAttribute("href") || "";
                        if (href.endsWith("/console")) {
                            link.click();
                            return true;
                        }
                    }
                    return false;
                    """
                )
            )
            if found:
                driver.sleep(6)
                save_status_screenshot(driver, f"console_entry_href_clicked_attempt_{attempt}")
                return True
        except Exception:
            pass

        driver.run_js("window.scrollBy(0, 500);")
        driver.sleep(2)
        save_status_screenshot(driver, f"console_entry_attempt_{attempt}_not_found")

    return "/console" in driver.current_url.lower()


def click_add_90_minutes(driver: Driver) -> bool:
    try:
        return bool(
            driver.run_js(
                """
                const buttons = Array.from(
                    document.querySelectorAll("button, a, [role='button'], input[type='submit']")
                );
                for (const button of buttons) {
                    const text = (button.innerText || button.textContent || button.value || "").trim().toLowerCase();
                    if (text.includes("add 90 minutes")) {
                        button.click();
                        return true;
                    }
                }
                return false;
                """
            )
        )
    except Exception:
        return False


def prepare_renew_recaptcha(driver: Driver, stage: str = "renew_retriggered") -> bool:
    try:
        driver.run_js("location.reload(true);")
    except Exception:
        pass
    driver.sleep(6)
    save_status_screenshot(driver, f"{stage}_page_reloaded")

    if "/console" not in driver.current_url.lower() and not click_console_entry(driver):
        log("Failed to return to console page while preparing renew retry.")
        save_status_screenshot(driver, f"{stage}_console_missing")
        return False

    if not click_add_90_minutes(driver):
        log("Failed to click 'Add 90 Minutes' while preparing renew retry.")
        save_status_screenshot(driver, f"{stage}_button_missing")
        return False

    driver.sleep(4)
    save_status_screenshot(driver, stage)
    return True


def get_remaining_time(driver: Driver) -> str:
    html_source = driver.page_html

    patterns = [
        r"suspended.*?in\s*<strong[^>]*>(.*?)</strong>",
        r"remaining.*?<strong[^>]*>(.*?)</strong>",
        r"expires?.*?<strong[^>]*>(.*?)</strong>",
    ]
    for pattern in patterns:
        match = re.search(pattern, html_source, re.IGNORECASE | re.DOTALL)
        if match:
            return clean_text(match.group(1))

    text = get_page_text(driver)
    fallback = re.search(
        r"(?:suspended|remaining|expires?)\s*(?:in|:)\s*(.+?)(?:$|\n)",
        text,
        re.IGNORECASE,
    )
    if fallback:
        return clean_text(fallback.group(1))

    return "Unknown"


class BusterExtension:
    def __init__(self, extension_path: str):
        self.extension_path = os.path.abspath(extension_path)

    def load(self, with_command_line_option=True):
        if with_command_line_option:
            return f"--load-extension={self.extension_path}"
        return self.extension_path

    @property
    def extension_absolute_path(self):
        return self.extension_path


def get_extensions():
    if BUSTER_EXTENSION_PATH and os.path.exists(BUSTER_EXTENSION_PATH):
        return [BusterExtension(BUSTER_EXTENSION_PATH)]
    return []


@browser(
    headless=False,
    window_size=(1920, 1080),
    extensions=get_extensions(),
)
def g4free_renewal_task(driver: Driver, data):
    del data

    try:
        log("Browser started with Buster extension flow.")
        save_status_screenshot(driver, "browser_started")

        if not ensure_panel_logged_in(driver):
            screenshot = save_status_screenshot(driver, "panel_login_failed_final")
            send_tg_message(
                "<b>Gaming4Free panel login failed</b>\nCould not log in with panel cookie or account/password.",
                screenshot,
            )
            return

        log("Panel login succeeded, continuing with the original panel flow.")
        save_status_screenshot(driver, "panel_login_success")

        if not click_console_entry(driver):
            screenshot = save_status_screenshot(driver, "console_entry_failed")
            send_tg_message(
                "<b>Gaming4Free panel flow failed</b>\nConsole entry was not found after panel login.",
                screenshot,
            )
            return

        time_before = get_remaining_time(driver)
        minutes_before = get_total_minutes(time_before)
        log(f"Remaining time before renew: {time_before}")
        save_status_screenshot(driver, "renew_before_click")

        if not click_add_90_minutes(driver):
            screenshot = save_status_screenshot(driver, "renew_button_not_found")
            send_tg_message(
                "<b>Gaming4Free renew failed</b>\nThe 'Add 90 Minutes' button was not found.",
                screenshot,
            )
            return

        driver.sleep(4)
        save_status_screenshot(driver, "renew_after_click")

        if has_recaptcha_anchor_frame(driver) or has_recaptcha_challenge_frame(driver):
            log("reCAPTCHA detected during renew, switching to audio mode and invoking Buster.")
            save_status_screenshot(driver, "renew_recaptcha_detected")
            if not solve_recaptcha_with_retries(
                driver,
                "renew",
                reset_action=lambda: prepare_renew_recaptcha(driver),
            ):
                screenshot = save_status_screenshot(driver, "renew_recaptcha_failed")
                send_tg_message(
                    "<b>Gaming4Free renew failed</b>\nreCAPTCHA was detected but audio-mode solving did not succeed.",
                    screenshot,
                )
                return
        else:
            log("No reCAPTCHA detected after clicking 'Add 90 Minutes'.")
            save_status_screenshot(driver, "renew_no_recaptcha")

        log("Waiting 90 seconds for the ad/renew cycle to finish.")
        driver.sleep(90)
        save_status_screenshot(driver, "renew_wait_finished")

        log("Refreshing console page to verify the new remaining time.")
        driver.run_js("location.reload(true);")
        driver.sleep(6)
        driver.run_js("location.reload(true);")
        driver.sleep(8)
        save_status_screenshot(driver, "renew_after_refresh")

        time_after = get_remaining_time(driver)
        minutes_after = get_total_minutes(time_after)
        log(f"Remaining time after renew: {time_after}")

        screenshot = save_status_screenshot(driver, "renew_final_result")

        if minutes_after > minutes_before + 3:
            send_tg_message(
                "<b>Gaming4Free renew succeeded</b>\n\n"
                f"<b>Before:</b> <code>{time_before}</code>\n"
                f"<b>After:</b> <code>{time_after}</code>",
                screenshot,
            )
        else:
            send_tg_message(
                "<b>Gaming4Free renew may have failed</b>\n\n"
                "The renew flow completed, but the remaining time did not increase clearly.\n"
                f"<b>Before:</b> <code>{time_before}</code>\n"
                f"<b>After:</b> <code>{time_after}</code>",
                screenshot,
            )

    except Exception as exc:
        screenshot = save_status_screenshot(driver, "script_exception")
        send_tg_message(
            f"<b>Gaming4Free script error</b>\n<code>{str(exc)}</code>",
            screenshot,
        )


if __name__ == "__main__":
    g4free_renewal_task()
