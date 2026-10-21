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
import { mkdirSync, readFileSync } from 'node:fs';
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

async function strictPlay(page, item, strict) {
  const slug = safeName(item.id || item.name);
  mkdirSync(strict.screenshotDir, { recursive: true });
  const observations = [];
  let startShot = null;
  let progressShot = null;
  let incompleteShot = null;
  let observation = null;
  const deadline = Date.now() + 90000;
  while (Date.now() < deadline) {
    const state = await observeMedia(page);
    if (state.present) {
      observation = state;
      if (!startShot && state.currentTime > 0.2) {
        startShot = join(strict.screenshotDir, `${slug}-start.png`);
        await page.screenshot({ path: startShot });
        observations.push({ phase: 'start', currentTime: state.currentTime, element: state.element, decodedFrames: state.decodedFrames });
      }
      if (state.currentTime >= strict.minimumSeconds && !progressShot) {
        progressShot = join(strict.screenshotDir, `${slug}-progress.png`);
        await page.screenshot({ path: progressShot });
        observations.push({ phase: 'progress', currentTime: state.currentTime, element: state.element, decodedFrames: state.decodedFrames });
        break;
      }
    }
    await page.waitForTimeout(500);
  }
  if (!progressShot) {
    incompleteShot = join(strict.screenshotDir, `${slug}-incomplete.png`);
    await page.screenshot({ path: incompleteShot }).catch(() => {});
  }
  return { observation, observations, startShot, progressShot, incompleteShot };
}

async function playItem(page, item, strict) {
  const mediaRequests = [];
  const playbackInfo = [];
  const onResponse = (response) => {
    const url = response.url();
    if (/\/videos\/|\/stream|\.m3u8|\.mp4|\.mkv|\.m4a|\.mp3|\/Audio\//i.test(url)) {
      mediaRequests.push({ status: response.status(), path: redactUrl(url), kind: 'media' });
    }
    if (/\/PlaybackInfo/i.test(url)) {
      const request = response.request();
      response.json().then((body) => {
        playbackInfo.push({ status: response.status(), method: request.method(), urlPath: redactUrl(url), body: summarizePlaybackInfo(body) });
      }).catch(() => {
        playbackInfo.push({ status: response.status(), method: request.method(), urlPath: redactUrl(url), body: null });
      });
    }
  };
  page.on('response', onResponse);
  try {
    await page.goto(cfg.baseUrl + '/web/index.html#/details?id=' + item.id, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForSelector('.btnPlay', { timeout: 45000 });
    await page.click('.btnPlay');
    if (strict.enabled) {
      const strictResult = await strictPlay(page, item, strict);
      const observed = strictResult.observation;
      const advanced = !!(observed && observed.present
        && observed.currentTime >= strict.minimumSeconds
        && (observed.element === 'audio' || (observed.videoWidth || 0) > 0));
      for (let index = 0; index < 10 && playbackInfo.length === 0; index += 1) {
        await page.waitForTimeout(200);
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
        startScreenshot: strictResult.startShot,
        progressScreenshot: strictResult.progressShot,
        incompleteScreenshot: strictResult.incompleteShot,
        strictObservations: strictResult.observations,
        mediaRequests: mediaRequests.slice(0, 40),
        playbackInfo: playbackInfo.slice(0, 10),
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
      result.results.push(await playItem(page, item, strict));
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