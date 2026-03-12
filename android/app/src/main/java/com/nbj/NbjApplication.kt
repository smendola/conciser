package com.nbj

import android.app.Application
import android.util.Log
import io.sentry.Sentry
import io.sentry.android.core.SentryAndroid
import io.sentry.android.core.SentryAndroidOptions

class NbjApplication : Application() {

    override fun onCreate() {
        super.onCreate()

        // Manual Sentry initialization (auto-init is disabled in manifest)
        if (BuildConfig.SENTRY_DSN.isNotBlank()) {
            try {
                SentryAndroid.init(this) { options: SentryAndroidOptions ->
                    options.dsn = BuildConfig.SENTRY_DSN
                    options.environment = if (BuildConfig.DEBUG) "debug" else "production"
                    options.release = "nbj-condenser@${BuildConfig.BUILD_VERSION}"
                    options.isDebug = BuildConfig.DEBUG
                    options.tracesSampleRate = if (BuildConfig.DEBUG) 1.0 else 0.1
                }
                Log.i("NbjApplication", "Sentry initialized successfully")

                // Send startup message to Sentry with build info as extra data
                Sentry.captureMessage("App started") { scope ->
                    scope.setExtra("build_version", BuildConfig.BUILD_VERSION)
                    scope.setExtra("app_name", "nbj-condenser")
                    scope.setTag("build", BuildConfig.BUILD_VERSION)
                }
            } catch (e: Exception) {
                Log.e("NbjApplication", "Failed to initialize Sentry", e)
            }
        } else {
            Log.w("NbjApplication", "Sentry DSN not configured - logging disabled")
        }
    }
}
