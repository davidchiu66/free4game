const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
const { execSync } = require('child_process');

const DASHBOARD_URL = 'https://gaming4free.net/dashboard';

const COOKIE = process.env.G4FREE_USER_COOKIE || '';
const PANEL_COOKIE = process.env.G4FREE_PANEL_COOKIE || '';
const ACCOUNT = process.env.G4FREE_ACCOUNT || '';
const PASSWORD = process.env.G4FREE_PASSWORD || '';
const TG_BOT_TOKEN = process.env.TG_BOT_TOKEN || '';
const TG_CHAT_ID = process.env.TG_CHAT_ID || '';
const BUSTER_EXTENSION_PATH = process.env.BUSTER_EXTENSION_PATH || path.join(__dirname, 'extensions', 'buster', 'unpacked');

function getTotalMinutes(timeStr) {
    if (!timeStr || timeStr === '未知') return 0;
    const hoursMatch = timeStr.match(/(\d+)\s*hour/i);
    const minutesMatch = timeStr.match(/(\d+)\s*minute/i);
    const hours = hoursMatch ? parseInt(hoursMatch[1]) : 0;
    const minutes = minutesMatch ? parseInt(minutesMatch[1]) : 0;
    return hours * 60 + minutes;
}

async function sendTgMessage(text, photoPath = null) {
    if (!TG_BOT_TOKEN || !TG_CHAT_ID) {
        console.log('⚠️ 未配置 Telegram Token 或 Chat ID，跳过消息推送。');
        console.log(`   TG_BOT_TOKEN: ${TG_BOT_TOKEN ? '已设置' : '未设置'}`);
        console.log(`   TG_CHAT_ID: ${TG_CHAT_ID ? '已设置' : '未设置'}`);
        return;
    }
    
    const tgUrl = `https://api.telegram.org/bot${TG_BOT_TOKEN}`;
    
    if (photoPath && fs.existsSync(photoPath)) {
        console.log(`📸 准备发送截图: ${photoPath}`);
        try {
            const captionText = `🎮\n${text}`;
            
            const cmd = `curl -s -X POST "${tgUrl}/sendPhoto" -F "chat_id=${TG_CHAT_ID}" -F "photo=@${photoPath};type=image/png" -F "caption=${captionText}" -F "parse_mode=HTML"`;
            console.log(`📸 执行命令: ${cmd}`);
            
            const output = execSync(cmd, { encoding: 'utf8' });
            console.log(`📸 curl 输出: ${output}`);
            
            const result = JSON.parse(output);
            console.log(`📨 TG API 响应: ${JSON.stringify(result)}`);
            
            if (result.ok) {
                console.log('📨 Telegram 截图发送成功！');
            } else {
                console.log(`❌ Telegram 截图发送失败: ${result.description}`);
                await sendTgMessageTextOnly(text);
            }
        } catch (e) {
            console.log(`❌ Telegram 发送异常: ${e.message}`);
            await sendTgMessageTextOnly(text);
        }
    } else {
        await sendTgMessageTextOnly(text);
    }
}

async function sendTgMessageTextOnly(text) {
    try {
        const response = await fetch(`https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                chat_id: TG_CHAT_ID,
                text: `🎮\n${text}`,
                parse_mode: 'HTML'
            })
        });
        const result = await response.json();
        if (result.ok) {
            console.log('📨 Telegram 文本消息发送成功！');
        } else {
            console.log(`❌ Telegram 文本消息发送失败: ${result.description}`);
        }
    } catch (e) {
        console.log(`❌ Telegram 文本消息发送失败: ${e.message}`);
    }
}

async function injectCookies(page, cookieStr, domain) {
    if (!cookieStr) return;
    console.log(`🍪 正在初始化并预加载 ${domain} 的环境...`);
    await page.goto(`https://${domain}/404_init_cookie`);
    
    const cookies = [];
    for (const pair of cookieStr.split(';')) {
        if (pair.includes('=')) {
            const [name, ...valueParts] = pair.split('=');
            cookies.push({
                name: name.trim(),
                value: valueParts.join('='),
                domain: domain,
                path: '/'
            });
        }
    }
    await page.context().addCookies(cookies);
    console.log(`✅ ${domain} Cookie 预加载完毕！`);
}

async function closeOverlays(page) {
    const overlays = await page.$$('.fixed.inset-0.z-\\[60\\]');
    for (const overlay of overlays) {
        try {
            await overlay.click({ timeout: 2000 });
            console.log('✅ 已关闭遮罩层');
            await page.waitForTimeout(500);
        } catch {}
    }
    
    const closeBtns = await page.$$('button');
    for (const btn of closeBtns) {
        const text = await btn.textContent();
        if (text && /^(close|x|×|cancel|esc)$/i.test(text.trim())) {
            try {
                await btn.click();
                console.log('✅ 已点击关闭按钮');
                await page.waitForTimeout(500);
            } catch {}
        }
    }
}

async function clickLinkByText(page, searchText, exactMatch = false, retryCount = 3) {
    for (let attempt = 0; attempt < retryCount; attempt++) {
        await closeOverlays(page);
        
        const found = await page.evaluate(({searchText, exactMatch}) => {
            const links = document.querySelectorAll('a');
            for (let i = 0; i < links.length; i++) {
                const text = links[i].innerText || links[i].textContent;
                if (text && (exactMatch ? text.trim().toLowerCase() === searchText.toLowerCase() : text.includes(searchText))) {
                    links[i].removeAttribute('target');
                    links[i].click();
                    return true;
                }
            }
            return false;
        }, {searchText, exactMatch});
        
        if (found) {
            console.log(`✅ 找到并点击 "${searchText}"`);
            try {
                await page.waitForLoadState('networkidle', { timeout: 10000 });
                console.log(`✅ 页面加载完成: ${page.url()}`);
            } catch (e) {
                console.log(`⚠️ 等待网络空闲超时，继续执行...`);
            }
            return true;
        }
        console.log(`⚠️ 第 ${attempt + 1} 次未找到 "${searchText}"，重试中...`);
        await page.waitForTimeout(1000);
    }
    return false;
}

async function clickLinkByHref(page, hrefEnd, retryCount = 3) {
    for (let attempt = 0; attempt < retryCount; attempt++) {
        await closeOverlays(page);
        
        const found = await page.evaluate(({hrefEnd}) => {
            const links = document.querySelectorAll('a');
            for (let i = 0; i < links.length; i++) {
                const href = links[i].getAttribute('href');
                if (href && href.endsWith(hrefEnd)) {
                    links[i].click();
                    return true;
                }
            }
            return false;
        }, {hrefEnd});
        
        if (found) {
            console.log(`✅ 通过 href 找到并点击 "${hrefEnd}"`);
            try {
                await page.waitForLoadState('networkidle', { timeout: 10000 });
            } catch (e) {}
            return true;
        }
        console.log(`⚠️ 第 ${attempt + 1} 次未找到 href "${hrefEnd}"，重试中...`);
        await page.waitForTimeout(1000);
    }
    return false;
}

async function clickButtonByText(page, searchText, retryCount = 3) {
    for (let attempt = 0; attempt < retryCount; attempt++) {
        await closeOverlays(page);
        
        const found = await page.evaluate(({searchText}) => {
            const btns = document.querySelectorAll('button');
            for (let i = 0; i < btns.length; i++) {
                const text = btns[i].innerText || btns[i].textContent;
                if (text && text.toLowerCase().includes(searchText.toLowerCase())) {
                    btns[i].click();
                    return true;
                }
            }
            return false;
        }, {searchText});
        
        if (found) {
            console.log(`✅ 找到并点击按钮 "${searchText}"`);
            try {
                await page.waitForLoadState('networkidle', { timeout: 10000 });
            } catch (e) {}
            return true;
        }
        console.log(`⚠️ 第 ${attempt + 1} 次未找到按钮 "${searchText}"，重试中...`);
        await page.waitForTimeout(1000);
    }
    return false;
}

async function getTimeInfo(page) {
    const html = await page.content();
    const match = html.match(/suspended.*?in\s*<strong>(.*?)<\/strong>/i);
    if (!match) {
        const match2 = html.match(/suspended.*?in\s*<strong[^>]*>(.*?)<\/strong>/i);
        return match2 ? match2[1].trim() : '未知';
    }
    return match[1].trim();
}

async function saveScreenshot(page, name) {
    const screenshotsDir = path.join(__dirname, 'scripts', 'screenshots');
    if (!fs.existsSync(screenshotsDir)) {
        fs.mkdirSync(screenshotsDir, { recursive: true });
    }
    const filePath = path.join(screenshotsDir, name);
    await page.screenshot({ path: filePath });
    console.log(`📸 截图已保存: ${filePath}`);
    return filePath;
}

async function runRenewal() {
    const screenshotName = 'g4free_status.png';
    let driver;
    let page;
    
    console.log('='.repeat(50));
    console.log('🚀 G4Free 续期任务启动');
    console.log(`   Cookie: ${COOKIE ? '已设置' : '未设置'}`);
    console.log(`   Panel Cookie: ${PANEL_COOKIE ? '已设置' : '未设置'}`);
    console.log(`   Account: ${ACCOUNT ? '已设置' : '未设置'}`);
    console.log(`   TG Token: ${TG_BOT_TOKEN ? '已设置' : '未设置'}`);
    console.log(`   TG ChatID: ${TG_CHAT_ID ? '已设置' : '未设置'}`);
    console.log('='.repeat(50));
    
    try {
        console.log('🛡️ 启动浏览器...');
        const extensionPath = BUSTER_EXTENSION_PATH;
        
        const contextOptions = {
            headless: false,
            args: []
        };
        
        if (fs.existsSync(extensionPath)) {
            contextOptions.args.push(`--disable-extensions-except=${extensionPath}`);
            contextOptions.args.push(`--load-extension=${extensionPath}`);
            console.log(`🛡️ 加载 Buster 插件: ${extensionPath}`);
        }
        
        driver = await chromium.launch(contextOptions);
        page = await driver.newPage();
        await page.setViewportSize({ width: 1920, height: 1080 });
        console.log('🖥️ 浏览器分辨率设置为: 1920x1080');
        
        await injectCookies(page, PANEL_COOKIE, 'panel.gaming4free.net');
        await injectCookies(page, COOKIE, 'gaming4free.net');
        
        console.log(`🌐 访问主站 Dashboard: ${DASHBOARD_URL}`);
        await page.goto(DASHBOARD_URL);
        await page.waitForTimeout(6000);
        
        if (page.url().toLowerCase().includes('login')) {
            console.log('⚠️ 主站 Cookie 失效，启动账号密码兜底登录...');
            const inputs = await page.$$('input');
            if (inputs.length >= 2) {
                await inputs[0].fill(ACCOUNT);
                await inputs[1].fill(PASSWORD);
                console.log('✅ 已填入账号和密码');
            } else if (inputs.length === 1) {
                await inputs[0].fill(ACCOUNT);
                console.log('✅ 已填入账号');
            }
            
            await page.evaluate(() => {
                const buttons = document.querySelectorAll('button');
                for (const btn of buttons) {
                    const text = btn.innerText || btn.textContent;
                    if (text && text.trim()) {
                        btn.click();
                        return;
                    }
                }
                const forms = document.querySelectorAll('form');
                if (forms.length > 0) {
                    forms[0].submit();
                }
            });
            console.log('✅ 已提交登录表单');
            await page.waitForTimeout(8000);
            
            if (page.url().toLowerCase().includes('login')) {
                const screenshotPath = await saveScreenshot(page, screenshotName);
                await sendTgMessage('🔴 <b>主站兜底登录失败</b>\n请检查账号密码。', screenshotPath);
                await driver.close();
                return;
            }
        }
        
        console.log('🔍 尝试自然点击 "Renew" 按钮...');
        const clickedRenew = await clickLinkByText(page, 'Renew');
        if (!clickedRenew) {
            const screenshotPath = await saveScreenshot(page, screenshotName);
            await sendTgMessage('🔴 <b>异常拦截</b>\n在 Dashboard 未找到 Renew 按钮。', screenshotPath);
            await driver.close();
            return;
        }
        await page.waitForTimeout(10000);
        
        console.log('🔗 尝试自然点击 "Panel" 按钮...');
        const clickedPanel = await clickLinkByText(page, 'Panel', true);
        if (!clickedPanel) {
            const screenshotPath = await saveScreenshot(page, screenshotName);
            await sendTgMessage('🔴 <b>页面结构异常</b>\n未找到 Panel 按钮。', screenshotPath);
            await driver.close();
            return;
        }
        await page.waitForTimeout(10000);
        
        if (page.url().toLowerCase().includes('login')) {
            const screenshotPath = await saveScreenshot(page, screenshotName);
            await sendTgMessage('🔴 <b>面板跨域认证失败</b>\n虽已模拟点击，但面板 Cookie 失效或被图形验证码拦截。', screenshotPath);
            await driver.close();
            return;
        }
        
        console.log('🖥️ 尝试自然点击 Console 终端入口...');
        let clickedConsole = await clickLinkByText(page, 'Console');
        if (!clickedConsole) {
            clickedConsole = await clickLinkByHref(page, '/console');
        }
        if (!clickedConsole) {
            const screenshotPath = await saveScreenshot(page, screenshotName);
            await sendTgMessage('🔴 <b>页面异常</b>\n在 Panel 页面未找到 Console。', screenshotPath);
            await driver.close();
            return;
        }
        await page.waitForTimeout(8000);
        
        console.log('⏱️ 正在获取加时前的初始时间...');
        const timeBefore = await getTimeInfo(page);
        const minutesBefore = getTotalMinutes(timeBefore);
        console.log(`⏱️ 当前时长: ${timeBefore} (${minutesBefore}分钟)`);
        
        console.log('👆 准备查找并点击 "Add 90 Minutes"...');
        const clickedAdd = await clickButtonByText(page, 'add 90 minutes');
        
        if (clickedAdd) {
            console.log('✅ 已点击 Add 90 Minutes，等待页面响应...');
            await page.waitForTimeout(5000);
            
            const frameElement = await page.$('iframe');
            if (frameElement) {
                console.log('🛡️ 检测到图形验证码弹窗！启动 Buster 音频破解方案...');
                try {
                    console.log('🔍 等待验证码iframe加载...');
                    await page.waitForTimeout(2000);
                    
                    console.log('🎧 切换至音频挑战模式...');
                    const frame = await frameElement.contentFrame();
                    if (frame) {
                        const audioBtn = await frame.$('#recaptcha-audio-button');
                        if (audioBtn) {
                            await audioBtn.click();
                            console.log('✅ 已点击音频挑战按钮');
                        } else {
                            console.log('⚠️ 未找到音频挑战按钮');
                        }
                        await page.waitForTimeout(3000);
                        
                        console.log('🤖 触发 Buster AI 破解...');
                        const solverBtn = await frame.$('#solver-button');
                        if (solverBtn) {
                            await solverBtn.click();
                            console.log('✅ 已触发 Buster 破解按钮');
                        } else {
                            console.log('⚠️ 未找到 Buster 破解按钮');
                        }
                        
                        console.log('⏳ 正在等待 Buster 请求 API 并完成破解 (30秒)...');
                        await page.waitForTimeout(30000);
                        console.log('✅ Buster 等待完成');
                    } else {
                        console.log('⚠️ 无法获取 iframe 内容帧');
                    }
                } catch (e) {
                    console.log(`⚠️ Buster 破解交互发生异常: ${e.message}`);
                }
            } else {
                console.log('✅ 未检测到验证码弹窗，直接进入等待阶段。');
            }
            
            console.log('📺 开始等待广告播放 (90 秒)...');
            await page.waitForTimeout(90000);
            
            console.log('🔄 等待结束，执行双重刷新...');
            await page.reload();
            await page.waitForTimeout(6000);
            await page.reload();
            await page.waitForTimeout(8000);
            
            const timeAfter = await getTimeInfo(page);
            const minutesAfter = getTotalMinutes(timeAfter);
            
            const screenshotPath = await saveScreenshot(page, screenshotName);
            
            if (minutesAfter > minutesBefore + 3) {
                const msg = `🟢 <b>G4Free JS版本续期成功！</b>\n\n时间已发生真实增长，Buster 破解与加时操作成功生效！\n⏱️ <b>操作前：</b><code>${timeBefore}</code>\n⏱️ <b>最新时长：</b><code>${timeAfter}</code>`;
                await sendTgMessage(msg, screenshotPath);
            } else {
                const msg = `🔴 <b>G4Free JS版本假成功警告 (破盾失败)</b>\n\n尝试了 Buster 破解，但服务器未生效(可能插件限流或音频挑战过难)。\n⏱️ <b>操作前：</b><code>${timeBefore}</code>\n⏱️ <b>操作后：</b><code>${timeAfter}</code>`;
                await sendTgMessage(msg, screenshotPath);
            }
        } else {
            const screenshotPath = await saveScreenshot(page, screenshotName);
            await sendTgMessage('🔴 <b>异常拦截</b>\n未找到加时按钮，请检查截图核实。', screenshotPath);
        }
        
        await driver.close();
        
    } catch (e) {
        console.error('❌ 脚本严重报错:', e);
        let screenshotPath = null;
        try {
            if (driver && page) {
                screenshotPath = await saveScreenshot(page, screenshotName);
            }
        } catch (screenshotError) {
            console.log(`⚠️ 截图失败: ${screenshotError.message}`);
        }
        try {
            const errorMsg = e.message.length > 200 ? e.message.substring(0, 200) + '...' : e.message;
            await sendTgMessage(`🔴 <b>脚本严重报错</b>\n<code>${errorMsg}</code>`, screenshotPath);
        } catch (tgError) {
            console.log(`⚠️ TG消息发送失败: ${tgError.message}`);
        }
        try {
            if (driver) await driver.close();
        } catch {}
    }
}

runRenewal();
