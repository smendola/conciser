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

// Wait for the page to load and inject our UI
function injectCondenserUI() {
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

  // Check if we've already injected
  if (document.getElementById('nbj-condenser-container')) {
    console.log('[CONCISER] CONTENT_SCRIPT: UI already injected');
    return;
  }

  console.log('[CONCISER] CONTENT_SCRIPT: injecting UI');

  // Create container
  const container = document.createElement('div');
  container.id = 'nbj-condenser-container';
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
    return;
  }

  // Set the innerHTML for the injected UI
  container.innerHTML = `
    <!-- Collapsed state - just a button -->
    <div id="nbj-condenser-collapsed">
      <button id="nbj-expand-btn">Too long! Condense this video</button>
    </div>

    <!-- Expanded state - full UI (hidden by default) -->
    <div id="nbj-condenser-expanded" class="hidden">
    <div class="title-row">
      <span class="title-text">🎬 NBJ Condenser</span>
      <span class="build-info" id="buildInfo">…</span>
    </div>

    <div class="tabs">
      <button class="tab active" data-tab="condense">Condense</button>
      <button class="tab" data-tab="takeaways">Takeaways</button>
    </div>

    <!-- Condense Tab -->
    <div class="tab-content active" id="condense-tab">
      <div class="settings" id="settings">
        <div class="setting-group">
          <label class="setting-label" for="videoModeSelect">Output Mode</label>
          <select id="videoModeSelect">
            <option value="slideshow">Slideshow</option>
            <option value="audio_only">Audio Only (MP3)</option>
          </select>
        </div>

        <div class="setting-group-grid">
          <div class="setting-group">
            <label class="setting-label" for="localeSelect">Language</label>
            <select id="localeSelect">
              <option value="">Loading...</option>
            </select>
          </div>
          <div class="setting-group">
            <label class="setting-label" for="voiceSelect">Voice</label>
            <select id="voiceSelect">
              <option value="">Select language</option>
            </select>
          </div>
        </div>

        <div class="setting-group">
          <div class="slider-label-row">
            <label class="setting-label" for="aggressivenessSlider">Aggressiveness</label>
            <span class="slider-value" id="aggressivenessValue">5</span>
          </div>
          <input type="range" id="aggressivenessSlider" min="1" max="10" value="5" step="1">
          <div id="strategyDesc" class="strategy-desc">Loading...</div>
        </div>

        <div class="setting-group">
          <div class="slider-label-row">
            <label class="setting-label" for="speedSlider">Speech Speed</label>
            <span class="slider-value" id="speedValue">1.10x</span>
          </div>
          <input type="range" id="speedSlider" min="0.9" max="2.0" value="1.10" step="0.05">
        </div>

        <div class="setting-group">
          <label class="checkbox-label">
            <input type="checkbox" id="prependIntroCheck">
            <span class="setting-label">Prepend key take-aways intro</span>
          </label>
        </div>
      </div>

      <button id="condenseBtn" disabled>Condense Video</button>

      <div id="statusContainer"></div>

      <div class="recent-jobs hidden" id="recentCondenseJobs">
        <h3>Recent</h3>
        <div id="recentCondenseJobsList"></div>
      </div>
    </div>

    <!-- Takeaways Tab -->
    <div class="tab-content" id="takeaways-tab">
      <div class="settings">
        <div class="setting-group">
          <label class="setting-label">Number of Takeaways</label>
          <div class="radio-group">
            <div class="radio-option">
              <input type="radio" id="top3" name="top" value="3">
              <label for="top3">Top 3</label>
            </div>
            <div class="radio-option">
              <input type="radio" id="top5" name="top" value="5">
              <label for="top5">Top 5</label>
            </div>
            <div class="radio-option">
              <input type="radio" id="top10" name="top" value="10">
              <label for="top10">Top 10</label>
            </div>
            <div class="radio-option">
              <input type="radio" id="topAuto" name="top" value="auto" checked>
              <label for="topAuto">Auto</label>
            </div>
          </div>
        </div>

        <div class="setting-group">
          <label class="setting-label">Output Format</label>
          <div class="radio-group">
            <div class="radio-option">
              <input type="radio" id="formatText" name="format" value="text" checked>
              <label for="formatText">Text</label>
            </div>
            <div class="radio-option">
              <input type="radio" id="formatAudio" name="format" value="audio">
              <label for="formatAudio">Audio</label>
            </div>
          </div>
        </div>

        <div class="setting-group takeaways-voice-group hidden" id="takeawaysVoiceGroup">
          <div class="setting-group-grid">
            <div class="setting-group">
              <label class="setting-label" for="takeawaysLocaleSelect">Language</label>
              <select id="takeawaysLocaleSelect">
                <option value="">Loading...</option>
              </select>
            </div>
            <div class="setting-group">
              <label class="setting-label" for="takeawaysVoiceSelect">Voice</label>
              <select id="takeawaysVoiceSelect">
                <option value="">Select language</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      <button id="takeawaysBtn" disabled>Extract Takeaways</button>

      <div id="takeawaysStatusContainer"></div>

      <div class="recent-jobs hidden" id="recentTakeawaysJobs">
        <h3>Recent</h3>
        <div id="recentTakeawaysJobsList"></div>
      </div>
    </div>

    </div>
  `;

  // Insert as first child of #secondary-inner
  secondaryInner.insertBefore(container, secondaryInner.firstChild);

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

  expandBtn.addEventListener('click', () => {
    collapsedDiv.classList.add('hidden');
    expandedDiv.classList.remove('hidden');

    // Initialize popup after expanding
    // Need to call both setupEventListeners and initializePopup (same as popup mode)
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
  });
}

// Wait for DOM to be ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', injectCondenserUI);
} else {
  injectCondenserUI();
}

// Also watch for YouTube navigation (SPA navigation)
let lastUrl = location.href;
new MutationObserver(() => {
  const url = location.href;
  if (url !== lastUrl) {
    lastUrl = url;
    console.log('[CONCISER] CONTENT_SCRIPT: URL changed, re-injecting UI');
    // Remove old container if exists
    const oldContainer = document.getElementById('nbj-condenser-container');
    if (oldContainer) {
      oldContainer.remove();
    }
    // Re-inject
    setTimeout(injectCondenserUI, 1000);
  }
}).observe(document, {subtree: true, childList: true});
