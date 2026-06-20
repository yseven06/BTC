const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');

const OUT_DIR = 'C:\\Users\\Wolrider\\.gemini\\antigravity\\brain\\e78fbd1e-b543-4c2d-8d82-a304b1ab61d5\\scratch';

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

(async () => {
  console.log('Launching browser...');
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1440,900'],
    defaultViewport: { width: 1440, height: 900 }
  });

  const page = await browser.newPage();

  // Listen for browser logs & errors
  page.on('console', msg => console.log('BROWSER CONSOLE:', msg.type(), msg.text()));
  page.on('pageerror', err => console.error('BROWSER EXCEPTION:', err.message));

  // 1. Navigate to signals page (which redirects to login page)
  console.log('Navigating to signals page...');
  await page.goto('http://localhost:3000/signals', { waitUntil: 'networkidle2', timeout: 30000 });
  await sleep(2000);

  // Take login screen screenshot
  const loginSS = path.join(OUT_DIR, 'ss_00_login.png');
  await page.screenshot({ path: loginSS });
  console.log('Saved login screenshot:', loginSS);

  // Perform login
  console.log('Performing login...');
  const loginResult = await page.evaluate((email, pass) => {
    const inputs = Array.from(document.querySelectorAll('input'));
    const emailInput = inputs.find(i => i.type === 'email' || i.name?.toLowerCase().includes('email') || i.placeholder?.toLowerCase().includes('mail'));
    const passInput = inputs.find(i => i.type === 'password' || i.name?.toLowerCase().includes('pass') || i.placeholder?.toLowerCase().includes('şifre'));
    
    if (!emailInput || !passInput) {
      return 'inputs-not-found';
    }

    emailInput.value = email;
    emailInput.dispatchEvent(new Event('input', { bubbles: true }));
    emailInput.dispatchEvent(new Event('change', { bubbles: true }));

    passInput.value = pass;
    passInput.dispatchEvent(new Event('input', { bubbles: true }));
    passInput.dispatchEvent(new Event('change', { bubbles: true }));

    const buttons = Array.from(document.querySelectorAll('button'));
    const loginBtn = buttons.find(b => b.textContent && (b.textContent.includes('Giriş') || b.textContent.includes('Login')));
    if (loginBtn) {
      loginBtn.click();
      return 'clicked-login-button';
    }
    return 'login-button-not-found';
  }, 'dev@trademinds.io', 'devpass123');

  console.log('Login action result:', loginResult);
  await sleep(4000); // wait for navigation/state to update

  // Take screenshot after login redirection
  const sig1 = path.join(OUT_DIR, 'ss_01_signals_list.png');
  await page.screenshot({ path: sig1 });
  console.log('Saved after-login signals list:', sig1);

  // Wait for table rows to be rendered
  console.log('Waiting for signals list rows to render...');
  try {
    await page.waitForSelector('.divide-y > div', { timeout: 20000 });
    console.log('Signals list rows rendered successfully.');
  } catch (e) {
    console.log('Timeout waiting for table rows. Taking screenshot of current state...');
    const errSS = path.join(OUT_DIR, 'ss_error_table_timeout.png');
    await page.screenshot({ path: errSS });
    const text = await page.evaluate(() => document.body.innerText);
    console.log('PAGE BODY TEXT:', text);
    throw e;
  }

  // Take screenshot after signals loaded
  const sig1Loaded = path.join(OUT_DIR, 'ss_01_signals_loaded.png');
  await page.screenshot({ path: sig1Loaded });
  console.log('Saved loaded signals list:', sig1Loaded);

  // 2. Click the first signal row
  const clicked = await page.evaluate(() => {
    // Find the first row in the list
    const firstRow = document.querySelector('.divide-y > div');
    if (!firstRow) return 'row-not-found';

    // Find the "Analiz" button inside this row
    const actionBtn = Array.from(firstRow.querySelectorAll('button')).find(b => b.textContent && b.textContent.includes('Analiz')) || firstRow.querySelector('button');
    if (!actionBtn) return 'action-button-not-found';
    actionBtn.click();
    return 'clicked-first-row-action';
  });
  console.log('Clicked signal row result:', clicked);
  await sleep(3000); // wait for drawer animation

  // Screenshot: drawer open (overview tab)
  const sig2 = path.join(OUT_DIR, 'ss_02_drawer_open.png');
  await page.screenshot({ path: sig2 });
  console.log('Saved drawer open overview:', sig2);

  // 3. Click "AI Açıklaması" tab
  const tabClicked = await page.evaluate(() => {
    // Find all tab buttons or buttons inside the sheet/drawer
    const allBtns = Array.from(document.querySelectorAll('[role="tab"], button'));
    const aiTab = allBtns.find(b => b.textContent && b.textContent.includes('AI Açıklaması'));
    if (aiTab) {
      aiTab.click();
      return 'ai-tab-clicked';
    }
    return 'ai-tab-not-found';
  });
  console.log('Tab selection:', tabClicked);
  await sleep(2000); // wait for AI content to render

  // Screenshot: AI Açıklaması tab (SignalDetailSection)
  const sig3 = path.join(OUT_DIR, 'ss_03_ai_aciklamasi.png');
  await page.screenshot({ path: sig3 });
  console.log('Saved AI explanation tab:', sig3);

  // 4. Navigate to markets page
  console.log('Navigating to markets page...');
  await page.goto('http://localhost:3000/markets/BTC%2FUSDT', { waitUntil: 'networkidle2', timeout: 30000 });
  await sleep(3000);

  const sig4 = path.join(OUT_DIR, 'ss_04_markets_page.png');
  await page.screenshot({ path: sig4 });
  console.log('Saved markets page:', sig4);

  await browser.close();
  console.log('DONE. All screenshots saved.');
})().catch(err => {
  console.error('ERROR:', err.message);
  process.exit(1);
});
