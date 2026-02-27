# NBJ Condenser Android App - Installation Guide

## Quick Start

### Prerequisites
- Android Studio Hedgehog (2023.1.1) or later
- Android SDK 24+ (Android 7.0+)
- Java JDK 8 or higher
- NBJ Condenser server running (see `../server/README.md`)

### Install on Device

**Method 1: Android Studio (Recommended)**

1. Open Android Studio
2. Click **File → Open**
3. Navigate to `nbj-condenser/android/` and click **OK**
4. Wait for Gradle sync to complete
5. Connect your Android device via USB (or use emulator)
6. Enable **USB Debugging** on your device:
   - Settings → About Phone → Tap "Build Number" 7 times
   - Settings → Developer Options → Enable "USB Debugging"
7. Click the **Run** button (▶️) in Android Studio
8. Select your device and click **OK**

**Method 2: Build APK and Install Manually**

```bash
cd android
./gradlew assembleDebug
```

The APK will be at: `app/build/outputs/apk/debug/app-debug.apk`

Install via ADB:
```bash
adb install app/build/outputs/apk/debug/app-debug.apk
```

Or copy the APK to your phone and install it directly.

## First Time Setup

1. **Open the NBJ Condenser app** on your device
2. **Tap the menu (⋮)** in the top-right → **Settings**
3. **Enter your server URL**:
   - Default: `https://conciser-aurora.ngrok.dev/`
   - Or your own server: `http://192.168.1.100:5000/` (local network)
4. **Tap Save**

## Usage

### Share from YouTube App

1. Open the **YouTube app**
2. Find a video to condense
3. Tap the **Share** button
4. Select **NBJ Condenser** from the share menu
5. Wait for processing (you'll see real-time progress)
6. Video opens automatically when ready!

### Share from Browser

1. Open YouTube in Chrome/Firefox
2. Navigate to a video
3. Tap **Share** → **NBJ Condenser**
4. Processing starts automatically

## Troubleshooting

### Gradle Sync Failed

**Error**: "Unsupported Gradle version"

**Solution**:
```bash
cd android
./gradlew wrapper --gradle-version 8.2
```

### Build Errors

**Error**: "SDK location not found"

**Solution**: Create `local.properties`:
```bash
echo "sdk.dir=/path/to/Android/Sdk" > local.properties
```

On Mac/Linux, typically:
```bash
echo "sdk.dir=$HOME/Library/Android/sdk" > local.properties
```

On Windows:
```bash
echo "sdk.dir=C:\\Users\\YourName\\AppData\\Local\\Android\\Sdk" > local.properties
```

### App Doesn't Appear in Share Menu

**Solution**:
1. Uninstall the app completely
2. Reinstall via Android Studio
3. Clear YouTube app cache: Settings → Apps → YouTube → Clear Cache

### "Connection Error"

**Solution**:
1. Check server is running: `curl https://conciser-aurora.ngrok.dev/health`
2. Verify server URL in app settings
3. Ensure phone can reach the server (same network or public ngrok URL)

## Building for Production

### Generate Signing Key

```bash
keytool -genkey -v -keystore nbj-release-key.jks -keyalg RSA -keysize 2048 -validity 10000 -alias nbj
```

### Configure Signing in build.gradle

Add to `app/build.gradle`:
```gradle
android {
    signingConfigs {
        release {
            storeFile file("nbj-release-key.jks")
            storePassword "your_store_password"
            keyAlias "nbj"
            keyPassword "your_key_password"
        }
    }

    buildTypes {
        release {
            signingConfig signingConfigs.release
            minifyEnabled true
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
        }
    }
}
```

### Build Release APK

```bash
./gradlew assembleRelease
```

Output: `app/build/outputs/apk/release/app-release.apk`

## Publishing to Google Play Store

1. Create a Google Play Developer account ($25 one-time fee)
2. Go to [Google Play Console](https://play.google.com/console)
3. Click **Create app**
4. Fill in app details:
   - Name: NBJ Condenser
   - Category: Video Players & Editors
   - Content rating: Everyone
5. Upload the release APK
6. Add screenshots, description, icon
7. Submit for review

## Development Setup

### Recommended Android Studio Plugins
- Kotlin
- Material Design Icons
- ADB Idea
- Rainbow Brackets

### Enable ViewBinding

Already configured in `app/build.gradle`:
```gradle
buildFeatures {
    viewBinding true
}
```

### Update Dependencies

```bash
./gradlew dependencies
```

Check for updates:
```bash
./gradlew dependencyUpdates
```

## System Requirements

### Minimum Device Requirements
- Android 7.0 (API 24) or higher
- 50 MB free storage
- Internet connection

### Recommended
- Android 10 (API 29) or higher
- 100 MB free storage
- WiFi connection (for faster video downloads)

## Common Issues

### "No video player found"
Install a video player: VLC, MX Player, or Google Photos

### "Server is busy"
Server is processing another video. Wait and retry.

### Videos don't play
Ensure you have a compatible video player installed.

## Next Steps

After installation:
1. Share a YouTube video to test the app
2. Customize server URL in Settings if needed
3. Check server logs if issues occur: `../server/nbj.log`

## Support

- GitHub Issues: https://github.com/yourusername/nbj-condenser/issues
- Server docs: `../server/README.md`
- Chrome extension docs: `../CHROME_EXTENSION_INSTALL.md`
