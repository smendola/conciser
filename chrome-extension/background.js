// Background service worker to manage icon state based on current page

// Icon paths
const ICON_ENABLED = {
  16: "icons/icon16.png",
  48: "icons/icon48.png",
  128: "icons/icon128.png"
};

const ICON_DISABLED = {
  16: "icons/icon16-disabled.png",
  48: "icons/icon48-disabled.png",
  128: "icons/icon128-disabled.png"
};

// Check if URL is a YouTube video page
function isYouTubeVideoPage(url) {
  if (!url) return false;
  try {
    const urlObj = new URL(url);
    // Check if it's YouTube and has a video ID (watch?v=...)
    return (urlObj.hostname === 'www.youtube.com' || urlObj.hostname === 'youtube.com') &&
           urlObj.pathname === '/watch' &&
           urlObj.searchParams.has('v');
  } catch (e) {
    return false;
  }
}

// Update icon based on tab
async function updateIcon(tabId, url) {
  const isVideoPage = isYouTubeVideoPage(url);

  try {
    // Set icon
    await chrome.action.setIcon({
      tabId: tabId,
      path: isVideoPage ? ICON_ENABLED : ICON_DISABLED
    });

    // Update title (tooltip)
    await chrome.action.setTitle({
      tabId: tabId,
      title: isVideoPage
        ? "NBJ Condenser - Click to condense this video"
        : "NBJ Condenser - Navigate to a YouTube video"
    });
  } catch (e) {
    console.error('Error updating icon:', e);
  }
}

// Listen for tab updates (URL changes, page loads)
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  // Only update when the URL changes or page completes loading
  if (changeInfo.url || changeInfo.status === 'complete') {
    updateIcon(tabId, tab.url);
  }
});

// Listen for tab activation (switching between tabs)
chrome.tabs.onActivated.addListener(async (activeInfo) => {
  try {
    const tab = await chrome.tabs.get(activeInfo.tabId);
    updateIcon(activeInfo.tabId, tab.url);
  } catch (e) {
    console.error('Error handling tab activation:', e);
  }
});

// Initialize icon state for existing tabs when extension loads
chrome.runtime.onInstalled.addListener(async () => {
  try {
    const tabs = await chrome.tabs.query({});
    for (const tab of tabs) {
      if (tab.id) {
        updateIcon(tab.id, tab.url);
      }
    }
  } catch (e) {
    console.error('Error initializing icons:', e);
  }
});

// Also update icon when extension starts
chrome.runtime.onStartup.addListener(async () => {
  try {
    const tabs = await chrome.tabs.query({});
    for (const tab of tabs) {
      if (tab.id) {
        updateIcon(tab.id, tab.url);
      }
    }
  } catch (e) {
    console.error('Error on startup:', e);
  }
});
