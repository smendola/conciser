# NBJ Condenser Android App

## Overview

Native Android app (Kotlin) that integrates with the NBJ Condenser server. Accepts YouTube video share intents and submits them for condensation, showing real-time progress and the final result.

## Package

`com.nbj`

## Features

### Core
- **YouTube Share Target**: Registered as a share handler for YouTube video URLs
- **API Integration**: Communicates with the NBJ Condenser Flask server via Retrofit
- **Real-Time Progress**: Polls server every 3 seconds during processing
- **Auto-Play**: Opens condensed video or audio when complete (via Android intent chooser)

### Settings (main screen)
- **Voice**: Edge TTS voice picker (populated from server `/api/voices?locale=en`)
- **Aggressiveness**: Slider 1–10
- **Speech Speed**: Slider (-50% to +100%)
- **Output Mode**: Spinner — `Slideshow` (MP4) or `Audio Only` (MP3)
- **Prepend key take-aways intro**: Switch

### Settings screen (overflow menu)
- **Server URL**: Configurable base URL (default: `https://conciser-aurora.ngrok.dev/`)

### Recent Jobs
- Stores up to 10 recent jobs in SharedPreferences as JSON
- Shows video title (fetched via YouTube oEmbed API) instead of raw video ID
- Tap a job to re-open its download URL

## Architecture

### AppState Machine
```
NO_URL → READY → SUBMITTING → PROCESSING → COMPLETED
                                         → ERROR
```

- `NO_URL` — No video URL yet (app opened directly, not via share)
- `READY` — URL received, settings visible, "Condense" button active
- `SUBMITTING` — POST to `/api/condense` in progress
- `PROCESSING` — Polling `/api/status/<job_id>` every 3 seconds
- `COMPLETED` — Download URL available, "Play" button shown
- `ERROR` — Error message shown, retry available

### Key Files

| File | Purpose |
|------|---------|
| `MainActivity.kt` | Main UI, AppState machine, intent handling, polling |
| `SettingsActivity.kt` | Server URL configuration |
| `ConciSerApi.kt` | Retrofit API client + data classes |
| `activity_main.xml` | Single-screen NestedScrollView layout |
| `strings.xml` | String resources |

### API Data Classes (ConciSerApi.kt)

```kotlin
data class CondenseRequest(
    val url: String,
    val aggressiveness: Int = 5,
    val voice: String = "",
    val speech_rate: String = "+10%",
    val video_mode: String = "slideshow",
    val prepend_intro: Boolean = false
)

data class CondenseResponse(val job_id: String, val status: String, val message: String)

data class StatusResponse(
    val job_id: String, val status: String,
    val progress: String? = null, val download_url: String? = null,
    val error: String? = null, val created_at: String? = null, val completed_at: String? = null
)
```

## UI Layout

Single-screen `NestedScrollView` with:
- Video info header (title, bold; video URL)
- Voice spinner (dialog mode, populated from server)
- Aggressiveness seekbar (blue)
- Speech speed seekbar (blue)
- Output mode spinner
- Prepend intro switch
- Status text + progress bar
- Action button (Condense / Play)
- Recent jobs list

## Build

```bash
cd android
./gradlew assembleDebug
adb install app/build/outputs/apk/debug/app-debug.apk
```

Or open `android/` in Android Studio and click Run.

## Configuration

**Default server**: `https://conciser-aurora.ngrok.dev/`

To change: open app → menu (⋮) → Settings → enter new server URL → Save.

All settings (voice, aggressiveness, speed, output mode, prepend intro, server URL) are persisted in SharedPreferences.

## API Communication

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/voices?locale=en` | GET | Populate voice spinner |
| `/api/condense` | POST | Submit video URL |
| `/api/status/<id>` | GET | Poll for progress |
| `/api/download/<id>` | GET | Stream output file |

Video title fetched via YouTube oEmbed: `https://www.youtube.com/oembed?url=<url>&format=json`

## Dependencies

```gradle
implementation 'com.squareup.retrofit2:retrofit:2.9.0'
implementation 'com.squareup.retrofit2:converter-gson:2.9.0'
implementation 'com.squareup.okhttp3:okhttp:4.12.0'
implementation 'com.squareup.okhttp3:logging-interceptor:4.12.0'
implementation 'org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3'
implementation 'androidx.core:core-ktx:1.12.0'
implementation 'androidx.appcompat:appcompat:1.6.1'
implementation 'com.google.android.material:material:1.11.0'
```

## Requirements

- **Minimum SDK**: Android 7.0 (API 24)
- **Target SDK**: Android 14 (API 34)
- **Permissions**: INTERNET, ACCESS_NETWORK_STATE
- **For playback**: Any video/audio player app (VLC, MX Player, system player, etc.)

## User Flow

```
1. User opens YouTube → shares video → selects "NBJ Condenser"
2. App opens with video URL pre-filled
3. User adjusts settings (voice, aggressiveness, etc.)
4. Taps "Condense"
5. App shows "Processing..." with live progress updates
6. When complete: "Play Video" button appears
7. Tap Play → Android intent chooser → watch in preferred player
```

## Troubleshooting

**"No video player found"** — Install VLC or MX Player from Play Store.

**"Connection error"** — Check server is running and server URL in Settings is correct.

**"Processing failed"** — Video may be private, age-restricted, or the server encountered an error. Check server logs.
