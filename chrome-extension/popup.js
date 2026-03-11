// NBJ Condenser - Chrome Extension

console.log('POPUP_BOOT: popup.js loaded');

let currentUrl = null;
let currentJobId = null;
let currentTakeawaysJobId = null;
let pollInterval = null;
let takeawaysPollInterval = null;
// DEFAULT_SERVER_URL is injected at build time via build-info.js
let serverUrl = DEFAULT_SERVER_URL;
let strategies = [];
let voices = [];
let currentTab = 'condense';
let clientId = null;
const POPUP_TAB_STORAGE_KEY = 'lastPopupTab';

function getServerCacheKeyPrefix() {
  return `serverCache:${serverUrl}`;
}

async function clearAllStateOnServerSwitchIfNeeded() {
  const storage = await chrome.storage.local.get(['lastServerUrl', 'settings']);
  const lastServerUrl = storage.lastServerUrl;
  const settings = storage.settings || {};
  const selectedServerUrl = normalizeServerUrl(settings.serverUrl || serverUrl);

  console.log('METADATA_CACHE: server_switch_check', {
    lastServerUrl,
    selectedServerUrl
  });
  await apiLog('server_switch_check', { lastServerUrl, selectedServerUrl });

  if (lastServerUrl && normalizeServerUrl(lastServerUrl) !== selectedServerUrl) {
    console.log('METADATA_CACHE: server_switch_wipe', {
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
  console.log('METADATA_CACHE: strategies_cache_read', {
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
  console.log('METADATA_CACHE: voices_cache_read', {
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
  console.log('METADATA_CACHE: strategies_fetch_start', { serverUrl });
  await apiLog('strategies_fetch_start', {});
  const response = await fetchWithAuth(`${serverUrl}/api/strategies`);
  if (!response.ok) throw new Error(`Failed to fetch strategies (${response.status})`);
  const data = await response.json();
  strategies = data.strategies || [];
  const key = getStrategiesCacheKey();
  await chrome.storage.local.set({ [key]: { data: strategies, timestamp: Date.now() } });
  console.log('METADATA_CACHE: strategies_cache_write', { serverUrl, key, count: strategies.length });
  await apiLog('strategies_cache_write', { key, count: strategies.length });
  updateStrategyDescription();
}

async function fetchAndCacheVoicesForCurrentServer(locale) {
  console.log('METADATA_CACHE: voices_fetch_start', { serverUrl, locale });
  await apiLog('voices_fetch_start', { locale });
  const response = await fetchWithAuth(`${serverUrl}/api/voices?locale=${locale}`);
  if (!response.ok) throw new Error(`Failed to fetch voices (${response.status})`);
  const data = await response.json();
  voices = data.voices || [];
  const key = getVoicesCacheKey(locale);
  await chrome.storage.local.set({ [key]: { data: voices, locale, timestamp: Date.now() } });
  console.log('METADATA_CACHE: voices_cache_write', { serverUrl, locale, key, count: voices.length });
  await apiLog('voices_cache_write', { locale, key, count: voices.length });
}

async function ensureServerMetadataLoaded({ allowNetwork = false } = {}) {
  const locale = getLanguageOnlyLocale();
  console.log('METADATA_CACHE: ensure_metadata_start', { serverUrl, locale, allowNetwork });
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

    console.log('METADATA_CACHE: restore_settings', {
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

      console.log('METADATA_CACHE: applied_selection', {
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

function buildDownloadUrl(jobId) {
  let url = `${serverUrl}/api/download/${jobId}`;
  if (clientId) {
    url += `?cid=${encodeURIComponent(clientId)}`;
  }
  return url;
}

function buildOpenUrl(jobId) {
  let url = `${serverUrl}/api/open/${jobId}`;
  if (clientId) {
    url += `?cid=${encodeURIComponent(clientId)}`;
  }
  return url;
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
  return response.json().catch(() => ({}));
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

// Initialize popup
async function initializePopup() {
  console.log('POPUP_BOOT: initializePopup start');
  clientId = await ensureClientId();
  // Get current tab and check if it's YouTube
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  const tab = tabs[0];
  currentUrl = tab.url;

  const videoInfo = document.getElementById('videoInfo');
  const condenseBtn = document.getElementById('condenseBtn');
  const takeawaysBtn = document.getElementById('takeawaysBtn');

  // Check if YouTube video page
  const youtubeRegex = /^https?:\/\/(www\.)?(youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})/;
  const match = currentUrl.match(youtubeRegex);

  if (match) {
    const videoId = match[3];
    videoInfo.textContent = `Video: ${videoId}`;
    videoInfo.title = currentUrl;
    condenseBtn.disabled = false;
    takeawaysBtn.disabled = false;

    // Fetch title async — update when ready without blocking init
    fetch(`https://www.youtube.com/oembed?url=${encodeURIComponent(currentUrl)}&format=json`)
      .then(r => r.json())
      .then(data => {
        if (data.title) {
          videoInfo.innerHTML = `Video: ${videoId}<br><span style="font-weight:700;color:#555;">${data.title}</span>`;
        }
      })
      .catch(() => { }); // silently ignore — title is decorative
  } else {
    videoInfo.textContent = '⚠️ Not a YouTube video page';
    condenseBtn.disabled = true;
    takeawaysBtn.disabled = true;
  }

  // Load settings and populate controls
  await clearAllStateOnServerSwitchIfNeeded();
  await loadSettings();
  await ensureServerMetadataLoaded({ allowNetwork: false });
  await ensureServerMetadataLoaded({ allowNetwork: true });

  // Setup tabs
  await setupTabs();

  // Check for existing job in storage
  const storage = await chrome.storage.local.get(['activeJob', 'completedJobs', 'activeTakeawaysJob', 'completedTakeawaysJobs']);

  // First check if this video has a completed job
  const completedJobs = storage.completedJobs || {};
  if (completedJobs[currentUrl]) {
    currentJobId = completedJobs[currentUrl];
    showCompleted({ job_id: currentJobId });
    return;
  }

  // Then check if there's an active job in progress FOR THIS VIDEO
  if (storage.activeJob && storage.activeJob.url === currentUrl) {
    currentJobId = storage.activeJob.jobId;
    condenseBtn.disabled = true;
    condenseBtn.textContent = 'Processing...';
    showStatus('processing', `Resuming job...\nJob ID: ${currentJobId}`);
    startPolling();
  }

  // Check for takeaways jobs FOR THIS VIDEO
  const completedTakeawaysJobs = storage.completedTakeawaysJobs || {};
  if (completedTakeawaysJobs[currentUrl]) {
    currentTakeawaysJobId = completedTakeawaysJobs[currentUrl];
    showTakeawaysCompleted({ job_id: currentTakeawaysJobId });
  } else if (storage.activeTakeawaysJob && storage.activeTakeawaysJob.url === currentUrl) {
    currentTakeawaysJobId = storage.activeTakeawaysJob.jobId;
    takeawaysBtn.disabled = true;
    takeawaysBtn.textContent = 'Processing...';
    showTakeawaysStatus('processing', `Resuming job...\nJob ID: ${currentTakeawaysJobId}`);
    startTakeawaysPolling();
  }

  // Load recent jobs
  await loadRecentJobs();
}

// Fetch and display recent jobs
async function loadRecentJobs() {
  try {
    const response = await fetchWithAuth(`${serverUrl}/api/jobs`);
    if (response.ok) {
      await ensureServerMetadataLoaded({ allowNetwork: true });
    }
    const data = await response.json();

    // Filter completed jobs that have files
    const condenseJobs = data.jobs.filter(job =>
      job.status === 'completed' && job.file_exists && job.job_type === 'condense'
    ).slice(0, 5);  // Show max 5 recent

    const takeawaysJobs = data.jobs.filter(job =>
      job.status === 'completed' && job.file_exists && job.job_type === 'takeaways'
    ).slice(0, 5);

    const renderJobs = (container, list, jobs) => {
      if (jobs.length > 0) {
        list.innerHTML = jobs.map((job, index) => {
          const date = new Date(job.created_at);
          const dateStr = date.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });

          const videoId = job.url.match(/[?&]v=([^&]+)/)?.[1] || job.job_id;
          const displayTitle = job.title || videoId;

          const format = job.output_format || (job.job_type === 'condense' ? 'mp4' : 'txt');
          const { badgeClass, badgeText } = getRecentJobBadge(format, job.job_type);

          const jobHtml = `
            <div class="recent-job" data-job-id="${job.job_id}">
              <div class="recent-job-badge ${badgeClass}">${badgeText}</div>
              <div class="recent-job-details">
                <div class="recent-job-title">${displayTitle}</div>
                <div class="recent-job-timestamp">${dateStr}</div>
              </div>
              <button class="recent-job-delete" data-job-id="${job.job_id}" aria-label="Delete">×</button>
            </div>
          `;
          const dividerHtml = index < jobs.length - 1 ? '<div class="recent-job-divider"></div>' : '';

          return jobHtml + dividerHtml;
        }).join('');

        container.style.display = 'block';

        list.querySelectorAll('.recent-job').forEach(el => {
          el.addEventListener('click', () => {
            const jobId = el.getAttribute('data-job-id');
            chrome.tabs.create({ url: buildOpenUrl(jobId) });
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

function setActiveTab(targetTab) {
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
}

// Setup tab switching
async function setupTabs() {
  const tabButtons = document.querySelectorAll('.tab');
  const storedTabState = await chrome.storage.local.get([POPUP_TAB_STORAGE_KEY]);
  setActiveTab(storedTabState[POPUP_TAB_STORAGE_KEY] || 'condense');

  tabButtons.forEach(button => {
    button.addEventListener('click', async () => {
      const targetTab = button.getAttribute('data-tab');
      setActiveTab(targetTab);
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
    speechSpeed: 1.0,
    videoMode: 'slideshow',
    prependIntro: false
  }, saved);

  const previousServerUrl = serverUrl;
  serverUrl = normalizeServerUrl(settings.serverUrl);
  if (previousServerUrl !== serverUrl) {
    await chrome.storage.local.set({ lastServerUrl: serverUrl });
  }

  document.getElementById('aggressivenessSlider').value = settings.aggressiveness;
  document.getElementById('aggressivenessValue').textContent = settings.aggressiveness;
  document.getElementById('speedSlider').value = settings.speechSpeed;
  document.getElementById('speedValue').textContent = settings.speechSpeed.toFixed(2) + 'x';
  document.getElementById('videoModeSelect').value = settings.videoMode;
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
    takeawaysFormat,
    speechSpeed: parseFloat(document.getElementById('speedSlider').value),
    videoMode: document.getElementById('videoModeSelect').value,
    prependIntro: document.getElementById('prependIntroCheck').checked
  };

  await chrome.storage.local.set({ settings });
}

function normalizeServerUrl(value) {
  const trimmed = (value || '').trim();
  if (!trimmed) return DEFAULT_SERVER_URL;
  return trimmed.replace(/\/+$/, '');
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
document.getElementById('aggressivenessSlider').addEventListener('input', (e) => {
  document.getElementById('aggressivenessValue').textContent = e.target.value;
  updateStrategyDescription();
  handleSettingChange();
});

document.getElementById('speedSlider').addEventListener('input', (e) => {
  const value = parseFloat(e.target.value);
  document.getElementById('speedValue').textContent = value.toFixed(2) + 'x';
  handleSettingChange();
});

document.getElementById('localeSelect').addEventListener('change', (e) => {
  updateVoiceSelectForLocale('voiceSelect', e.target.value);
  handleSettingChange();
});

document.getElementById('takeawaysLocaleSelect').addEventListener('change', (e) => {
  updateVoiceSelectForLocale('takeawaysVoiceSelect', e.target.value);
  handleSettingChange();
});

document.getElementById('voiceSelect').addEventListener('change', () => {
  handleSettingChange();
});

document.getElementById('takeawaysVoiceSelect').addEventListener('change', handleSettingChange);


document.getElementById('videoModeSelect').addEventListener('change', handleSettingChange);

document.getElementById('prependIntroCheck').addEventListener('change', handleSettingChange);

// Display build version
if (typeof BUILD_VERSION !== 'undefined') {
  document.getElementById('buildInfo').textContent = `Build: ${BUILD_VERSION}`;
} else {
  document.getElementById('buildInfo').textContent = 'Build: Unknown';
}

// Run initialization
initializePopup();

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

    const response = await fetchWithAuth(`${serverUrl}/api/condense`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        url: currentUrl,
        aggressiveness: aggressiveness,
        voice: voice,
        speech_rate: speechRate,
        video_mode: videoMode,
        prepend_intro: prependIntro
      })
    });

    const data = await response.json();

    if (response.ok) {
      currentJobId = data.job_id;

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

function showStatus(type, message, progress = '') {
  const container = document.getElementById('statusContainer');

  let progressHtml = '';
  if (progress) {
    progressHtml = `<div class="progress">${progress}</div>`;
  }
  container.innerHTML = `<div class="status ${type}">${message.replace(/\n/g, '<br>')}${progressHtml}</div>`;
}

function startPolling() {
  // Poll every 3 seconds
  pollInterval = setInterval(checkStatus, 3000);
  checkStatus(); // Check immediately
}

async function checkStatus() {
  try {
    const response = await fetchWithAuth(`${serverUrl}/api/status/${currentJobId}`);

    // If job returns 404, forget it ever existed
    if (response.status === 404) {
      clearInterval(pollInterval);
      await clearJobStorage();
      // Also clear completed jobs for this URL
      const storage = await chrome.storage.local.get(['completedJobs']);
      if (storage.completedJobs && storage.completedJobs[currentUrl]) {
        delete storage.completedJobs[currentUrl];
        await chrome.storage.local.set({ completedJobs: storage.completedJobs });
      }
      showStatus('error', `Job ${currentJobId} not found on server`);
      resetButton();
      return;
    }

    const data = await response.json();

    if (data.status === 'completed') {
      clearInterval(pollInterval);
      await saveCompletedJob();
      showCompleted(data);
    } else if (data.status === 'error') {
      clearInterval(pollInterval);
      await clearJobStorage();
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
    chrome.tabs.create({ url: toServerAbsoluteUrl(data.open_url || buildOpenUrl(currentJobId)) });
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

    const payload = {
      url: currentUrl,
      format: format
    };

    if (top !== null) {
      payload.top = top;
    }

    if (voice) {
      payload.voice = voice;
    }

    const response = await fetchWithAuth(`${serverUrl}/api/takeaways`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload)
    });

    const data = await response.json();

    if (response.ok) {
      currentTakeawaysJobId = data.job_id;

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

function showTakeawaysStatus(type, message, progress = '') {
  const container = document.getElementById('takeawaysStatusContainer');

  let progressHtml = '';
  if (progress) {
    progressHtml = `<div class="progress">${progress}</div>`;
  }
  container.innerHTML = `<div class="status ${type}">${message.replace(/\n/g, '<br>')}${progressHtml}</div>`;
}

function startTakeawaysPolling() {
  // Poll every 2 seconds (faster than condense since takeaways is quicker)
  takeawaysPollInterval = setInterval(checkTakeawaysStatus, 2000);
  checkTakeawaysStatus(); // Check immediately
}

async function checkTakeawaysStatus() {
  try {
    const response = await fetchWithAuth(`${serverUrl}/api/status/${currentTakeawaysJobId}`);

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
      showTakeawaysCompleted(data);
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
    chrome.tabs.create({ url: toServerAbsoluteUrl(data.open_url || buildOpenUrl(currentTakeawaysJobId)) });
  });
}

function resetTakeawaysButton() {
  const takeawaysBtn = document.getElementById('takeawaysBtn');
  takeawaysBtn.disabled = false;
  takeawaysBtn.textContent = 'Extract Takeaways';
  takeawaysBtn.style.display = '';
}
