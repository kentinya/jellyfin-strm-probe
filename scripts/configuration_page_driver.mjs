// Browser driver for the STRM Probe Optimizer configuration page.
//
// It is invoked by scripts/run_isolated_configuration_integration.py with a JSON scenario file and prints a JSON
// result on stdout. It only talks to the repository's isolated Jellyfin instance, drives the real web UI
// (login -> plugin entry -> configuration page) and records redacted interaction evidence. It never uses a real
// server or media library and never prints credentials, tokens or signed URLs.
//
// Each scenario returns its own result object with the page states, the exact configuration POST bodies the page
// produced, whether a POST was attempted at all, and screenshots named per step. The runner saves each scenario
// under its own evidence directory so scene names never overwrite one another.

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

async function capture(page, name) {
  await page.screenshot({ path: screenshotPath(name), fullPage: true });
  return name;
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

async function setLibraryCheckbox(page, rawValue, desired) {
  const wanted = rawValue.replace(/-/g, '').toLowerCase();
  const count = await page.locator('#BatchLibraryList input[type="checkbox"]').count();
  for (let index = 0; index < count; index += 1) {
    const input = page.locator('#BatchLibraryList input[type="checkbox"]').nth(index);
    const currentValue = (await input.getAttribute('value')) || '';
    if (currentValue.replace(/-/g, '').toLowerCase() !== wanted) {
      continue;
    }

    if ((await input.isChecked()) === desired) {
      return;
    }

    // Click the visible label, like a real administrator toggling the checkbox.
    await input.locator('xpath=ancestor::label[1]').click({ timeout: 10000 }).catch(async () => {
      await input.setChecked(desired, { force: true });
    });
    if ((await input.isChecked()) !== desired) {
      await input.setChecked(desired, { force: true });
    }
    return;
  }
  throw new Error(`The library checkbox ${rawValue} was not rendered on the page.`);
}

async function openPage(page) {
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
      stale: input.getAttribute('data-stale') === 'true',
    }));
    const saveButton = document.querySelector('#SaveConfiguration');
    return {
      pagePresent: !!document.querySelector(pageSelector),
      loaded: status.getAttribute('data-loaded') === 'true',
      saveState: status.getAttribute('data-save-state') || '',
      statusKind: status.getAttribute('data-status-kind') || '',
      statusText: status.textContent.trim(),
      enabled: document.querySelector('#Enabled').checked,
      playbackAutoCheck: document.querySelector('#PlaybackAutoCheck').checked,
      maxConcurrentProbes: document.querySelector('#MaxConcurrentProbes').value,
      detailedLog: document.querySelector('#DetailedLog').checked,
      batchAllLibraries: document.querySelector('#BatchAllLibraries').checked,
      selectionVisible: document.querySelector('#BatchLibrarySelection').style.display !== 'none',
      saveDisabled: !!(saveButton && saveButton.disabled),
      staleWarning: !!document.querySelector('#BatchLibraryList [data-stale-warning="true"]'),
      libraryListUnavailable: !!document.querySelector('#BatchLibraryList [data-library-list="unavailable"]'),
      libraries,
    };
  }, { pageSelector, statusSelector });
}

async function clearOutcome(page) {
  await page.evaluate((selector) => {
    const status = document.querySelector(selector);
    if (status) {
      status.removeAttribute('data-save-state');
      status.removeAttribute('data-status-kind');
    }
  }, statusSelector);
}

async function submitAndWait(page, timeout = 60000) {
  await clearOutcome(page);
  await page.click('#SaveConfiguration');
  await page.waitForFunction(
    (selector) => {
      const status = document.querySelector(selector);
      const state = status && status.getAttribute('data-save-state');
      return state === 'success' || state === 'error';
    },
    statusSelector,
    { timeout },
  );
  // Give the success/error banner a moment to settle, then read the final state.
  await page.waitForTimeout(500);
  return await readState(page);
}

async function clickReload(page, timeout = 60000) {
  await clearOutcome(page);
  await page.click('#ReloadConfiguration');
  await page.waitForFunction(
    (selector) => {
      const status = document.querySelector(selector);
      return !!status && (status.getAttribute('data-loaded') === 'true' || status.getAttribute('data-save-state') === 'error');
    },
    statusSelector,
    { timeout },
  );
  await page.waitForTimeout(300);
  return await readState(page);
}

function makeRecorder() {
  return { postBodies: [], postAttempts: 0, postApplied: 0 };
}

function attachConfigRoute(page, recorder, options) {
  const opts = options || {};
  return page.route('**/Plugins/*/Configuration', async (route) => {
    const method = route.request().method();
    if (method === 'GET') {
      if (opts.getStatus && opts.getStatus !== 200) {
        return route.fulfill({ status: opts.getStatus, contentType: 'application/json', body: '{}' });
      }
      if (opts.getBody !== undefined) {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(opts.getBody) });
      }
      return route.continue();
    }

    if (method === 'POST') {
      recorder.postAttempts += 1;
      let body = null;
      try {
        body = route.request().postDataJSON();
      } catch {
        body = null;
      }
      recorder.postBodies.push(body);
      if (opts.postMode === 'reject') {
        return route.fulfill({ status: opts.postStatus || 400, contentType: 'application/json', body: '{}' });
      }
      if (opts.postMode === 'mutate_invalid') {
        // Tamper the intercepted body and let the real isolated server reject it, so the page handles a genuine
        // server-side validation response rather than a browser-injected one.
        const body = route.request().postDataJSON();
        body.MaxConcurrentProbes = 99;
        return route.continue({ postData: JSON.stringify(body) });
      }
      if (opts.postMode === 'commit_then_drop') {
        const response = await route.fetch();
        recorder.postApplied += 1;
        recorder.serverStatus = response.status();
        return route.abort('failed');
      }
      if (opts.postMode === 'drop_before_server') {
        return route.abort('failed');
      }
      // Let the request reach the real isolated server.
      recorder.postApplied += 1;
      return route.continue();
    }

    return route.continue();
  });
}

async function withServerConfig(page, mutate) {
  return await page.evaluate(async ({ id, mutateSource }) => {
    const mutate = eval('(' + mutateSource + ')');
    const config = await ApiClient.getPluginConfiguration(id);
    const changed = mutate(config);
    if (changed) {
      await ApiClient.updatePluginConfiguration(id, config);
    }
    return await ApiClient.getPluginConfiguration(id);
  }, { id: cfg.pluginId, mutateSource: mutate.toString() });
}

const scenarios = {
  // AC-U1: open the page from the plugin entry; the five effective values and the real library list load.
  async inspect(page) {
    await openPage(page);
    const state = await readState(page);
    return { initial: state, final: state, screenshots: [await capture(page, 'page-loaded')] };
  },

  // AC-U2: edit all five fields, save, and read the persisted values back.
  async save_valid(page, recorder) {
    await attachConfigRoute(page, recorder, {});
    await openPage(page);
    const initial = await readState(page);
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
        await setLibraryCheckbox(page, value, wanted.has(value.replace(/-/g, '').toLowerCase()));
      }
      await page.waitForTimeout(200);
    }
    const afterEdit = await readState(page);
    const screenshots = [await capture(page, 'page-loaded'), await capture(page, 'after-edit')];
    const afterSave = await submitAndWait(page);
    screenshots.push(await capture(page, 'after-save'));
    return { initial, afterEdit, afterSave, final: afterSave, postAttempts: recorder.postAttempts, postBodies: recorder.postBodies, postApplied: recorder.postApplied, screenshots };
  },

  // FR-U1/AC-U3: a saved library that no longer exists is shown as stale and cannot be silently dropped.
  async stale_scope(page, recorder) {
    const staleId = (cfg.staleLibraryId || '').replace(/-/g, '').toLowerCase();
    const realId = (cfg.realLibraryId || '').replace(/-/g, '').toLowerCase();
    const injected = Object.assign({}, cfg.baseConfig, {
      BatchAllLibraries: false,
      BatchLibraryIds: realId + ',' + staleId,
    });
    await attachConfigRoute(page, recorder, { getBody: injected });
    await openPage(page);
    const initial = await readState(page);
    const screenshots = [await capture(page, 'stale-scope-loaded')];

    // Attempting to save the untouched scope must be blocked client-side; no POST may reach the server.
    const blockedSave = await submitAndWait(page);
    screenshots.push(await capture(page, 'stale-scope-blocked'));
    const attemptsAfterBlock = recorder.postAttempts;

    // The administrator removes the stale entry and keeps the real library, then saves.
    await setLibraryCheckbox(page, staleId, false);
    await page.waitForTimeout(200);
    const afterCorrection = await readState(page);
    const correctedSave = await submitAndWait(page);
    screenshots.push(await capture(page, 'stale-scope-corrected'));
    return {
      initial,
      blockedSave,
      attemptsAfterBlock,
      afterCorrection,
      correctedSave,
      final: correctedSave,
      postAttempts: recorder.postAttempts,
      postBodies: recorder.postBodies,
      postApplied: recorder.postApplied,
      screenshots,
    };
  },

  // FR-U2/AC-U4: the server commits the save but the browser loses the response.
  async lost_save_response(page, recorder) {
    const committed = await withServerConfig(page, (config) => {
      config.DetailedLog = false;
      return true;
    });
    await attachConfigRoute(page, recorder, { postMode: 'commit_then_drop' });
    await openPage(page);
    const initial = await readState(page);
    // Toggle a field so the committed value is observably different from the page's original value.
    await setCheckbox(page, '#DetailedLog', !initial.detailedLog);
    const afterEdit = await readState(page);
    const screenshots = [await capture(page, 'page-loaded'), await capture(page, 'after-edit')];
    const afterSave = await submitAndWait(page);
    screenshots.push(await capture(page, 'lost-response-feedback'));

    // Independent read of the effective configuration, without the interception route.
    await page.unroute('**/Plugins/*/Configuration');
    const effectiveAfter = await page.evaluate(async (id) => await ApiClient.getPluginConfiguration(id), cfg.pluginId);

    // "重新读取" must show the real server value, not the page's optimistic edit.
    await page.route('**/Plugins/*/Configuration', (route) => route.continue());
    const reloaded = await clickReload(page);
    screenshots.push(await capture(page, 'lost-response-reloaded'));
    return {
      initial,
      afterEdit,
      afterSave,
      effectiveAfter,
      committed,
      reloaded,
      postAttempts: recorder.postAttempts,
      postBodies: recorder.postBodies,
      postApplied: recorder.postApplied,
      serverStatus: recorder.serverStatus,
      screenshots,
    };
  },

  // AC-U4: the save request never reaches the server, so the effective configuration must be unchanged.
  async pre_submit_failure(page, recorder) {
    const before = await page.evaluate(async (id) => await ApiClient.getPluginConfiguration(id), cfg.pluginId);
    await attachConfigRoute(page, recorder, { postMode: 'drop_before_server' });
    await openPage(page);
    const initial = await readState(page);
    await setCheckbox(page, '#DetailedLog', !initial.detailedLog);
    const afterEdit = await readState(page);
    const screenshots = [await capture(page, 'page-loaded'), await capture(page, 'after-edit')];
    const afterSave = await submitAndWait(page);
    screenshots.push(await capture(page, 'pre-submit-failure-feedback'));

    await page.unroute('**/Plugins/*/Configuration');
    await page.route('**/Plugins/*/Configuration', (route) => route.continue());
    const effectiveAfter = await page.evaluate(async (id) => await ApiClient.getPluginConfiguration(id), cfg.pluginId);
    const reloaded = await clickReload(page);
    screenshots.push(await capture(page, 'pre-submit-reloaded'));
    return {
      before,
      initial,
      afterEdit,
      afterSave,
      effectiveAfter,
      reloaded,
      postAttempts: recorder.postAttempts,
      postBodies: recorder.postBodies,
      postApplied: recorder.postApplied,
      screenshots,
    };
  },

  // AC-U4: the server rejects the save; the page reports the rejection and leaves the configuration unchanged.
  async save_failure(page, recorder) {
    const before = await page.evaluate(async (id) => await ApiClient.getPluginConfiguration(id), cfg.pluginId);
    await attachConfigRoute(page, recorder, { postMode: 'reject', postStatus: 400 });
    await openPage(page);
    const initial = await readState(page);
    await setCheckbox(page, '#DetailedLog', !initial.detailedLog);
    const afterEdit = await readState(page);
    const screenshots = [await capture(page, 'page-loaded'), await capture(page, 'after-edit')];
    const afterSave = await submitAndWait(page);
    screenshots.push(await capture(page, 'rejected-feedback'));

    await page.unroute('**/Plugins/*/Configuration');
    await page.route('**/Plugins/*/Configuration', (route) => route.continue());
    const effectiveAfter = await page.evaluate(async (id) => await ApiClient.getPluginConfiguration(id), cfg.pluginId);
    const reloaded = await clickReload(page);
    screenshots.push(await capture(page, 'rejected-reloaded'));
    return {
      before,
      initial,
      afterEdit,
      afterSave,
      effectiveAfter,
      reloaded,
      postAttempts: recorder.postAttempts,
      postBodies: recorder.postBodies,
      postApplied: recorder.postApplied,
      screenshots,
    };
  },

  // AC-U4: an out-of-range concurrency is rejected client-side before any request is sent, then recovered.
  async concurrent_out_of_range(page, recorder) {
    await attachConfigRoute(page, recorder, {});
    await openPage(page);
    const initial = await readState(page);
    const screenshots = [await capture(page, 'page-loaded')];
    await page.fill('#MaxConcurrentProbes', '9');
    const invalidSave = await submitAndWait(page);
    screenshots.push(await capture(page, 'concurrency-rejected'));
    const attemptsAfterInvalid = recorder.postAttempts;
    const effectiveAfterInvalid = await page.evaluate(async (id) => await ApiClient.getPluginConfiguration(id), cfg.pluginId);

    await page.fill('#MaxConcurrentProbes', '3');
    const correctedSave = await submitAndWait(page);
    screenshots.push(await capture(page, 'concurrency-corrected'));
    return {
      initial,
      invalidSave,
      attemptsAfterInvalid,
      effectiveAfterInvalid,
      correctedSave,
      final: correctedSave,
      postAttempts: recorder.postAttempts,
      postBodies: recorder.postBodies,
      postApplied: recorder.postApplied,
      screenshots,
    };
  },

  // AC-U3: an explicit scope with no library is refused, then recovered by selecting a real library.
  async empty_scope(page, recorder) {
    await attachConfigRoute(page, recorder, {});
    await openPage(page);
    const initial = await readState(page);
    const screenshots = [await capture(page, 'page-loaded')];
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
    const refusedSave = await submitAndWait(page, 30000);
    screenshots.push(await capture(page, 'empty-scope-rejected'));
    const attemptsAfterRefusal = recorder.postAttempts;
    const effectiveAfterRefusal = await page.evaluate(async (id) => await ApiClient.getPluginConfiguration(id), cfg.pluginId);

    const realId = (cfg.realLibraryId || '').replace(/-/g, '').toLowerCase();
    await setLibraryCheckbox(page, realId, true);
    await page.waitForTimeout(200);
    const correctedSave = await submitAndWait(page);
    screenshots.push(await capture(page, 'empty-scope-corrected'));
    return {
      initial,
      refusedSave,
      attemptsAfterRefusal,
      effectiveAfterRefusal,
      correctedSave,
      final: correctedSave,
      postAttempts: recorder.postAttempts,
      postBodies: recorder.postBodies,
      postApplied: recorder.postApplied,
      screenshots,
    };
  },

  // AC-U1/AC-U3: a failed configuration load disables saving; "重新读取" recovers.
  async load_failure(page, recorder) {
    let failGet = true;
    await page.route('**/Plugins/*/Configuration', (route) => {
      if (route.request().method() === 'GET' && failGet) {
        return route.fulfill({ status: 500, contentType: 'application/json', body: '{}' });
      }
      return route.continue();
    });
    await openPage(page);
    const initial = await readState(page);
    const screenshots = [await capture(page, 'page-loaded')];
    failGet = false;
    const reloaded = await clickReload(page);
    screenshots.push(await capture(page, 'load-recovered'));
    return { initial, reloaded, final: reloaded, postAttempts: recorder.postAttempts, postBodies: recorder.postBodies, screenshots };
  },

  // AC-U3: when the library list cannot be read, the page reports it; "重新读取" recovers.
  async library_read_failure(page, recorder) {
    let failFolders = true;
    await page.route('**/Library/VirtualFolders**', (route) => {
      if (failFolders) {
        return route.fulfill({ status: 500, contentType: 'application/json', body: '[]' });
      }
      return route.continue();
    });
    await openPage(page);
    const initial = await readState(page);
    const screenshots = [await capture(page, 'page-loaded')];
    failFolders = false;
    const reloaded = await clickReload(page);
    screenshots.push(await capture(page, 'library-read-recovered'));
    return { initial, reloaded, final: reloaded, postAttempts: recorder.postAttempts, postBodies: recorder.postBodies, screenshots };
  },

  // AC-U1/AC-U2: a legacy configuration without the scope fields loads as the documented all-library default.
  async legacy_scope(page, recorder) {
    const legacy = { Enabled: true, PlaybackAutoCheck: true, MaxConcurrentProbes: 2, DetailedLog: false };
    await attachConfigRoute(page, recorder, { getBody: legacy });
    await openPage(page);
    const state = await readState(page);
    return { initial: state, final: state, postAttempts: recorder.postAttempts, postBodies: recorder.postBodies, screenshots: [await capture(page, 'legacy-scope-loaded')] };
  },
};

async function run() {
  const browser = await chromium.launch({ headless: true });
  // Pin a real locale so headless Chromium never inherits the host's POSIX locale (which makes Jellyfin's
  // number formatting throw "Invalid language tag: en-us@posix" during web-component upgrades).
  const context = await browser.newContext({ viewport: { width: 1400, height: 1000 }, locale: 'zh-CN', timezoneId: 'Asia/Shanghai' });
  const page = await context.newPage();
  const consoleErrors = [];
  const pageErrors = [];
  const failedResponses = [];
  page.on('console', (message) => {
    if (message.type() === 'error') {
      const location = message.location();
      consoleErrors.push({ text: message.text(), url: location && location.url ? location.url : '', pageUrl: page.url() });
    }
  });
  page.on('pageerror', (error) => pageErrors.push({ text: String(error && error.message ? error.message : error), stack: String(error && error.stack ? error.stack : ''), pageUrl: page.url() }));
  page.on('response', (response) => {
    if (response.status() >= 400) {
      failedResponses.push({ status: response.status(), url: response.url() });
    }
  });

  const recorder = makeRecorder();
  const result = { scenario: cfg.scenario, screenshots: [], consoleErrors, pageErrors, failedResponses };

  try {
    await login(page);
    const handler = scenarios[cfg.scenario];
    if (!handler) {
      throw new Error(`Unknown scenario ${cfg.scenario}`);
    }
    Object.assign(result, await handler(page, recorder));
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

run().catch((error) => {
  console.log(JSON.stringify({ error: String(error && error.message ? error.message : error) }));
  process.exit(1);
});
