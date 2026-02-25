// Conciser Remote - Chrome Extension

let currentUrl = null;
let currentJobId = null;
let pollInterval = null;
const serverUrl = 'https://conciser-aurora.ngrok.dev';

// Get current tab and check if it's YouTube
chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
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
});

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
      showCompleted(data);
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

function showCompleted(data) {
  const container = document.getElementById('statusContainer');

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
}
