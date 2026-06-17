// 小红书 Cookie 提取工具 (自动检测版)
// 用法: node scripts/get_xhs_cookie.js
// 弹出浏览器 → 扫码登录 → 自动检测登录状态 → 保存Cookie到 .env

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const ENV_PATH = path.join(__dirname, '..', '.env');

(async () => {
  console.log('正在启动浏览器...');
  const browser = await chromium.launch({
    headless: false,
    args: ['--start-maximized']
  });

  // 每次用全新 context，不复用旧 session
  const context = await browser.newContext({
    viewport: null,
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0'
  });
  const page = await context.newPage();

  console.log('正在打开小红书...');
  await page.goto('https://www.xiaohongshu.com', { waitUntil: 'domcontentloaded' });

  console.log('');
  console.log('========================================');
  console.log('  请在浏览器中扫码登录小红书');
  console.log('  登录成功后会自动提取Cookie');
  console.log('  最长等待5分钟');
  console.log('========================================');
  console.log('');

  // 每3秒检测一次 cookie，最长等5分钟
  let saved = false;
  for (let i = 0; i < 100; i++) {
    await new Promise(r => setTimeout(r, 3000));

    const cookies = await context.cookies('https://www.xiaohongshu.com');
    const a1 = cookies.find(c => c.name === 'a1');
    const ws = cookies.find(c => c.name === 'web_session');
    const gid = cookies.find(c => c.name === 'gid');

    // 登录成功的标志: 有 a1 + web_session(长度>20) + gid
    if (a1 && ws && ws.value && ws.value.length > 20 && gid) {
      const cookieStr = cookies.map(c => c.name + '=' + c.value).join('; ');

      console.log('');
      console.log('登录成功! 提取到 ' + cookies.length + ' 个Cookie字段');
      console.log('  a1: ' + a1.value.slice(0, 12) + '...');
      console.log('  web_session: ' + ws.value.slice(0, 12) + '...');

      // 读取并更新 .env
      let envContent = '';
      if (fs.existsSync(ENV_PATH)) {
        envContent = fs.readFileSync(ENV_PATH, 'utf-8');
        envContent = envContent.replace(/^XHS_COOKIE=.*$/m, '');
      }
      envContent = envContent.trimEnd() + '\nXHS_COOKIE=' + cookieStr + '\n';
      fs.writeFileSync(ENV_PATH, envContent);

      console.log('');
      console.log('Cookie 已保存到 ' + ENV_PATH);
      console.log('Cookie 长度: ' + cookieStr.length + ' 字符');
      saved = true;
      break;
    }

    if (i % 5 === 0 && i > 0) {
      console.log('等待登录中... (' + (i * 3) + '秒)');
    }
  }

  if (!saved) {
    console.log('');
    console.log('超时! 未检测到登录状态，请重新运行此脚本');
  }

  await browser.close();
  if (saved) {
    console.log('浏览器已关闭，可以开始爬取了!');
  }
  process.exit(saved ? 0 : 1);
})();
