const DEFAULT_SERVER_URL = 'https://conciser.603apps.net';
const PRESET_URLS = [
  'https://conciser.603apps.net',
  'https://x13.puma-garibaldi.ts.net',
  'https://cuda-linux.puma-garibaldi.ts.net'
];
let pingTimeoutId = null;
let currentPingController = null;

function normalizeServerUrl(value) {
  const trimmed = (value || '').trim();
  if (!trimmed) return DEFAULT_SERVER_URL;
  return trimmed.replace(/\/+$/, '');
}

function setStatus(text, type = 'info') {
  const el = document.getElementById('status');
  if (!el) return;
  el.textContent = text || '';
  el.className = `status ${type}`;
}

async function pingServer(rawValue) {
  const serverUrl = normalizeServerUrl(rawValue);
  if (!serverUrl) {
    setStatus('Enter a server URL to test', 'info');
    return;
  }

  const healthUrl = `${serverUrl}/health`;

  if (currentPingController) {
    currentPingController.abort();
  }
  const controller = new AbortController();
  currentPingController = controller;

  setStatus('Checking server...', 'pending');

  const timeoutId = window.setTimeout(() => controller.abort(), 5000);

  try {
    const response = await fetch(healthUrl, {
      signal: controller.signal,
      headers: { 'Accept': 'application/json' },
      cache: 'no-store'
    });

    if (!response.ok) {
      setStatus(`Server responded ${response.status}`, 'error');
      return;
    }

    let payload = null;
    try {
      payload = await response.json();
    } catch (err) {
      payload = null;
    }

    if (payload && payload.status && payload.status.toLowerCase() !== 'ok') {
      setStatus(`Server responded: ${payload.status}`, 'pending');
      return;
    }

    setStatus('Server OK', 'ok');
  } catch (err) {
    if (err.name === 'AbortError') {
      setStatus('Server check timed out', 'error');
    } else {
      setStatus('Could not reach server', 'error');
    }
  } finally {
    clearTimeout(timeoutId);
    if (currentPingController === controller) {
      currentPingController = null;
    }
  }
}

async function load() {
  const storage = await chrome.storage.local.get(['settings']);
  const settings = storage.settings || {};

  const normalized = normalizeServerUrl(settings.serverUrl);
  const selectEl = document.getElementById('serverUrlSelect');
  const inputEl = document.getElementById('serverUrl');

  // Check if the current URL is one of the presets
  if (PRESET_URLS.includes(normalized)) {
    selectEl.value = normalized;
    inputEl.value = '';
    inputEl.style.display = 'none';
  } else {
    selectEl.value = normalized ? 'custom' : '';
    inputEl.value = normalized;
    inputEl.style.display = normalized ? 'block' : 'none';
  }

  if (normalized) {
    pingServer(normalized);
  }
}

async function save(andPing = true) {
  const selectEl = document.getElementById('serverUrlSelect');
  const inputEl = document.getElementById('serverUrl');

  let serverUrl;
  if (selectEl.value && selectEl.value !== 'custom') {
    serverUrl = normalizeServerUrl(selectEl.value);
  } else {
    serverUrl = normalizeServerUrl(inputEl.value);
  }

  const storage = await chrome.storage.local.get(['settings']);
  const existing = storage.settings || {};

  await chrome.storage.local.set({
    settings: {
      ...existing,
      serverUrl
    }
  });

  setStatus('Saved', 'ok');

  if (andPing) {
    // Use a small delay to let the UI update before the ping
    setTimeout(() => pingServer(serverUrl), 100);
  }
}

async function resetAllState() {
  if (!confirm('Are you sure you want to reset all state? This will clear:\n\n• All active and completed jobs\n• All settings\n• Cached voices and strategies\n• Client ID\n\nThis cannot be undone.')) {
    return;
  }

  try {
    await chrome.storage.local.clear();
    setStatus('All state has been reset. Reloading...', 'ok');
    setTimeout(() => location.reload(), 1000);
  } catch (error) {
    setStatus('Failed to reset state', 'error');
    console.error('Reset state error:', error);
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  await load();

  const selectEl = document.getElementById('serverUrlSelect');
  const inputEl = document.getElementById('serverUrl');

  // Handle dropdown changes
  selectEl.addEventListener('change', () => {
    if (selectEl.value === 'custom') {
      inputEl.style.display = 'block';
      inputEl.focus();
      // Don't save here, wait for blur on the text input
    } else {
      inputEl.style.display = 'none';
      inputEl.value = '';
      save(); // Save and ping immediately
    }
  });

  // Handle custom input blur (focus lost)
  inputEl.addEventListener('blur', () => {
    save(); // Save and ping when focus is lost
  });

  document.getElementById('resetStateBtn').addEventListener('click', async () => {
    try {
      await resetAllState();
    } catch (e) {
      setStatus('Failed to reset state', 'error');
      console.error(e);
    }
  });
});
