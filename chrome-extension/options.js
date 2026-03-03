const DEFAULT_SERVER_URL = 'http://conciser.603apps.net';

function normalizeServerUrl(value) {
  const trimmed = (value || '').trim();
  if (!trimmed) return DEFAULT_SERVER_URL;
  return trimmed.replace(/\/+$/, '');
}

function setStatus(text) {
  const el = document.getElementById('status');
  el.textContent = text || '';
}

async function load() {
  const storage = await chrome.storage.local.get(['settings']);
  const settings = storage.settings || {};

  const normalized = normalizeServerUrl(settings.serverUrl);
  document.getElementById('serverUrl').value = normalized;
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

  setStatus('Saved');

  window.setTimeout(() => {
    setStatus('');
  }, 1200);
}

async function resetToDefault() {
  document.getElementById('serverUrl').value = DEFAULT_SERVER_URL;
  await save();
}

document.addEventListener('DOMContentLoaded', async () => {
  await load();

  document.getElementById('saveBtn').addEventListener('click', async () => {
    try {
      await save();
    } catch (e) {
      setStatus('Failed to save');
      console.error(e);
    }
  });

  document.getElementById('resetBtn').addEventListener('click', async () => {
    try {
      await resetToDefault();
    } catch (e) {
      setStatus('Failed to reset');
      console.error(e);
    }
  });
});
