// NBJ Condenser - Content Script
// Injects the condenser UI directly into YouTube pages

console.log('[CONCISER] CONTENT_SCRIPT: content.js loaded');

// Helper to check if extension context is still valid
function isExtensionContextValid() {
  try {
    return !!chrome.runtime?.id;
  } catch (e) {
    return false;
  }
}

let injecting = false;
let keepExpanded = false; // remember open state across video navigations

// Wait for the page to load and inject our UI
async function injectCondenserUI() {
  console.log('[CONCISER] CONTENT_SCRIPT: attempting to inject UI');

  // Check if extension context is still valid
  if (!isExtensionContextValid()) {
    console.log('[CONCISER] CONTENT_SCRIPT: extension context invalidated, aborting');
    return;
  }

  // Find the #secondary-inner div (right sidebar on YouTube)
  const secondaryInner = document.getElementById('secondary-inner');

  if (!secondaryInner) {
    console.log('[CONCISER] CONTENT_SCRIPT: #secondary-inner not found, retrying...');
    // Retry after a short delay
    setTimeout(injectCondenserUI, 500);
    return;
  }

  // Check if we've already injected (or injection is in progress)
  if (injecting || document.getElementById('conciser')) {
    console.log('[CONCISER] CONTENT_SCRIPT: UI already injected or injection in progress');
    return;
  }
  injecting = true;

  console.log('[CONCISER] CONTENT_SCRIPT: injecting UI');

  // Create container
  const container = document.createElement('div');
  container.id = 'conciser';
  // Add some inline styles to make it visible and override any YouTube CSS
  container.style.cssText = 'display: block !important; visibility: visible !important; background: white; padding: 16px; border: 1px solid #ddd; border-radius: 4px; margin-bottom: 16px; width: 100%; box-sizing: border-box; position: relative; z-index: 1000;';

  // Import the CSS
  try {
    const style = document.createElement('link');
    style.rel = 'stylesheet';
    style.href = chrome.runtime.getURL('content.css');
    document.head.appendChild(style);
  } catch (e) {
    console.error('[CONCISER] CONTENT_SCRIPT: failed to load CSS', e);
    injecting = false;
    return;
  }

  // Load the UI HTML from the extension file
  try {
    const html = await fetch(chrome.runtime.getURL('content-panel.html')).then(r => r.text());
    container.innerHTML = html;
  } catch (e) {
    console.error('[CONCISER] CONTENT_SCRIPT: failed to load content-panel.html', e);
    injecting = false;
    return;
  }

  // Insert as first child of #secondary-inner
  secondaryInner.insertBefore(container, secondaryInner.firstChild);
  injecting = false;

  // Show the current video title (for context awareness)
  const titleEl = document.querySelector('ytd-watch-metadata h1 yt-formatted-string') ||
                  document.querySelector('#title h1 yt-formatted-string');
  const videoTitle = titleEl ? titleEl.textContent.trim() : document.title.replace(/ - YouTube$/, '');
  document.getElementById('nbj-video-title-collapsed').textContent = videoTitle;
  document.getElementById('nbj-video-title-expanded').textContent = videoTitle;

  // Watch for YouTube trying to hide our container
  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
        const currentClass = container.className;
        if (currentClass.includes('hidden')) {
          console.log('[CONCISER] CONTENT_SCRIPT: YouTube added hidden class, removing it');
          container.className = currentClass.replace(/\bhidden\b/g, '').trim();
        }
      }
    });
  });
  observer.observe(container, { attributes: true, attributeFilter: ['class'] });

  console.log('[CONCISER] CONTENT_SCRIPT: UI injected, initializing popup...');

  // Setup expand/collapse functionality
  const expandBtn = document.getElementById('nbj-expand-btn');
  const collapsedDiv = document.getElementById('nbj-condenser-collapsed');
  const expandedDiv = document.getElementById('nbj-condenser-expanded');

  function expand() {
    collapsedDiv.classList.add('hidden');
    expandedDiv.classList.remove('hidden');
    keepExpanded = true;
    if (typeof setupEventListeners === 'function' && typeof initializePopup === 'function') {
      console.log('[CONCISER] CONTENT_SCRIPT: Calling setupEventListeners and initializePopup');
      setupEventListeners();
      initializePopup();
    } else {
      console.error('[CONCISER] CONTENT_SCRIPT: setupEventListeners or initializePopup not found!', {
        hasSetupEventListeners: typeof setupEventListeners === 'function',
        hasInitializePopup: typeof initializePopup === 'function'
      });
    }
  }

  expandBtn.addEventListener('click', expand);

  if (keepExpanded) {
    expand();
  }
}

function resetForNavigation() {
  injecting = false;
  const old = document.getElementById('conciser');
  if (old) old.remove();
}

// Primary trigger: YouTube's own navigation-complete event.
// Fires reliably for both SPA navigations (recommendations, search, etc.)
// and the initial hard page load, after the new page DOM is ready.
document.addEventListener('yt-navigate-finish', () => {
  console.log('[CONCISER] CONTENT_SCRIPT: yt-navigate-finish');
  resetForNavigation();
  if (location.pathname.startsWith('/watch')) {
    injectCondenserUI();
  }
});

// Fallback for cases where yt-navigate-finish fires before the content script loads
// (e.g. extension installed while already on a video page, or hard reload).
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', injectCondenserUI);
} else {
  injectCondenserUI();
}
