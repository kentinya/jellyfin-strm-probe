// Browser driver for the STRM Probe Optimizer configuration page.
//
// It is invoked by scripts/run_isolated_configuration_integration.py with a JSON scenario file and prints a JSON
// result on stdout. It only talks to the repository's isolated Jellyfin instance, drives the real web UI
// (login -> plugin entry -> configuration page) and records redacted interaction evidence. It never uses a real
// server or media library and never prints credentials, tokens or signed URLs.

import { createRequire } from 'node:module';
import { readFileSync, mkdirSync } from 'node:fs';

// The browser toolchain is pinned under artifacts/dev-env/browser-tools/node (git-ignored) and is not a plugin
// production dependency. The runner passes its project root so this driver can resolve the pinned playwright
// without relying on the current working directory.
const playwrightRoot = process.env.STRM_CONFIG_PLAYWRIGHT_ROOT;
const requireFromToolchain = playwrightRoot
  ? createRequire(playwrightRoot + '/package.json')
  : createRequire(import.meta.url);
const { chromium } = requireFromToolchain('playwright');

const scenarioPath = process.argv[2];
if (!scenarioPath) {
  console.error('usage: node configuration_page_driver.mjs <scenario.json>');
  process.exit(2);
}

const cfg = JSON.parse(readFileSync(scenarioPath, 'utf8'));
mkdirSync(cfg.screenshotDir, { recursive: true });

const pageSelector = '#StrmProbeOptimizerConfigPage';
const statusSelector = '#BatchLibraryStatus';

function screenshotPath(name) {
  return `${cfg.screenshotDir}/${name}.png`;
}

async function login(page) {
  await page.goto(cfg.baseUrl + '/web/index.html', { waitUntil: 'domcontentloaded', timeout: 60000 });
  // Wait until the SPA has either rendered the login form or restored an authenticated session. A fresh context
  // is always logged out, so the username field is expected; auto-waiting for it avoids racing the initial splash.
  const userField = await page.waitForSelector('#txtManualName, input[name="username"]', { timeout: 60000 }).catch(() => null);
  if (userField) {
    await page.fill('#txtManualName, input[name="username"]', cfg.username);
    await page.fill('#txtManualPassword, input[name="password"]', cfg.password);
    await page.click('.btnSubmit, button[type="submit"]');
    await page.waitForFunction(() => location.hash.indexOf('/login') < 0, null, { timeout: 60000 });
  }
  // Wait until the dashboard session is usable so the plugin page is reachable.
  await page.waitForFunction(() => !!window.ApiClient && !!window.ApiClient.accessToken(), null, { timeout: 60000 });
}

async function setCheckbox(page, id, value) {
  const current = await page.isChecked(id);
  if (current === value) {
    return;
  }

  // Jellyfin renders an emby-checkbox as a styled label; click the visible label (a real user click) and only
  // fall back to a forced click on the input if the custom element layout makes the label unclickable.
  try {
    await page.locator(id).locator('xpath=ancestor::label[1]').click({ timeout: 10000 });
  } catch {
    await page.setChecked(id, value, { force: true });
  }

  if ((await page.isChecked(id)) !== value) {
    await page.setChecked(id, value, { force: true });
  }
  if ((await page.isChecked(id)) !== value) {
    throw new Error(`Could not set checkbox ${id} to ${value}.`);
  }
}

async function openViaPluginEntry(page) {
  // Open the native plugin entry and follow its configuration link, exactly like an administrator would. The
  // dashboard plugin card uses the id without dashes, so match the normalized id.
  const normalizedId = cfg.pluginId.replace(/-/g, '').toLowerCase();
  await page.goto(cfg.baseUrl + '/web/index.html#/dashboard/plugins', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForFunction(
    (id) => !!document.querySelector(`a[href*="${id}"]`),
    normalizedId,
    { timeout: 60000 },
  );
  await page.click(`a[href*="${normalizedId}"]`);
  await page.waitForSelector(`a[href*="configurationpage?name=${cfg.pageName}"]`, { timeout: 60000 });
  await page.click(`a[href*="configurationpage?name=${cfg.pageName}"]`);
  await page.waitForSelector(pageSelector, { timeout: 60000 });
  // The page reports its load outcome through the status element, so wait for either a successful load or the
  // explicit load-failure state instead of a fixed delay.
  await page.waitForFunction(
    (selector) => {
      const status = document.querySelector(selector);
      return !!status && (status.getAttribute('data-loaded') === 'true' || status.getAttribute('data-save-state') === 'error');
    },
    statusSelector,
    { timeout: 60000 },
  );
}

async function readState(page) {
  return await page.evaluate(({ pageSelector, statusSelector }) => {
    const status = document.querySelector(statusSelector);
    const libraries = Array.from(document.querySelectorAll('#BatchLibraryList input[type="checkbox"]')).map((input) => ({
      id: input.value,
      checked: input.checked,
    }));
    return {
      pagePresent: !!document.querySelector(pageSelector),
      loaded: status.getAttribute('data-loaded') === 'true',
      saveState: status.getAttribute('data-save-state') || '',
      statusText: status.textContent.trim(),
      enabled: document.querySelector('#Enabled').checked,
      playbackAutoCheck: document.querySelector('#PlaybackAutoCheck').checked,
      maxConcurrentProbes: document.querySelector('#MaxConcurrentProbes').value,
      detailedLog: document.querySelector('#DetailedLog').checked,
      batchAllLibraries: document.querySelector('#BatchAllLibraries').checked,
      selectionVisible: document.querySelector('#BatchLibrarySelection').style.display !== 'none',
      libraries,
    };
  }, { pageSelector, statusSelector });
}

async function submitAndWait(page) {
  // Clear the previous outcome so the wait observes this save's result rather than the load banner.
  await page.evaluate((selector) => {
    const status = document.querySelector(selector);
    if (status) {
      status.removeAttribute('data-save-state');
    }
  }, statusSelector);
  await page.click('#SaveConfiguration');
  await page.waitForFunction(
    (selector) => {
      const status = document.querySelector(selector);
      const state = status && status.getAttribute('data-save-state');
      return state === 'success' || state === 'error';
    },
    statusSelector,
    { timeout: 60000 },
  );
  // Give the success/error banner a moment to settle, then read the final state.
  await page.waitForTimeout(500);
  return await readState(page);
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1400, height: 1000 } });
  const page = await context.newPage();
  const consoleErrors = [];
  const pageErrors = [];
  const failedResponses = [];
  page.on('console', (message) => {
    if (message.type() === 'error') {
      const location = message.location();
      consoleErrors.push({ text: message.text(), url: location && location.url ? location.url : '' });
    }
  });
  page.on('pageerror', (error) => pageErrors.push({ text: String(error && error.message ? error.message : error), stack: String(error && error.stack ? error.stack : '') }));
  page.on('response', (response) => {
    if (response.status() >= 400) {
      failedResponses.push({ status: response.status(), url: response.url() });
    }
  });

  const result = { scenario: cfg.scenario, screenshots: [], consoleErrors, pageErrors, failedResponses };

  try {
    await login(page);

    if (cfg.scenario === 'load_failure') {
      await page.route('**/Plugins/*/Configuration', (route) => {
        if (route.request().method() === 'GET') {
          return route.fulfill({ status: 500, contentType: 'application/json', body: '{}' });
        }
        return route.continue();
      });
    } else if (cfg.scenario === 'save_failure') {
      await page.route('**/Plugins/*/Configuration', (route) => {
        if (route.request().method() === 'POST') {
          return route.fulfill({ status: 400, contentType: 'application/json', body: '{}' });
        }
        return route.continue();
      });
    } else if (cfg.scenario === 'library_read_failure') {
      await page.route('**/Library/VirtualFolders**', (route) =>
        route.fulfill({ status: 500, contentType: 'application/json', body: '[]' }));
    }

    await openViaPluginEntry(page);
    result.screenshots.push(await capture(page, 'page-loaded'));
    result.initial = await readState(page);

    if (cfg.scenario === 'inspect' || cfg.scenario === 'load_failure' || cfg.scenario === 'library_read_failure') {
      result.final = result.initial;
    } else if (cfg.scenario === 'save_valid' || cfg.scenario === 'save_failure') {
      const edits = cfg.edits || {};
      if (edits.enabled !== undefined) await setCheckbox(page, '#Enabled', edits.enabled);
      if (edits.playbackAutoCheck !== undefined) await setCheckbox(page, '#PlaybackAutoCheck', edits.playbackAutoCheck);
      if (edits.detailedLog !== undefined) await setCheckbox(page, '#DetailedLog', edits.detailedLog);
      if (edits.maxConcurrentProbes !== undefined) await page.fill('#MaxConcurrentProbes', String(edits.maxConcurrentProbes));
      if (edits.batchAllLibraries !== undefined) {
        await setCheckbox(page, '#BatchAllLibraries', edits.batchAllLibraries);
        await page.waitForTimeout(200);
      }
      if (edits.libraryIds !== undefined) {
        const wanted = new Set(edits.libraryIds.map((id) => id.replace(/-/g, '').toLowerCase()));
        const count = await page.locator('#BatchLibraryList input[type="checkbox"]').count();
        for (let index = 0; index < count; index += 1) {
          const input = page.locator('#BatchLibraryList input[type="checkbox"]').nth(index);
          const value = (await input.getAttribute('value')) || '';
          const shouldCheck = wanted.has(value.replace(/-/g, '').toLowerCase());
          if (shouldCheck === (await input.isChecked())) {
            continue;
          }

          // Click the visible label, like a real administrator toggling the checkbox.
          await input.locator('xpath=ancestor::label[1]').click({ timeout: 10000 }).catch(async () => {
            await input.setChecked(shouldCheck, { force: true });
          });
          if ((await input.isChecked()) !== shouldCheck) {
            await input.setChecked(shouldCheck, { force: true });
          }
        }
        await page.waitForTimeout(200);
      }
      result.afterEdit = await readState(page);
      result.screenshots.push(await capture(page, 'after-edit'));
      result.final = await submitAndWait(page);
      result.screenshots.push(await capture(page, 'after-save'));
    } else if (cfg.scenario === 'save_empty_scope') {
      await setCheckbox(page, '#BatchAllLibraries', false);
      await page.waitForTimeout(200);
      await page.evaluate(() => {
        document.querySelectorAll('#BatchLibraryList input[type="checkbox"]').forEach((input) => {
          if (input.checked) {
            input.checked = false;
            input.dispatchEvent(new Event('change', { bubbles: true }));
          }
        });
      });
      await page.evaluate((selector) => {
        const status = document.querySelector(selector);
        if (status) {
          status.removeAttribute('data-save-state');
        }
      }, statusSelector);
      await page.click('#SaveConfiguration');
      // The page must refuse client-side; wait for the error banner.
      await page.waitForFunction(
        (selector) => document.querySelector(selector).getAttribute('data-save-state') === 'error',
        statusSelector,
        { timeout: 30000 },
      );
      result.final = await readState(page);
      result.screenshots.push(await capture(page, 'empty-scope-rejected'));
    } else {
      throw new Error(`Unknown scenario ${cfg.scenario}`);
    }
  } catch (error) {
    result.error = String(error && error.message ? error.message : error);
    try {
      result.failureUrl = page.url();
      result.failureState = await readState(page);
    } catch {
      // Best effort failure diagnostics.
    }
    try {
      result.screenshots.push(await capture(page, 'failure'));
    } catch {
      // Best effort screenshot on failure.
    }
  } finally {
    await browser.close();
  }

  console.log(JSON.stringify(result));
}

async function capture(page, name) {
  const path = screenshotPath(name);
  await page.screenshot({ path, fullPage: true });
  return name;
}

run().catch((error) => {
  console.log(JSON.stringify({ error: String(error && error.message ? error.message : error) }));
  process.exit(1);
});
