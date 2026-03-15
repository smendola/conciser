// Set flag to indicate we're in content script mode
// This MUST load before content-panel.js so that content-panel.js knows not to auto-initialize
window.NBJ_CONTENT_SCRIPT_MODE = true;
console.log('[CONCISER] CONTENT_MODE_FLAG: set window.NBJ_CONTENT_SCRIPT_MODE = true');
