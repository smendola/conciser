// NBJ Condenser - Chrome Extension

console.log('[CONCISER] POPUP_BOOT: content-panel.js loaded');

// Forward declarations - actual implementations after this block
let currentUrl = null;
let currentJobId = null;
let currentTakeawaysJobId = null;
let eventSource = null;  // SSE connection for condense jobs
let takeawaysEventSource = null;  // SSE connection for takeaways jobs
// DEFAULT_SERVER_URL is injected at build time via build-info.js
let serverUrl = DEFAULT_SERVER_URL;
let strategies = [];
let voices = [];
let currentTab = 'condense';
let clientId = null;
let sseReconnectAttempts = 0;
let takeawaysSseReconnectAttempts = 0;
const SSE_RECONNECT_DELAY_MS = 1000;
const SSE_MAX_RECONNECT_ATTEMPTS = 3;
const POPUP_TAB_STORAGE_KEY = 'lastPopupTab';

function getServerCacheKeyPrefix() {
  return `serverCache:${serverUrl}`;
}

async function clearAllStateOnServerSwitchIfNeeded() {
  const storage = await chrome.storage.local.get(['lastServerUrl', 'settings']);
  const lastServerUrl = storage.lastServerUrl;
  const settings = storage.settings || {};
  const selectedServerUrl = normalizeServerUrl(settings.serverUrl || serverUrl);

  console.log('[CONCISER] METADATA_CACHE: server_switch_check', {
    lastServerUrl,
    selectedServerUrl
  });
  await apiLog('server_switch_check', { lastServerUrl, selectedServerUrl });

  if (lastServerUrl && normalizeServerUrl(lastServerUrl) !== selectedServerUrl) {
    console.log('[CONCISER] METADATA_CACHE: server_switch_wipe', {
      from: lastServerUrl,
      to: selectedServerUrl
    });
    await apiLog('server_switch_wipe', { from: lastServerUrl, to: selectedServerUrl });
    await chrome.storage.local.clear();
    await chrome.storage.local.set({
      settings: { serverUrl: selectedServerUrl },
      lastServerUrl: selectedServerUrl
    });
  }
}

function getStrategiesCacheKey() {
  return `${getServerCacheKeyPrefix()}:strategies`;
}

function getVoicesCacheKey(locale) {
  return `${getServerCacheKeyPrefix()}:voices:${locale}`;
}

function getLanguageOnlyLocale() {
  return (navigator.language || 'en').split('-')[0];
}

async function loadCachedStrategiesForCurrentServer() {
  const key = getStrategiesCacheKey();
  const storage = await chrome.storage.local.get([key]);
  const cache = storage[key];
  console.log('[CONCISER] METADATA_CACHE: strategies_cache_read', {
    serverUrl,
    key,
    hit: !!(cache && Array.isArray(cache.data)),
    count: cache && Array.isArray(cache.data) ? cache.data.length : 0
  });
  await apiLog('strategies_cache_read', {
    key,
    hit: !!(cache && Array.isArray(cache.data)),
    count: cache && Array.isArray(cache.data) ? cache.data.length : 0
  });
  if (cache && Array.isArray(cache.data)) {
    strategies = cache.data;
    updateStrategyDescription();
    return true;
  }
  return false;
}

async function loadCachedVoicesForCurrentServer(locale) {
  const key = getVoicesCacheKey(locale);
  const storage = await chrome.storage.local.get([key]);
  const cache = storage[key];
  console.log('[CONCISER] METADATA_CACHE: voices_cache_read', {
    serverUrl,
    locale,
    key,
    hit: !!(cache && Array.isArray(cache.data)),
    count: cache && Array.isArray(cache.data) ? cache.data.length : 0
  });
  await apiLog('voices_cache_read', {
    locale,
    key,
    hit: !!(cache && Array.isArray(cache.data)),
    count: cache && Array.isArray(cache.data) ? cache.data.length : 0
  });
  if (cache && Array.isArray(cache.data)) {
    voices = cache.data;
    return true;
  }
  return false;
}

async function fetchAndCacheStrategiesForCurrentServer() {
  console.log('[CONCISER] METADATA_CACHE: strategies_fetch_start', { serverUrl });
  await apiLog('strategies_fetch_start', {});
  const response = await fetchWithAuth(`${serverUrl}/api/strategies`);
  if (!response.ok) throw new Error(`Failed to fetch strategies (${response.status})`);
  const data = await response.json();
  strategies = data.strategies || [];
  const key = getStrategiesCacheKey();
  await chrome.storage.local.set({ [key]: { data: strategies, timestamp: Date.now() } });
  console.log('[CONCISER] METADATA_CACHE: strategies_cache_write', { serverUrl, key, count: strategies.length });
  await apiLog('strategies_cache_write', { key, count: strategies.length });
  updateStrategyDescription();
}

async function fetchAndCacheVoicesForCurrentServer(locale) {
  console.log('[CONCISER] METADATA_CACHE: voices_fetch_start', { serverUrl, locale });
  await apiLog('voices_fetch_start', { locale });
  const response = await fetchWithAuth(`${serverUrl}/api/voices?locale=${locale}`);
  if (!response.ok) throw new Error(`Failed to fetch voices (${response.status})`);
  const data = await response.json();
  voices = data.voices || [];
  const key = getVoicesCacheKey(locale);
  await chrome.storage.local.set({ [key]: { data: voices, locale, timestamp: Date.now() } });
  console.log('[CONCISER] METADATA_CACHE: voices_cache_write', { serverUrl, locale, key, count: voices.length });
  await apiLog('voices_cache_write', { locale, key, count: voices.length });
}

async function ensureServerMetadataLoaded({ allowNetwork = false } = {}) {
  const locale = getLanguageOnlyLocale();
  console.log('[CONCISER] METADATA_CACHE: ensure_metadata_start', { serverUrl, locale, allowNetwork });
  await apiLog('ensure_metadata_start', { locale, allowNetwork });
  const haveStrategies = await loadCachedStrategiesForCurrentServer();
  const haveVoices = await loadCachedVoicesForCurrentServer(locale);

  if (haveVoices) {
    populateLocaleSelect('localeSelect');
    populateLocaleSelect('takeawaysLocaleSelect');
    updateVoiceSelectForLocale('voiceSelect', document.getElementById('localeSelect').value);
    updateVoiceSelectForLocale('takeawaysVoiceSelect', document.getElementById('takeawaysLocaleSelect').value);
    const storage = await chrome.storage.local.get(['settings']);
    const settings = storage.settings || {};

    console.log('[CONCISER] METADATA_CACHE: restore_settings', {
      condenseLocale: settings.condenseLocale,
      condenseVoice: settings.condenseVoice,
      takeawaysLocale: settings.takeawaysLocale,
      takeawaysVoice: settings.takeawaysVoice
    });
    await apiLog('restore_settings', {
      condenseLocale: settings.condenseLocale,
      condenseVoice: settings.condenseVoice,
      takeawaysLocale: settings.takeawaysLocale,
      takeawaysVoice: settings.takeawaysVoice
    });

    const applySelection = (localeSelectId, voiceSelectId, savedLocaleKey, savedVoiceKey) => {
      const localeSelectEl = document.getElementById(localeSelectId);
      const voiceSelectEl = document.getElementById(voiceSelectId);
      const savedLocale = settings[savedLocaleKey];
      const savedVoice = settings[savedVoiceKey];

      let localeToUse = savedLocale;
      if (!localeToUse && savedVoice) {
        const voiceItem = voices.find(v => v.name === savedVoice);
        if (voiceItem) localeToUse = voiceItem.locale;
      }

      if (localeToUse) {
        localeSelectEl.value = localeToUse;
        updateVoiceSelectForLocale(voiceSelectId, localeToUse);
      }

      if (savedVoice) {
        voiceSelectEl.value = savedVoice;
      }

      console.log('[CONCISER] METADATA_CACHE: applied_selection', {
        localeSelectId,
        voiceSelectId,
        savedLocaleKey,
        savedVoiceKey,
        appliedLocale: localeSelectEl.value,
        appliedVoice: voiceSelectEl.value
      });
      apiLog('applied_selection', {
        localeSelectId,
        voiceSelectId,
        savedLocaleKey,
        savedVoiceKey,
        appliedLocale: localeSelectEl.value,
        appliedVoice: voiceSelectEl.value
      });
    };

    applySelection('localeSelect', 'voiceSelect', 'condenseLocale', 'condenseVoice');
    applySelection('takeawaysLocaleSelect', 'takeawaysVoiceSelect', 'takeawaysLocale', 'takeawaysVoice');
  }

  if (allowNetwork) {
    const tasks = [];
    if (!haveStrategies) tasks.push(fetchAndCacheStrategiesForCurrentServer());
    if (!haveVoices) tasks.push(fetchAndCacheVoicesForCurrentServer(locale).then(() => {
      populateLocaleSelect('localeSelect');
      populateLocaleSelect('takeawaysLocaleSelect');
      updateVoiceSelectForLocale('voiceSelect', document.getElementById('localeSelect').value);
      updateVoiceSelectForLocale('takeawaysVoiceSelect', document.getElementById('takeawaysLocaleSelect').value);
    }));
    if (tasks.length) {
      await Promise.allSettled(tasks);
    }
  }

  return { haveStrategies, haveVoices };
}

async function ensureClientId() {
  if (clientId) return clientId;
  const storage = await chrome.storage.local.get(['clientId']);
  let storedId = storage.clientId;
  if (!storedId) {
    const generated = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    storedId = `ext-${generated}`;
    await chrome.storage.local.set({ clientId: storedId });
  }
  clientId = storedId;
  return clientId;
}

function withAuthHeaders(options = {}) {
  const headers = new Headers(options.headers || {});
  if (clientId) {
    headers.set('X-User-Id', clientId);
  }
  return { ...options, headers };
}

async function fetchWithAuth(url, options = {}) {
  await ensureClientId();
  const method = (options && options.method) ? options.method : 'GET';
  console.log(`API_CALL: ${method} ${url}`);
  try {
    const response = await fetch(url, withAuthHeaders(options));
    console.log(`API_CALL_RESULT: ${method} ${url} -> ${response.status} ok=${response.ok}`);
    return response;
  } catch (error) {
    const message = error && error.message ? error.message : String(error);
    console.log(`API_CALL_ERROR: ${method} ${url} -> ${message}`);
    throw error;
  }
}

async function apiLog(event, data = {}) {
  return;
}

async function fetchArtifacts(jobId) {
  const response = await fetchWithAuth(`${serverUrl}/api/jobs/${jobId}/artifacts`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const msg = (data && data.error) ? data.error : `Failed to fetch artifacts (${response.status})`;
    throw new Error(msg);
  }
  return data;
}

async function openJobInNewTab(jobId) {
  const data = await fetchArtifacts(jobId);
  const artifacts = (data && Array.isArray(data.artifacts)) ? data.artifacts : [];
  const artifact = artifacts[0];
  const renderUrl = artifact ? toServerAbsoluteUrl(artifact.render_url) : null;
  if (!renderUrl) {
    throw new Error('No render_url available');
  }
  // Check if we're in content script context or popup context
  if (document.getElementById('nbj-condenser-container')) {
    // Content script context - use window.open
    window.open(renderUrl, '_blank');
  } else {
    // Popup context - use chrome.tabs.create
    chrome.tabs.create({ url: renderUrl });
  }
}

async function deleteJob(jobId) {
  const response = await fetchWithAuth(`${serverUrl}/api/jobs/${jobId}`, { method: 'DELETE' });
  if (!response.ok) {
    let message = `Failed to delete job ${jobId}`;
    try {
      const data = await response.json();
      if (data && data.error) message = data.error;
    } catch (_) {
      // ignore
    }
    throw new Error(message);
  }
  return {};
}

function getRecentJobBadge(outputFormat, jobType) {
  const normalizedFormat = (outputFormat || '').toString().trim().toLowerCase();

  if (normalizedFormat === 'audio' || normalizedFormat === 'mp3') {
    return { badgeClass: 'mp3', badgeText: 'MP3' };
  }

  if (normalizedFormat === 'text' || normalizedFormat === 'txt' || normalizedFormat === 'markdown' || normalizedFormat === 'md') {
    return { badgeClass: 'txt', badgeText: 'TXT' };
  }

  if (normalizedFormat === 'video' || normalizedFormat === 'mp4') {
    return { badgeClass: 'mp4', badgeText: 'MP4' };
  }

  if (jobType === 'takeaways') {
    return { badgeClass: 'txt', badgeText: 'TXT' };
  }

  return { badgeClass: 'mp4', badgeText: 'MP4' };
}

function toServerAbsoluteUrl(url) {
  if (!url) {
    return url;
  }

  try {
    return new URL(url, serverUrl).toString();
  } catch (_) {
    return url;
  }
}

// Helper functions - defined before initializePopup so they can be called from it
function showStatus(type, message, progress = '') {
  const container = document.getElementById('statusContainer');
  if (!container) {
    return;
  }

  let progressHtml = '';
  if (progress) {
    progressHtml = `<div class="progress">${progress}</div>`;
  }
  container.innerHTML = `<div class="status ${type}">${message.replace(/\n/g, '<br>')}${progressHtml}</div>`;
}

function showTakeawaysStatus(type, message, progress = '') {
  const container = document.getElementById('takeawaysStatusContainer');
  if (!container) {
    return;
  }

  let progressHtml = '';
  if (progress) {
    progressHtml = `<div class="progress">${progress}</div>`;
  }
  container.innerHTML = `<div class="status ${type}">${message.replace(/\n/g, '<br>')}${progressHtml}</div>`;
}

// SSE-based status checking (no longer used - replaced by startPolling SSE connection)
// Kept for potential fallback scenarios
async function checkStatus() {
  try {
    const response = await fetchWithAuth(`${serverUrl}/api/jobs/${currentJobId}`);

    if (response.status === 404) {
      showStatus('error', `Job ${currentJobId} not found on server`);
      resetButton();
      return;
    }

    const data = await response.json();

    if (data.status === 'completed') {
      showCompleted({ job_id: currentJobId });
    } else if (data.status === 'error') {
      showStatus('error', `Processing failed\n${data.error}`);
      resetButton();
    } else if (data.status === 'processing') {
      showStatus('processing', `Processing video...\nJob ID: ${currentJobId}`, data.progress);
    } else {
      showStatus('processing', `Status: ${data.status}\nJob ID: ${currentJobId}`);
    }
  } catch (error) {
    console.error('Status check error:', error);
    const errorMsg = error.message.includes('Failed to fetch')
      ? 'Connection lost. Check that the server is running or reload the extension.'
      : `Status check error: ${error.message}`;
    showStatus('error', errorMsg);
    resetButton();
  }
}

function showCompleted(data) {
  const container = document.getElementById('statusContainer');
  if (!container) return;

  const condenseBtn = document.getElementById('condenseBtn');
  if (condenseBtn) condenseBtn.style.display = 'none';

  container.innerHTML = `
    <div class="status completed">
      ✅ Video ready!<br>
      Job ID: ${currentJobId}
    </div>
    <button class="download-btn" id="downloadBtn">
      Watch Video
    </button>
  `;

  const downloadBtn = document.getElementById('downloadBtn');
  if (downloadBtn) {
    downloadBtn.addEventListener('click', async () => {
      openJobInNewTab(currentJobId).catch(err => console.error(err));
      // Reload recent jobs and reset UI
      await loadRecentJobs();
      resetButton();
      const statusContainer = document.getElementById('statusContainer');
      if (statusContainer) statusContainer.innerHTML = '';
      currentJobId = null;
    });
  }
}

function resetButton() {
  const condenseBtn = document.getElementById('condenseBtn');
  if (!condenseBtn) return;
  condenseBtn.disabled = false;
  condenseBtn.textContent = 'Condense Video';
  condenseBtn.style.display = '';
}

function startPollingInternal({ resetAttempts } = {}) {
  // Close any existing connection
  if (eventSource) {
    eventSource.close();
  }

  if (resetAttempts) {
    sseReconnectAttempts = 0;
  }

  // Create SSE connection
  const url = `${serverUrl}/api/jobs/${currentJobId}/stream?cid=${encodeURIComponent(clientId)}`;
  eventSource = new EventSource(url);

  eventSource.onmessage = async (event) => {
    const data = JSON.parse(event.data);

    if (data.status === 'completed') {
      eventSource.close();
      showCompleted({ job_id: currentJobId });
    } else if (data.status === 'error') {
      eventSource.close();
      showStatus('error', `Processing failed\n${data.error || 'Unknown error'}`);
      resetButton();
    } else if (data.status === 'processing') {
      showStatus('processing', `Processing video...\nJob ID: ${currentJobId}`, data.progress);
    } else {
      showStatus('processing', `Status: ${data.status}\nJob ID: ${currentJobId}`);
    }
  };

  // Called on connection errors (network issues, server down, etc.)
  eventSource.onerror = async (error) => {
    console.error('SSE connection error:', error);
    eventSource.close();

    if (sseReconnectAttempts < SSE_MAX_RECONNECT_ATTEMPTS) {
      sseReconnectAttempts += 1;
      showStatus('processing', `Connection lost. Reconnecting... (attempt ${sseReconnectAttempts}/${SSE_MAX_RECONNECT_ATTEMPTS})\nJob ID: ${currentJobId}`);
      await new Promise(resolve => setTimeout(resolve, SSE_RECONNECT_DELAY_MS));
      startPollingInternal({ resetAttempts: false });
      return;
    }

    // Try one regular fetch to see if job still exists
    try {
      const response = await fetchWithAuth(`${serverUrl}/api/jobs/${currentJobId}`);
      if (response.status === 404) {
        showStatus('error', `Job ${currentJobId} not found on server`);
        resetButton();
      } else {
        const errorMsg = 'Connection lost. Check that the server is running or reload the extension.';
        showStatus('error', errorMsg);
        resetButton();
      }
    } catch (e) {
      const errorMsg = 'Connection lost. Check that the server is running or reload the extension.';
      showStatus('error', errorMsg);
      resetButton();
    }
  };
}

function startPolling() {
  startPollingInternal({ resetAttempts: true });
}

function startTakeawaysPollingInternal({ resetAttempts } = {}) {
  // Close any existing connection
  if (takeawaysEventSource) {
    takeawaysEventSource.close();
  }

  if (resetAttempts) {
    takeawaysSseReconnectAttempts = 0;
  }

  // Create SSE connection for takeaways
  const url = `${serverUrl}/api/jobs/${currentTakeawaysJobId}/stream?cid=${encodeURIComponent(clientId)}`;
  takeawaysEventSource = new EventSource(url);

  takeawaysEventSource.onmessage = async (event) => {
    const data = JSON.parse(event.data);

    if (data.status === 'completed') {
      takeawaysEventSource.close();
      showTakeawaysCompleted({ job_id: currentTakeawaysJobId });
    } else if (data.status === 'error') {
      takeawaysEventSource.close();
      showTakeawaysStatus('error', `Processing failed\n${data.error || 'Unknown error'}`);
      resetTakeawaysButton();
    } else if (data.status === 'processing') {
      showTakeawaysStatus('processing', `Extracting takeaways...\nJob ID: ${currentTakeawaysJobId}`, data.progress);
    } else {
      showTakeawaysStatus('processing', `Status: ${data.status}\nJob ID: ${currentTakeawaysJobId}`);
    }
  };

  takeawaysEventSource.onerror = async (error) => {
    console.error('SSE connection error (takeaways):', error);
    takeawaysEventSource.close();

    if (takeawaysSseReconnectAttempts < SSE_MAX_RECONNECT_ATTEMPTS) {
      takeawaysSseReconnectAttempts += 1;
      showTakeawaysStatus('processing', `Connection lost. Reconnecting... (attempt ${takeawaysSseReconnectAttempts}/${SSE_MAX_RECONNECT_ATTEMPTS})\nJob ID: ${currentTakeawaysJobId}`);
      await new Promise(resolve => setTimeout(resolve, SSE_RECONNECT_DELAY_MS));
      startTakeawaysPollingInternal({ resetAttempts: false });
      return;
    }

    try {
      const response = await fetchWithAuth(`${serverUrl}/api/jobs/${currentTakeawaysJobId}`);
      if (response.status === 404) {
        showTakeawaysStatus('error', `Job ${currentTakeawaysJobId} not found on server`);
        resetTakeawaysButton();
      } else {
        const errorMsg = 'Connection lost. Check that the server is running or reload the extension.';
        showTakeawaysStatus('error', errorMsg);
        resetTakeawaysButton();
      }
    } catch (e) {
      const errorMsg = 'Connection lost. Check that the server is running or reload the extension.';
      showTakeawaysStatus('error', errorMsg);
      resetTakeawaysButton();
    }
  };
}

function startTakeawaysPolling() {
  startTakeawaysPollingInternal({ resetAttempts: true });
}

// Fallback check function (kept for potential fallback scenarios)
async function checkTakeawaysStatus() {
  try {
    const response = await fetchWithAuth(`${serverUrl}/api/jobs/${currentTakeawaysJobId}`);

    if (response.status === 404) {
      showTakeawaysStatus('error', `Job ${currentTakeawaysJobId} not found on server`);
      resetTakeawaysButton();
      return;
    }

    const data = await response.json();

    if (data.status === 'completed') {
      showTakeawaysCompleted({ job_id: currentTakeawaysJobId });
    } else if (data.status === 'error') {
      showTakeawaysStatus('error', `Processing failed\n${data.error}`);
      resetTakeawaysButton();
    } else if (data.status === 'processing') {
      showTakeawaysStatus('processing', `Extracting takeaways...\nJob ID: ${currentTakeawaysJobId}`, data.progress);
    } else {
      showTakeawaysStatus('processing', `Status: ${data.status}\nJob ID: ${currentTakeawaysJobId}`);
    }
  } catch (error) {
    console.error('Status check error:', error);
    const errorMsg = error.message.includes('Failed to fetch')
      ? 'Connection lost. Check that the server is running or reload the extension.'
      : `Status check error: ${error.message}`;
    showTakeawaysStatus('error', errorMsg);
    resetTakeawaysButton();
  }
}

function showTakeawaysCompleted(data) {
  const container = document.getElementById('takeawaysStatusContainer');
  if (!container) return;

  const takeawaysBtn = document.getElementById('takeawaysBtn');
  if (takeawaysBtn) takeawaysBtn.style.display = 'none';

  container.innerHTML = `
    <div class="status completed">
      ✅ Takeaways ready!<br>
      Job ID: ${currentTakeawaysJobId}
    </div>
    <button class="download-btn" id="downloadTakeawaysBtn">
      View Takeaways
    </button>
  `;

  const downloadBtn = document.getElementById('downloadTakeawaysBtn');
  if (downloadBtn) {
    downloadBtn.addEventListener('click', async () => {
      openJobInNewTab(currentTakeawaysJobId).catch(err => console.error(err));
      // Reload recent jobs and reset UI
      await loadRecentJobs();
      resetTakeawaysButton();
      const statusContainer = document.getElementById('takeawaysStatusContainer');
      if (statusContainer) statusContainer.innerHTML = '';
      currentTakeawaysJobId = null;
    });
  }
}

function resetTakeawaysButton() {
  const takeawaysBtn = document.getElementById('takeawaysBtn');
  if (!takeawaysBtn) return;
  takeawaysBtn.disabled = false;
  takeawaysBtn.textContent = 'Extract Takeaways';
  takeawaysBtn.style.display = '';
}

// Check for in-progress jobs and attach to them
async function checkForInProgressJobs(jobType) {
  try {
    console.log(`[CONCISER] Checking for in-progress ${jobType} jobs...`);
    const response = await fetchWithAuth(`${serverUrl}/api/jobs`);
    if (!response.ok) return;

    const data = await response.json();
    const jobs = data.jobs || [];

    // Find in-progress job for current URL and type
    const inProgressJob = jobs.find(job =>
      job.url === currentUrl &&
      job.type === jobType &&
      (job.status === 'processing' || job.status === 'queued')
    );

    if (inProgressJob) {
      console.log(`[CONCISER] Found in-progress ${jobType} job:`, inProgressJob.id);

      if (jobType === 'condense') {
        currentJobId = inProgressJob.id;
        const condenseBtn = document.getElementById('condenseBtn');
        if (condenseBtn) {
          condenseBtn.disabled = true;
          condenseBtn.textContent = 'Processing...';
        }
        showStatus('processing', `Resuming job...\nJob ID: ${currentJobId}`, inProgressJob.progress);
        startPolling();
      } else if (jobType === 'takeaways') {
        currentTakeawaysJobId = inProgressJob.id;
        const takeawaysBtn = document.getElementById('takeawaysBtn');
        if (takeawaysBtn) {
          takeawaysBtn.disabled = true;
          takeawaysBtn.textContent = 'Processing...';
        }
        showTakeawaysStatus('processing', `Resuming job...\nJob ID: ${currentTakeawaysJobId}`, inProgressJob.progress);
        startTakeawaysPolling();
      }
    } else {
      console.log(`[CONCISER] No in-progress ${jobType} job found for this video`);
    }
  } catch (error) {
    console.error(`[CONCISER] Error checking for in-progress ${jobType} jobs:`, error);
  }
}

// Initialize popup
async function initializePopup() {
  console.log('[CONCISER] POPUP_BOOT: initializePopup start');

  // Set build version (may not exist if UI is collapsed)
  const buildInfoEl = document.getElementById('buildInfo');
  if (buildInfoEl) {
    if (typeof BUILD_VERSION !== 'undefined') {
      console.log('[CONCISER] BUILD_VERSION found:', BUILD_VERSION);
      buildInfoEl.textContent = `${BUILD_VERSION}`;
    } else {
      console.log('[CONCISER] BUILD_VERSION not defined');
      buildInfoEl.textContent = '???';
    }
    buildInfoEl.addEventListener('click', () => chrome.runtime.sendMessage({ action: 'openOptionsPage' }));
  } else {
    console.log('[CONCISER] buildInfo element not found');
  }

  clientId = await ensureClientId();
  // Get current tab and check if it's YouTube
  // In content script context, just use window.location.href
  if (window.NBJ_CONTENT_SCRIPT_MODE) {
    // We're in content script context
    currentUrl = window.location.href;
  } else {
    // We're in popup context
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const tab = tabs[0];
    currentUrl = tab.url;
  }

  const condenseBtn = document.getElementById('condenseBtn');
  const takeawaysBtn = document.getElementById('takeawaysBtn');

  // Check if YouTube video page
  const youtubeRegex = /^https?:\/\/(www\.)?(youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})/;
  const match = currentUrl.match(youtubeRegex);

  if (match) {
    if (condenseBtn) condenseBtn.disabled = false;
    if (takeawaysBtn) takeawaysBtn.disabled = false;
  } else {
    if (condenseBtn) condenseBtn.disabled = true;
    if (takeawaysBtn) takeawaysBtn.disabled = true;
  }

  // Load settings and populate controls
  await clearAllStateOnServerSwitchIfNeeded();
  await loadSettings();
  await ensureServerMetadataLoaded({ allowNetwork: false });
  await ensureServerMetadataLoaded({ allowNetwork: true });

  // Setup tabs
  await setupTabs();

  // No job state persistence - server is source of truth
  // Just load recent jobs from server
  await loadRecentJobs();

  // Check for in-progress jobs and attach to them
  await checkForInProgressJobs(currentTab);

}

// Fetch and display recent jobs
async function loadRecentJobs() {
  try {
    const response = await fetchWithAuth(`${serverUrl}/api/jobs`);
    if (response.ok) {
      await ensureServerMetadataLoaded({ allowNetwork: true });
    }
    const data = await response.json();

    const jobs = Array.isArray(data.jobs) ? data.jobs : [];

    const condenseJobs = jobs.filter(job =>
      job.status === 'completed' && job.type === 'condense'
    ).slice(0, 5);

    const takeawaysJobs = jobs.filter(job =>
      job.status === 'completed' && job.type === 'takeaways'
    ).slice(0, 5);

    const renderJobs = (container, list, jobs) => {
      if (jobs.length > 0) {
        list.innerHTML = jobs.map((job, index) => {
          const date = new Date(job.created_at);
          const dateStr = date.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });

          const videoId = job.url.match(/[?&]v=([^&]+)/)?.[1] || job.id;
          const displayTitle = job.title || videoId;

          const { badgeClass, badgeText } = getRecentJobBadge('unknown', job.type);

          const jobHtml = `
            <div class="recent-job" data-job-id="${job.id}">
              <div class="recent-job-badge ${badgeClass}">${badgeText}</div>
              <div class="recent-job-details">
                <div class="recent-job-title">${displayTitle}</div>
                <div class="recent-job-timestamp">${dateStr}</div>
              </div>
              <button class="recent-job-delete" data-job-id="${job.id}" aria-label="Delete">×</button>
            </div>
          `;
          const dividerHtml = index < jobs.length - 1 ? '<div class="recent-job-divider"></div>' : '';

          return jobHtml + dividerHtml;
        }).join('');

        container.style.display = 'block';

        list.querySelectorAll('.recent-job').forEach(el => {
          el.addEventListener('click', () => {
            const jobId = el.getAttribute('data-job-id');
            openJobInNewTab(jobId).catch(err => console.error(err));
          });
        });

        list.querySelectorAll('.recent-job-delete').forEach(btn => {
          btn.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            const jobId = btn.getAttribute('data-job-id');
            btn.disabled = true;
            try {
              await deleteJob(jobId);
              await loadRecentJobs();
            } catch (err) {
              console.error(err);
              btn.disabled = false;
            }
          });
        });
      } else {
        container.style.display = 'none';
      }
    };

    // Display condense jobs
    const condenseContainer = document.getElementById('recentCondenseJobs');
    const condenseList = document.getElementById('recentCondenseJobsList');
    renderJobs(condenseContainer, condenseList, condenseJobs);

    // Display takeaways jobs
    const takeawaysContainer = document.getElementById('recentTakeawaysJobs');
    const takeawaysList = document.getElementById('recentTakeawaysJobsList');
    renderJobs(takeawaysContainer, takeawaysList, takeawaysJobs);

  } catch (error) {
    console.error('Failed to load recent jobs:', error);
  }
}

// Fetch strategies/voices are now loaded on first successful server contact and cached per-server.

async function setActiveTab(targetTab) {
  const tabButtons = document.querySelectorAll('.tab');
  const tabContents = document.querySelectorAll('.tab-content');

  if (!['condense', 'takeaways'].includes(targetTab)) {
    targetTab = 'condense';
  }

  tabButtons.forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-tab') === targetTab);
  });

  tabContents.forEach(content => {
    content.classList.toggle('active', content.id === `${targetTab}-tab`);
  });

  currentTab = targetTab;

  // Check for in-progress jobs when switching tabs
  await checkForInProgressJobs(targetTab);
}

// Setup tab switching
async function setupTabs() {
  const tabButtons = document.querySelectorAll('.tab');
  const storedTabState = await chrome.storage.local.get([POPUP_TAB_STORAGE_KEY]);
  await setActiveTab(storedTabState[POPUP_TAB_STORAGE_KEY] || 'condense');

  tabButtons.forEach(button => {
    button.addEventListener('click', async () => {
      const targetTab = button.getAttribute('data-tab');
      await setActiveTab(targetTab);
      await chrome.storage.local.set({ [POPUP_TAB_STORAGE_KEY]: targetTab });
    });
  });

  // Format radio buttons - show/hide voice select AND reset completed state
  const formatRadios = document.querySelectorAll('input[name="format"]');
  formatRadios.forEach(radio => {
    radio.addEventListener('change', () => {
      const voiceGroup = document.getElementById('takeawaysVoiceGroup');
      voiceGroup.style.display = radio.value === 'audio' ? 'block' : 'none';
      handleSettingChange();
    });
  });

  // Top radio buttons - reset completed state on change
  const topRadios = document.querySelectorAll('input[name="top"]');
  topRadios.forEach(radio => {
    radio.addEventListener('change', () => {
      handleSettingChange();
    });
  });
}

// Fetch strategies/voices are now loaded on first successful server contact and cached per-server.

function populateLocaleSelect(localeSelectId) {
  const select = document.getElementById(localeSelectId);
  if (!select) return;

  const locales = [...new Set(voices.map(v => v.locale))].sort();
  const userLocale = navigator.language.split('-')[0];
  const userLocaleLong = navigator.language;

  const previousValue = select.value;
  select.innerHTML = '';
  locales.forEach(locale => {
    const option = document.createElement('option');
    option.value = locale;
    option.textContent = locale;
    select.appendChild(option);
  });

  if (previousValue && locales.includes(previousValue)) {
    select.value = previousValue;
    return;
  }

  if (locales.includes(userLocaleLong)) {
    select.value = userLocaleLong;
  } else if (locales.find(l => l.startsWith(userLocale))) {
    select.value = locales.find(l => l.startsWith(userLocale));
  }
}

function updateVoiceSelectForLocale(voiceSelectId, locale) {
  const select = document.getElementById(voiceSelectId);
  if (!select) return;

  const filteredVoices = voices.filter(v => v.locale === locale);
  const currentVal = select.value;
  select.innerHTML = '';

  if (filteredVoices.length === 0) {
    select.innerHTML = '<option value="">No voices</option>';
    return;
  }

  filteredVoices.forEach(voice => {
    const option = document.createElement('option');
    option.value = voice.name;
    option.textContent = `${voice.friendly_name} (${voice.gender})`;
    select.appendChild(option);
  });

  if (filteredVoices.some(v => v.name === currentVal)) {
    select.value = currentVal;
  } else {
    select.value = filteredVoices[0].name;
  }
}

function updateCondenseVoiceVisibility(videoMode) {
  const voiceGroup = document.getElementById('condenseVoiceGroup');
  const speechGroup = document.getElementById('condenseSpeechGroup');
  const isText = videoMode === 'text';
  if (voiceGroup) voiceGroup.style.display = isText ? 'none' : '';
  if (speechGroup) speechGroup.style.display = isText ? 'none' : '';
}

// Load settings from storage
async function loadSettings() {
  const storage = await chrome.storage.local.get(['settings']);
  const saved = storage?.settings || {};
  const settings = Object.assign({
    serverUrl: DEFAULT_SERVER_URL,
    aggressiveness: 5,
    condenseLocale: null,
    condenseVoice: null,
    takeawaysLocale: null,
    takeawaysVoice: null,
    takeawaysFormat: 'text',
    speechSpeed: 1.00,
    videoMode: 'slideshow',
    prependIntro: false
  }, saved);

  const previousServerUrl = serverUrl;
  serverUrl = normalizeServerUrl(settings.serverUrl);
  if (previousServerUrl !== serverUrl) {
    await chrome.storage.local.set({ lastServerUrl: serverUrl });
  }

  const aggrSlider = document.getElementById('aggressivenessSlider');
  const spdSlider = document.getElementById('speedSlider');
  aggrSlider.value = settings.aggressiveness;
  document.getElementById('aggressivenessValue').textContent = settings.aggressiveness;
  spdSlider.value = settings.speechSpeed;
  document.getElementById('speedValue').textContent = settings.speechSpeed.toFixed(2) + 'x';
  updateSliderFill(aggrSlider);
  updateSliderFill(spdSlider);
  const vmEl = document.querySelector(`input[name="videoMode"][value="${settings.videoMode}"]`);
  if (vmEl) vmEl.checked = true;
  updateCondenseVoiceVisibility(settings.videoMode || 'slideshow');
  document.getElementById('prependIntroCheck').checked = settings.prependIntro || false;

  const normalizedTakeawaysFormat = (settings.takeawaysFormat || 'text').toString().trim().toLowerCase();
  const takeawaysFormatValue = normalizedTakeawaysFormat === 'audio' ? 'audio' : 'text';
  const formatTextEl = document.getElementById('formatText');
  const formatAudioEl = document.getElementById('formatAudio');
  if (takeawaysFormatValue === 'audio') {
    if (formatAudioEl) formatAudioEl.checked = true;
  } else {
    if (formatTextEl) formatTextEl.checked = true;
  }
  const voiceGroup = document.getElementById('takeawaysVoiceGroup');
  if (voiceGroup) voiceGroup.style.display = takeawaysFormatValue === 'audio' ? 'block' : 'none';
}

// Save settings to storage
async function saveSettings() {
  const storage = await chrome.storage.local.get(['settings']);
  const existing = storage.settings || {};

  const condenseLocale = document.getElementById('localeSelect').value;
  const takeawaysLocale = document.getElementById('takeawaysLocaleSelect').value;
  const selectedFormat = document.querySelector('input[name="format"]:checked');
  const takeawaysFormat = selectedFormat ? selectedFormat.value : 'text';

  const settings = {
    ...existing,
    serverUrl: normalizeServerUrl(existing.serverUrl || serverUrl),
    aggressiveness: parseInt(document.getElementById('aggressivenessSlider').value),
    condenseLocale,
    condenseVoice: document.getElementById('voiceSelect').value,
    takeawaysLocale,
    takeawaysVoice: document.getElementById('takeawaysVoiceSelect').value,
    takeawaysFormat: takeawaysFormat,
    speechSpeed: parseFloat(document.getElementById('speedSlider').value),
    videoMode: (document.querySelector('input[name="videoMode"]:checked') || {}).value || 'slideshow',
    prependIntro: document.getElementById('prependIntroCheck').checked
  };

  await chrome.storage.local.set({ settings });
}

function normalizeServerUrl(value) {
  const trimmed = (value || '').trim();
  if (!trimmed) return DEFAULT_SERVER_URL;
  return trimmed.replace(/\/+$/, '');
}

// Update slider fill gradient to show progress up to thumb
function updateSliderFill(slider) {
  const min = parseFloat(slider.min);
  const max = parseFloat(slider.max);
  const val = parseFloat(slider.value);
  const pct = ((val - min) / (max - min) * 100).toFixed(1) + '%';
  slider.style.setProperty('--fill-pct', pct);
}

// Update strategy description based on slider value
function updateStrategyDescription() {
  const level = parseInt(document.getElementById('aggressivenessSlider').value);
  const strategy = strategies.find(s => s.level === level);

  if (strategy) {
    // Extract just the retention percentage from description
    const match = strategy.description.match(/\(([^)]+)\)/);
    const desc = match ? match[1] : strategy.description;
    document.getElementById('strategyDesc').textContent = desc;
  }
}

// Convert speech speed (0.9x-2.0x) to backend format (+/-N%)
function convertSpeedToRate(speed) {
  const percentage = Math.round((speed - 1.0) * 100);
  return percentage >= 0 ? `+${percentage}%` : `${percentage}%`;
}

// Unified settings handler
async function handleSettingChange() {
  await saveSettings();

  if (currentTab === 'condense') {
    const storage = await chrome.storage.local.get(['completedJobs']);
    if (storage.completedJobs && storage.completedJobs[currentUrl]) {
      console.log('Settings changed on a completed job - resetting to condense mode');
      delete storage.completedJobs[currentUrl];
      await chrome.storage.local.set({ completedJobs: storage.completedJobs });
      resetToCondenseMode();
      await loadRecentJobs();
    }
  } else if (currentTab === 'takeaways') {
    const storage = await chrome.storage.local.get(['completedTakeawaysJobs']);
    if (storage.completedTakeawaysJobs && storage.completedTakeawaysJobs[currentUrl]) {
      console.log('Settings changed on a completed takeaways job - resetting');
      delete storage.completedTakeawaysJobs[currentUrl];
      await chrome.storage.local.set({ completedTakeawaysJobs: storage.completedTakeawaysJobs });
      resetTakeawaysButton();
      document.getElementById('takeawaysStatusContainer').innerHTML = '';
      currentTakeawaysJobId = null;
      await loadRecentJobs();
    }
  }
}

function resetToCondenseMode() {
  // Clear status container
  document.getElementById('statusContainer').innerHTML = '';

  // Show and enable condense button
  const condenseBtn = document.getElementById('condenseBtn');
  condenseBtn.style.display = '';
  condenseBtn.disabled = false;
  condenseBtn.textContent = 'Condense Video';

  // Reset current job ID
  currentJobId = null;
}

// Setup event listeners for controls
function setupEventListeners() {
  const aggressivenessSlider = document.getElementById('aggressivenessSlider');
  const speedSlider = document.getElementById('speedSlider');
  const localeSelect = document.getElementById('localeSelect');
  const takeawaysLocaleSelect = document.getElementById('takeawaysLocaleSelect');
  const voiceSelect = document.getElementById('voiceSelect');
  const takeawaysVoiceSelect = document.getElementById('takeawaysVoiceSelect');
  const prependIntroCheck = document.getElementById('prependIntroCheck');
  const condenseBtn = document.getElementById('condenseBtn');
  const takeawaysBtn = document.getElementById('takeawaysBtn');

  if (!aggressivenessSlider || !speedSlider || !condenseBtn || !takeawaysBtn) {
    return;
  }

  aggressivenessSlider.addEventListener('input', (e) => {
    document.getElementById('aggressivenessValue').textContent = e.target.value;
    updateSliderFill(e.target);
    updateStrategyDescription();
    handleSettingChange();
  });

  speedSlider.addEventListener('input', (e) => {
    const value = parseFloat(e.target.value);
    document.getElementById('speedValue').textContent = value.toFixed(2) + 'x';
    updateSliderFill(e.target);
    handleSettingChange();
  });

  if (localeSelect) {
    localeSelect.addEventListener('change', (e) => {
      updateVoiceSelectForLocale('voiceSelect', e.target.value);
      handleSettingChange();
    });
  }

  if (takeawaysLocaleSelect) {
    takeawaysLocaleSelect.addEventListener('change', (e) => {
      updateVoiceSelectForLocale('takeawaysVoiceSelect', e.target.value);
      handleSettingChange();
    });
  }

  if (voiceSelect) {
    voiceSelect.addEventListener('change', () => {
      handleSettingChange();
    });
  }

  if (takeawaysVoiceSelect) {
    takeawaysVoiceSelect.addEventListener('change', handleSettingChange);
  }

  document.querySelectorAll('input[name="videoMode"]').forEach(radio => {
    radio.addEventListener('change', () => {
      updateCondenseVoiceVisibility(radio.value);
      handleSettingChange();
    });
  });

  if (prependIntroCheck) {
    prependIntroCheck.addEventListener('change', handleSettingChange);
  }

  // Condense button click
  document.getElementById('condenseBtn').addEventListener('click', async () => {
    const condenseBtn = document.getElementById('condenseBtn');
    condenseBtn.disabled = true;
    condenseBtn.textContent = 'Processing...';

    try {
      // Get current settings
      const aggressiveness = parseInt(document.getElementById('aggressivenessSlider').value);
      const voice = document.getElementById('voiceSelect').value;
      const speechSpeed = parseFloat(document.getElementById('speedSlider').value);
      const speechRate = convertSpeedToRate(speechSpeed);
      const videoMode = (document.querySelector('input[name="videoMode"]:checked') || {}).value || 'slideshow';
      const prependIntro = document.getElementById('prependIntroCheck').checked;

      const response = await fetchWithAuth(`${serverUrl}/api/jobs`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          type: 'condense',
          url: currentUrl,
          params: {
            aggressiveness: aggressiveness,
            voice: voice,
            speech_rate: speechRate,
            video_mode: videoMode,
            prepend_intro: prependIntro
          }
        })
      });

      const data = await response.json();

      if (response.ok) {
        currentJobId = data.id;

        showStatus('processing', `Processing started\nJob ID: ${currentJobId}`);
        startPolling();
      } else {
        if (response.status === 429 && data && data.active_job && data.active_job.id) {
          const activeId = data.active_job.id;
          const activeStatus = data.active_job.status || 'processing';
          showStatus(
            'error',
            `You already have an active job (${activeId}, ${activeStatus}).\nPlease wait for it to finish, or cancel it from the Recent list, then try again.`
          );
        } else {
          showStatus('error', data.error || 'Failed to submit video');
        }
        condenseBtn.disabled = false;
        condenseBtn.textContent = 'Condense Video';
      }
    } catch (error) {
      showStatus('error', `Connection error: ${error.message}\nCheck that the server is running`);
      condenseBtn.disabled = false;
      condenseBtn.textContent = 'Condense Video';
    }
  });

  // Takeaways button click
  document.getElementById('takeawaysBtn').addEventListener('click', async () => {
    const takeawaysBtn = document.getElementById('takeawaysBtn');
    takeawaysBtn.disabled = true;
    takeawaysBtn.textContent = 'Processing...';

    try {
      // Get takeaways settings
      const topRadio = document.querySelector('input[name="top"]:checked');
      const formatRadio = document.querySelector('input[name="format"]:checked');
      const top = topRadio.value === 'auto' ? null : parseInt(topRadio.value);
      const format = formatRadio.value;
      const voice = format === 'audio' ? document.getElementById('takeawaysVoiceSelect').value : null;

      const params = {
        format_type: format
      };

      if (top !== null) {
        params.top = top;
      }

      if (voice) {
        params.voice = voice;
      }

      const response = await fetchWithAuth(`${serverUrl}/api/jobs`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          type: 'takeaways',
          url: currentUrl,
          params
        })
      });

      const data = await response.json();

      if (response.ok) {
        currentTakeawaysJobId = data.id;

        showTakeawaysStatus('processing', `Processing started\nJob ID: ${currentTakeawaysJobId}`);
        startTakeawaysPolling();
      } else {
        if (response.status === 429 && data && data.active_job && data.active_job.id) {
          const activeId = data.active_job.id;
          const activeStatus = data.active_job.status || 'processing';
          showTakeawaysStatus(
            'error',
            `You already have an active job (${activeId}, ${activeStatus}).\nPlease wait for it to finish, or cancel it from the Recent list, then try again.`
          );
        } else {
          showTakeawaysStatus('error', data.error || 'Failed to extract takeaways');
        }
        takeawaysBtn.disabled = false;
        takeawaysBtn.textContent = 'Extract Takeaways';
      }
    } catch (error) {
      showTakeawaysStatus('error', `Connection error: ${error.message}\nCheck that the server is running`);
      takeawaysBtn.disabled = false;
      takeawaysBtn.textContent = 'Extract Takeaways';
    }
  });
}

// Removed duplicate code - initialization handled by NBJ_CONTENT_SCRIPT_MODE check below

// Call setupEventListeners when in popup mode (not content script)
// Don't auto-run when loaded as content script - wait for content.js to call us
// Display build version only if we're in popup context (not content script)
if (!window.NBJ_CONTENT_SCRIPT_MODE) {
  // We're in popup context (not content script)
  try {
    const buildInfoEl = document.getElementById('buildInfo');
    if (buildInfoEl) {
      if (typeof BUILD_VERSION !== 'undefined') {
        buildInfoEl.textContent = `${BUILD_VERSION}`;
      } else {
        buildInfoEl.textContent = '???';
      }
    }
  } catch (e) {
    // Ignore
  }
  // Setup event listeners for popup mode
  setupEventListeners();
  // Run initialization
  initializePopup();
}
// If we're in content script context, content.js will call initializePopup() and setupEventListeners() after injecting the DOM

// Old duplicate code below - keeping for reference but not executing
/*
// Condense button click
document.getElementById('condenseBtn').addEventListener('click', async () => {
  const condenseBtn = document.getElementById('condenseBtn');
  condenseBtn.disabled = true;
  condenseBtn.textContent = 'Processing...';

  try {
    // Get current settings
    const aggressiveness = parseInt(document.getElementById('aggressivenessSlider').value);
    const voice = document.getElementById('voiceSelect').value;
    const speechSpeed = parseFloat(document.getElementById('speedSlider').value);
    const speechRate = convertSpeedToRate(speechSpeed);
    const videoMode = document.getElementById('videoModeSelect').value;
    const prependIntro = document.getElementById('prependIntroCheck').checked;

    const response = await fetchWithAuth(`${serverUrl}/api/jobs`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        type: 'condense',
        url: currentUrl,
        params: {
          aggressiveness: aggressiveness,
          voice: voice,
          speech_rate: speechRate,
          video_mode: videoMode,
          prepend_intro: prependIntro
        }
      })
    });

    const data = await response.json();

    if (response.ok) {
      currentJobId = data.id;

      // Clear any previous completed job for this URL
      const storage = await chrome.storage.local.get(['completedJobs']);
      if (storage.completedJobs && storage.completedJobs[currentUrl]) {
        delete storage.completedJobs[currentUrl];
        await chrome.storage.local.set({ completedJobs: storage.completedJobs });
      }

      // Save job to storage for persistence
      await chrome.storage.local.set({
        activeJob: {
          jobId: currentJobId,
          url: currentUrl,
          startedAt: new Date().toISOString()
        }
      });

      showStatus('processing', `Processing started\nJob ID: ${currentJobId}`);
      startPolling();
    } else {
      showStatus('error', data.error || 'Failed to submit video');
      condenseBtn.disabled = false;
      condenseBtn.textContent = 'Condense Video';
    }
  } catch (error) {
    showStatus('error', `Connection error: ${error.message}\nCheck that the server is running`);
    condenseBtn.disabled = false;
    condenseBtn.textContent = 'Condense Video';
  }
});

// All helper functions moved earlier in file before initializePopup

// REMOVED DUPLICATE: async function checkStatus() {
  try {
    const response = await fetchWithAuth(`${serverUrl}/api/jobs/${currentJobId}`);

    // If job returns 404
    if (response.status === 404) {
      clearInterval(pollInterval);
      showStatus('error', `Job ${currentJobId} not found on server`);
      resetButton();
      return;
    }

    const data = await response.json();

    if (data.status === 'completed') {
      clearInterval(pollInterval);
      showCompleted({ job_id: currentJobId });
    } else if (data.status === 'error') {
      clearInterval(pollInterval);
      showStatus('error', `Processing failed\n${data.error}`);
      resetButton();
    } else if (data.status === 'processing') {
      showStatus('processing', `Processing video...\nJob ID: ${currentJobId}`, data.progress);
    } else {
      showStatus('processing', `Status: ${data.status}\nJob ID: ${currentJobId}`);
    }
  } catch (error) {
    // Don't stop polling on network errors
    console.error('Polling error:', error);
  }
}

async function saveCompletedJob() {
  // Save this job as completed for this video URL
  const storage = await chrome.storage.local.get(['completedJobs']);
  const completedJobs = storage.completedJobs || {};
  completedJobs[currentUrl] = currentJobId;

  await chrome.storage.local.set({ completedJobs });
  await chrome.storage.local.remove(['activeJob']);
}

async function clearJobStorage() {
  await chrome.storage.local.remove(['activeJob']);
}

function showCompleted(data) {
  const container = document.getElementById('statusContainer');
  const condenseBtn = document.getElementById('condenseBtn');

  // Hide the condense button since job is complete
  condenseBtn.style.display = 'none';

  container.innerHTML = `
    <div class="status completed">
      ✅ Video ready!<br>
      Job ID: ${currentJobId}
    </div>
    <button class="download-btn" id="downloadBtn">
      Watch Video
    </button>
  `;

  document.getElementById('downloadBtn').addEventListener('click', () => {
    openJobInNewTab(currentJobId).catch(err => console.error(err));
  });
}

function resetButton() {
  const condenseBtn = document.getElementById('condenseBtn');
  condenseBtn.disabled = false;
  condenseBtn.textContent = 'Condense Video';
  condenseBtn.style.display = '';  // Make sure it's visible
}

// Takeaways button click
document.getElementById('takeawaysBtn').addEventListener('click', async () => {
  const takeawaysBtn = document.getElementById('takeawaysBtn');
  takeawaysBtn.disabled = true;
  takeawaysBtn.textContent = 'Processing...';

  try {
    // Get takeaways settings
    const topRadio = document.querySelector('input[name="top"]:checked');
    const formatRadio = document.querySelector('input[name="format"]:checked');
    const top = topRadio.value === 'auto' ? null : parseInt(topRadio.value);
    const format = formatRadio.value;
    const voice = format === 'audio' ? document.getElementById('takeawaysVoiceSelect').value : null;

    const params = {
      format_type: format
    };

    if (top !== null) {
      params.top = top;
    }

    if (voice) {
      params.voice = voice;
    }

    const response = await fetchWithAuth(`${serverUrl}/api/jobs`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        type: 'takeaways',
        url: currentUrl,
        params
      })
    });

    const data = await response.json();

    if (response.ok) {
      currentTakeawaysJobId = data.id;

      // Clear any previous completed takeaways for this URL
      const storage = await chrome.storage.local.get(['completedTakeawaysJobs']);
      if (storage.completedTakeawaysJobs && storage.completedTakeawaysJobs[currentUrl]) {
        delete storage.completedTakeawaysJobs[currentUrl];
        await chrome.storage.local.set({ completedTakeawaysJobs: storage.completedTakeawaysJobs });
      }

      // Save job to storage for persistence
      await chrome.storage.local.set({
        activeTakeawaysJob: {
          jobId: currentTakeawaysJobId,
          url: currentUrl,
          startedAt: new Date().toISOString()
        }
      });

      showTakeawaysStatus('processing', `Processing started\nJob ID: ${currentTakeawaysJobId}`);
      startTakeawaysPolling();
    } else {
      showTakeawaysStatus('error', data.error || 'Failed to extract takeaways');
      takeawaysBtn.disabled = false;
      takeawaysBtn.textContent = 'Extract Takeaways';
    }
  } catch (error) {
    showTakeawaysStatus('error', `Connection error: ${error.message}\nCheck that the server is running`);
    takeawaysBtn.disabled = false;
    takeawaysBtn.textContent = 'Extract Takeaways';
  }
});

// showTakeawaysStatus and startTakeawaysPolling moved earlier in file before initializePopup

async function checkTakeawaysStatus() {
  try {
    const response = await fetchWithAuth(`${serverUrl}/api/jobs/${currentTakeawaysJobId}`);

    // If job returns 404, forget it ever existed
    if (response.status === 404) {
      clearInterval(takeawaysPollInterval);
      await clearTakeawaysJobStorage();
      // Also clear completed takeaways jobs for this URL
      const storage = await chrome.storage.local.get(['completedTakeawaysJobs']);
      if (storage.completedTakeawaysJobs && storage.completedTakeawaysJobs[currentUrl]) {
        delete storage.completedTakeawaysJobs[currentUrl];
        await chrome.storage.local.set({ completedTakeawaysJobs: storage.completedTakeawaysJobs });
      }
      showTakeawaysStatus('error', `Job ${currentTakeawaysJobId} not found on server`);
      resetTakeawaysButton();
      return;
    }

    const data = await response.json();

    if (data.status === 'completed') {
      clearInterval(takeawaysPollInterval);
      await saveTakeawaysCompletedJob();
      showTakeawaysCompleted({ job_id: currentTakeawaysJobId });
    } else if (data.status === 'error') {
      clearInterval(takeawaysPollInterval);
      await clearTakeawaysJobStorage();
      showTakeawaysStatus('error', `Processing failed\n${data.error}`);
      resetTakeawaysButton();
    } else if (data.status === 'processing') {
      showTakeawaysStatus('processing', `Extracting takeaways...\nJob ID: ${currentTakeawaysJobId}`, data.progress);
    } else {
      showTakeawaysStatus('processing', `Status: ${data.status}\nJob ID: ${currentTakeawaysJobId}`);
    }
  } catch (error) {
    // Don't stop polling on network errors
    console.error('Polling error:', error);
  }
}

async function saveTakeawaysCompletedJob() {
  // Save this job as completed for this video URL
  const storage = await chrome.storage.local.get(['completedTakeawaysJobs']);
  const completedTakeawaysJobs = storage.completedTakeawaysJobs || {};
  completedTakeawaysJobs[currentUrl] = currentTakeawaysJobId;

  await chrome.storage.local.set({ completedTakeawaysJobs });
  await chrome.storage.local.remove(['activeTakeawaysJob']);
}

async function clearTakeawaysJobStorage() {
  await chrome.storage.local.remove(['activeTakeawaysJob']);
}

function showTakeawaysCompleted(data) {
  const container = document.getElementById('takeawaysStatusContainer');
  const takeawaysBtn = document.getElementById('takeawaysBtn');

  // Hide the takeaways button since job is complete
  takeawaysBtn.style.display = 'none';

  container.innerHTML = `
    <div class="status completed">
      ✅ Takeaways ready!<br>
      Job ID: ${currentTakeawaysJobId}
    </div>
    <button class="download-btn" id="downloadTakeawaysBtn">
      View Takeaways
    </button>
  `;

  document.getElementById('downloadTakeawaysBtn').addEventListener('click', async () => {
    openJobInNewTab(currentTakeawaysJobId).catch(err => console.error(err));
  });
}

function resetTakeawaysButton() {
  const takeawaysBtn = document.getElementById('takeawaysBtn');
  takeawaysBtn.disabled = false;
  takeawaysBtn.textContent = 'Extract Takeaways';
  takeawaysBtn.style.display = '';
}
*/
