// Conciser Remote - Chrome Extension

let currentUrl = null;
let currentJobId = null;
let pollInterval = null;
const serverUrl = 'https://conciser-aurora.ngrok.dev';

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

// Run initialization
initializePopup();

// Condense button click
document.getElementById('condenseBtn').addEventListener('click', async () => {
  const condenseBtn = document.getElementById('condenseBtn');
  condenseBtn.disabled = true;
  condenseBtn.textContent = 'Submitting...';

  try {
    const response = await fetch(`${serverUrl}/api/condense`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ url: currentUrl })
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

  document.getElementById('downloadBtn').addEventListener('click', () => {
    const downloadUrl = `${serverUrl}/api/download/${currentJobId}`;
    chrome.tabs.create({ url: downloadUrl });
  });
}

function resetButton() {
  const condenseBtn = document.getElementById('condenseBtn');
  condenseBtn.disabled = false;
  condenseBtn.textContent = 'Condense Video';
  condenseBtn.style.display = '';  // Make sure it's visible
}
