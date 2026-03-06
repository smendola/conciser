const DEFAULT_SERVER_URL = 'http://conciser.603apps.net';
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
  document.getElementById('serverUrl').value = normalized;
  if (normalized) {
    pingServer(normalized);
  }
}

async function save() {
  const input = document.getElementById('serverUrl');
  const serverUrl = normalizeServerUrl(input.value);
  input.value = serverUrl;

  const storage = await chrome.storage.local.get(['settings']);
  const existing = storage.settings || {};

  await chrome.storage.local.set({
    settings: {
      ...existing,
      serverUrl
    }
  });

  setStatus('Saved. Checking server...', 'pending');
  await pingServer(serverUrl);
}

async function resetToDefault() {
  document.getElementById('serverUrl').value = DEFAULT_SERVER_URL;
  await save();
}

async function resetAllState() {
  if (!confirm('Are you sure you want to reset all state? This will clear:\n\n• All active and completed jobs\n• All settings\n• Cached voices and strategies\n• Client ID\n\nThis cannot be undone.')) {
    return;
  }

  try {
    // Clear all storage
    await chrome.storage.local.clear();
    
    setStatus('All state has been reset. Reloading...', 'ok');
    
    // Reload the page to refresh everything
    setTimeout(() => {
      location.reload();
    }, 1000);
    
  } catch (error) {
    setStatus('Failed to reset state', 'error');
    console.error('Reset state error:', error);
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  await load();

  const input = document.getElementById('serverUrl');
  input.addEventListener('input', () => {
    setStatus('', 'info');
  });

  document.getElementById('saveBtn').addEventListener('click', async () => {
    try {
      await save();
    } catch (e) {
      setStatus('Failed to save', 'error');
      console.error(e);
    }
  });

  document.getElementById('resetBtn').addEventListener('click', async () => {
    try {
      await resetToDefault();
    } catch (e) {
      setStatus('Failed to reset', 'error');
      console.error(e);
    }
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
