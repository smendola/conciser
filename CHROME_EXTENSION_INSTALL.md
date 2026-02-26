# NBJ Condenser Chrome Extension - Installation Guide

## Package Created
A production-ready package has been created: `nbj-chrome-extension.zip` (14 KB)

## Features
- **Smart Icon State**: Icon appears colored when on a YouTube video page, grayed out elsewhere
- **One-Click Condensing**: Send videos to your NBJ Condenser server with a single click
- **Real-Time Progress**: See processing updates every 3 seconds
- **Persistent State**: Close and reopen the popup - it remembers your active job and resumes tracking
- **Automatic Detection**: Knows when you're on a YouTube video page

## Installation Options

### Option 1: Install Locally (No Developer Mode Required)

1. Open Chrome and go to `chrome://extensions/`
2. Drag and drop the `nbj-chrome-extension.zip` file directly onto the extensions page
3. Chrome will extract and install the extension automatically
4. The extension will appear in your Chrome toolbar

**Note:** Chrome may show a warning that the extension is "not from the Chrome Web Store". This is normal for locally installed extensions. Users can dismiss this warning and continue using the extension.

### Option 2: Chrome Web Store Publication (Recommended for Wide Distribution)

To publish on the Chrome Web Store and allow users to install without any warnings:

1. Create a Chrome Web Store Developer account at https://chrome.google.com/webstore/devconsole
   - One-time registration fee: $5

2. Upload the `conciser-chrome-extension.zip` file
   - Click "New Item" → Upload the zip file
   - Fill in the store listing details:
     - Description
     - Screenshots
     - Category: Productivity
     - Privacy policy URL (if collecting data)

3. Submit for review
   - Review typically takes 1-3 business days
   - Once approved, users can install with one click from the Chrome Web Store

4. Users install via: https://chrome.google.com/webstore/category/extensions

### Option 3: Manual Installation (Alternative)

If drag-and-drop doesn't work:

1. Unzip `conciser-chrome-extension.zip` to a folder
2. Open `chrome://extensions/`
3. Enable "Developer mode" (toggle in top-right)
4. Click "Load unpacked"
5. Select the unzipped folder

## What's Included

The package contains:
- `manifest.json` - Extension configuration
- `popup.html` - Extension popup interface
- `popup.js` - Extension functionality
- `icons/` - Extension icons (16x16, 48x48, 128x128)

## Usage

Once installed, click the NBJ Condenser icon in your Chrome toolbar while on a YouTube video page to send it to your NBJ Condenser server for AI-powered condensation.
