// Open options page on request from content scripts
chrome.runtime.onMessage.addListener((message) => {
  if (message.action === 'openOptionsPage') {
    chrome.runtime.openOptionsPage();
  }
});
