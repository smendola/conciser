package com.smendola.conciser

import android.app.Application
import android.util.Log
import io.sentry.Sentry
import io.sentry.SentryLevel
import io.sentry.android.core.SentryAndroid
import io.sentry.android.core.SentryAndroidOptions
import kotlinx.coroutines.DelicateCoroutinesApi
import kotlinx.coroutines.GlobalScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

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
                    options.isDebug = true
                    options.tracesSampleRate = 1.0
                    options.profilesSampleRate = 1.0
                    options.maxBreadcrumbs = 5000
                }
                Log.i("NbjApplication", "Sentry initialized successfully")

                // Send startup message to Sentry with build info as extra data
                Sentry.captureMessage("App started") { scope ->
                    scope.setExtra("build_version", BuildConfig.BUILD_VERSION)
                    scope.setExtra("app_name", "nbj-condenser")
                    scope.setTag("build", BuildConfig.BUILD_VERSION)
                }

                // Flush early so you can confirm Sentry is actually delivering events.
                Sentry.flush(5000)

                // During debugging: periodically flush so high-volume events are less likely to
                // sit in memory while you're clicking around.
                startPeriodicSentryFlush()
            } catch (e: Exception) {
                Log.e("NbjApplication", "Failed to initialize Sentry", e)
            }
        } else {
            Log.w("NbjApplication", "Sentry DSN not configured - logging disabled")
        }
    }

    @OptIn(DelicateCoroutinesApi::class)
    private fun startPeriodicSentryFlush() {
        GlobalScope.launch {
            while (true) {
                try {
                    delay(3000)
                    Sentry.flush(2000)
                } catch (_: Exception) {
                }
            }
        }
    }
}
