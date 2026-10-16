// Playback driver for the package-acceptance instance.
//
// It drives the real Jellyfin web client: log in, open each item's details page, click the
// real Play button and wait until the native <video> element reports both advancing media
// time and a decoded picture. It returns only redacted observations (advancing time, frame
// dimensions, container/duration and the request path family), never signed URLs or tokens.
//
// The toolchain is the test-only pinned Playwright under artifacts/dev-env/browser-tools; it
// is never a plugin production dependency.

import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';

const playwrightRoot = process.env.STRM_CONFIG_PLAYWRIGHT_ROOT;
const requireFromToolchain = playwrightRoot
  ? createRequire(playwrightRoot + '/package.json')
  : createRequire(import.meta.url);
const { chromium } = requireFromToolchain('playwright');

const scenarioPath = process.argv[2];
if (!scenarioPath) {
  console.error('usage: node package_playback_driver.mjs <scenario.json>');
  process.exit(2);
}
const cfg = JSON.parse(readFileSync(scenarioPath, 'utf8'));

function redactUrl(raw) {
  const value = String(raw || '');
  const withoutQuery = value.split('?')[0];
  return withoutQuery.replace(/https?:\/\/[^/]+/, '').slice(0, 160);
}

async function login(page) {
  await page.goto(cfg.baseUrl + '/web/index.html', { waitUntil: 'domcontentloaded', timeout: 60000 });
  const userField = await page.waitForSelector('#txtManualName, input[name="username"]', { timeout: 60000 }).catch(() => null);
  if (userField) {
    await page.fill('#txtManualName, input[name="username"]', cfg.username);
    await page.fill('#txtManualPassword, input[name="password"]', cfg.password);
    await page.click('.btnSubmit, button[type="submit"]');
    await page.waitForFunction(() => location.hash.indexOf('/login') < 0, null, { timeout: 60000 });
  }
  await page.waitForFunction(() => !!window.ApiClient && !!window.ApiClient.accessToken(), null, { timeout: 60000 });
}

async function playItem(page, item) {
  const mediaRequests = [];
  const onResponse = (response) => {
    const url = response.url();
    if (/\/videos\/|\/stream|\.m3u8|\.mp4|\.mkv/i.test(url)) {
      mediaRequests.push({ status: response.status(), path: redactUrl(url) });
    }
  };
  page.on('response', onResponse);
  try {
    await page.goto(cfg.baseUrl + '/web/index.html#/details?id=' + item.id, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForSelector('.btnPlay', { timeout: 45000 });
    await page.click('.btnPlay');
    let observed = null;
    for (let index = 0; index < 80; index += 1) {
      const state = await page.evaluate(() => {
        const video = document.querySelector('video');
        if (!video) {
          return { present: false };
        }
        return {
          present: true,
          currentTime: video.currentTime,
          duration: video.duration,
          videoWidth: video.videoWidth,
          videoHeight: video.videoHeight,
          readyState: video.readyState,
          paused: video.paused,
          srcPath: (video.currentSrc || '').split('?')[0],
        };
      });
      if (state.present) {
        observed = state;
      }
      if (state.present && state.currentTime > 0.1 && state.videoWidth > 0) {
        break;
      }
      await page.waitForTimeout(500);
    }
    const advanced = !!(observed && observed.present && observed.currentTime > 0.1 && observed.videoWidth > 0);
    return {
      name: item.name,
      itemId: item.id,
      advanced,
      currentTime: observed ? observed.currentTime : null,
      duration: observed ? observed.duration : null,
      videoWidth: observed ? observed.videoWidth : null,
      videoHeight: observed ? observed.videoHeight : null,
      readyState: observed ? observed.readyState : null,
      videoSrcPath: observed && observed.srcPath ? redactUrl(observed.srcPath) : null,
      mediaRequests: mediaRequests.slice(0, 20),
    };
  } finally {
    page.off('response', onResponse);
  }
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1400, height: 1000 }, locale: 'zh-CN', timezoneId: 'Asia/Shanghai' });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push({ text: message.text().slice(0, 200), url: redactUrl(message.location() && message.location().url) });
    }
  });
  const result = { results: [], consoleErrors };
  try {
    await login(page);
    for (const item of cfg.items) {
      result.results.push(await playItem(page, item));
    }
  } catch (error) {
    result.error = String(error && error.message ? error.message : error);
  } finally {
    await browser.close();
  }
  console.log(JSON.stringify(result));
}

run().catch((error) => {
  console.log(JSON.stringify({ error: String(error && error.message ? error.message : error) }));
  process.exit(1);
});
