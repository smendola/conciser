// NBJ Condenser - Chrome Extension

let currentUrl = null;
let currentJobId = null;
let pollInterval = null;
const serverUrl = 'https://conciser-aurora.ngrok.dev';
let strategies = [];
let voices = [];
const CACHE_TTL_MS = 60 * 60 * 1000; // 1 hour

// Initialize popup
async function initializePopup() {
  // Get current tab and check if it's YouTube
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  const tab = tabs[0];
  currentUrl = tab.url;

  const videoInfo = document.getElementById('videoInfo');
  const condenseBtn = document.getElementById('condenseBtn');

  // Check if YouTube video page
  const youtubeRegex = /^https?:\/\/(www\.)?(youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})/;
  const match = currentUrl.match(youtubeRegex);

  if (match) {
    const videoId = match[3];
    videoInfo.textContent = `Video: ${videoId}`;
    videoInfo.title = currentUrl;
    condenseBtn.disabled = false;
  } else {
    videoInfo.textContent = '⚠️ Not a YouTube video page';
    condenseBtn.disabled = true;
  }

  // Load settings and populate controls
  await loadSettings();
  await fetchStrategies();
  await fetchVoices();

  // Check for existing job in storage
  const storage = await chrome.storage.local.get(['activeJob', 'completedJobs']);

  // First check if this video has a completed job
  const completedJobs = storage.completedJobs || {};
  if (completedJobs[currentUrl]) {
    currentJobId = completedJobs[currentUrl];
    showCompleted({ job_id: currentJobId });
    return;
  }

  // Then check if there's an active job in progress
  if (storage.activeJob) {
    currentJobId = storage.activeJob.jobId;
    condenseBtn.disabled = true;
    condenseBtn.textContent = 'Processing...';
    showStatus('processing', `Resuming job...\nJob ID: ${currentJobId}`);
    startPolling();
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
    const response = await fetch(`${serverUrl}/api/strategies`);
    const data = await response.json();
    strategies = data.strategies;
    await chrome.storage.local.set({ strategiesCache: { data: strategies, timestamp: Date.now() } });
    updateStrategyDescription();
  } catch (error) {
    console.error('Failed to fetch strategies:', error);
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
      const response = await fetch(`${serverUrl}/api/voices?locale=${locale}`);
      const data = await response.json();
      voices = data.voices || [];
      await chrome.storage.local.set({ voicesCache: { data: voices, locale, timestamp: Date.now() } });
    }

    const voiceSelect = document.getElementById('voiceSelect');
    voiceSelect.innerHTML = '';

    if (voices.length === 0) {
      voiceSelect.innerHTML = '<option value="">No voices available</option>';
      return;
    }

    voices.forEach(voice => {
      const option = document.createElement('option');
      option.value = voice.name;
      option.textContent = `${voice.locale} - ${voice.friendly_name}`;
      voiceSelect.appendChild(option);
    });

    // Restore saved voice
    if (storage.settings && storage.settings.voice && voices.some(v => v.name === storage.settings.voice)) {
      voiceSelect.value = storage.settings.voice;
    } else if (voices.length > 0) {
      voiceSelect.value = voices[0].name;
    }
  } catch (error) {
    console.error('Failed to fetch voices:', error);
    document.getElementById('voiceSelect').innerHTML = '<option value="">Error loading voices</option>';
  }
}

// Load settings from storage
async function loadSettings() {
  const storage = await chrome.storage.local.get(['settings']);
  const settings = storage.settings || {
    aggressiveness: 5,
    voice: null,
    speechSpeed: 1.10,
    videoMode: 'slideshow'
  };

  document.getElementById('aggressivenessSlider').value = settings.aggressiveness;
  document.getElementById('aggressivenessValue').textContent = settings.aggressiveness;
  document.getElementById('speedSlider').value = settings.speechSpeed;
  document.getElementById('speedValue').textContent = settings.speechSpeed.toFixed(2) + 'x';
  document.getElementById('videoModeSelect').value = settings.videoMode;
}

// Save settings to storage
async function saveSettings() {
  const settings = {
    aggressiveness: parseInt(document.getElementById('aggressivenessSlider').value),
    voice: document.getElementById('voiceSelect').value,
    speechSpeed: parseFloat(document.getElementById('speedSlider').value),
    videoMode: document.getElementById('videoModeSelect').value
  };

  await chrome.storage.local.set({ settings });
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

document.getElementById('voiceSelect').addEventListener('change', () => {
  handleSettingChange();
});

document.getElementById('videoModeSelect').addEventListener('change', () => {
  handleSettingChange();
});

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

    const response = await fetch(`${serverUrl}/api/condense`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        url: currentUrl,
        aggressiveness: aggressiveness,
        voice: voice,
        speech_rate: speechRate,
        video_mode: videoMode
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
    showStatus('error', `Connection error: ${error.message}\nCheck that server and ngrok are running`);
    condenseBtn.disabled = false;
    condenseBtn.textContent = 'Condense Video';
  }
});

function showStatus(type, message, progress = '') {
  const container = document.getElementById('statusContainer');

  let html = `<div class="status ${type}">${message.replace(/\n/g, '<br>')}</div>`;

  if (progress) {
    html += `<div class="progress">${progress}</div>`;
  }

  container.innerHTML = html;
}

function startPolling() {
  // Poll every 3 seconds
  pollInterval = setInterval(checkStatus, 3000);
  checkStatus(); // Check immediately
}

async function checkStatus() {
  try {
    const response = await fetch(`${serverUrl}/api/status/${currentJobId}`);
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
    const downloadUrl = `${serverUrl}/api/download/${currentJobId}`;
    chrome.tabs.create({ url: downloadUrl });

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
