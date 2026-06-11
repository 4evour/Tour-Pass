// 小红书 Cookie 提取工具
// 用法: node scripts/get_xhs_cookie.js
// 弹出浏览器 → 你手动登录 → 按回车 → 自动提取Cookie保存到 .env

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const readline = require('readline');

const ENV_PATH = path.join(__dirname, '..', '.env');

(async () => {
  console.log('正在启动浏览器...');
  const browser = await chromium.launch({
    headless: false,  // 显示浏览器窗口
    args: ['--start-maximized']
  });

  const context = await browser.newContext({
    viewport: null  // 最大化窗口
  });
  const page = await context.newPage();

  console.log('正在打开小红书...');
  await page.goto('https://www.xiaohongshu.com', { waitUntil: 'domcontentloaded' });

  console.log('\n========================================');
  console.log('请在浏览器中登录你的小红书小号');
  console.log('登录完成后，回到这里按回车键继续');
  console.log('========================================\n');

  // 等待用户按回车
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  await new Promise(resolve => rl.question('按回车键提取Cookie > ', resolve));
  rl.close();

  // 提取所有 cookie
  const cookies = await context.cookies('https://www.xiaohongshu.com');
  const cookieStr = cookies.map(c => `${c.name}=${c.value}`).join('; ');

  // 检查关键字段
  const hasA1 = cookies.some(c => c.name === 'a1');
  const hasWebSession = cookies.some(c => c.name === 'web_session');

  console.log('\n提取到 ' + cookies.length + ' 个 Cookie 字段');
  console.log('a1: ' + (hasA1 ? '✓' : '✗ 缺失'));
  console.log('web_session: ' + (hasWebSession ? '✓' : '✗ 缺失'));

  if (!hasA1 || !hasWebSession) {
    console.log('\n⚠️ 警告：缺少关键Cookie字段，可能未登录成功');
    console.log('请确认已在浏览器中完成登录，然后重新运行此脚本');
    await browser.close();
    process.exit(1);
  }

  // 读取现有 .env 内容
  let envContent = '';
  if (fs.existsSync(ENV_PATH)) {
    envContent = fs.readFileSync(ENV_PATH, 'utf-8');
    // 删除已有的 XHS_COOKIE 行
    envContent = envContent.replace(/^XHS_COOKIE=.*$/m, '');
  }

  // 追加新的 XHS_COOKIE
  envContent = envContent.trimEnd() + '\nXHS_COOKIE=' + cookieStr + '\n';
  fs.writeFileSync(ENV_PATH, envContent);

  console.log('\n✅ Cookie 已保存到 ' + ENV_PATH);
  console.log('Cookie 长度: ' + cookieStr.length + ' 字符');

  await browser.close();
  console.log('浏览器已关闭，可以开始爬取了！');
})();