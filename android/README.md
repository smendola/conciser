# NBJ Condenser Android App

Android app for condensing YouTube videos using the NBJ Condenser server.

## Features

- **Share Target**: Share YouTube videos directly from the YouTube app
- **Real-Time Progress**: See condensing progress with live status updates
- **Auto-Play**: Automatically opens the condensed video when ready
- **External Player Support**: Choose your favorite video player (VLC, MX Player, etc.)
- **Configurable Server**: Set your own NBJ Condenser server URL
- **Material Design 3**: Modern, clean UI following Android design guidelines

## How It Works

1. **Share a YouTube video** from the YouTube app
2. Select **NBJ Condenser** from the share menu
3. App submits the video to your NBJ Condenser server
4. **Real-time progress updates** show condensing status
5. When complete, the app **automatically opens** the condensed video
6. **Choose your video player** from Android's default player chooser

## Requirements

- **Android 7.0 (API 24)** or higher
- **Internet connection** to communicate with NBJ Condenser server
- **Video player app** (VLC, MX Player, etc.) installed on your device
- **NBJ Condenser server** running and accessible (see `../server/`)

## Installation

### Option 1: Build from Source (Android Studio)

1. Open **Android Studio**
2. Click **File → Open** and select the `android/` folder
3. Wait for Gradle sync to complete
4. Click **Run** (▶️) or press `Shift+F10`
5. Select your device/emulator

### Option 2: Build APK via Command Line

```bash
cd android
./gradlew assembleDebug
```

The APK will be in: `app/build/outputs/apk/debug/app-debug.apk`

Install on your device:
```bash
adb install app/build/outputs/apk/debug/app-debug.apk
```

### Option 3: Build Release APK

```bash
cd android
./gradlew assembleRelease
```

## Configuration

### Server URL

By default, the app connects to: `https://conciser-aurora.ngrok.dev/`

To change the server URL:
1. Open the NBJ Condenser app
2. Tap the **⋮ menu** → **Settings**
3. Enter your server URL
4. Tap **Save**

You can also edit `ConciSerApi.kt` to change the default:
```kotlin
private const val BASE_URL = "https://your-server-url.com/"
```

## Usage

### From YouTube App

1. Open **YouTube app**
2. Find a video you want to condense
3. Tap the **Share** button
4. Select **NBJ Condenser** from the list
5. Wait for processing (5-15 minutes depending on video length)
6. Video opens automatically when ready

### From Browser

1. Open a YouTube video in Chrome/Firefox
2. Tap **Share** → **NBJ Condenser**
3. Wait for processing
4. Choose your video player when prompted

## Architecture

```
com.nbj/
├── MainActivity.kt          # Main activity handling share intents
├── SettingsActivity.kt      # Server configuration
├── ConciSerApi.kt          # Retrofit API service
└── res/
    ├── layout/             # UI layouts
    ├── values/             # Strings, colors, themes
    ├── menu/               # App menu
    └── drawable/           # Icons and graphics
```

### Key Components

**MainActivity**
- Receives YouTube share intents
- Submits videos to NBJ Condenser server API
- Polls for job status every 3 seconds
- Launches video player when complete

**ConciSerApi**
- Retrofit service for server communication
- Endpoints: `/api/condense`, `/api/status/{id}`, `/api/download/{id}`
- Handles network requests with OkHttp

**SettingsActivity**
- Configure server URL
- Stored in SharedPreferences

## API Communication

The app communicates with the NBJ Condenser server via REST API:

### Submit Video
```
POST /api/condense
Body: {"url": "https://youtube.com/watch?v=..."}
Response: {"job_id": "abc123", "status": "queued"}
```

### Check Status
```
GET /api/status/abc123
Response: {"status": "processing", "progress": "Transcribing..."}
```

### Download Video
```
GET /api/download/abc123
Response: MP4 video file
```

## Troubleshooting

### "No video player found"
**Solution**: Install a video player app like:
- VLC for Android
- MX Player
- Google Photos
- Default Android video player

### "Connection error"
**Solution**:
- Check that the NBJ Condenser server is running
- Verify the server URL in Settings
- Ensure your device can reach the server (same network or ngrok)
- Check internet connection

### "Processing failed"
**Solution**:
- Video may be age-restricted or unavailable
- Server may be busy (single-threaded)
- Check server logs for details

### App crashes when opening
**Solution**:
- Clear app data: Settings → Apps → NBJ Condenser → Clear Data
- Reinstall the app
- Check Android version (requires Android 7.0+)

## Development

### Tech Stack
- **Kotlin** - Modern Android development language
- **Material Design 3** - UI components
- **Retrofit** - REST API client
- **OkHttp** - HTTP client
- **Coroutines** - Asynchronous programming
- **ViewBinding** - Type-safe view access

### Building

Debug build:
```bash
./gradlew assembleDebug
```

Release build (requires signing):
```bash
./gradlew assembleRelease
```

Run tests:
```bash
./gradlew test
```

### Code Style

Follow [Kotlin coding conventions](https://kotlinlang.org/docs/coding-conventions.html)

### Adding Features

1. Update `MainActivity.kt` for UI changes
2. Update `ConciSerApi.kt` for new API endpoints
3. Update layouts in `res/layout/`
4. Add strings to `res/values/strings.xml`

## Permissions

The app requests the following permissions:

- `INTERNET` - Required to communicate with NBJ Condenser server
- `ACCESS_NETWORK_STATE` - Check network connectivity

No other permissions are needed. The app does not:
- Access your files
- Use your camera
- Track your location
- Access contacts

## Future Enhancements

- [ ] Download video to device storage
- [ ] Queue multiple videos
- [ ] Background processing with notifications
- [ ] Adjust aggressiveness level in-app
- [ ] View processing history
- [ ] Share condensed videos
- [ ] Offline mode (cached videos)
- [ ] Dark theme support

## License

MIT License - see main project LICENSE file

## Support

For issues, check:
- Server logs: `../server/nbj.log`
- Android logcat: `adb logcat | grep NBJ`
- GitHub issues: https://github.com/yourusername/nbj-condenser/issues
