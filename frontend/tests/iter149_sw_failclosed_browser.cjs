/* iter149 focused browser validation: real SW v5 + interception fail-closed checks */
const assert = require('node:assert/strict');
const path = require('node:path');
const dotenv = require('dotenv');
const { chromium } = require(process.env.CP_PLAYWRIGHT_MODULE || 'playwright');

dotenv.config({ path: path.join(__dirname, '../.env') });

const BASE_URL = process.env.REACT_APP_BACKEND_URL;
const PRO_EMAIL = process.env.TEST_PRO_EMAIL;
const PRO_PASSWORD = process.env.TEST_PRO_PASSWORD;
const MEMBER_EMAIL = process.env.TEST_MEMBER_EMAIL;
const MEMBER_PASSWORD = process.env.TEST_MEMBER_PASSWORD;

if (!BASE_URL) throw new Error('REACT_APP_BACKEND_URL missing from frontend/.env');
if (!PRO_EMAIL || !PRO_PASSWORD || !MEMBER_EMAIL || !MEMBER_PASSWORD) {
  throw new Error('Missing TEST_PRO_* or TEST_MEMBER_* credentials env vars');
}

async function login(page, email, password) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' });
  const cookieBanner = page.getByTestId('cookie-consent-banner');
  if (await cookieBanner.count()) {
    const refuse = page.getByTestId('cookie-refuse-btn');
    if (await refuse.count()) await refuse.click({ force: true });
  }
  await page.getByTestId('tab-login').click();
  await page.getByTestId('login-email-input').fill(email);
  await page.getByTestId('login-password-input').fill(password);
  await page.getByTestId('login-submit-btn').click();
  await page.waitForURL('**/dashboard**', { timeout: 45000 });
  await page.getByTestId('workspace-account-menu').waitFor({ timeout: 30000 });
}

async function logout(page) {
  await page.getByTestId('workspace-account-menu').click();
  await page.getByTestId('logout-btn').click();
  await page.waitForURL('**/', { timeout: 20000 });
}

async function sw_live_validation(browser) {
  const context = await browser.newContext({ serviceWorkers: 'allow' });
  const page = await context.newPage();

  await login(page, PRO_EMAIL, PRO_PASSWORD);
  await page.waitForTimeout(1500);

  const swInfo = await page.evaluate(async () => {
    const swSupported = 'serviceWorker' in navigator;
    const registration = swSupported ? await navigator.serviceWorker.getRegistration() : null;
    const swText = await fetch('/sw.js', { cache: 'no-store' }).then(r => r.text());

    await fetch('/api/auth/me', { credentials: 'include' });
    await fetch('/api/company/me', { credentials: 'include' });

    const keys = await caches.keys();
    const entries = [];
    for (const key of keys) {
      const cache = await caches.open(key);
      const reqs = await cache.keys();
      reqs.forEach(req => entries.push(req.url));
    }

    const me = await fetch('/api/company/me', { credentials: 'include' }).then(r => r.json());

    return {
      swSupported,
      hasRegistration: !!registration,
      scriptUrl: registration?.active?.scriptURL || registration?.waiting?.scriptURL || '',
      swText,
      keys,
      entries,
      role: me?.role,
    };
  });

  assert.equal(swInfo.swSupported, true);
  assert.equal(swInfo.hasRegistration, true);
  assert.match(swInfo.scriptUrl, /\/sw\.js/);
  assert.match(swInfo.swText, /construpilot-v5-private-api-network-only/);
  assert.ok(swInfo.keys.every((k) => !/v4/i.test(k)), `Old v4 cache remains: ${JSON.stringify(swInfo.keys)}`);
  assert.ok(swInfo.entries.some((u) => /manifest\.json|logo192\.png|logo512\.png|\.js$|\.css$/.test(u)), 'No static shell assets were cached');
  assert.ok(swInfo.entries.every((u) => !u.includes('/api/')), `API cached unexpectedly: ${JSON.stringify(swInfo.entries.filter((u) => u.includes('/api/')))}`);

  await context.setOffline(true);
  const offlineResult = await page.evaluate(async () => {
    try {
      const r = await fetch('/api/company/me', { credentials: 'include' });
      return { resolved: true, status: r.status };
    } catch (e) {
      return { resolved: false, error: String(e?.name || e) };
    }
  });
  assert.equal(offlineResult.resolved, false, `Offline API call unexpectedly resolved: ${JSON.stringify(offlineResult)}`);
  await context.setOffline(false);

  assert.equal(swInfo.role, 'owner');
  await logout(page);
  await login(page, MEMBER_EMAIL, MEMBER_PASSWORD);
  const memberRole = await page.evaluate(() => fetch('/api/company/me', { credentials: 'include' }).then(r => r.json()).then(d => d?.role));
  assert.equal(memberRole, 'member');

  await context.close();
}

async function failclosed_interception_validation(browser) {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  const page = await context.newPage();
  await login(page, PRO_EMAIL, PRO_PASSWORD);

  const makeScenario = async (name, handler) => {
    await context.unroute('**/api/company/me').catch(() => {});
    await context.route('**/api/company/me', handler);
    await page.goto(`${BASE_URL}/devis`, { waitUntil: 'domcontentloaded' });
    await page.getByTestId('workspace-permission-notice').waitFor({ timeout: 20000 });
    await page.getByTestId('workspace-account-menu').waitFor({ timeout: 15000 });
    const visible = await page.getByTestId('workspace-permission-notice').isVisible();
    assert.equal(visible, true, `${name}: permission notice not visible`);
  };

  // 503 response
  await makeScenario('503 fail-closed', async (route) => {
    await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'downstream unavailable' }) });
  });

  // Network failure
  await makeScenario('network abort fail-closed', async (route) => {
    await route.abort('failed');
  });

  // Malformed payload
  await makeScenario('malformed payload fail-closed', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ role: 'owner', permissions: { dashboard: true } }) });
  });

  // Missing expected booleans + unknown key only
  await makeScenario('unknown/missing keys fail-closed', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ role: 'owner', active: true, in_org: true, permissions: { unknown_key: true } }),
    });
  });

  await context.close();
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    await sw_live_validation(browser);
    await failclosed_interception_validation(browser);
    console.log('iter149 browser validations passed');
  } finally {
    await browser.close();
  }
})().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
