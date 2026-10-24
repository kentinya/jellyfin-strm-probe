// Playback driver for the package-acceptance instance.
//
// It drives the real Jellyfin web client: log in, open each item's details page, click the
// real Play button and wait until the native media element reports both advancing media
// time and a decoded picture. It returns only redacted observations (advancing time, frame
// dimensions, container/duration and the request path family), never signed URLs or tokens.
//
// The legacy mode (no ``strict`` block in the scenario) keeps the original 0.1 s / width
// heuristic so the existing package acceptance is unchanged. The Slice 5 baseline entry
// passes a ``strict`` block, which additionally: requires an explicit ``mediaType`` per item
// (``video`` or ``audio``), captures a start screenshot and a second screenshot after the
// media time has advanced by ``minimumSeconds``, records decoded video frames or audio
// progress, and captures the PlaybackInfo request/response. A strict scenario that omits a
// required field is rejected instead of silently falling back to the loose heuristic.
//
// The toolchain is the test-only pinned Playwright under artifacts/dev-env/browser-tools; it
// is never a plugin production dependency.

import { createRequire } from 'node:module';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join } from 'node:path';

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

function sha256(value) {
  return createHash('sha256').update(String(value)).digest('hex');
}

function safeName(value) {
  return String(value || 'item').replace(/[^A-Za-z0-9._-]/g, '_').slice(0, 80);
}

// Only local synthetic fixture URLs are ever echoed back; anything else is reported as a hash.
function safePathValue(raw) {
  const value = String(raw || '').split('?')[0];
  if (/^http:\/\/media:\d+\//.test(value) || value.startsWith('/media/')) {
    return value;
  }
  return null;
}

function summarizePlaybackInfo(body) {
  const sources = Array.isArray(body && body.MediaSources) ? body.MediaSources : [];
  return {
    playSessionId: body && body.PlaySessionId ? String(body.PlaySessionId).slice(0, 64) : null,
    mediaSources: sources.map((source) => ({
      id: source.Id ? String(source.Id) : null,
      pathHash: source.Path ? sha256(source.Path) : null,
      pathValue: safePathValue(source.Path),
      protocol: source.Protocol ? String(source.Protocol) : null,
      isRemote: source.IsRemote === true,
      streamTypes: Array.from(new Set((source.MediaStreams || []).map((stream) => stream.Type))).sort(),
    })),
  };
}

function strictSettings(cfgObject) {
  if (cfgObject.strict === undefined || cfgObject.strict === null) {
    return { enabled: false };
  }
  const settings = cfgObject.strict;
  if (typeof settings !== 'object') {
    return { enabled: true, invalid: 'strict must be an object' };
  }
  const minimumSeconds = Number(settings.minimumSeconds);
  if (!Number.isFinite(minimumSeconds) || minimumSeconds < 1) {
    return { enabled: true, invalid: 'strict.minimumSeconds must be a number >= 1' };
  }
  if (typeof settings.screenshotDir !== 'string' || settings.screenshotDir.length === 0) {
    return { enabled: true, invalid: 'strict.screenshotDir is required' };
  }
  return { enabled: true, minimumSeconds, screenshotDir: settings.screenshotDir };
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

async function observeMedia(page) {
  return page.evaluate(() => {
    const video = document.querySelector('video');
    const audio = document.querySelector('audio');
    const media = video || audio;
    if (!media) {
      return { present: false };
    }
    let decodedFrames = null;
    if (video) {
      const quality = typeof video.getVideoPlaybackQuality === 'function' ? video.getVideoPlaybackQuality() : null;
      if (quality && typeof quality.totalVideoFrames === 'number') {
        decodedFrames = quality.totalVideoFrames;
      } else if (typeof video.webkitDecodedFrameCount === 'number') {
        decodedFrames = video.webkitDecodedFrameCount;
      }
    }
    return {
      present: true,
      element: video ? 'video' : 'audio',
      currentTime: Number(media.currentTime),
      duration: Number.isFinite(media.duration) ? Number(media.duration) : null,
      paused: media.paused,
      readyState: media.readyState,
      videoWidth: video ? video.videoWidth : null,
      videoHeight: video ? video.videoHeight : null,
      decodedFrames,
      mediaErrorCode: media.error ? media.error.code : null,
      srcPath: (media.currentSrc || '').split('?')[0],
      playerVisible: !!document.querySelector('.videoPlayerContainer, .videoOsdBottom, .osdHeader, .nowPlayingBar, .nowPlayingBarInfoContainer'),
    };
  });
}

// Sample the decoded picture of the media element into an 8x8 luminance grid. This is real
// decoded-pixel evidence (distinct from "the element exists"), and it lets a reviewer compare the
// rows: the A/B fixtures use different test patterns, so the grids must differ between rows.
async function pictureSample(page, element) {
  return page.evaluate((kind) => {
    const media = document.querySelector(kind === 'video' ? 'video' : 'audio, video');
    if (!media) {
      return null;
    }
    const width = kind === 'video' ? media.videoWidth : 0;
    const height = kind === 'video' ? media.videoHeight : 0;
    if (!width || !height) {
      return null;
    }
    const canvas = document.createElement('canvas');
    canvas.width = 64;
    canvas.height = 64;
    const context = canvas.getContext('2d', { willReadFrequently: true });
    if (!context) {
      return null;
    }
    try {
      context.drawImage(media, 0, 0, canvas.width, canvas.height);
    } catch (error) {
      return { error: String(error && error.message ? error.message : error) };
    }
    const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
    const grid = [];
    const colors = new Set();
    let total = 0;
    for (let gy = 0; gy < 8; gy += 1) {
      for (let gx = 0; gx < 8; gx += 1) {
        let sum = 0;
        for (let y = 0; y < 8; y += 1) {
          for (let x = 0; x < 8; x += 1) {
            const index = (((gy * 8 + y) * canvas.width) + (gx * 8 + x)) * 4;
            const luma = 0.299 * data[index] + 0.587 * data[index + 1] + 0.114 * data[index + 2];
            sum += luma;
            total += luma;
            colors.add((data[index] >> 4) * 256 + (data[index + 1] >> 4) * 16 + (data[index + 2] >> 4));
          }
        }
        grid.push(Math.round(sum / 64));
      }
    }
    return {
      width,
      height,
      meanLuma: Math.round((total / (canvas.width * canvas.height)) * 100) / 100,
      distinctColors: colors.size,
      grid,
    };
  }, element);
}

// End the playback through the client's own stop path before the browser goes away.
//
// The pinned web client stops a playback from the video OSD page's own ``viewbeforehide`` handler and
// from the app's ``beforeunload`` handler; both reach ``playbackManager.stop()``, which posts
// ``Sessions/Playing/Stopped``. The server turns that report into ``KillTranscodingJobs``
// (``Jellyfin.Api/Controllers/PlaystateController.cs``). Closing the browser without it left the owned
// transcode job alive until its own 60 s kill timer, so stopping the owned instance afterwards
// consumed the compose grace period and exited 137. This only performs real client navigations (the
// same route changes the OSD back button and the native back command trigger) and records what the
// client actually did; it never calls internal playback functions and never turns a window that
// failed to start playback into a stop success.
async function endPlaybackLikeTheClient(page, budgetMs) {
  const stopReports = [];
  const onResponse = (response) => {
    if (/\/Sessions\/Playing\/Stopped/i.test(response.url())) {
      stopReports.push({ status: response.status(), method: response.request().method(),
        path: redactUrl(response.url()) });
    }
  };
  const attempts = [];
  page.on('response', onResponse);
  let mediaElement = null;
  try {
    const navigate = async (action, operation) => {
      try {
        await operation();
        attempts.push({ action, navigated: true });
        return true;
      } catch (error) {
        attempts.push({ action, error: String(error && error.message ? error.message : error).slice(0, 160) });
        return false;
      }
    };
    // 1) The route change the OSD back button performs: the client's router hides the video OSD page,
    //    and that page's own viewbeforehide handler stops the player.
    await navigate('osd-back', () => page.goBack({ waitUntil: 'domcontentloaded', timeout: budgetMs }));
    let reported = await waitForStopReports(stopReports, 15000);
    if (!reported) {
      // 2) A second real client route: loading the app home route hides the OSD page the same way, so
      //    the identical client stop handler runs.
      await navigate('client-route-home', () => page.goto(cfg.baseUrl + '/web/index.html#/home.html',
        { waitUntil: 'domcontentloaded', timeout: budgetMs }));
      reported = await waitForStopReports(stopReports, 15000);
    }
    if (!reported) {
      // 3) The app's own beforeunload handler stops a playing media element; dispatch the real event
      //    the browser fires when the page is left.
      try {
        await page.evaluate(() => window.dispatchEvent(new Event('beforeunload', { cancelable: true })));
        attempts.push({ action: 'beforeunload', navigated: false });
      } catch (error) {
        attempts.push({ action: 'beforeunload', error: String(error && error.message ? error.message : error).slice(0, 160) });
      }
      reported = await waitForStopReports(stopReports, 15000);
    }
    mediaElement = await page.evaluate(() => {
      const video = document.querySelector('video');
      const audio = document.querySelector('audio');
      const media = video || audio;
      return media
        ? { present: true, element: video ? 'video' : 'audio', paused: media.paused,
            currentTime: Number(media.currentTime) }
        : { present: false };
    }).catch(() => null);
  } finally {
    page.off('response', onResponse);
  }
  return {
    stopReports,
    stopReported: stopReports.length > 0,
    stopStatuses: stopReports.map((report) => report.status),
    attempts,
    mediaElementAfterStop: mediaElement,
  };
}

async function waitForStopReports(stopReports, budgetMs) {
  const deadline = Date.now() + budgetMs;
  while (Date.now() < deadline) {
    if (stopReports.length > 0) {
      return true;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  return stopReports.length > 0;
}

async function strictPlay(page, item, strict) {
  const slug = safeName(item.id || item.name);
  mkdirSync(strict.screenshotDir, { recursive: true });
  const observations = [];
  let startShot = null;
  let progressShot = null;
  let incompleteShot = null;
  let observation = null;
  let startObservation = null;
  const deadline = Date.now() + 120000;
  while (Date.now() < deadline) {
    const state = await observeMedia(page);
    if (state.present) {
      observation = state;
      if (!startShot && state.currentTime > 0.2) {
        startShot = join(strict.screenshotDir, `${slug}-start.png`);
        await page.screenshot({ path: startShot });
        startObservation = { phase: 'start', currentTime: state.currentTime, element: state.element,
          decodedFrames: state.decodedFrames, picture: await pictureSample(page, state.element) };
        observations.push(startObservation);
      }
      // The contract is a real advance of the media clock between the start observation and the
      // progress observation, so the threshold is measured from the start sample. Measuring an
      // absolute media time let a playback that only advanced ~4.9 s pass as "at least 5 s".
      if (startObservation && !progressShot
          && state.currentTime - startObservation.currentTime >= strict.minimumSeconds) {
        progressShot = join(strict.screenshotDir, `${slug}-progress.png`);
        await page.screenshot({ path: progressShot });
        observations.push({ phase: 'progress', currentTime: state.currentTime, element: state.element,
          decodedFrames: state.decodedFrames,
          advancedSeconds: state.currentTime - startObservation.currentTime,
          picture: await pictureSample(page, state.element) });
        break;
      }
    }
    await page.waitForTimeout(500);
  }
  if (!progressShot) {
    incompleteShot = join(strict.screenshotDir, `${slug}-incomplete.png`);
    await page.screenshot({ path: incompleteShot }).catch(() => {});
  }
  const advancedSeconds = startObservation && observation
    ? observation.currentTime - startObservation.currentTime
    : null;
  return { observation, observations, startShot, progressShot, incompleteShot,
    startCurrentTime: startObservation ? startObservation.currentTime : null,
    advancedSeconds };
}

// Choose one native media source (version) through the details page's own source selector.
//
// The pinned web client renders an emby-select `.selectSource` only when the item really has more
// than one MediaSource, and it loads the chosen version in its own `change` handler. This performs
// the same real selection an administrator makes: it refuses a selector that is missing or does not
// offer the requested id, fires the client's own `change` event, waits for the client's alternate
// version request, and re-reads the selection. It never calls an internal playback function.
async function chooseSource(page, item) {
  const wanted = String(item.selectedSourceId);
  const marker = String(item.selectedSourceIdProgressMarker || '');
  const select = page.locator('.selectSource');
  await select.waitFor({ state: 'attached', timeout: 30000 });
  const options = await page.evaluate(() => Array.from(document.querySelectorAll('.selectSource option'))
    .map((option) => ({ value: String(option.value), text: String(option.textContent || '') })));
  const matching = options.filter((option) => option.value.replace(/-/g, '').toLowerCase()
    === wanted.replace(/-/g, '').toLowerCase());
  if (matching.length !== 1) {
    return { requested: wanted, options, error: 'the requested media source is not offered by the native selector' };
  }
  const value = matching[0].value;
  const alternate = page.waitForResponse((response) => {
    const path = new URL(response.url()).pathname.replace(/-/g, '').toLowerCase();
    return path.includes(value.replace(/-/g, '').toLowerCase()) && response.status() < 400;
  }, { timeout: 60000 }).catch(() => null);
  await page.evaluate((selected) => {
    const element = document.querySelector('.selectSource');
    element.value = selected;
    element.dispatchEvent(new Event('change', { bubbles: true }));
  }, value);
  const alternateResponse = await alternate;
  await page.waitForFunction((selected) => {
    const element = document.querySelector('.selectSource');
    return !!element && element.value === selected;
  }, value, { timeout: 30000 });
  const observed = await page.evaluate(() => {
    const element = document.querySelector('.selectSource');
    return { value: element ? element.value : null, text: element && element.selectedOptions[0] ? element.selectedOptions[0].textContent : null };
  });
  return {
    requested: wanted,
    options,
    selected: observed.value,
    selectedText: observed.text,
    alternateVersionLoaded: !!alternateResponse,
    alternateVersionStatus: alternateResponse ? alternateResponse.status() : null,
    markerMatched: marker ? String(observed.text || '').includes(marker) : null,
  };
}

async function playItem(page, item, strict, consoleErrors) {
  const mediaRequests = [];
  const playbackInfo = [];
  let requestErrorShot = null;
  let playbackStop = null;
  let consoleBookmark = consoleErrors ? consoleErrors.length : 0;
  if (strict.enabled) {
    mkdirSync(strict.screenshotDir, { recursive: true });
  }
  const onResponse = (response) => {
    const url = response.url();
    if (/\/videos\/|\/stream|\.m3u8|\.mp4|\.mkv|\.m4a|\.mp3|\/Audio\//i.test(url)) {
      mediaRequests.push({ status: response.status(), path: redactUrl(url), kind: 'media' });
      // A failed media/stream response is a failure state the reviewer must be able to open; the
      // first one is captured next to the normal screenshots without touching the legacy output.
      if (strict.enabled && response.status() >= 400 && requestErrorShot === null) {
        requestErrorShot = join(strict.screenshotDir, `${safeName(item.id || item.name)}-request-error-${response.status()}.png`);
        page.screenshot({ path: requestErrorShot }).catch(() => {});
      }
    }
    if (/\/PlaybackInfo/i.test(url)) {
      const request = response.request();
      const index = playbackInfo.length;
      response.json().then((body) => {
        const entry = { status: response.status(), method: request.method(), urlPath: redactUrl(url), body: summarizePlaybackInfo(body) };
        // The redacted summary cannot prove the full stream fields, so strict mode additionally keeps
        // the exact raw response next to the screenshots for the three-stage field comparison.
        if (strict.enabled) {
          entry.rawBodyFile = join(strict.screenshotDir, `${safeName(item.id || item.name)}-playbackinfo-${index}.json`);
          writeFileSync(entry.rawBodyFile, JSON.stringify(body, null, 2));
        }
        playbackInfo.push(entry);
      }).catch(() => {
        playbackInfo.push({ status: response.status(), method: request.method(), urlPath: redactUrl(url), body: null });
      });
    }
  };
  page.on('response', onResponse);
  try {
    await page.goto(cfg.baseUrl + '/web/index.html#/details?id=' + item.id, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForSelector('.btnPlay', { timeout: 45000 });
    let sourceSelection = null;
    if (item.selectedSourceId) {
      sourceSelection = await chooseSource(page, item);
      if (sourceSelection.error) {
        return { name: item.name, itemId: item.id, mediaType: item.mediaType, advanced: false,
          sourceSelection };
      }
    }
    await page.click('.btnPlay');
    if (strict.enabled) {
      const strictResult = await strictPlay(page, item, strict);
      const observed = strictResult.observation;
      const advanced = !!(observed && observed.present
        && typeof strictResult.advancedSeconds === 'number'
        && strictResult.advancedSeconds >= strict.minimumSeconds
        && (observed.element === 'audio' || (observed.videoWidth || 0) > 0));
      for (let index = 0; index < 10 && playbackInfo.length === 0; index += 1) {
        await page.waitForTimeout(200);
      }
      // End the client playback now that this window's measurement evidence is complete, so the owned
      // transcode job is released through the client's own stop before the instance is stopped. Console
      // entries produced by that teardown navigation belong to the stop record, not to the measured
      // window, so the row's own console evidence stays exactly what the playback produced.
      consoleBookmark = consoleErrors ? consoleErrors.length : 0;
      try {
        playbackStop = await endPlaybackLikeTheClient(page, 30000);
      } catch (error) {
        playbackStop = { stopReported: false, error: String(error && error.message ? error.message : error).slice(0, 160) };
      }
      if (consoleErrors) {
        playbackStop.consoleErrors = consoleErrors.splice(consoleBookmark);
      }
      return {
        name: item.name,
        itemId: item.id,
        mediaType: item.mediaType,
        advanced,
        currentTime: observed ? observed.currentTime : null,
        duration: observed ? observed.duration : null,
        element: observed ? observed.element : null,
        videoWidth: observed ? observed.videoWidth : null,
        videoHeight: observed ? observed.videoHeight : null,
        decodedFrames: observed ? observed.decodedFrames : null,
        readyState: observed ? observed.readyState : null,
        paused: observed ? observed.paused : null,
        mediaErrorCode: observed ? observed.mediaErrorCode : null,
        playerVisible: observed ? observed.playerVisible : null,
        videoSrcPath: observed && observed.srcPath ? redactUrl(observed.srcPath) : null,
        progressSeconds: strict.minimumSeconds,
        startCurrentTime: strictResult.startCurrentTime,
        advancedSeconds: strictResult.advancedSeconds,
        startScreenshot: strictResult.startShot,
        progressScreenshot: strictResult.progressShot,
        incompleteScreenshot: strictResult.incompleteShot,
        strictObservations: strictResult.observations,
        mediaRequests: mediaRequests.slice(0, 40),
        requestErrorScreenshot: requestErrorShot,
        playbackInfo: playbackInfo.slice(0, 10),
        playbackStop,
        sourceSelection,
      };
    }
    let observed = null;
    for (let index = 0; index < 80; index += 1) {
      const state = await observeMedia(page);
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
    // A window that never reached the strict measurement result (for example a real 500 before any
    // playback) has no successful playback to stop; its failure is preserved untouched.
    if (strict.enabled && playbackStop === null) {
      consoleBookmark = consoleErrors ? consoleErrors.length : 0;
      try {
        playbackStop = await endPlaybackLikeTheClient(page, 30000);
      } catch (error) {
        playbackStop = { stopReported: false, error: String(error && error.message ? error.message : error).slice(0, 160) };
      }
      if (consoleErrors) {
        playbackStop.consoleErrors = consoleErrors.splice(consoleBookmark);
      }
    }
  }
}

async function run() {
  const strict = strictSettings(cfg);
  if (strict.enabled && strict.invalid) {
    console.log(JSON.stringify({ error: strict.invalid, strictRejected: true }));
    process.exit(2);
  }
  if (strict.enabled) {
    for (const item of cfg.items || []) {
      if (item.mediaType !== 'video' && item.mediaType !== 'audio') {
        console.log(JSON.stringify({
          error: `strict playback requires item.mediaType 'video' or 'audio' for item ${JSON.stringify(item.name)}`,
          strictRejected: true,
        }));
        process.exit(2);
      }
    }
  }
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1400, height: 1000 }, locale: 'zh-CN', timezoneId: 'Asia/Shanghai' });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push({ text: message.text().slice(0, 200), url: redactUrl(message.location() && message.location().url) });
    }
  });
  const result = { strict: strict.enabled, results: [], consoleErrors };
  try {
    await login(page);
    for (const item of cfg.items) {
      result.results.push(await playItem(page, item, strict, consoleErrors));
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