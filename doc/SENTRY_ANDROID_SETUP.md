# Sentry Integration - Android App

This document describes the Sentry error monitoring and logging integration for the NBJ Condenser Android app.

## Overview

Sentry has been integrated into the Android app to provide:
- Automatic crash reporting
- Error tracking and logging
- Performance monitoring
- Release tracking
- Environment-based configuration

## Configuration

### 1. Setting the Sentry DSN

The Sentry DSN (Data Source Name) can be configured in two ways:

#### Option A: Environment Variable (Recommended)
```bash
export SENTRY_DSN="https://your-sentry-dsn@sentry.io/project-id"
./gradlew assembleDebug
```

#### Option B: build-settings.json
Add the following to `build-settings.json` in the project root:
```json
{
  "sentry_dsn": "https://your-sentry-dsn@sentry.io/project-id",
  "default_server_url": "http://127.0.0.1:5000"
}
```

If no DSN is configured, Sentry will be disabled and a warning will be logged.

### 2. Getting a Sentry DSN

1. Create a free account at [sentry.io](https://sentry.io)
2. Create a new Android project
3. Copy the DSN from the project settings
4. Configure it using one of the methods above

## What Gets Logged

### Automatic Crash Reporting
All uncaught exceptions are automatically sent to Sentry.

### Manual Error Logging
The following errors are explicitly captured:

#### MainActivity
- **Intent/Media Player Errors**: When opening YouTube videos or media files fails
- **Metadata Fetch Errors**: When fetching voices or strategies from the server fails
- **Job Submission Errors**: When submitting condense or takeaways jobs fails
- **Job Polling Errors**:
  - 404 errors when a job is not found
  - Network errors during polling (logged as warnings)

#### SettingsActivity
- **Health Check Errors**: When the server health check fails

### Event Context

Each error includes:
- **Release Version**: e.g., `nbj-condenser@1.0.123`
- **Environment**: `debug` or `production`
- **Platform Tag**: `android`
- **App Tag**: `nbj-condenser`
- **User Context**: Automatically captured by Sentry SDK
- **Device Info**: OS version, device model, etc.

## Performance Monitoring

Performance tracing is enabled with:
- **Debug builds**: 100% of transactions sampled (`tracesSampleRate = 1.0`)
- **Production builds**: 10% of transactions sampled (`tracesSampleRate = 0.1`)

This helps track:
- App startup time
- Network request performance
- Activity lifecycle timing

## Build Integration

The Sentry Gradle plugin automatically:
- Generates unique build IDs
- Creates sentry-debug.properties
- Uploads source maps (when configured for release builds)

### Build Files Modified

1. **android/build.gradle**
   - Added Sentry Gradle plugin to classpath

2. **android/app/build.gradle**
   - Applied Sentry Android Gradle plugin
   - Added Sentry SDK dependency
   - Added SENTRY_DSN build config field
   - Configured Sentry plugin options

3. **android/app/src/main/AndroidManifest.xml**
   - Added `android:name=".NbjApplication"` to use custom Application class

## Code Changes

### New Files
- **NbjApplication.kt**: Custom Application class that initializes Sentry on app startup

### Modified Files
- **MainActivity.kt**: Added Sentry import and error logging to catch blocks
- **SettingsActivity.kt**: Added Sentry error logging for health checks

## Testing Sentry Integration

### 1. Verify Build
```bash
cd android
./gradlew assembleDebug
```

### 2. Check Initialization Logs
After installing and running the app, check logcat for:
```
I/NbjApplication: Sentry initialized successfully
```

Or if no DSN is configured:
```
W/NbjApplication: Sentry DSN not configured - logging disabled
```

### 3. Trigger a Test Error
To verify errors are being captured:

1. Set an invalid server URL in Settings
2. Try to submit a job
3. Check Sentry dashboard for the error event

### 4. View Events in Sentry Dashboard
- Go to your Sentry project
- Navigate to "Issues" to see error reports
- Check "Performance" for transaction data

## Environment Tags

Errors are tagged with the build environment:
- `debug`: Debug builds running on development devices
- `production`: Release builds installed from APK

This helps filter issues in the Sentry dashboard.

## Privacy Considerations

Sentry collects:
- Error stack traces
- Device information (OS version, model)
- App version and build number
- Network request URLs (but not request bodies)

Sentry does NOT collect:
- User credentials
- Video URLs (unless they appear in error messages)
- Personal information

## Disabling Sentry

To build without Sentry:
1. Don't set the SENTRY_DSN environment variable
2. Don't add `sentry_dsn` to build-settings.json
3. The app will run normally but won't send error reports

## Additional Resources

- [Sentry Android Documentation](https://docs.sentry.io/platforms/android/)
- [Sentry Gradle Plugin](https://docs.sentry.io/platforms/android/configuration/gradle/)
- [Sentry SDK on GitHub](https://github.com/getsentry/sentry-java)
