package com.nbj

import android.content.Context
import android.content.Intent
import android.graphics.Typeface
import android.text.SpannableString
import android.text.Spanned
import android.text.style.StyleSpan
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.Editable
import android.text.TextWatcher
import android.util.Log
import android.view.MotionEvent
import android.view.Menu
import android.view.MenuItem
import android.view.Gravity
import android.graphics.Color
import android.view.View
import android.util.TypedValue
import android.view.ViewGroup
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.ImageView
import android.widget.SeekBar
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.widget.Toolbar
import androidx.core.content.FileProvider
import androidx.core.view.isVisible
import androidx.lifecycle.lifecycleScope
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import com.google.android.material.snackbar.Snackbar
import com.nbj.databinding.ActivityMainBinding
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import android.os.SystemClock
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.sse.EventSource
import okhttp3.sse.EventSourceListener
import okhttp3.sse.EventSources
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TreeSet
import kotlin.math.roundToInt
import kotlin.math.abs
import io.sentry.Sentry
import io.sentry.SentryLevel

class MainActivity : AppCompatActivity() {

    private val logTag = "MetadataCache"

    private val EXPECTED_CONDENSE_LOCALE = "en-US"
    private val EXPECTED_CONDENSE_VOICE_ID = "en-US-TonyNeural"
    private val EXPECTED_CONDENSE_VOICE_LABEL = "Tony"
    private val EXPECTED_TAKEAWAYS_LOCALE = "en-GB"
    private val EXPECTED_TAKEAWAYS_VOICE_ID = "en-GB-OliverNeural"
    private val EXPECTED_TAKEAWAYS_VOICE_LABEL = "Oliver"

    private fun verboseLangVoiceLoggingEnabled(): Boolean {
        return try {
            BuildConfig.SENTRY_VERBOSE_LANG_VOICE_LOGGING
        } catch (_: Exception) {
            false
        }
    }

    private data class RecentJobBadge(val badgeText: String, val bgColor: Int)

    private fun getRecentJobBadge(job: JobResponse): RecentJobBadge {
        val params = job.params ?: emptyMap()
        val outputFormat = (params["output_format"] ?: params["outputFormat"] ?: "").toString().trim().lowercase(Locale.US)
        val jobType = job.type.trim().lowercase(Locale.US)

        if (outputFormat == "audio" || outputFormat == "mp3") {
            return RecentJobBadge("MP3", 0xFF28a745.toInt())
        }
        if (outputFormat == "text" || outputFormat == "txt" || outputFormat == "markdown" || outputFormat == "md") {
            return RecentJobBadge("📄", 0xFF28a745.toInt())
        }
        if (outputFormat == "slideshow") {
            return RecentJobBadge("🎞️", 0xFF1a73e8.toInt())
        }
        if (outputFormat == "video" || outputFormat == "mp4") {
            return RecentJobBadge("MP4", 0xFF1a73e8.toInt())
        }
        if (jobType == "takeaways") {
            return RecentJobBadge("📄", 0xFF28a745.toInt())
        }
        return RecentJobBadge("🎞️", 0xFF1a73e8.toInt())
    }

    private fun getRecentJobDisplayTitle(job: JobResponse): String {
        val title = job.title?.trim().orEmpty()
        if (title.isNotBlank()) return title
        val url = job.url
        val videoId = Regex("""[?&]v=([^&]+)""").find(url)?.groupValues?.getOrNull(1)
        return videoId ?: job.id
    }

    private fun attachSwipeToDelete(row: View, deleteBg: LinearLayout, job: JobResponse, serverUrl: String) {
        val dp = resources.displayMetrics.density
        var startX = 0f
        var startY = 0f
        var swiping = false
        // Start hidden until swipe begins.
        deleteBg.visibility = View.GONE

        row.setOnTouchListener { v, ev ->
            when (ev.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    startX = ev.rawX
                    startY = ev.rawY
                    swiping = false
                    v.translationX = 0f
                    deleteBg.visibility = View.GONE
                    false
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = ev.rawX - startX
                    val dy = ev.rawY - startY
                    if (!swiping) {
                        if (abs(dx) > (8 * dp) && abs(dx) > abs(dy) * 1.5f) {
                            swiping = true
                            v.parent?.requestDisallowInterceptTouchEvent(true)
                        }
                    }
                    if (swiping) {
                        // Reveal delete bg and position icon opposite swipe direction.
                        deleteBg.visibility = View.VISIBLE
                        deleteBg.gravity = if (dx > 0) Gravity.END or Gravity.CENTER_VERTICAL else Gravity.START or Gravity.CENTER_VERTICAL
                        v.translationX = dx
                        // While swiping, disable selectable ripple/gray press states.
                        v.isPressed = false
                        v.isActivated = false
                        true
                    } else {
                        false
                    }
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    if (!swiping) return@setOnTouchListener false
                    val dx = ev.rawX - startX
                    val commitThresholdPx = v.width * 0.40f
                    if (abs(dx) >= commitThresholdPx) {
                        val dir = if (dx > 0) 1f else -1f
                        v.animate().translationX(dir * v.width.toFloat()).setDuration(120).withEndAction {
                            // Remove immediately with collapse animation so remaining rows slide up.
                            val parent = v.parent as? android.widget.FrameLayout
                            if (parent != null) {
                                collapseAndRemoveRecentRowContainer(parent)
                            }
                            // Fire-and-forget server delete.
                            deleteRecentServerJob(job.id, serverUrl)
                        }.start()
                    } else {
                        v.animate().translationX(0f).setDuration(120).start()
                        deleteBg.visibility = View.GONE
                    }
                    true
                }
                else -> false
            }
        }
    }

    private fun collapseAndRemoveRecentRowContainer(container: android.widget.FrameLayout) {
        val parent = container.parent as? LinearLayout ?: return

        val containerIndex = parent.indexOfChild(container)
        val divider = parent.getChildAt(containerIndex + 1)
        val dividerHeightPx = (1 * resources.displayMetrics.density).toInt()
        val shouldRemoveDivider = divider != null && divider.layoutParams?.height == dividerHeightPx

        fun animateCollapse(v: View, onEnd: () -> Unit) {
            v.post {
                val initialHeight = v.height
                if (initialHeight <= 0) {
                    onEnd()
                    return@post
                }
                val anim = android.animation.ValueAnimator.ofInt(initialHeight, 0)
                anim.duration = 150
                anim.addUpdateListener { va ->
                    val lp = v.layoutParams
                    lp.height = va.animatedValue as Int
                    v.layoutParams = lp
                }
                anim.addListener(object : android.animation.AnimatorListenerAdapter() {
                    override fun onAnimationEnd(animation: android.animation.Animator) {
                        onEnd()
                    }
                })
                anim.start()
            }
        }

        animateCollapse(container) { parent.removeView(container) }
        if (shouldRemoveDivider) {
            animateCollapse(divider) { parent.removeView(divider) }
        }
    }

    private fun deleteRecentServerJob(jobId: String, serverUrl: String) {
        lifecycleScope.launch {
            try {
                val api = ConciserApi.createService(serverUrl, ClientIdentity.getOrCreate(this@MainActivity))
                withContext(Dispatchers.IO) {
                    api.deleteJob(jobId)
                }
            } catch (e: Exception) {
                Sentry.captureException(e)
            } finally {
                refreshRecentJobsUI()
            }
        }
    }

    private fun sentryBreadcrumb(
        what: String,
        extras: Map<String, Any?> = emptyMap(),
        level: SentryLevel = SentryLevel.INFO
    ) {
        try {
            if (!verboseLangVoiceLoggingEnabled()) return
            val prefs = try {
                getSharedPreferences(prefsName, Context.MODE_PRIVATE)
            } catch (_: Exception) {
                null
            }

            val merged = linkedMapOf<String, Any?>(
                "what" to what,
                "ts" to System.currentTimeMillis(),
                "thread" to Thread.currentThread().name,
                "appMode" to appMode,
                "currentState" to currentState.name,
                "voicesCount" to voices.size,
                "strategiesCount" to strategies.size,
                "blockVoiceSelectionCallbacksUntilMs" to blockVoiceSelectionCallbacksUntilMs,
                "blockTakeawaysVoicePersistUntilMs" to blockTakeawaysVoicePersistUntilMs,
                "suppressAutoSave" to suppressAutoSave,
                "restoringVoiceSelections" to restoringVoiceSelections,
                "spinnerLocale_selected" to (runCatching { binding.spinnerLocale.selectedItem?.toString() }.getOrNull()),
                "spinnerVoice_pos" to (runCatching { binding.spinnerVoice.selectedItemPosition }.getOrNull()),
                "spinnerVoice_selected" to (runCatching { binding.spinnerVoice.selectedItem?.toString() }.getOrNull()),
                "spinnerTakeawaysLocale_selected" to (runCatching { binding.spinnerTakeawaysLocale.selectedItem?.toString() }.getOrNull()),
                "spinnerTakeawaysVoice_pos" to (runCatching { binding.spinnerTakeawaysVoice.selectedItemPosition }.getOrNull()),
                "spinnerTakeawaysVoice_selected" to (runCatching { binding.spinnerTakeawaysVoice.selectedItem?.toString() }.getOrNull()),
                "prefs_server_url" to (prefs?.getString("server_url", null)),
                "prefs_condense_locale" to (prefs?.getString(KEY_CONDENSE_LOCALE, null)),
                "prefs_condense_voice" to (prefs?.getString(KEY_CONDENSE_VOICE, null)),
                "prefs_takeaways_locale" to (prefs?.getString(KEY_TAKEAWAYS_LOCALE, null)),
                "prefs_takeaways_voice" to (prefs?.getString(KEY_TAKEAWAYS_VOICE, null)),
                "prefs_takeaways_format" to (prefs?.getString(KEY_TAKEAWAYS_FORMAT, null)),
            )
            for ((k, v) in extras) merged[k] = v

            Sentry.withScope { scope ->
                scope.level = level
                scope.setContexts("voice_locale_debug", merged)
                scope.setExtra("voice_locale_debug_json", Gson().toJson(merged))
                scope.setExtra("voice_locale_debug_keys", merged.keys.joinToString(","))
                Sentry.captureMessage(what)
            }
        } catch (_: Exception) {
        }
    }

    private fun voiceIdToFriendlyLabel(voiceId: String?): String? {
        if (voiceId.isNullOrBlank()) return null
        val v = voices.firstOrNull { it.name == voiceId }
        val friendly = v?.friendly_name?.ifBlank { null }
        if (!friendly.isNullOrBlank()) return friendly
        return voiceId
    }

    private fun isPlaceholderLocale(value: String?): Boolean {
        val v = value?.trim().orEmpty()
        if (v.isBlank()) return true
        return v.equals("Loading...", ignoreCase = true)
    }

    private fun isPlaceholderVoiceSelectionText(value: String?): Boolean {
        val v = value?.trim().orEmpty()
        if (v.isBlank()) return true
        return v.equals("Select language", ignoreCase = true) ||
            v.equals("Select voice", ignoreCase = true) ||
            v.equals("Failed to load voices", ignoreCase = true) ||
            v.equals("Loading...", ignoreCase = true)
    }

    private fun blockedPrefWrite(marker: String, where: String, extras: Map<String, Any?> = emptyMap()) {
        val merged = LinkedHashMap<String, Any?>(extras.size + 2)
        merged.putAll(extras)
        merged["blocked_where"] = where
        merged["blocked_marker"] = marker
        sentryErrorMessage(marker, merged)
        sentryErrorWithStack(marker, merged)
    }

    private fun expectedInvariantOk(
        condenseLocale: String?,
        condenseVoiceId: String?,
        takeawaysLocale: String?,
        takeawaysVoiceId: String?
    ): Boolean {
        val cLocOk = condenseLocale == EXPECTED_CONDENSE_LOCALE
        val cVoiceOk = if (voices.isNotEmpty()) {
            voiceIdToFriendlyLabel(condenseVoiceId) == EXPECTED_CONDENSE_VOICE_LABEL
        } else {
            condenseVoiceId == EXPECTED_CONDENSE_VOICE_ID
        }
        val tLocOk = takeawaysLocale == EXPECTED_TAKEAWAYS_LOCALE
        val tVoiceOk = if (voices.isNotEmpty()) {
            voiceIdToFriendlyLabel(takeawaysVoiceId) == EXPECTED_TAKEAWAYS_VOICE_LABEL
        } else {
            takeawaysVoiceId == EXPECTED_TAKEAWAYS_VOICE_ID
        }
        return cLocOk && cVoiceOk && tLocOk && tVoiceOk
    }

    private fun sentryErrorWithStack(what: String, extras: Map<String, Any?> = emptyMap()) {
        try {
            val stack = Thread.currentThread().stackTrace
                .joinToString("\n") { it.toString() }
            val merged = LinkedHashMap<String, Any?>(extras.size + 2)
            merged.putAll(extras)
            merged["stacktrace"] = stack
            merged["stacktrace_len"] = stack.length

            Sentry.withScope { scope ->
                scope.level = SentryLevel.ERROR
                scope.setExtra("voice_locale_debug_json", Gson().toJson(merged))
                scope.setContexts("voice_locale_debug", merged)
                Sentry.captureMessage(what)
            }
        } catch (_: Exception) {
        }
    }

    private fun sentryErrorMessage(what: String, extras: Map<String, Any?> = emptyMap()) {
        try {
            Sentry.withScope { scope ->
                scope.level = SentryLevel.ERROR
                scope.setExtra("voice_locale_debug_json", Gson().toJson(extras))
                scope.setContexts("voice_locale_debug", extras)
                Sentry.captureMessage(what)
            }
        } catch (_: Exception) {
        }
    }

    private fun assertExpectedInvariant(where: String) {
        try {
            if (!verboseLangVoiceLoggingEnabled()) return
            val prefs = getSharedPreferences(prefsName, Context.MODE_PRIVATE)
            val cLoc = prefs.getString(KEY_CONDENSE_LOCALE, null)
            val cVoice = prefs.getString(KEY_CONDENSE_VOICE, null)
            val tLoc = prefs.getString(KEY_TAKEAWAYS_LOCALE, null)
            val tVoice = prefs.getString(KEY_TAKEAWAYS_VOICE, null)
            val ok = expectedInvariantOk(cLoc, cVoice, tLoc, tVoice)
            if (!ok) {
                val extras = linkedMapOf<String, Any?>(
                    "where" to where,
                    "expected_condense_locale" to EXPECTED_CONDENSE_LOCALE,
                    "expected_condense_voice_id" to EXPECTED_CONDENSE_VOICE_ID,
                    "expected_condense_voice_label" to EXPECTED_CONDENSE_VOICE_LABEL,
                    "expected_takeaways_locale" to EXPECTED_TAKEAWAYS_LOCALE,
                    "expected_takeaways_voice_id" to EXPECTED_TAKEAWAYS_VOICE_ID,
                    "expected_takeaways_voice_label" to EXPECTED_TAKEAWAYS_VOICE_LABEL,
                    "actual_condense_locale" to cLoc,
                    "actual_condense_voice_id" to cVoice,
                    "actual_condense_voice_label" to voiceIdToFriendlyLabel(cVoice),
                    "actual_takeaways_locale" to tLoc,
                    "actual_takeaways_voice_id" to tVoice,
                    "actual_takeaways_voice_label" to voiceIdToFriendlyLabel(tVoice),
                    "invariant_mode" to if (voices.isNotEmpty()) "friendly_label" else "voice_id",
                    "spinner_condense_locale" to runCatching { binding.spinnerLocale.selectedItem?.toString() }.getOrNull(),
                    "spinner_condense_voice" to runCatching { binding.spinnerVoice.selectedItem?.toString() }.getOrNull(),
                    "spinner_takeaways_locale" to runCatching { binding.spinnerTakeawaysLocale.selectedItem?.toString() }.getOrNull(),
                    "spinner_takeaways_voice" to runCatching { binding.spinnerTakeawaysVoice.selectedItem?.toString() }.getOrNull(),
                    "spinner_takeaways_voice_pos" to runCatching { binding.spinnerTakeawaysVoice.selectedItemPosition }.getOrNull(),
                    "suppressAutoSave" to suppressAutoSave,
                    "restoringVoiceSelections" to restoringVoiceSelections,
                    "blockVoiceSelectionCallbacksUntilMs" to blockVoiceSelectionCallbacksUntilMs,
                    "blockTakeawaysVoicePersistUntilMs" to blockTakeawaysVoicePersistUntilMs,
                    "voicesCount" to voices.size,
                    "thread" to Thread.currentThread().name,
                    "ts" to System.currentTimeMillis()
                )

                val condenseVoiceOk = if (voices.isNotEmpty()) {
                    voiceIdToFriendlyLabel(cVoice) == EXPECTED_CONDENSE_VOICE_LABEL
                } else {
                    cVoice == EXPECTED_CONDENSE_VOICE_ID
                }
                val takeawaysVoiceOk = if (voices.isNotEmpty()) {
                    voiceIdToFriendlyLabel(tVoice) == EXPECTED_TAKEAWAYS_VOICE_LABEL
                } else {
                    tVoice == EXPECTED_TAKEAWAYS_VOICE_ID
                }
                val condenseLocaleOk = cLoc == EXPECTED_CONDENSE_LOCALE
                val takeawaysLocaleOk = tLoc == EXPECTED_TAKEAWAYS_LOCALE

                val marker = when {
                    !condenseVoiceOk -> "NOT TONY"
                    !takeawaysVoiceOk -> "NOT OLIVER"
                    !condenseLocaleOk -> "NOT en-US"
                    !takeawaysLocaleOk -> "NOT en-GB"
                    else -> "UNEXPECTED"
                }
                extras["marker"] = marker

                sentryErrorMessage(marker, extras)
                sentryErrorWithStack(marker, extras)
            }
        } catch (e: Exception) {
            sentryErrorWithStack("INVARIANT_CHECK_FAILED:$where", mapOf("error" to (e.message ?: "")))
        }
    }

    private fun prefsGetStringLogged(prefs: android.content.SharedPreferences, key: String, def: String? = null, where: String): String? {
        val v = prefs.getString(key, def)
        sentryBreadcrumb("prefs:read:string", mapOf("where" to where, "key" to key, "value" to v))
        assertExpectedInvariant("prefs:read:$where:$key")
        return v
    }

    private fun prefsGetIntLogged(prefs: android.content.SharedPreferences, key: String, def: Int, where: String): Int {
        val v = prefs.getInt(key, def)
        sentryBreadcrumb("prefs:read:int", mapOf("where" to where, "key" to key, "value" to v))
        assertExpectedInvariant("prefs:read:$where:$key")
        return v
    }

    private fun prefsGetFloatLogged(prefs: android.content.SharedPreferences, key: String, def: Float, where: String): Float {
        val v = prefs.getFloat(key, def)
        sentryBreadcrumb("prefs:read:float", mapOf("where" to where, "key" to key, "value" to v))
        assertExpectedInvariant("prefs:read:$where:$key")
        return v
    }

    private fun prefsGetBooleanLogged(prefs: android.content.SharedPreferences, key: String, def: Boolean, where: String): Boolean {
        val v = prefs.getBoolean(key, def)
        sentryBreadcrumb("prefs:read:boolean", mapOf("where" to where, "key" to key, "value" to v))
        assertExpectedInvariant("prefs:read:$where:$key")
        return v
    }

    private fun prefsPutStringLogged(prefs: android.content.SharedPreferences, key: String, value: String?, where: String) {
        sentryBreadcrumb("prefs:write:string", mapOf("where" to where, "key" to key, "value" to value))
        prefs.edit().putString(key, value).apply()
        assertExpectedInvariant("prefs:write:$where:$key")
    }

    private suspend fun apiLog(serverUrl: String, event: String, data: Map<String, Any?> = emptyMap()) {
        try {
            val payload = mutableMapOf<String, Any?>(
                "source" to "android",
                "event" to event,
                "ts" to System.currentTimeMillis()
            )
            payload.putAll(data)

            withContext(Dispatchers.IO) {
                apiLogPost(serverUrl, payload)
            }
        } catch (_: Exception) {
        }
    }

    // -------------------------------------------------------------------------
    // Playback
    // -------------------------------------------------------------------------

    private fun toAbsoluteUrl(serverBaseUrl: String, maybeRelative: String?): String? {
        if (maybeRelative.isNullOrBlank()) return null
        return try {
            URL(URL(if (serverBaseUrl.endsWith("/")) serverBaseUrl else "$serverBaseUrl/"), maybeRelative).toString()
        } catch (e: Exception) {
            maybeRelative
        }
    }

    private suspend fun firstArtifactUrls(jobId: String): Pair<String?, String?> {
        val api = createApi()
        val baseUrl = getServerUrl()
        val artifacts = api.getArtifacts(jobId).artifacts
        val first = artifacts.firstOrNull()
        val renderAbs = toAbsoluteUrl(baseUrl, first?.render_url)
        val rawAbs = toAbsoluteUrl(baseUrl, first?.raw_url)
        return Pair(renderAbs, rawAbs)
    }

    private fun openCurrentResult(jobId: String) {
        lifecycleScope.launch {
            try {
                val (renderUrl, _) = firstArtifactUrls(jobId)
                if (renderUrl.isNullOrBlank()) {
                    Toast.makeText(this@MainActivity, "No render URL available", Toast.LENGTH_SHORT).show()
                    return@launch
                }
                val intent = Intent(Intent.ACTION_VIEW).apply {
                    data = Uri.parse(renderUrl)
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                startActivity(intent)
            } catch (e: Exception) {
                Sentry.captureException(e)
                val msg = if (currentOutputFormat == "text") {
                    "No browser found."
                } else {
                    "No media player found. Please install a media player app."
                }
                Toast.makeText(this@MainActivity, msg, Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun shareCurrentResult(jobId: String) {
        lifecycleScope.launch {
            try {
                val (renderUrl, _) = firstArtifactUrls(jobId)
                if (renderUrl.isNullOrBlank()) {
                    Toast.makeText(this@MainActivity, "No share link available", Toast.LENGTH_SHORT).show()
                    return@launch
                }
                val intent = Intent(Intent.ACTION_SEND).apply {
                    type = "text/plain"
                    putExtra(Intent.EXTRA_TEXT, renderUrl)
                }
                startActivity(Intent.createChooser(intent, "Share link"))
            } catch (e: Exception) {
                Sentry.captureException(e)
                Toast.makeText(this@MainActivity, "Failed to get share link", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun openRecentJob(job: RecentJob) {
        lifecycleScope.launch {
            try {
                val artifacts = ConciserApi
                    .createService(job.serverUrl, ClientIdentity.getOrCreate(this@MainActivity))
                    .getArtifacts(job.jobId)
                    .artifacts
                val renderUrl = artifacts.firstOrNull()?.render_url
                val abs = toAbsoluteUrl(job.serverUrl, renderUrl)
                if (abs.isNullOrBlank()) {
                    Toast.makeText(this@MainActivity, "No render URL available", Toast.LENGTH_SHORT).show()
                    return@launch
                }
                val intent = Intent(Intent.ACTION_VIEW).apply {
                    data = Uri.parse(abs)
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                startActivity(intent)
            } catch (e: Exception) {
                Sentry.captureException(e)
                val msg = if (job.outputFormat == "text") "No browser found." else "No media player found."
                Toast.makeText(this@MainActivity, msg, Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun apiLogPost(serverUrl: String, payload: Map<String, Any?>) {
        try {
            val json = Gson().toJson(payload)
            val request = okhttp3.Request.Builder()
                .url(serverUrl.trimEnd('/') + "/api/log")
                .post(json.toRequestBody("application/json".toMediaType()))
                .build()

            // Use the same client/headers as ConciserApi by reusing its underlying OkHttp isn't exposed;
            // fall back to a plain OkHttp with X-User-Id header for logging.
            val clientId = ClientIdentity.getOrCreate(this)
            val client = okhttp3.OkHttpClient.Builder()
                .connectTimeout(5, java.util.concurrent.TimeUnit.SECONDS)
                .readTimeout(5, java.util.concurrent.TimeUnit.SECONDS)
                .build()
            val reqWithHeader = request.newBuilder().header("X-User-Id", clientId).build()
            client.newCall(reqWithHeader).execute().close()
        } catch (_: Exception) {
        }
    }

    // Mirrors Chrome extension's state model exactly.
    enum class AppState {
        NO_URL,       // No YouTube URL — launched directly, not via Share
        READY,        // URL stored, waiting for user to tap Condense
        SUBMITTING,   // POST to /api/condense in flight
        PROCESSING,   // Polling — server is processing the job
        COMPLETED,    // Job done — player auto-launched; Watch button shown
        ERROR         // Server error or network failure
    }

    private lateinit var binding: ActivityMainBinding
    private var currentState = AppState.NO_URL
    private var currentVideoUrl: String? = null
    private var currentVideoTitle: String? = null
    private var currentJobId: String? = null
    private var currentVideoMode: String = "slideshow"
    private var currentJobType: String = "condense"  // "condense" or "takeaways"
    private var currentOutputFormat: String = "video"  // "video", "audio", "text"
    private var eventSource: EventSource? = null  // SSE connection for job updates
    private var isForeground: Boolean = false
    private var sseReconnectAttempts: Int = 0
    private val SSE_RECONNECT_DELAY_MS: Long = 1000
    private val SSE_MAX_RECONNECT_ATTEMPTS: Int = 3

    private var voices: List<VoiceItem> = emptyList()
    private var strategies: List<StrategyItem> = emptyList()

    private data class VoiceOption(
        val id: String,
        val displayName: String,
        val voice: VoiceItem
    )

    private val videoModeValues = listOf("slideshow", "text")
    private val videoModeLabels = listOf("🎞️+🗣️", "📄")

    // Takeaways mode
    private var appMode: String = "condense" // "condense" or "takeaways"
    private val takeawaysTopValues = listOf("3", "5", "10", "auto")
    private val prefsName = "nbj_prefs"

    private val KEY_CONDENSE_LOCALE = "condense_locale"
    private val KEY_CONDENSE_VOICE = "condense_voice"
    private val KEY_TAKEAWAYS_LOCALE = "takeaways_locale"
    private val KEY_TAKEAWAYS_VOICE = "takeaways_voice"
    private val KEY_TAKEAWAYS_FORMAT = "takeaways_format"
    private var suppressAutoSave = false
    private var restoringVoiceSelections = false
    private var blockVoiceSelectionCallbacksUntilMs = 0L
    private var blockTakeawaysVoicePersistUntilMs = 0L

    private fun resetReadyStateDueToSettingsChange(source: String) {
        if (suppressAutoSave || restoringVoiceSelections) return
        if (currentState == AppState.NO_URL || currentState == AppState.READY) return
        sentryBreadcrumb("ui:settings_changed_reset_state", mapOf("source" to source, "from" to currentState.name))
        eventSource?.cancel()
        currentJobId = null
        updateUI(if (currentVideoUrl != null) AppState.READY else AppState.NO_URL)
    }

    private var condenseLocaleTouched = false
    private var condenseVoiceTouched = false
    private var takeawaysLocaleTouched = false
    private var takeawaysVoiceTouched = false

    private fun migratePrefsKeysIfNeeded() {
        val prefs = getSharedPreferences(prefsName, Context.MODE_PRIVATE)
        val editor = prefs.edit()
        var changed = false

        sentryBreadcrumb(
            "prefs:migrate:start",
            mapOf(
                "has_locale" to prefs.contains("locale"),
                "has_voice" to prefs.contains("voice"),
                "has_condense_locale" to prefs.contains(KEY_CONDENSE_LOCALE),
                "has_condense_voice" to prefs.contains(KEY_CONDENSE_VOICE),
                "has_takeaways_locale" to prefs.contains(KEY_TAKEAWAYS_LOCALE),
                "has_takeaways_voice" to prefs.contains(KEY_TAKEAWAYS_VOICE),
                "has_takeaways_format" to prefs.contains(KEY_TAKEAWAYS_FORMAT)
            )
        )

        if (!prefs.contains(KEY_CONDENSE_LOCALE) && prefs.contains("locale")) {
            editor.putString(KEY_CONDENSE_LOCALE, prefs.getString("locale", null))
            changed = true
        }
        if (!prefs.contains(KEY_CONDENSE_VOICE) && prefs.contains("voice")) {
            editor.putString(KEY_CONDENSE_VOICE, prefs.getString("voice", null))
            changed = true
        }

        if (!prefs.contains(KEY_TAKEAWAYS_LOCALE) && prefs.contains("takeaways_locale")) {
            editor.putString(KEY_TAKEAWAYS_LOCALE, prefs.getString("takeaways_locale", null))
            changed = true
        }
        if (!prefs.contains(KEY_TAKEAWAYS_VOICE) && prefs.contains("takeaways_voice")) {
            editor.putString(KEY_TAKEAWAYS_VOICE, prefs.getString("takeaways_voice", null))
            changed = true
        }
        if (!prefs.contains(KEY_TAKEAWAYS_FORMAT) && prefs.contains("takeaways_format")) {
            editor.putString(KEY_TAKEAWAYS_FORMAT, prefs.getString("takeaways_format", null))
            changed = true
        }

        if (changed) {
            editor.apply()
            sentryBreadcrumb("prefs:migrate:applied")
            assertExpectedInvariant("prefs:migrate:applied")
        } else {
            sentryBreadcrumb("prefs:migrate:no_changes")
            assertExpectedInvariant("prefs:migrate:no_changes")
        }
    }

    // -------------------------------------------------------------------------
    // Minimal stubs to keep compilation working after API migration
    // -------------------------------------------------------------------------

    private fun setupSettingsControls() {
        // Keep this wiring minimal but functional: persist key settings to SharedPreferences.
        val prefs = getSharedPreferences(prefsName, Context.MODE_PRIVATE)

        sentryBreadcrumb(
            "ui:setupSettingsControls",
            mapOf(
                "spinnerLocale_id" to binding.spinnerLocale.id,
                "spinnerVoice_id" to binding.spinnerVoice.id,
                "spinnerTakeawaysLocale_id" to binding.spinnerTakeawaysLocale.id,
                "spinnerTakeawaysVoice_id" to binding.spinnerTakeawaysVoice.id
            )
        )

        binding.spinnerLocale.setOnTouchListener { _, _ ->
            condenseLocaleTouched = true
            false
        }
        binding.spinnerVoice.setOnTouchListener { _, _ ->
            condenseVoiceTouched = true
            false
        }
        binding.spinnerTakeawaysLocale.setOnTouchListener { _, _ ->
            takeawaysLocaleTouched = true
            false
        }
        binding.spinnerTakeawaysVoice.setOnTouchListener { _, _ ->
            takeawaysVoiceTouched = true
            false
        }

        // Aggressiveness
        binding.seekbarAggressiveness.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                val level = progress + 1
                binding.tvAggressivenessValue.text = level.toString()
                updateStrategyDesc(level)
                if (!fromUser) return
                if (suppressAutoSave || restoringVoiceSelections) return
                prefs.edit().putInt("aggressiveness", level).apply()
                resetReadyStateDueToSettingsChange("condense_aggressiveness")
            }

            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) {}
        })

        // Speech speed
        binding.seekbarSpeechSpeed.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                // progress is 0..110 representing 0.00x..1.10x? Existing UI expects 1.10x default.
                // Keep compatible: store float in [0.00, 2.10] would be weird; instead map 0..110 to 0.0..2.10 is unknown.
                // Use simple mapping to [0.50, 1.60] with 1.10 at 60.
                val rawSpeed = 0.50f + (progress / 100f) * 1.10f
                val speed = (rawSpeed / 0.05f).roundToInt() * 0.05f
                binding.tvSpeechSpeedValue.text = String.format(Locale.US, "%.2fx", speed)
                if (!fromUser) return
                if (suppressAutoSave || restoringVoiceSelections) return
                prefs.edit().putFloat("speech_speed", speed).apply()
                resetReadyStateDueToSettingsChange("condense_speech_speed")
            }

            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) {}
        })

        // Prepend intro
        binding.switchPrependIntro.setOnCheckedChangeListener { _, isChecked ->
            if (suppressAutoSave || restoringVoiceSelections) return@setOnCheckedChangeListener
            prefs.edit().putBoolean("prepend_intro", isChecked).apply()
            resetReadyStateDueToSettingsChange("condense_prepend_intro")
        }

        fun updateCondenseVoiceVisibility(videoMode: String) {
            binding.layoutCondenseVoice.isVisible = (videoMode != "text")
        }

        // Video mode (condense)
        binding.toggleVideoMode.addOnButtonCheckedListener { _, checkedId, isChecked ->
            if (!isChecked) return@addOnButtonCheckedListener
            val value = when (checkedId) {
                binding.btnVideoModeText.id -> "text"
                binding.btnVideoModeSlideshow.id -> "slideshow"
                else -> "slideshow"
            }
            updateCondenseVoiceVisibility(value)
            if (suppressAutoSave || restoringVoiceSelections) return@addOnButtonCheckedListener
            prefs.edit().putString("video_mode", value).apply()
            resetReadyStateDueToSettingsChange("condense_video_mode")
        }

        // Restore saved video mode selection
        suppressAutoSave = true
        val savedVideoMode = prefs.getString("video_mode", "slideshow") ?: "slideshow"
        when (savedVideoMode) {
            "text" -> binding.toggleVideoMode.check(binding.btnVideoModeText.id)
            else -> binding.toggleVideoMode.check(binding.btnVideoModeSlideshow.id)
        }
        updateCondenseVoiceVisibility(savedVideoMode)
        suppressAutoSave = false

        // Takeaways controls (buttons)
        fun updateTakeawaysVoiceVisibility(formatValue: String) {
            binding.layoutTakeawaysVoice.isVisible = (formatValue == "audio")
        }

        fun readTakeawaysTopValueFromUI(): String {
            return when (binding.toggleTakeawaysTop.checkedButtonId) {
                binding.btnTakeawaysTop3.id -> "3"
                binding.btnTakeawaysTop5.id -> "5"
                binding.btnTakeawaysTop10.id -> "10"
                binding.btnTakeawaysTopAuto.id -> "auto"
                else -> "auto"
            }
        }

        fun readTakeawaysFormatValueFromUI(): String = "text"

        binding.toggleTakeawaysTop.addOnButtonCheckedListener { _, checkedId, isChecked ->
            if (!isChecked) return@addOnButtonCheckedListener
            if (suppressAutoSave || restoringVoiceSelections) return@addOnButtonCheckedListener
            val value = when (checkedId) {
                binding.btnTakeawaysTop3.id -> "3"
                binding.btnTakeawaysTop5.id -> "5"
                binding.btnTakeawaysTop10.id -> "10"
                binding.btnTakeawaysTopAuto.id -> "auto"
                else -> "auto"
            }
            prefs.edit().putString("takeaways_top", value).apply()
            resetReadyStateDueToSettingsChange("takeaways_top")
        }


        // Restore saved takeaways selections
        suppressAutoSave = true
        val savedTop = prefs.getString("takeaways_top", "auto") ?: "auto"
        when (savedTop) {
            "3" -> binding.toggleTakeawaysTop.check(binding.btnTakeawaysTop3.id)
            "5" -> binding.toggleTakeawaysTop.check(binding.btnTakeawaysTop5.id)
            "10" -> binding.toggleTakeawaysTop.check(binding.btnTakeawaysTop10.id)
            else -> binding.toggleTakeawaysTop.check(binding.btnTakeawaysTopAuto.id)
        }
        suppressAutoSave = false

        // Persist voice selection changes.
        val voiceListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                sentryBreadcrumb(
                    "ui:condense_voice:onItemSelected",
                    mapOf(
                        "position" to position,
                        "id" to id,
                        "fromUser_blocked" to (suppressAutoSave || restoringVoiceSelections),
                        "parentClass" to (parent?.javaClass?.name ?: ""),
                        "selectedText" to (parent?.getItemAtPosition(position)?.toString())
                    )
                )
                if (suppressAutoSave || restoringVoiceSelections) return
                if (!condenseVoiceTouched) return
                val selectedLocale = binding.spinnerLocale.selectedItem as? String
                val voiceId = getSelectedVoiceOption(binding.spinnerVoice, selectedLocale)?.id ?: return
                if (isPlaceholderLocale(selectedLocale) || voiceId.isBlank() || voiceId == "Loading...") {
                    blockedPrefWrite(
                        "BLOCKED_WRITE_CONDENSE_VOICE",
                        "ui:condense_voice:onItemSelected",
                        mapOf("selectedLocale" to selectedLocale, "voiceId" to voiceId)
                    )
                    return
                }
                prefs.edit().putString(KEY_CONDENSE_VOICE, voiceId).apply()
                condenseVoiceTouched = false
                resetReadyStateDueToSettingsChange("condense_voice")
                sentryBreadcrumb(
                    "prefs:write:condense_voice",
                    mapOf(
                        "key" to KEY_CONDENSE_VOICE,
                        "value" to voiceId,
                        "selectedLocale" to selectedLocale
                    )
                )
            }

            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }
        binding.spinnerVoice.onItemSelectedListener = voiceListener

        val takeawaysVoiceListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                // Don't save while we're restoring, but allow normal user selection even if
                // suppressAutoSave is being used for unrelated bulk UI updates.
                sentryBreadcrumb(
                    "ui:takeaways_voice:onItemSelected",
                    mapOf(
                        "position" to position,
                        "id" to id,
                        "blocked_restoring" to restoringVoiceSelections,
                        "blocked_time" to (SystemClock.elapsedRealtime() < blockTakeawaysVoicePersistUntilMs),
                        "blockTakeawaysVoicePersistUntilMs" to blockTakeawaysVoicePersistUntilMs,
                        "nowMs" to SystemClock.elapsedRealtime(),
                        "selectedText" to (parent?.getItemAtPosition(position)?.toString())
                    )
                )
                if (restoringVoiceSelections) return
                if (SystemClock.elapsedRealtime() < blockTakeawaysVoicePersistUntilMs) return
                if (!takeawaysVoiceTouched) return
                val selectedLocale = binding.spinnerTakeawaysLocale.selectedItem as? String
                val voiceId = getSelectedVoiceOption(binding.spinnerTakeawaysVoice, selectedLocale)?.id ?: return
                if (isPlaceholderLocale(selectedLocale) || voiceId.isBlank() || voiceId == "Loading...") {
                    blockedPrefWrite(
                        "BLOCKED_WRITE_TAKEAWAYS_VOICE",
                        "ui:takeaways_voice:onItemSelected",
                        mapOf("selectedLocale" to selectedLocale, "voiceId" to voiceId)
                    )
                    return
                }
                prefs.edit().putString(KEY_TAKEAWAYS_VOICE, voiceId).apply()
                takeawaysVoiceTouched = false
                resetReadyStateDueToSettingsChange("takeaways_voice")
                sentryBreadcrumb(
                    "prefs:write:takeaways_voice",
                    mapOf(
                        "key" to KEY_TAKEAWAYS_VOICE,
                        "value" to voiceId,
                        "selectedLocale" to selectedLocale
                    )
                )
                lifecycleScope.launch {
                    apiLog(
                        getServerUrl(),
                        "takeaways_voice_changed",
                        mapOf("locale" to selectedLocale, "voice" to voiceId)
                    )
                }
            }

            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }
        binding.spinnerTakeawaysVoice.onItemSelectedListener = takeawaysVoiceListener

        // Persist locale selections.
        binding.spinnerLocale.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                sentryBreadcrumb(
                    "ui:condense_locale:onItemSelected",
                    mapOf(
                        "position" to position,
                        "blocked_time" to (SystemClock.elapsedRealtime() < blockVoiceSelectionCallbacksUntilMs),
                        "blocked_flags" to (suppressAutoSave || restoringVoiceSelections),
                        "selectedLocale" to (parent?.getItemAtPosition(position)?.toString())
                    )
                )
                if (SystemClock.elapsedRealtime() < blockVoiceSelectionCallbacksUntilMs) return
                val selectedLocale = parent?.getItemAtPosition(position)?.toString() ?: return
                if (suppressAutoSave || restoringVoiceSelections) return
                if (!condenseLocaleTouched) return
                if (isPlaceholderLocale(selectedLocale)) {
                    blockedPrefWrite(
                        "BLOCKED_WRITE_CONDENSE_LOCALE",
                        "ui:condense_locale:onItemSelected",
                        mapOf("selectedLocale" to selectedLocale, "position" to position)
                    )
                    return
                }
                prefs.edit().putString(KEY_CONDENSE_LOCALE, selectedLocale).apply()
                condenseLocaleTouched = false
                resetReadyStateDueToSettingsChange("condense_locale")
                sentryBreadcrumb(
                    "prefs:write:condense_locale",
                    mapOf("key" to KEY_CONDENSE_LOCALE, "value" to selectedLocale)
                )
            }

            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }
        binding.spinnerTakeawaysLocale.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                sentryBreadcrumb(
                    "ui:takeaways_locale:onItemSelected",
                    mapOf(
                        "position" to position,
                        "blocked_time" to (SystemClock.elapsedRealtime() < blockVoiceSelectionCallbacksUntilMs),
                        "blocked_restoring" to restoringVoiceSelections,
                        "selectedLocale" to (parent?.getItemAtPosition(position)?.toString())
                    )
                )
                if (SystemClock.elapsedRealtime() < blockVoiceSelectionCallbacksUntilMs) return
                val selectedLocale = parent?.getItemAtPosition(position)?.toString() ?: return
                if (restoringVoiceSelections) return
                if (!takeawaysLocaleTouched) {
                    populateTakeawaysVoiceSpinnerForLocale(selectedLocale)
                    return
                }
                if (isPlaceholderLocale(selectedLocale)) {
                    blockedPrefWrite(
                        "BLOCKED_WRITE_TAKEAWAYS_LOCALE",
                        "ui:takeaways_locale:onItemSelected",
                        mapOf("selectedLocale" to selectedLocale, "position" to position)
                    )
                    return
                }
                prefs.edit().putString(KEY_TAKEAWAYS_LOCALE, selectedLocale).apply()
                takeawaysLocaleTouched = false

                resetReadyStateDueToSettingsChange("takeaways_locale")

                sentryBreadcrumb(
                    "prefs:write:takeaways_locale",
                    mapOf("key" to KEY_TAKEAWAYS_LOCALE, "value" to selectedLocale)
                )

                // Also refresh voice list immediately when locale changes.
                populateTakeawaysVoiceSpinnerForLocale(selectedLocale)
                lifecycleScope.launch {
                    apiLog(getServerUrl(), "takeaways_locale_changed", mapOf("locale" to selectedLocale))
                }
            }

            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }
    }

    private fun loadSettingsToUI() {
        val prefs = getSharedPreferences(prefsName, Context.MODE_PRIVATE)

        sentryBreadcrumb("settings:loadSettingsToUI:start")

        suppressAutoSave = true
        try {
            val aggressiveness = prefsGetIntLogged(prefs, "aggressiveness", 5, "loadSettingsToUI").coerceIn(1, 10)
            binding.seekbarAggressiveness.progress = aggressiveness - 1
            binding.tvAggressivenessValue.text = aggressiveness.toString()

            val speechSpeed = prefsGetFloatLogged(prefs, "speech_speed", 1.00f, "loadSettingsToUI")
            val quantSpeechSpeed = (speechSpeed / 0.05f).roundToInt() * 0.05f
            binding.tvSpeechSpeedValue.text = String.format(Locale.US, "%.2fx", quantSpeechSpeed)
            // Map back to progress using the same mapping used in listener.
            val p = (((quantSpeechSpeed - 0.50f) / 1.10f) * 100f).toInt().coerceIn(0, 110)
            binding.seekbarSpeechSpeed.progress = p

            binding.switchPrependIntro.isChecked = prefsGetBooleanLogged(prefs, "prepend_intro", false, "loadSettingsToUI")

            val videoMode = prefsGetStringLogged(prefs, "video_mode", "slideshow", "loadSettingsToUI") ?: "slideshow"
            when (videoMode) {
                "text" -> binding.toggleVideoMode.check(binding.btnVideoModeText.id)
                else -> binding.toggleVideoMode.check(binding.btnVideoModeSlideshow.id)
            }

            val takeawaysTop = prefsGetStringLogged(prefs, "takeaways_top", "auto", "loadSettingsToUI") ?: "auto"
            when (takeawaysTop) {
                "3" -> binding.toggleTakeawaysTop.check(binding.btnTakeawaysTop3.id)
                "5" -> binding.toggleTakeawaysTop.check(binding.btnTakeawaysTop5.id)
                "10" -> binding.toggleTakeawaysTop.check(binding.btnTakeawaysTop10.id)
                else -> binding.toggleTakeawaysTop.check(binding.btnTakeawaysTopAuto.id)
            }

            binding.layoutTakeawaysVoice.isVisible = false
        } finally {
            suppressAutoSave = false
            sentryBreadcrumb("settings:loadSettingsToUI:end")
            assertExpectedInvariant("loadSettingsToUI:end")
        }
    }

    private fun populateLocaleSpinners() {
        populateCondenseLocaleSpinner()
        populateTakeawaysLocaleSpinner()
    }

    private fun availableLocaleItems(): List<String> {
        val localeSet = TreeSet<String>(String.CASE_INSENSITIVE_ORDER)
        for (v in voices) {
            val loc = v.locale.trim()
            if (loc.isNotBlank()) localeSet.add(loc)
        }
        return if (localeSet.isNotEmpty()) localeSet.toList() else listOf(Locale.getDefault().toLanguageTag())
    }

    private fun defaultLocaleIndex(localeItems: List<String>): Int {
        val deviceTag = Locale.getDefault().toLanguageTag()
        val exactIdx = localeItems.indexOfFirst { it.equals(deviceTag, ignoreCase = true) }
        val langOnly = deviceTag.substringBefore('-')
        val langIdx = localeItems.indexOfFirst { it.substringBefore('-').equals(langOnly, ignoreCase = true) }
        return when {
            exactIdx >= 0 -> exactIdx
            langIdx >= 0 -> langIdx
            else -> 0
        }
    }

    private fun populateCondenseLocaleSpinner() {
        sentryBreadcrumb("ui:populateCondenseLocaleSpinner:start")
        val localeItems = availableLocaleItems()
        val adapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, localeItems)
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)

        suppressAutoSave = true
        try {
            binding.spinnerLocale.adapter = adapter

            val voicePlaceholder = ArrayAdapter(this, android.R.layout.simple_spinner_item, listOf("Select voice"))
            voicePlaceholder.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
            binding.spinnerVoice.adapter = voicePlaceholder

            val idx = defaultLocaleIndex(localeItems)
            binding.spinnerLocale.setSelection(idx)

            val locale = binding.spinnerLocale.selectedItem?.toString()
            if (!locale.isNullOrBlank()) {
                populateCondenseVoiceSpinnerForLocale(locale)
            }
        } finally {
            suppressAutoSave = false
            sentryBreadcrumb(
                "ui:populateCondenseLocaleSpinner:end",
                mapOf("localeItemsCount" to localeItems.size, "selected" to binding.spinnerLocale.selectedItem?.toString())
            )
            assertExpectedInvariant("populateCondenseLocaleSpinner:end")
        }
    }

    private fun populateTakeawaysLocaleSpinner() {
        sentryBreadcrumb("ui:populateTakeawaysLocaleSpinner:start")
        val localeItems = availableLocaleItems()
        val adapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, localeItems)
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)

        suppressAutoSave = true
        try {
            binding.spinnerTakeawaysLocale.adapter = adapter

            val voicePlaceholder = ArrayAdapter(this, android.R.layout.simple_spinner_item, listOf("Select voice"))
            voicePlaceholder.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
            binding.spinnerTakeawaysVoice.adapter = voicePlaceholder

            val idx = defaultLocaleIndex(localeItems)
            binding.spinnerTakeawaysLocale.setSelection(idx)

            val locale = binding.spinnerTakeawaysLocale.selectedItem?.toString()
            if (!locale.isNullOrBlank()) {
                populateTakeawaysVoiceSpinnerForLocale(locale)
            }
        } finally {
            suppressAutoSave = false
            sentryBreadcrumb(
                "ui:populateTakeawaysLocaleSpinner:end",
                mapOf("localeItemsCount" to localeItems.size, "selected" to binding.spinnerTakeawaysLocale.selectedItem?.toString())
            )
            assertExpectedInvariant("populateTakeawaysLocaleSpinner:end")
        }
    }

    private fun populateCondenseVoiceSpinnerForLocale(localeTag: String) {
        sentryBreadcrumb("ui:populateCondenseVoiceSpinnerForLocale:start", mapOf("localeTag" to localeTag))
        val options = voices
            .filter { it.locale.equals(localeTag, ignoreCase = true) }
            .map {
                val genderSuffix = when (it.gender?.trim()?.lowercase()) {
                    "male" -> " (Male)"
                    "female" -> " (Female)"
                    null, "" -> ""
                    else -> " (${it.gender.trim()})"
                }
                VoiceOption(
                    id = it.name,
                    displayName = (it.friendly_name.ifBlank { it.name }) + genderSuffix,
                    voice = it
                )
            }
            .sortedBy { it.displayName.lowercase() }

        val adapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, options.map { it.displayName })
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        binding.spinnerVoice.adapter = adapter

        sentryBreadcrumb(
            "ui:populateCondenseVoiceSpinnerForLocale:end",
            mapOf("localeTag" to localeTag, "optionsCount" to options.size)
        )
        assertExpectedInvariant("populateCondenseVoiceSpinnerForLocale:end")
    }

    private fun populateTakeawaysVoiceSpinnerForLocale(localeTag: String) {
        sentryBreadcrumb("ui:populateTakeawaysVoiceSpinnerForLocale:start", mapOf("localeTag" to localeTag))
        blockTakeawaysVoicePersistUntilMs = SystemClock.elapsedRealtime() + 1500L
        val options = voices
            .filter { it.locale.equals(localeTag, ignoreCase = true) }
            .map {
                val genderSuffix = when (it.gender?.trim()?.lowercase()) {
                    "male" -> " (Male)"
                    "female" -> " (Female)"
                    null, "" -> ""
                    else -> " (${it.gender.trim()})"
                }
                VoiceOption(
                    id = it.name,
                    displayName = (it.friendly_name.ifBlank { it.name }) + genderSuffix,
                    voice = it
                )
            }
            .sortedBy { it.displayName.lowercase() }

        val adapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, options.map { it.displayName })
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        binding.spinnerTakeawaysVoice.adapter = adapter

        sentryBreadcrumb(
            "ui:populateTakeawaysVoiceSpinnerForLocale:end",
            mapOf(
                "localeTag" to localeTag,
                "optionsCount" to options.size,
                "blockTakeawaysVoicePersistUntilMs" to blockTakeawaysVoicePersistUntilMs
            )
        )
        assertExpectedInvariant("populateTakeawaysVoiceSpinnerForLocale:end")
    }

    private fun restoreLocaleAndVoiceSelection(
        localeSpinner: android.widget.Spinner,
        voiceSpinner: android.widget.Spinner,
        savedLocale: String?,
        savedVoice: String?
    ) {
        // Best-effort restore: if options exist, try to select saved values.
        try {
            sentryBreadcrumb(
                "ui:restoreLocaleAndVoiceSelection:start",
                mapOf(
                    "savedLocale" to savedLocale,
                    "savedVoice" to savedVoice,
                    "isTakeaways" to (voiceSpinner === binding.spinnerTakeawaysVoice)
                )
            )
            if (!savedLocale.isNullOrBlank()) {
                val adapter = localeSpinner.adapter
                for (i in 0 until adapter.count) {
                    if (adapter.getItem(i)?.toString() == savedLocale) {
                        localeSpinner.setSelection(i)
                        break
                    }
                }
            }

            // Always populate the voice spinner based on the currently selected locale.
            val selectedLocale = localeSpinner.selectedItem?.toString()
            if (!selectedLocale.isNullOrBlank()) {
                if (voiceSpinner === binding.spinnerTakeawaysVoice) {
                    blockTakeawaysVoicePersistUntilMs = SystemClock.elapsedRealtime() + 2000L
                }
                if (voiceSpinner === binding.spinnerTakeawaysVoice) {
                    populateTakeawaysVoiceSpinnerForLocale(selectedLocale)
                } else {
                    populateCondenseVoiceSpinnerForLocale(selectedLocale)
                }

                if (!savedVoice.isNullOrBlank()) {
                    val options = voices
                        .filter { it.locale.equals(selectedLocale, ignoreCase = true) }
                        .map {
                            val genderSuffix = when (it.gender?.trim()?.lowercase()) {
                                "male" -> " (Male)"
                                "female" -> " (Female)"
                                null, "" -> ""
                                else -> " (${it.gender.trim()})"
                            }
                            VoiceOption(
                                id = it.name,
                                displayName = (it.friendly_name.ifBlank { it.name }) + genderSuffix,
                                voice = it
                            )
                        }
                        .sortedBy { it.displayName.lowercase() }
                    val pos = options.indexOfFirst { it.id == savedVoice }
                    if (pos >= 0) {
                        voiceSpinner.setSelection(pos)
                    }
                }
            }

            sentryBreadcrumb(
                "ui:restoreLocaleAndVoiceSelection:end",
                mapOf(
                    "selectedLocale" to localeSpinner.selectedItem?.toString(),
                    "selectedVoice" to voiceSpinner.selectedItem?.toString(),
                    "selectedVoicePos" to voiceSpinner.selectedItemPosition,
                    "isTakeaways" to (voiceSpinner === binding.spinnerTakeawaysVoice)
                )
            )
            assertExpectedInvariant("restoreLocaleAndVoiceSelection:end")
        } catch (_: Exception) {
            sentryErrorWithStack(
                "ui:restoreLocaleAndVoiceSelection:exception",
                mapOf(
                    "savedLocale" to savedLocale,
                    "savedVoice" to savedVoice,
                    "isTakeaways" to (voiceSpinner === binding.spinnerTakeawaysVoice)
                )
            )
        }
    }

    private fun updateStrategyDesc(level: Int) {
        // Best-effort: find matching strategy and show description.
        val match = strategies.firstOrNull { it.level == level }
        binding.tvStrategyDesc.text = match?.description ?: ""
    }

    private fun refreshRecentJobsUI() {
        lifecycleScope.launch {
            try {
                val api = createApi()
                val serverUrl = getServerUrl()

                val jobs = withContext(Dispatchers.IO) {
                    api.getJobs().jobs
                }

                setServerCallStatus(true)

                val sorted = jobs
                    .filter { it.status != "error" }
                    .sortedByDescending { parseIsoToEpochMs(it.created_at) }
                    .take(10)

                renderRecentJobs(sorted, serverUrl)
            } catch (e: Exception) {
                setServerCallStatus(false)
                Sentry.captureException(e)
            }
        }
    }

    private fun renderRecentJobs(jobs: List<JobResponse>, serverUrl: String) {
        val container = binding.layoutRecentJobs
        container.removeAllViews()

        if (jobs.isEmpty()) {
            binding.tvRecentJobsHeader.visibility = View.GONE
            return
        }
        binding.tvRecentJobsHeader.visibility = View.VISIBLE

        val dateFormat = SimpleDateFormat("MMM d, h:mm a", Locale.US)

        for (job in jobs) {
            val createdAt = parseIsoToEpochMs(job.created_at)
            val displayTitle = getRecentJobDisplayTitle(job)
            val badge = getRecentJobBadge(job)
            val isCompleted = job.status == "completed"

            val swipeContainer = android.widget.FrameLayout(this).apply {
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                )
            }

            val deleteBg = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                setBackgroundColor(Color.parseColor("#d32f2f"))
                gravity = Gravity.CENTER_VERTICAL
                layoutParams = android.widget.FrameLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.MATCH_PARENT
                )
            }

            val trash = ImageView(this).apply {
                setImageResource(android.R.drawable.ic_menu_delete)
                // User requested red trash icon.
                setColorFilter(Color.parseColor("#b71c1c"))
            }
            val density = resources.displayMetrics.density
            val trashLp = LinearLayout.LayoutParams((18 * density).toInt(), (18 * density).toInt()).apply {
                marginStart = (16 * density).toInt()
                marginEnd = (16 * density).toInt()
            }
            deleteBg.addView(trash, trashLp)

            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(0, (10 * density).toInt(), 0, (10 * density).toInt())
                isClickable = isCompleted
                isFocusable = isCompleted
                if (isCompleted) {
                    val tv = TypedValue()
                    context.theme.resolveAttribute(android.R.attr.selectableItemBackground, tv, true)
                    setBackgroundResource(tv.resourceId)
                    setOnClickListener { openRecentServerJob(job, serverUrl) }
                }
            }

            // Swipe gesture applies to the row content and reveals deleteBg beneath.
            attachSwipeToDelete(row, deleteBg, job, serverUrl)

            val badgeView = TextView(this).apply {
                text = badge.badgeText
                setTextSize(TypedValue.COMPLEX_UNIT_SP, if (badge.badgeText.any { it.isHighSurrogate() }) 14f else 9f)
                setTypeface(null, Typeface.BOLD)
                setTextColor(0xFFFFFFFF.toInt())
                setBackgroundColor(if (isCompleted) badge.bgColor else 0xFFBDBDBD.toInt())
                setPadding((4 * density).toInt(), (2 * density).toInt(), (4 * density).toInt(), (2 * density).toInt())
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.WRAP_CONTENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).also { it.marginEnd = (8 * density).toInt() }
            }

            val textCol = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            }

            val titleView = TextView(this).apply {
                text = displayTitle
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
                setTextColor(if (isCompleted) 0xFF212121.toInt() else 0xFF9E9E9E.toInt())
                maxLines = 1
                ellipsize = android.text.TextUtils.TruncateAt.END
            }

            val subtitleText = if (!isCompleted) {
                val label = if (job.status == "queued") "queued…" else "processing…"
                val time = createdAt?.let { dateFormat.format(Date(it)) }
                if (time != null) "$label  ·  $time" else label
            } else {
                createdAt?.let { dateFormat.format(Date(it)) } ?: ""
            }
            val timeView = TextView(this).apply {
                text = subtitleText
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 10f)
                setTextColor(0xFF757575.toInt())
            }

            textCol.addView(titleView)
            textCol.addView(timeView)

            row.addView(badgeView)
            row.addView(textCol)

            if (isCompleted) {
                val shareBtn = TextView(this).apply {
                    text = "↗"
                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
                    setTextColor(0xFF9E9E9E.toInt())
                    setPadding((8 * density).toInt(), (2 * density).toInt(), (4 * density).toInt(), (2 * density).toInt())
                    isClickable = true
                    isFocusable = true
                    contentDescription = "Share link"
                    setOnClickListener { v ->
                        v.isEnabled = false
                        lifecycleScope.launch {
                            try {
                                val api = ConciserApi.createService(serverUrl, ClientIdentity.getOrCreate(this@MainActivity))
                                val artifacts = withContext(Dispatchers.IO) {
                                    api.getArtifacts(job.id).artifacts
                                }
                                val renderUrl = artifacts.firstOrNull()?.render_url
                                val abs = toAbsoluteUrl(serverUrl, renderUrl)
                                if (abs.isNullOrBlank()) {
                                    Toast.makeText(this@MainActivity, "No share link available", Toast.LENGTH_SHORT).show()
                                } else {
                                    val intent = Intent(Intent.ACTION_SEND).apply {
                                        type = "text/plain"
                                        putExtra(Intent.EXTRA_TEXT, abs)
                                    }
                                    startActivity(Intent.createChooser(intent, "Share link"))
                                }
                            } catch (e: Exception) {
                                Sentry.captureException(e)
                                Toast.makeText(this@MainActivity, "Failed to get share link", Toast.LENGTH_SHORT).show()
                            } finally {
                                v.isEnabled = true
                            }
                        }
                    }
                }
                row.addView(shareBtn)
            }

            swipeContainer.addView(deleteBg)
            swipeContainer.addView(row)
            container.addView(swipeContainer)

            if (job != jobs.last()) {
                val divider = View(this).apply {
                    layoutParams = LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT,
                        (1 * density).toInt()
                    )
                    setBackgroundColor(0xFF666666.toInt())
                }
                container.addView(divider)
            }
        }
    }

    private fun openRecentServerJob(job: JobResponse, serverUrl: String) {
        lifecycleScope.launch {
            try {
                val api = ConciserApi.createService(serverUrl, ClientIdentity.getOrCreate(this@MainActivity))
                val artifacts = withContext(Dispatchers.IO) {
                    api.getArtifacts(job.id).artifacts
                }
                val renderUrl = artifacts.firstOrNull()?.render_url
                val abs = toAbsoluteUrl(serverUrl, renderUrl)
                if (abs.isNullOrBlank()) {
                    Toast.makeText(this@MainActivity, "No render URL available", Toast.LENGTH_SHORT).show()
                    return@launch
                }
                val intent = Intent(Intent.ACTION_VIEW).apply {
                    data = Uri.parse(abs)
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                startActivity(intent)
            } catch (e: Exception) {
                Sentry.captureException(e)
                Toast.makeText(this@MainActivity, "No browser found.", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun parseIsoToEpochMs(iso: String?): Long? {
        if (iso.isNullOrBlank()) return null
        return try {
            val patterns = listOf(
                "yyyy-MM-dd'T'HH:mm:ss.SSSX",
                "yyyy-MM-dd'T'HH:mm:ssX",
                "yyyy-MM-dd HH:mm:ss",
                "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'",
                "yyyy-MM-dd'T'HH:mm:ss'Z'"
            )
            for (p in patterns) {
                try {
                    val sdf = SimpleDateFormat(p, Locale.US)
                    sdf.parse(iso)?.time?.let { return it }
                } catch (_: Exception) {
                }
            }
            null
        } catch (_: Exception) {
            null
        }
    }

    private fun autoSaveSettings(forceCommit: Boolean = false) {
        if (suppressAutoSave || restoringVoiceSelections) return
        val prefs = getSharedPreferences(prefsName, Context.MODE_PRIVATE)
        val editor = prefs.edit()

        sentryBreadcrumb("settings:autoSaveSettings:start", mapOf("forceCommit" to forceCommit))

        val aggressiveness = binding.seekbarAggressiveness.progress + 1
        editor.putInt("aggressiveness", aggressiveness)
        editor.putBoolean("prepend_intro", binding.switchPrependIntro.isChecked)

        val videoMode = when (binding.toggleVideoMode.checkedButtonId) {
            binding.btnVideoModeText.id -> "text"
            binding.btnVideoModeSlideshow.id -> "slideshow"
            else -> "slideshow"
        }
        editor.putString("video_mode", videoMode)

        val takeawaysTop = when (binding.toggleTakeawaysTop.checkedButtonId) {
            binding.btnTakeawaysTop3.id -> "3"
            binding.btnTakeawaysTop5.id -> "5"
            binding.btnTakeawaysTop10.id -> "10"
            binding.btnTakeawaysTopAuto.id -> "auto"
            else -> "auto"
        }
        editor.putString("takeaways_top", takeawaysTop)

        val takeawaysFormat = "text"
        editor.putString("takeaways_format", takeawaysFormat)

        val locale = binding.spinnerLocale.selectedItem as? String
        if (!locale.isNullOrBlank()) {
            if (isPlaceholderLocale(locale)) {
                blockedPrefWrite(
                    "BLOCKED_WRITE_CONDENSE_LOCALE",
                    "settings:autoSaveSettings",
                    mapOf("selectedLocale" to locale)
                )
            } else {
                sentryBreadcrumb("prefs:write:condense_locale:autoSave", mapOf("value" to locale))
                editor.putString(KEY_CONDENSE_LOCALE, locale)
            }
        }
        val takeawaysLocale = binding.spinnerTakeawaysLocale.selectedItem as? String
        if (!takeawaysLocale.isNullOrBlank()) {
            if (isPlaceholderLocale(takeawaysLocale)) {
                blockedPrefWrite(
                    "BLOCKED_WRITE_TAKEAWAYS_LOCALE",
                    "settings:autoSaveSettings",
                    mapOf("selectedLocale" to takeawaysLocale)
                )
            } else {
                sentryBreadcrumb("prefs:write:takeaways_locale:autoSave", mapOf("value" to takeawaysLocale))
                editor.putString(KEY_TAKEAWAYS_LOCALE, takeawaysLocale)
            }
        }

        // Only save voice if it looks like a real voice id.
        getSelectedVoiceOption(binding.spinnerVoice, locale)?.id?.let {
            if (isPlaceholderLocale(locale) || it.isBlank() || it == "Loading...") {
                blockedPrefWrite(
                    "BLOCKED_WRITE_CONDENSE_VOICE",
                    "settings:autoSaveSettings",
                    mapOf("selectedLocale" to locale, "voiceId" to it)
                )
            } else {
                sentryBreadcrumb("prefs:write:condense_voice:autoSave", mapOf("value" to it, "locale" to locale))
                editor.putString(KEY_CONDENSE_VOICE, it)
            }
        }
        getSelectedVoiceOption(binding.spinnerTakeawaysVoice, takeawaysLocale)?.id?.let {
            if (isPlaceholderLocale(takeawaysLocale) || it.isBlank() || it == "Loading...") {
                blockedPrefWrite(
                    "BLOCKED_WRITE_TAKEAWAYS_VOICE",
                    "settings:autoSaveSettings",
                    mapOf("selectedLocale" to takeawaysLocale, "voiceId" to it)
                )
            } else {
                sentryBreadcrumb("prefs:write:takeaways_voice:autoSave", mapOf("value" to it, "locale" to takeawaysLocale))
                editor.putString(KEY_TAKEAWAYS_VOICE, it)
            }
        }

        if (forceCommit) editor.commit() else editor.apply()
        sentryBreadcrumb("settings:autoSaveSettings:end", mapOf("forceCommit" to forceCommit))
        assertExpectedInvariant("autoSaveSettings:end")
    }

    private data class _VoiceOption(val id: String)

    private fun getSelectedVoiceOption(spinner: android.widget.Spinner, locale: String?): _VoiceOption? {
        val selectedLocale = locale?.ifBlank { null } ?: Locale.getDefault().toLanguageTag()

        val options = voices
            .filter { it.locale.equals(selectedLocale, ignoreCase = true) }
            .map {
                val genderSuffix = when (it.gender?.trim()?.lowercase()) {
                    "male" -> " (Male)"
                    "female" -> " (Female)"
                    null, "" -> ""
                    else -> " (${it.gender.trim()})"
                }
                VoiceOption(
                    id = it.name,
                    displayName = (it.friendly_name.ifBlank { it.name }) + genderSuffix,
                    voice = it
                )
            }
            .sortedBy { it.displayName.lowercase() }

        val pos = spinner.selectedItemPosition
        if (pos < 0 || pos >= options.size) return null
        return _VoiceOption(options[pos].id)
    }

    // Background colors for layoutStatus — mirror Chrome popup CSS classes
    private val STATUS_BG_SUBMITTING = 0xFFE8F0FE.toInt() // blue-grey (default status)
    private val STATUS_BG_PROCESSING = 0xFFFFF3CD.toInt() // yellow  (.status.processing)
    private val STATUS_BG_COMPLETED  = 0xFFD4EDDA.toInt() // green   (.status.completed)
    private val STATUS_BG_ERROR      = 0xFFF8D7DA.toInt() // red     (.status.error)

    // -------------------------------------------------------------------------
    // Lifecycle
    // -------------------------------------------------------------------------

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        updateBuildInfoLabel()

        sentryBreadcrumb("lifecycle:onCreate")

        migratePrefsKeysIfNeeded()

        assertExpectedInvariant("after_migrate_onCreate")

        suppressAutoSave = true
        setupSettingsControls()
        loadSettingsToUI()
        suppressAutoSave = false
        clearAllStateOnServerSwitchIfNeeded()
        loadCachedVoicesAndStrategiesIntoUI()
        fetchVoicesAndStrategiesIfMissing()
        setupUI()
        handleIntent(intent)

        assertExpectedInvariant("end_onCreate")
    }

    private fun getServerCacheKeyPrefix(serverUrl: String): String = "serverCache:$serverUrl"

    private fun getStrategiesCacheKey(serverUrl: String): String = "${getServerCacheKeyPrefix(serverUrl)}:strategies"

    private fun getVoicesCacheKey(serverUrl: String, locale: String): String = "${getServerCacheKeyPrefix(serverUrl)}:voices:$locale"

    private fun getLanguageOnlyLocale(): String {
        val raw = Locale.getDefault().toString()
        val value = raw.substringBefore('-').substringBefore('_').ifBlank { "en" }
        Log.i(logTag, "METADATA_CACHE: language_only_locale raw=$raw value=$value")
        return value
    }

    private fun loadCachedVoicesAndStrategiesIntoUI() {
        val serverUrl = getServerUrl()
        val userLanguage = getLanguageOnlyLocale()
        val prefs = getSharedPreferences(prefsName, Context.MODE_PRIVATE)

        val cachedVoicesJson = prefs.getString(getVoicesCacheKey(serverUrl, userLanguage), null)
        val cachedStrategiesJson = prefs.getString(getStrategiesCacheKey(serverUrl), null)

        Log.i(logTag, "METADATA_CACHE: cache_read serverUrl=$serverUrl voicesKey=${getVoicesCacheKey(serverUrl, userLanguage)} voicesPresent=${cachedVoicesJson != null} strategiesKey=${getStrategiesCacheKey(serverUrl)} strategiesPresent=${cachedStrategiesJson != null}")

        lifecycleScope.launch {
            apiLog(
                serverUrl,
                "metadata_cache_read",
                mapOf(
                    "lang" to userLanguage,
                    "voicesKey" to getVoicesCacheKey(serverUrl, userLanguage),
                    "voicesPresent" to (cachedVoicesJson != null),
                    "strategiesKey" to getStrategiesCacheKey(serverUrl),
                    "strategiesPresent" to (cachedStrategiesJson != null)
                )
            )
        }

        if (cachedVoicesJson != null) {
            try {
                val type = object : TypeToken<List<VoiceItem>>() {}.type
                voices = Gson().fromJson(cachedVoicesJson, type) ?: emptyList()
            } catch (_: Exception) {
                voices = emptyList()
            }
        }

        if (cachedStrategiesJson != null) {
            try {
                val type = object : TypeToken<List<StrategyItem>>() {}.type
                strategies = Gson().fromJson(cachedStrategiesJson, type) ?: emptyList()
            } catch (_: Exception) {
                strategies = emptyList()
            }
        }

        if (voices.isNotEmpty()) {
            suppressAutoSave = true
            restoringVoiceSelections = true
            blockVoiceSelectionCallbacksUntilMs = SystemClock.elapsedRealtime() + 2000L
            try {
                populateLocaleSpinners()
                val savedLocale = prefs.getString(KEY_CONDENSE_LOCALE, null)
                val savedVoice = prefs.getString(KEY_CONDENSE_VOICE, null)
                val savedTakeawaysLocale = prefs.getString(KEY_TAKEAWAYS_LOCALE, savedLocale)
                val savedTakeawaysVoice = prefs.getString(KEY_TAKEAWAYS_VOICE, null)
                    ?: prefs.getString(KEY_TAKEAWAYS_VOICE, savedVoice)
                Log.i(logTag, "METADATA_CACHE: restore_settings condenseLocale=$savedLocale condenseVoice=$savedVoice")
                lifecycleScope.launch {
                    apiLog(
                        serverUrl,
                        "metadata_restore_settings",
                        mapOf(
                            "condenseLocale" to savedLocale,
                            "condenseVoice" to savedVoice,
                            "takeawaysLocale" to savedTakeawaysLocale,
                            "takeawaysVoice" to savedTakeawaysVoice
                        )
                    )
                }
                restoreLocaleAndVoiceSelection(binding.spinnerLocale, binding.spinnerVoice, savedLocale, savedVoice)
                restoreLocaleAndVoiceSelection(binding.spinnerTakeawaysLocale, binding.spinnerTakeawaysVoice, savedTakeawaysLocale, savedTakeawaysVoice)

                // If takeaways voice UI starts hidden (format != audio), the spinner may not
                // get fully initialized until later. Re-apply once more after UI settles.
                lifecycleScope.launch {
                    delay(250)
                    restoreLocaleAndVoiceSelection(
                        binding.spinnerTakeawaysLocale,
                        binding.spinnerTakeawaysVoice,
                        savedTakeawaysLocale,
                        savedTakeawaysVoice
                    )

                    // If takeaways format is audio, ensure the voice selection is applied.
                    val fmt = prefs.getString(KEY_TAKEAWAYS_FORMAT, "text") ?: "text"
                    if (fmt == "audio") {
                        val selectedLocale = binding.spinnerTakeawaysLocale.selectedItem?.toString()
                        if (!selectedLocale.isNullOrBlank()) {
                            populateTakeawaysVoiceSpinnerForLocale(selectedLocale)
                        }
                        val savedTv = prefs.getString(KEY_TAKEAWAYS_VOICE, null)
                        if (!savedTv.isNullOrBlank()) {
                            restoreLocaleAndVoiceSelection(
                                binding.spinnerTakeawaysLocale,
                                binding.spinnerTakeawaysVoice,
                                savedTakeawaysLocale,
                                savedTv
                            )
                        }
                    }
                }
            } finally {
                lifecycleScope.launch {
                    delay(500)
                    restoringVoiceSelections = false
                    suppressAutoSave = false
                    blockVoiceSelectionCallbacksUntilMs = maxOf(blockVoiceSelectionCallbacksUntilMs, SystemClock.elapsedRealtime() + 1500L)
                }
            }
        }

        if (strategies.isNotEmpty()) {
            updateStrategyDesc(binding.seekbarAggressiveness.progress + 1)
        }
    }

    private fun clearAllStateOnServerSwitchIfNeeded() {
        val prefs = getSharedPreferences(prefsName, Context.MODE_PRIVATE)
        val selectedServerUrl = getServerUrl()
        val lastServerUrl = prefs.getString("last_server_url", "").orEmpty()

        Log.i(logTag, "METADATA_CACHE: server_switch_check last=$lastServerUrl selected=$selectedServerUrl")

        lifecycleScope.launch {
            apiLog(
                selectedServerUrl,
                "metadata_server_switch_check",
                mapOf(
                    "lastServerUrl" to lastServerUrl,
                    "selectedServerUrl" to selectedServerUrl
                )
            )
        }

        if (lastServerUrl.isNotEmpty() && lastServerUrl != selectedServerUrl) {
            Log.i(logTag, "METADATA_CACHE: server_switch_wipe from=$lastServerUrl to=$selectedServerUrl")
            lifecycleScope.launch {
                apiLog(
                    selectedServerUrl,
                    "metadata_server_switch_wipe",
                    mapOf("from" to lastServerUrl, "to" to selectedServerUrl)
                )
            }
            prefs.edit().clear().apply()
            getSharedPreferences("client_identity", Context.MODE_PRIVATE).edit().clear().apply()
            getSharedPreferences(prefsName, Context.MODE_PRIVATE)
                .edit()
                .putString("server_url", selectedServerUrl)
                .putString("last_server_url", selectedServerUrl)
                .apply()
        } else if (lastServerUrl.isEmpty() && selectedServerUrl.isNotEmpty()) {
            Log.i(logTag, "METADATA_CACHE: server_switch_set_last value=$selectedServerUrl")
            lifecycleScope.launch {
                apiLog(selectedServerUrl, "metadata_server_switch_set_last", mapOf("value" to selectedServerUrl))
            }
            prefs.edit().putString("last_server_url", selectedServerUrl).apply()
        }
    }

    private fun fetchVoicesAndStrategiesIfMissing() {
        val serverUrl = getServerUrl()
        val prefs = getSharedPreferences(prefsName, Context.MODE_PRIVATE)
        val userLanguage = getLanguageOnlyLocale()

        val haveVoices = prefs.contains(getVoicesCacheKey(serverUrl, userLanguage))
        val haveStrategies = prefs.contains(getStrategiesCacheKey(serverUrl))
        Log.i(logTag, "METADATA_CACHE: fetch_if_missing serverUrl=$serverUrl lang=$userLanguage haveVoices=$haveVoices haveStrategies=$haveStrategies")
        lifecycleScope.launch {
            apiLog(
                serverUrl,
                "metadata_fetch_if_missing",
                mapOf(
                    "lang" to userLanguage,
                    "haveVoices" to haveVoices,
                    "haveStrategies" to haveStrategies
                )
            )
        }
        if (haveVoices && haveStrategies) return

        setSettingsEnabled(false, "metadata_loading")

        lifecycleScope.launch {
            ensureServerMetadataLoadedAfterSuccessfulContact(serverUrl)
        }
    }

    private suspend fun ensureServerMetadataLoadedAfterSuccessfulContact(serverUrl: String) {
        val prefs = getSharedPreferences(prefsName, Context.MODE_PRIVATE)
        val userLanguage = getLanguageOnlyLocale()

        val haveVoices = prefs.contains(getVoicesCacheKey(serverUrl, userLanguage))
        val haveStrategies = prefs.contains(getStrategiesCacheKey(serverUrl))
        if (haveVoices && haveStrategies) return

        val api = ConciserApi.createService(serverUrl, ClientIdentity.getOrCreate(this@MainActivity))

        if (!haveVoices) {
            try {
                Log.i(logTag, "METADATA_CACHE: voices_fetch_start url=$serverUrl locale=$userLanguage")
                apiLog(serverUrl, "metadata_voices_fetch_start", mapOf("lang" to userLanguage))
                val response = api.getVoices(userLanguage)
                voices = response.voices
                prefs.edit().putString(getVoicesCacheKey(serverUrl, userLanguage), Gson().toJson(voices)).apply()
                Log.i(logTag, "METADATA_CACHE: voices_cache_write key=${getVoicesCacheKey(serverUrl, userLanguage)} count=${voices.size}")
                apiLog(
                    serverUrl,
                    "metadata_voices_cache_write",
                    mapOf(
                        "lang" to userLanguage,
                        "key" to getVoicesCacheKey(serverUrl, userLanguage),
                        "count" to voices.size
                    )
                )
            } catch (e: Exception) {
                Sentry.captureException(e)
                Log.w(logTag, "METADATA_CACHE: voices_fetch_failed", e)
                apiLog(serverUrl, "metadata_voices_fetch_failed", mapOf("lang" to userLanguage, "error" to (e.message ?: "")))
            }
        }

        if (!haveStrategies) {
            try {
                Log.i(logTag, "METADATA_CACHE: strategies_fetch_start url=$serverUrl")
                apiLog(serverUrl, "metadata_strategies_fetch_start")
                val response = api.getStrategies()
                strategies = response.strategies
                prefs.edit().putString(getStrategiesCacheKey(serverUrl), Gson().toJson(strategies)).apply()
                Log.i(logTag, "METADATA_CACHE: strategies_cache_write key=${getStrategiesCacheKey(serverUrl)} count=${strategies.size}")
                apiLog(
                    serverUrl,
                    "metadata_strategies_cache_write",
                    mapOf(
                        "key" to getStrategiesCacheKey(serverUrl),
                        "count" to strategies.size
                    )
                )
            } catch (e: Exception) {
                Sentry.captureException(e)
                Log.w(logTag, "METADATA_CACHE: strategies_fetch_failed", e)
                apiLog(serverUrl, "metadata_strategies_fetch_failed", mapOf("error" to (e.message ?: "")))
            }
        }

        runOnUiThread {
            loadCachedVoicesAndStrategiesIntoUI()

            val prefs2 = getSharedPreferences(prefsName, Context.MODE_PRIVATE)
            val haveVoicesNow = prefs2.contains(getVoicesCacheKey(serverUrl, userLanguage))
            val haveStrategiesNow = prefs2.contains(getStrategiesCacheKey(serverUrl))
            setSettingsEnabled(haveVoicesNow && haveStrategiesNow, "metadata_loaded")
            if (!haveVoicesNow) {
                val fallback = ArrayAdapter(this, android.R.layout.simple_spinner_item, listOf(userLanguage))
                fallback.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
                binding.spinnerLocale.adapter = fallback
                binding.spinnerTakeawaysLocale.adapter = fallback
                val loadingVoiceAdapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, listOf("Failed to load voices"))
                loadingVoiceAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
                binding.spinnerVoice.adapter = loadingVoiceAdapter
                binding.spinnerTakeawaysVoice.adapter = loadingVoiceAdapter
            }
            if (!haveStrategiesNow) {
                binding.tvStrategyDesc.text = "Failed to load"
            }
        }
    }

    private fun setSettingsEnabled(enabled: Boolean, reason: String) {
        try {
            binding.cardCondenseSettings.isEnabled = enabled
            binding.cardTakeawaysSettings.isEnabled = enabled
            binding.cardCondenseSettings.alpha = if (enabled) 1.0f else 0.4f
            binding.cardTakeawaysSettings.alpha = if (enabled) 1.0f else 0.4f
            sentryBreadcrumb("ui:settings_enabled", mapOf("enabled" to enabled, "reason" to reason))
        } catch (_: Exception) {
        }
    }

    override fun onResume() {
        super.onResume()
        isForeground = true
        updateBuildInfoLabel()
        refreshRecentJobsUI()
        fetchVoicesAndStrategiesIfMissing()

        val jobId = currentJobId
        if (jobId != null && (currentState == AppState.PROCESSING || currentState == AppState.SUBMITTING)) {
            lifecycleScope.launch {
                delay(SSE_RECONNECT_DELAY_MS)
                if (isForeground && currentJobId == jobId && eventSource == null) {
                    startSsePolling(jobId, resetAttempts = true)
                }
            }
        }
    }

    override fun onPause() {
        autoSaveSettings(forceCommit = true)
        isForeground = false
        super.onPause()
        eventSource?.cancel()
        eventSource = null
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        intent?.let { handleIntent(it) }
    }

    override fun onDestroy() {
        super.onDestroy()
        eventSource?.cancel()
    }

    // -------------------------------------------------------------------------
    // UI Wiring
    // -------------------------------------------------------------------------

    private fun setupUI() {
        // Mode toggle
        binding.btnModeCondense.setOnClickListener {
            switchMode("condense")
        }
        binding.btnModeTakeaways.setOnClickListener {
            switchMode("takeaways")
        }

        // Condense button
        binding.btnCondense.setOnClickListener {
            currentVideoUrl?.let { url -> submitCondense(url) }
        }

        // Takeaways button
        binding.btnTakeaways.setOnClickListener {
            currentVideoUrl?.let { url -> submitTakeaways(url) }
        }

        binding.btnCancel.setOnClickListener {
            eventSource?.cancel()
            updateUI(if (currentVideoUrl != null) AppState.READY else AppState.NO_URL)
        }
        binding.btnWatch.setOnClickListener {
            currentJobId?.let { jobId -> openCurrentResult(jobId) }
        }
        binding.btnShare.setOnClickListener {
            currentJobId?.let { jobId -> shareCurrentResult(jobId) }
        }

        // Default to condense mode
        binding.toggleMode.check(binding.btnModeCondense.id)
        switchMode("condense")
    }

    private fun switchMode(mode: String) {
        appMode = mode
        currentJobType = mode  // Update current job type for in-progress checks
        if (mode == "condense") {
            binding.cardCondenseSettings.visibility = View.VISIBLE
            binding.cardTakeawaysSettings.visibility = View.GONE
            binding.btnCondense.visibility = View.VISIBLE
            binding.btnTakeaways.visibility = View.GONE
            // Set condense button state
            binding.btnCondense.isEnabled = currentVideoUrl != null
        } else {
            binding.cardCondenseSettings.visibility = View.GONE
            binding.cardTakeawaysSettings.visibility = View.VISIBLE
            binding.btnCondense.visibility = View.GONE
            binding.btnTakeaways.visibility = View.VISIBLE
            // Set takeaways button state
            binding.btnTakeaways.isEnabled = currentVideoUrl != null
        }
        // Reset state when switching modes
        if (currentState != AppState.NO_URL && currentState != AppState.READY) {
            eventSource?.cancel()
            currentJobId = null
            updateUI(if (currentVideoUrl != null) AppState.READY else AppState.NO_URL)
        }

        // Check for in-progress jobs after switching tabs
        checkForInProgressJobs()
        refreshRecentJobsUI()

        // Retry loading voices/strategies if a previous attempt failed
        fetchVoicesAndStrategiesIfMissing()
    }

    // -------------------------------------------------------------------------
    // State Machine
    // -------------------------------------------------------------------------

    /**
     * Single source of truth for all view visibility and enabled-state.
     * Maps 1:1 with Chrome popup state transitions.
     *
     * NO_URL      → condense disabled, status hidden
     * READY       → condense enabled, status hidden
     * SUBMITTING  → condense disabled, status blue, cancel visible
     * PROCESSING  → condense disabled, status yellow, cancel visible, progress optional
     * COMPLETED   → condense GONE, status green, watch visible
     * ERROR       → condense re-enabled, status red
     */
    private fun updateUI(
        state: AppState,
        statusText: String? = null,
        progressText: String? = null
    ) {
        currentState = state

        when (state) {
            AppState.NO_URL -> {
                binding.tvVideoInfo.text = getString(R.string.waiting_for_video)
                if (appMode == "condense") {
                    binding.btnCondense.visibility = View.VISIBLE
                    binding.btnCondense.isEnabled = false
                } else {
                    binding.btnTakeaways.visibility = View.VISIBLE
                    binding.btnTakeaways.isEnabled = false
                }
                binding.layoutStatus.visibility = View.GONE
                binding.btnCancel.visibility = View.GONE
                binding.btnWatch.visibility = View.GONE
                binding.btnShare.visibility = View.GONE
            }

            AppState.READY -> {
                if (appMode == "condense") {
                    binding.btnCondense.visibility = View.VISIBLE
                    binding.btnCondense.isEnabled = true
                } else {
                    binding.btnTakeaways.visibility = View.VISIBLE
                    binding.btnTakeaways.isEnabled = true
                }
                binding.layoutStatus.visibility = View.GONE
                binding.btnCancel.visibility = View.GONE
                binding.btnWatch.visibility = View.GONE
                binding.btnShare.visibility = View.GONE
            }

            AppState.SUBMITTING -> {
                if (appMode == "condense") {
                    binding.btnCondense.visibility = View.VISIBLE
                    binding.btnCondense.isEnabled = false
                } else {
                    binding.btnTakeaways.visibility = View.VISIBLE
                    binding.btnTakeaways.isEnabled = false
                }
                binding.layoutStatus.visibility = View.VISIBLE
                binding.layoutStatus.setBackgroundColor(STATUS_BG_SUBMITTING)
                binding.tvStatus.text = statusText ?: "Submitting..."
                binding.tvProgress.visibility = View.GONE
                binding.btnCancel.visibility = View.VISIBLE
                binding.btnWatch.visibility = View.GONE
                binding.btnShare.visibility = View.GONE
            }

            AppState.PROCESSING -> {
                if (appMode == "condense") {
                    binding.btnCondense.visibility = View.VISIBLE
                    binding.btnCondense.isEnabled = false
                } else {
                    binding.btnTakeaways.visibility = View.VISIBLE
                    binding.btnTakeaways.isEnabled = false
                }
                binding.layoutStatus.visibility = View.VISIBLE
                binding.layoutStatus.setBackgroundColor(STATUS_BG_PROCESSING)
                binding.tvStatus.text = statusText ?: "Processing video..."
                if (progressText != null) {
                    binding.tvProgress.text = progressText
                    binding.tvProgress.visibility = View.VISIBLE
                } else {
                    binding.tvProgress.visibility = View.GONE
                }
                binding.btnCancel.visibility = View.VISIBLE
                binding.btnWatch.visibility = View.GONE
                binding.btnShare.visibility = View.GONE
            }

            AppState.COMPLETED -> {
                // Button is GONE on completion — same as Chrome popup (display:none)
                binding.btnCondense.visibility = View.GONE
                binding.btnTakeaways.visibility = View.GONE
                binding.layoutStatus.visibility = View.VISIBLE
                binding.layoutStatus.setBackgroundColor(STATUS_BG_COMPLETED)
                binding.tvStatus.text = statusText ?: "✅ Ready!\nJob ID: $currentJobId"
                binding.tvProgress.visibility = View.GONE
                binding.btnCancel.visibility = View.GONE
                binding.btnWatch.text = when (currentOutputFormat) {
                    "text" -> "Read Takeaways"
                    "audio" -> "Play Audio"
                    else -> "Play Video"
                }
                binding.btnWatch.visibility = View.VISIBLE
                binding.btnShare.visibility = View.VISIBLE
            }

            AppState.ERROR -> {
                // Re-enable button so user can retry — mirrors Chrome's resetButton()
                if (appMode == "condense") {
                    binding.btnCondense.visibility = View.VISIBLE
                    binding.btnCondense.isEnabled = currentVideoUrl != null
                } else {
                    binding.btnTakeaways.visibility = View.VISIBLE
                    binding.btnTakeaways.isEnabled = currentVideoUrl != null
                }
                binding.layoutStatus.visibility = View.VISIBLE
                binding.layoutStatus.setBackgroundColor(STATUS_BG_ERROR)
                binding.tvStatus.text = statusText ?: "An error occurred"
                binding.tvProgress.visibility = View.GONE
                binding.btnCancel.visibility = View.GONE
                binding.btnWatch.visibility = View.GONE
                binding.btnShare.visibility = View.GONE
            }
        }
    }

    // -------------------------------------------------------------------------
    // Intent Handling — stores URL but does NOT auto-start condensing
    // -------------------------------------------------------------------------

    private fun handleIntent(intent: Intent) {
        // Stop any in-progress job when a new share arrives
        eventSource?.cancel()

        val url = when (intent.action) {
            Intent.ACTION_SEND -> {
                if (intent.type == "text/plain") intent.getStringExtra(Intent.EXTRA_TEXT) else null
            }
            Intent.ACTION_VIEW -> intent.dataString
            else -> null
        }

        if (url != null && isYouTubeUrl(url)) {
            currentVideoUrl = url
            currentVideoTitle = null
            currentJobId = null
            val videoId = extractVideoId(url)
            binding.tvVideoInfo.text = if (videoId != null) "Video: $videoId" else url
            updateUI(AppState.READY)
            // Fetch title asynchronously and update below the ID
            lifecycleScope.launch {
                val title = ConciserApi.fetchVideoTitle(url)
                if (title != null && currentVideoUrl == url) {
                    currentVideoTitle = title
                    val full = if (videoId != null) "Video: $videoId\n$title" else title
                    val span = SpannableString(full)
                    val titleStart = full.length - title.length
                    span.setSpan(StyleSpan(Typeface.BOLD), titleStart, full.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                    binding.tvVideoInfo.text = span
                }
            }
            // Check for in-progress jobs for this video
            checkForInProgressJobs()
        } else {
            currentVideoUrl = null
            updateUI(AppState.NO_URL)
        }
    }

    // -------------------------------------------------------------------------
    // Condensing
    // -------------------------------------------------------------------------

    private fun submitCondense(url: String) {
        updateUI(AppState.SUBMITTING, "Submitting...")

        val prefs = getSharedPreferences(prefsName, Context.MODE_PRIVATE)
        val serverUrl = prefs.getString("server_url", ConciserApi.DEFAULT_URL) ?: ConciserApi.DEFAULT_URL
        val clientId = ClientIdentity.getOrCreate(this)
        val aggressiveness = prefs.getInt("aggressiveness", 5)
        val voice = prefs.getString(KEY_CONDENSE_VOICE, "") ?: ""
        val speechSpeed = prefs.getFloat("speech_speed", 1.00f)
        val videoMode = prefs.getString("video_mode", "slideshow") ?: "slideshow"
        val prependIntro = prefs.getBoolean("prepend_intro", false)

        currentOutputFormat = when (videoMode) {
            "text" -> "text"
            else -> "slideshow"
        }

        val req = CreateJobRequest(
            type = "condense",
            url = url,
            params = mapOf(
                "aggressiveness" to aggressiveness,
                "voice" to voice,
                "speech_rate" to convertSpeedToRate(speechSpeed),
                "video_mode" to videoMode,
                "prepend_intro" to prependIntro,
            )
        )

        lifecycleScope.launch {
            try {
                val api = ConciserApi.createService(serverUrl, clientId)
                val response = ConciserApi.createJobWithActiveJobHandling(api, req)
                ensureServerMetadataLoadedAfterSuccessfulContact(serverUrl)
                currentJobId = response.id
                updateUI(AppState.PROCESSING, statusText = "Processing video...\nJob ID: ${response.id}")
                startPolling()
            } catch (e: ActiveJobInProgressException) {
                val idPart = if (!e.activeJobId.isNullOrBlank()) " (${e.activeJobId}${if (!e.activeJobStatus.isNullOrBlank()) ", ${e.activeJobStatus}" else ""})" else ""
                val msg = "You already have an active job$idPart. Please wait for it to finish, or cancel it from Recent Jobs, then try again."
                updateUI(AppState.READY, statusText = msg)
            } catch (e: Exception) {
                Sentry.captureException(e)
                updateUI(AppState.ERROR, statusText = "Failed to submit: ${e.message}")
            }
        }
    }

    private fun submitTakeaways(url: String) {
        updateUI(AppState.SUBMITTING, "Submitting...")

        val prefs = getSharedPreferences(prefsName, Context.MODE_PRIVATE)
        val serverUrl = prefs.getString("server_url", ConciserApi.DEFAULT_URL) ?: ConciserApi.DEFAULT_URL
        val clientId = ClientIdentity.getOrCreate(this)

        // Get takeaways settings
        val topValue = when (binding.toggleTakeawaysTop.checkedButtonId) {
            binding.btnTakeawaysTop3.id -> "3"
            binding.btnTakeawaysTop5.id -> "5"
            binding.btnTakeawaysTop10.id -> "10"
            binding.btnTakeawaysTopAuto.id -> "auto"
            else -> "auto"
        }
        val top = if (topValue == "auto") null else topValue.toIntOrNull()

        val format = "text"
        val voice = null

        currentJobType = "takeaways"
        currentOutputFormat = format  // "text" or "audio"

        val req = CreateJobRequest(
            type = "takeaways",
            url = url,
            params = mapOf(
                "top" to top,
                "format_type" to format,
                "voice" to voice,
            )
        )

        lifecycleScope.launch {
            try {
                val api = ConciserApi.createService(serverUrl, clientId)
                val response = ConciserApi.createJobWithActiveJobHandling(api, req)
                ensureServerMetadataLoadedAfterSuccessfulContact(serverUrl)
                currentJobId = response.id
                updateUI(AppState.PROCESSING, statusText = "Extracting takeaways...\nJob ID: ${response.id}")
                startPolling()
            } catch (e: ActiveJobInProgressException) {
                val idPart = if (!e.activeJobId.isNullOrBlank()) " (${e.activeJobId}${if (!e.activeJobStatus.isNullOrBlank()) ", ${e.activeJobStatus}" else ""})" else ""
                val msg = "You already have an active job$idPart. Please wait for it to finish, or cancel it from Recent Jobs, then try again."
                updateUI(AppState.READY, statusText = msg)
            } catch (e: Exception) {
                Sentry.captureException(e)
                updateUI(AppState.ERROR, statusText = "Failed to submit: ${e.message}")
            }
        }
    }

    private fun checkForInProgressJobs() {
        val videoUrl = currentVideoUrl ?: return

        lifecycleScope.launch {
            try {
                Log.d("JobResume", "Checking for in-progress jobs for current video...")
                val api = createApi()
                val response = api.getJobs()
                setServerCallStatus(true)
                val jobs = response.jobs

                // Find in-progress job for current URL and type
                val inProgressJob = jobs.firstOrNull { job ->
                    job.url == videoUrl &&
                    job.type == currentJobType &&
                    (job.status == "processing" || job.status == "queued")
                }

                if (inProgressJob != null) {
                    Log.d("JobResume", "Found in-progress ${currentJobType} job: ${inProgressJob.id}")
                    currentJobId = inProgressJob.id
                    updateUI(
                        AppState.PROCESSING,
                        statusText = "Resuming job...\nJob ID: ${currentJobId}",
                        progressText = inProgressJob.progress
                    )
                    startPolling()
                } else {
                    Log.d("JobResume", "No in-progress ${currentJobType} job found for this video")
                }
            } catch (e: Exception) {
                setServerCallStatus(false)
                Log.e("JobResume", "Error checking for in-progress jobs: ${e.message}")
                // Silently fail - don't interrupt user experience
            }
        }
    }

    private fun startPolling() {
        // Close any existing SSE connection
        eventSource?.cancel()

        val jobId = currentJobId ?: return
        startSsePolling(jobId, resetAttempts = true)
    }

    private fun startSsePolling(jobId: String, resetAttempts: Boolean = true) {
        if (resetAttempts) {
            sseReconnectAttempts = 0
        }

        val cid = ClientIdentity.getOrCreate(this)
        val url = "${getServerUrl().trimEnd('/')}/api/jobs/${jobId}/stream?cid=${cid}"

        Log.d("SSE", "Connecting to: $url")

        lifecycleScope.launch {
            ensureServerMetadataLoadedAfterSuccessfulContact(getServerUrl())
        }

        val request = Request.Builder().url(url).build()

        eventSource = EventSources.createFactory(okhttp3.OkHttpClient())
            .newEventSource(request, object : EventSourceListener() {
                override fun onOpen(eventSource: EventSource, response: Response) {
                    Log.d("SSE", "Connection opened")
                }

                override fun onEvent(
                    eventSource: EventSource,
                    id: String?,
                    type: String?,
                    data: String
                ) {
                    Log.d("SSE", "Received event: $data")
                    try {
                        val gson = com.google.gson.Gson()
                        val job = gson.fromJson(data, JobResponse::class.java)
                        runOnUiThread {
                            updateJobUI(job)
                            if (job.status == "completed" || job.status == "error") {
                                eventSource.cancel()
                            }
                        }
                    } catch (e: Exception) {
                        Log.e("SSE", "Error parsing job data: ${e.message}")
                        Sentry.captureException(e)
                    }
                }

                override fun onClosed(eventSource: EventSource) {
                    Log.d("SSE", "Connection closed")
                    if (this@MainActivity.eventSource === eventSource) {
                        this@MainActivity.eventSource = null
                    }
                }

                override fun onFailure(
                    eventSource: EventSource,
                    t: Throwable?,
                    response: Response?
                ) {
                    Log.e("SSE", "Connection error: ${t?.message}, response: ${response?.code}")

                    if (this@MainActivity.eventSource === eventSource) {
                        this@MainActivity.eventSource = null
                    }

                    // If we are backgrounded, do not surface an error; we'll reconnect on resume.
                    if (!isForeground) {
                        return
                    }

                    // Retry a few times with 1s delay before giving up.
                    if (sseReconnectAttempts < SSE_MAX_RECONNECT_ATTEMPTS) {
                        sseReconnectAttempts += 1
                        runOnUiThread {
                            updateUI(
                                AppState.PROCESSING,
                                statusText = "Connection lost. Reconnecting... (attempt ${sseReconnectAttempts}/${SSE_MAX_RECONNECT_ATTEMPTS})\nJob ID: ${currentJobId ?: jobId}"
                            )
                        }
                        lifecycleScope.launch {
                            delay(SSE_RECONNECT_DELAY_MS)
                            val current = currentJobId
                            if (isForeground && current != null && (currentState == AppState.PROCESSING || currentState == AppState.SUBMITTING)) {
                                startSsePolling(current, resetAttempts = false)
                            }
                        }
                        return
                    }

                    // Try one regular fetch to see if job still exists
                    lifecycleScope.launch {
                        try {
                            val api = createApi()
                            val job = api.getJob(currentJobId!!)
                            runOnUiThread {
                                updateJobUI(job)
                            }
                        } catch (e: Exception) {
                            if (e is retrofit2.HttpException && e.code() == 404) {
                                val missingId = currentJobId
                                currentJobId = null
                                runOnUiThread {
                                    updateUI(
                                        AppState.ERROR,
                                        statusText = "Job ${missingId ?: "(unknown)"} not found on server"
                                    )
                                }
                            } else {
                                runOnUiThread {
                                    updateUI(
                                        AppState.ERROR,
                                        statusText = "Connection lost. Check that the server is running."
                                    )
                                }
                            }
                        }
                    }
                }
            })
    }

    private fun updateJobUI(job: JobResponse) {
        when (job.status) {
            "queued" -> {
                updateUI(
                    AppState.PROCESSING,
                    statusText = "Queued...\nJob ID: ${job.id}",
                    progressText = job.progress
                )
            }
            "processing" -> {
                updateUI(
                    AppState.PROCESSING,
                    statusText = "Processing video...\nJob ID: ${job.id}",
                    progressText = job.progress
                )
            }
            "completed" -> {
                updateUI(AppState.COMPLETED, statusText = "✅ Ready!\nJob ID: ${job.id}")
            }
            "error" -> {
                updateUI(AppState.ERROR, statusText = "Processing failed: ${job.error ?: "Unknown error"}")
            }
            else -> {
                updateUI(
                    AppState.PROCESSING,
                    statusText = "${job.status}\nJob ID: ${job.id}",
                    progressText = job.progress
                )
            }
        }
    }

    private fun createApi(): ConciserApiService {
        val url = getServerUrl()
        val cid = ClientIdentity.getOrCreate(this)
        return ConciserApi.createService(url, cid)
    }

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------

    private fun isYouTubeUrl(url: String): Boolean =
        url.contains("youtube.com") || url.contains("youtu.be")

    private fun extractVideoId(url: String): String? {
        val watch = Regex("""[?&]v=([a-zA-Z0-9_-]{11})""").find(url)?.groupValues?.get(1)
        val short = Regex("""youtu\.be/([a-zA-Z0-9_-]{11})""").find(url)?.groupValues?.get(1)
        return watch ?: short
    }

    private fun getServerUrl(): String =
        getSharedPreferences(prefsName, Context.MODE_PRIVATE).let { prefs ->
            prefsGetStringLogged(prefs, "server_url", ConciserApi.DEFAULT_URL, "getServerUrl") ?: ConciserApi.DEFAULT_URL
        }

    private fun convertSpeedToRate(speed: Float): String {
        val percentage = ((speed - 1.0f) * 100).roundToInt()
        return if (percentage >= 0) "+${percentage}%" else "${percentage}%"
    }

    private fun updateBuildInfoLabel() {
        val prefs = getSharedPreferences(prefsName, Context.MODE_PRIVATE)
        val activeUrl = prefs.getString("server_url", BuildConfig.DEFAULT_SERVER_URL) ?: BuildConfig.DEFAULT_SERVER_URL
        val presetIdx = BuildConfig.PRESET_SERVER_URLS.indexOf(activeUrl)
        val serverLabel = if (presetIdx >= 0) {
            BuildConfig.PRESET_SERVER_NAMES[presetIdx]
        } else {
            try { java.net.URL(activeUrl).host.split('.')[0] } catch (e: Exception) { null }
        }
        binding.tvBuildInfo.text = if (serverLabel != null) "${BuildConfig.BUILD_VERSION} | $serverLabel" else BuildConfig.BUILD_VERSION
        setServerCallStatus(true)
    }

    private fun setServerCallStatus(ok: Boolean) {
        binding.tvBuildInfo.setTextColor(
            if (ok) Color.parseColor("#757575") else Color.parseColor("#d32f2f")
        )
    }

    // -------------------------------------------------------------------------
    // Menu
    // -------------------------------------------------------------------------

    override fun onCreateOptionsMenu(menu: Menu?): Boolean {
        menuInflater.inflate(R.menu.main_menu, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        return when (item.itemId) {
            R.id.action_settings -> {
                startActivity(Intent(this, SettingsActivity::class.java))
                true
            }
            else -> super.onOptionsItemSelected(item)
        }
    }
}
