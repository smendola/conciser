// NBJ Condenser - Chrome Extension

let currentUrl = null;
let currentJobId = null;
let currentTakeawaysJobId = null;
let pollInterval = null;
let takeawaysPollInterval = null;
// DEFAULT_SERVER_URL is injected at build time via build-info.js
let serverUrl = DEFAULT_SERVER_URL;
let strategies = [];
let voices = [];
const CACHE_TTL_MS = 60 * 60 * 1000; // 1 hour
let currentTab = 'condense';
let clientId = null;

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
  return fetch(url, withAuthHeaders(options));
}

function buildDownloadUrl(jobId) {
  let url = `${serverUrl}/api/download/${jobId}`;
  if (clientId) {
    url += `?cid=${encodeURIComponent(clientId)}`;
  }
  return url;
}

// Initialize popup
async function initializePopup() {
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
  await loadSettings();
  await fetchStrategies();
  await fetchVoices();

  // Setup tabs
  setupTabs();

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
    const data = await response.json();

    // Filter completed jobs that have files
    const condenseJobs = data.jobs.filter(job =>
      job.status === 'completed' && job.file_exists && job.job_type === 'condense'
    ).slice(0, 5);  // Show max 5 recent

    const takeawaysJobs = data.jobs.filter(job =>
      job.status === 'completed' && job.file_exists && job.job_type === 'takeaways'
    ).slice(0, 5);

    // Display condense jobs
    const condenseContainer = document.getElementById('recentCondenseJobs');
    const condenseList = document.getElementById('recentCondenseJobsList');

    if (condenseJobs.length > 0) {
      condenseList.innerHTML = condenseJobs.map(job => {
        const date = new Date(job.created_at);
        const dateStr = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

        // Use title if available, otherwise extract video ID as fallback
        const videoId = job.url.match(/[?&]v=([^&]+)/)?.[1] || job.job_id;
        const displayTitle = job.title || videoId;

        return `
          <div class="recent-job" data-job-id="${job.job_id}" data-url="${job.url}" data-video-id="${videoId}">
            <div class="recent-job-info">${displayTitle}</div>
            <div class="recent-job-date">${dateStr}</div>
          </div>
        `;
      }).join('');

      condenseContainer.style.display = 'block';

      // Add click handlers
      condenseList.querySelectorAll('.recent-job').forEach(el => {
        el.addEventListener('click', () => {
          const jobId = el.getAttribute('data-job-id');
          chrome.tabs.create({ url: buildDownloadUrl(jobId) });
        });
      });
    } else {
      condenseContainer.style.display = 'none';
    }

    // Display takeaways jobs
    const takeawaysContainer = document.getElementById('recentTakeawaysJobs');
    const takeawaysList = document.getElementById('recentTakeawaysJobsList');

    if (takeawaysJobs.length > 0) {
      takeawaysList.innerHTML = takeawaysJobs.map(job => {
        const date = new Date(job.created_at);
        const dateStr = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

        // Use title if available, otherwise extract video ID as fallback
        const videoId = job.url.match(/[?&]v=([^&]+)/)?.[1] || job.job_id;
        const displayTitle = job.title || videoId;

        return `
          <div class="recent-job" data-job-id="${job.job_id}" data-url="${job.url}" data-video-id="${videoId}">
            <div class="recent-job-info">${displayTitle}</div>
            <div class="recent-job-date">${dateStr}</div>
          </div>
        `;
      }).join('');

      takeawaysContainer.style.display = 'block';

      // Add click handlers
      takeawaysList.querySelectorAll('.recent-job').forEach(el => {
        el.addEventListener('click', () => {
          const jobId = el.getAttribute('data-job-id');
          chrome.tabs.create({ url: buildDownloadUrl(jobId) });
        });
      });
    } else {
      takeawaysContainer.style.display = 'none';
    }

  } catch (error) {
    console.error('Failed to load recent jobs:', error);
  }
}

// Fetch strategies from API (cached 1 hour)
async function fetchStrategies() {
  try {
    const storage = await chrome.storage.local.get(['strategiesCache']);
    const cache = storage.strategiesCache;
    if (cache && (Date.now() - cache.timestamp) < CACHE_TTL_MS) {
      strategies = cache.data;
      updateStrategyDescription();
      return;
    }
    const response = await fetchWithAuth(`${serverUrl}/api/strategies`);
    const data = await response.json();
    strategies = data.strategies;
    await chrome.storage.local.set({ strategiesCache: { data: strategies, timestamp: Date.now() } });
    updateStrategyDescription();
  } catch (error) {
    console.error('Failed to fetch strategies:', error);
  }
}

// Setup tab switching
function setupTabs() {
  const tabButtons = document.querySelectorAll('.tab');
  const tabContents = document.querySelectorAll('.tab-content');

  tabButtons.forEach(button => {
    button.addEventListener('click', () => {
      const targetTab = button.getAttribute('data-tab');

      // Update active tab button
      tabButtons.forEach(btn => btn.classList.remove('active'));
      button.classList.add('active');

      // Update active tab content
      tabContents.forEach(content => content.classList.remove('active'));
      document.getElementById(`${targetTab}-tab`).classList.add('active');

      currentTab = targetTab;
    });
  });

  // Format radio buttons - show/hide voice select AND reset completed state
  const formatRadios = document.querySelectorAll('input[name="format"]');
  formatRadios.forEach(radio => {
    radio.addEventListener('change', () => {
      const voiceGroup = document.getElementById('takeawaysVoiceGroup');
      voiceGroup.style.display = radio.value === 'audio' ? 'block' : 'none';
      resetTakeawaysIfCompleted();
    });
  });

  // Top radio buttons - reset completed state on change
  const topRadios = document.querySelectorAll('input[name="top"]');
  topRadios.forEach(radio => {
    radio.addEventListener('change', resetTakeawaysIfCompleted);
  });

  // Voice select - reset completed state on change
  const takeawaysVoiceSelect = document.getElementById('takeawaysVoiceSelect');
  if (takeawaysVoiceSelect) {
    takeawaysVoiceSelect.addEventListener('change', resetTakeawaysIfCompleted);
  }
}

// Reset takeaways UI if settings changed after completion
async function resetTakeawaysIfCompleted() {
  const storage = await chrome.storage.local.get(['completedTakeawaysJobs']);
  if (storage.completedTakeawaysJobs && storage.completedTakeawaysJobs[currentUrl]) {
    // Clear the completed job for this URL
    delete storage.completedTakeawaysJobs[currentUrl];
    await chrome.storage.local.set({ completedTakeawaysJobs: storage.completedTakeawaysJobs });

    // Reset UI to extract mode
    document.getElementById('takeawaysStatusContainer').innerHTML = '';
    const takeawaysBtn = document.getElementById('takeawaysBtn');
    takeawaysBtn.style.display = '';
    takeawaysBtn.disabled = false;
    takeawaysBtn.textContent = 'Extract Takeaways';
    currentTakeawaysJobId = null;
  }
}

// Fetch voices from API (cached 1 hour)
async function fetchVoices() {
  try {
    const locale = navigator.language.split('-')[0];
    const storage = await chrome.storage.local.get(['voicesCache', 'settings']);
    const cache = storage.voicesCache;

    if (cache && cache.locale === locale && (Date.now() - cache.timestamp) < CACHE_TTL_MS) {
      voices = cache.data;
    } else {
      const response = await fetchWithAuth(`${serverUrl}/api/voices?locale=${locale}`);
      const data = await response.json();
      voices = data.voices || [];
      await chrome.storage.local.set({ voicesCache: { data: voices, locale, timestamp: Date.now() } });
    }

    populateLocaleSelects();
    updateVoiceSelects();

    // Restore saved voice
    if (storage.settings && storage.settings.voice) {
      const savedVoice = voices.find(v => v.name === storage.settings.voice);
      if (savedVoice) {
        const locale = savedVoice.locale;
        document.getElementById('localeSelect').value = locale;
        document.getElementById('takeawaysLocaleSelect').value = locale;
        updateVoiceSelects(locale);
        document.getElementById('voiceSelect').value = savedVoice.name;
        document.getElementById('takeawaysVoiceSelect').value = savedVoice.name;
      }
    }

  } catch (error) {
    console.error('Failed to fetch voices:', error);
    const selects = ['localeSelect', 'voiceSelect', 'takeawaysLocaleSelect', 'takeawaysVoiceSelect'];
    selects.forEach(id => {
      document.getElementById(id).innerHTML = '<option value="">Error</option>';
    });
  }
}

function populateLocaleSelects() {
  const locales = [...new Set(voices.map(v => v.locale))].sort();
  const localeSelects = [
    document.getElementById('localeSelect'),
    document.getElementById('takeawaysLocaleSelect')
  ];

  const userLocale = navigator.language.split('-')[0];
  const userLocaleLong = navigator.language;

  localeSelects.forEach(select => {
    select.innerHTML = '';
    locales.forEach(locale => {
      const option = document.createElement('option');
      option.value = locale;
      option.textContent = locale;
      select.appendChild(option);
    });

    // Set default locale
    if (locales.includes(userLocaleLong)) {
      select.value = userLocaleLong;
    } else if (locales.find(l => l.startsWith(userLocale))) {
      select.value = locales.find(l => l.startsWith(userLocale));
    }
  });
}

function updateVoiceSelects(locale) {
  const voiceSelects = [
    document.getElementById('voiceSelect'),
    document.getElementById('takeawaysVoiceSelect')
  ];

  if (!locale) {
    locale = document.getElementById('localeSelect').value;
  }

  const filteredVoices = voices.filter(v => v.locale === locale);

  voiceSelects.forEach(select => {
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

    // Try to restore previous selection if it exists in the new list
    if (filteredVoices.some(v => v.name === currentVal)) {
      select.value = currentVal;
    } else if (filteredVoices.length > 0) {
      select.value = filteredVoices[0].name;
    }
  });
  handleSettingChange();
}

// Load settings from storage
async function loadSettings() {
  const storage = await chrome.storage.local.get(['settings']);
  const saved = storage?.settings || {};
  const settings = Object.assign({
    serverUrl: DEFAULT_SERVER_URL,
    aggressiveness: 5,
    voice: null,
    speechSpeed: 1.0,
    videoMode: 'slideshow',
    prependIntro: false
  }, saved);

  serverUrl = normalizeServerUrl(settings.serverUrl);

  document.getElementById('aggressivenessSlider').value = settings.aggressiveness;
  document.getElementById('aggressivenessValue').textContent = settings.aggressiveness;
  document.getElementById('speedSlider').value = settings.speechSpeed;
  document.getElementById('speedValue').textContent = settings.speechSpeed.toFixed(2) + 'x';
  document.getElementById('videoModeSelect').value = settings.videoMode;
  document.getElementById('prependIntroCheck').checked = settings.prependIntro || false;
}

// Save settings to storage
async function saveSettings() {
  const storage = await chrome.storage.local.get(['settings']);
  const existing = storage.settings || {};

  const settings = {
    ...existing,
    aggressiveness: parseInt(document.getElementById('aggressivenessSlider').value),
    voice: document.getElementById('voiceSelect').value,
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

// Check if settings changed after video was watched
async function handleSettingChange() {
  saveSettings();

  // Check if this video has been watched
  const storage = await chrome.storage.local.get(['watchedVideos', 'completedJobs']);
  const watchedVideos = storage.watchedVideos || {};

  if (watchedVideos[currentUrl] && storage.completedJobs && storage.completedJobs[currentUrl]) {
    // Video was watched and settings changed - allow re-condensing
    console.log('Settings changed after watching - resetting to condense mode');

    // Clear the completed job for this video
    delete storage.completedJobs[currentUrl];
    await chrome.storage.local.set({ completedJobs: storage.completedJobs });

    // Reset UI to condense mode
    resetToCondenseMode();
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
  updateVoiceSelects(e.target.value);
});

document.getElementById('takeawaysLocaleSelect').addEventListener('change', (e) => {
  // Keep both voice dropdowns in sync with locale for simplicity
  document.getElementById('localeSelect').value = e.target.value;
  updateVoiceSelects(e.target.value);
});

document.getElementById('voiceSelect').addEventListener('change', () => {
  // Keep takeaways voice in sync for simplicity
  const voice = document.getElementById('voiceSelect').value;
  document.getElementById('takeawaysVoiceSelect').value = voice;
  handleSettingChange();
});

document.getElementById('takeawaysVoiceSelect').addEventListener('change', () => {
  handleSettingChange();
});

document.getElementById('videoModeSelect').addEventListener('change', () => {
  handleSettingChange();
});

document.getElementById('prependIntroCheck').addEventListener('change', () => {
  handleSettingChange();
});

// Display build timestamp
if (typeof BUILD_TIMESTAMP !== 'undefined') {
  document.getElementById('buildInfo').textContent = `Build: ${BUILD_TIMESTAMP}`;
} else {
  document.getElementById('buildInfo').textContent = 'Build: Unknown';
}

// Run initialization
initializePopup();

// Condense button click
document.getElementById('condenseBtn').addEventListener('click', async () => {
  const condenseBtn = document.getElementById('condenseBtn');
  condenseBtn.disabled = true;
  condenseBtn.textContent = 'Submitting...';

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
      const storage = await chrome.storage.local.get(['completedJobs', 'watchedVideos']);
      if (storage.completedJobs && storage.completedJobs[currentUrl]) {
        delete storage.completedJobs[currentUrl];
        await chrome.storage.local.set({ completedJobs: storage.completedJobs });
      }

      // Clear watched status for this URL (starting fresh)
      if (storage.watchedVideos && storage.watchedVideos[currentUrl]) {
        delete storage.watchedVideos[currentUrl];
        await chrome.storage.local.set({ watchedVideos: storage.watchedVideos });
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

  document.getElementById('downloadBtn').addEventListener('click', async () => {
    chrome.tabs.create({ url: buildDownloadUrl(currentJobId) });

    // Mark this video as watched
    const storage = await chrome.storage.local.get(['watchedVideos']);
    const watchedVideos = storage.watchedVideos || {};
    watchedVideos[currentUrl] = true;
    await chrome.storage.local.set({ watchedVideos });

    console.log('Video marked as watched - settings changes will now allow re-condensing');
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
    chrome.tabs.create({ url: buildDownloadUrl(currentTakeawaysJobId) });
  });
}

function resetTakeawaysButton() {
  const takeawaysBtn = document.getElementById('takeawaysBtn');
  takeawaysBtn.disabled = false;
  takeawaysBtn.textContent = 'Extract Takeaways';
  takeawaysBtn.style.display = '';
}
