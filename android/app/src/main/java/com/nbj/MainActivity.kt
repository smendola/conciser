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
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.LinearLayout
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
import okhttp3.RequestBody.Companion.toRequestBody
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TreeSet
import kotlin.math.roundToInt

class MainActivity : AppCompatActivity() {

    private val logTag = "MetadataCache"

    private suspend fun apiLog(serverUrl: String, event: String, data: Map<String, Any?> = emptyMap()) {
        try {
            val payload = mutableMapOf<String, Any?>(
                "source" to "android",
                "event" to event,
                "serverUrl" to serverUrl,
                "ts" to System.currentTimeMillis()
            )
            payload.putAll(data)

            val api = ConciserApi.createService(serverUrl, ClientIdentity.getOrCreate(this@MainActivity))
            withContext(Dispatchers.IO) {
                apiLogPost(api, payload)
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
                val msg = if (currentOutputFormat == "text") {
                    "No browser found."
                } else {
                    "No media player found. Please install a media player app."
                }
                Toast.makeText(this@MainActivity, msg, Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun openRecentJob(job: RecentJob) {
        lifecycleScope.launch {
            try {
                val api = ConciserApi.createService(job.serverUrl, ClientIdentity.getOrCreate(this@MainActivity))
                val artifacts = api.getArtifacts(job.jobId).artifacts
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
                val msg = if (job.outputFormat == "text") "No browser found." else "No media player found."
                Toast.makeText(this@MainActivity, msg, Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun apiLogPost(api: ConciserApiService, payload: Map<String, Any?>) {
        try {
            val json = Gson().toJson(payload)
            val request = okhttp3.Request.Builder()
                .url((payload["serverUrl"] as String).trimEnd('/') + "/api/log")
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
    private var isPolling = false

    private var voices: List<VoiceItem> = emptyList()
    private var strategies: List<StrategyItem> = emptyList()

    private data class VoiceOption(
        val id: String,
        val displayName: String,
        val voice: VoiceItem
    )

    private val videoModeValues = listOf("slideshow", "audio_only")
    private val videoModeLabels = listOf("Slideshow", "Audio Only (MP3)")

    // Takeaways mode
    private var appMode: String = "condense" // "condense" or "takeaways"
    private val takeawaysTopValues = listOf("3", "5", "10", "auto")
    private val takeawaysTopLabels = listOf("Top 3", "Top 5", "Top 10", "Auto")
    private val takeawaysFormatValues = listOf("text", "audio")
    private val takeawaysFormatLabels = listOf("Text", "Audio")
    private val prefsName = "nbj_prefs"
    private var suppressAutoSave = false
    private var restoringVoiceSelections = false
    private var blockVoiceSelectionCallbacksUntilMs = 0L

    // -------------------------------------------------------------------------
    // Minimal stubs to keep compilation working after API migration
    // -------------------------------------------------------------------------

    private fun setupSettingsControls() {
        // No-op: UI wiring is handled elsewhere.
    }

    private fun loadSettingsToUI() {
        // No-op: settings are already loaded as part of setupUI().
    }

    private fun populateLocaleSpinners() {
        // No-op: leave existing spinner contents as-is.
    }

    private fun restoreLocaleAndVoiceSelection(
        localeSpinner: android.widget.Spinner,
        voiceSpinner: android.widget.Spinner,
        savedLocale: String?,
        savedVoice: String?
    ) {
        // Best-effort restore: if options exist, try to select saved values.
        try {
            if (!savedLocale.isNullOrBlank()) {
                val adapter = localeSpinner.adapter
                for (i in 0 until adapter.count) {
                    if (adapter.getItem(i)?.toString() == savedLocale) {
                        localeSpinner.setSelection(i)
                        break
                    }
                }
            }
            if (!savedVoice.isNullOrBlank()) {
                val adapter = voiceSpinner.adapter
                for (i in 0 until adapter.count) {
                    if (adapter.getItem(i)?.toString() == savedVoice) {
                        voiceSpinner.setSelection(i)
                        break
                    }
                }
            }
        } catch (_: Exception) {
        }
    }

    private fun updateStrategyDesc(level: Int) {
        // Best-effort: find matching strategy and show description.
        val match = strategies.firstOrNull { it.level == level }
        binding.tvStrategyDesc.text = match?.description ?: ""
    }

    private fun refreshRecentJobsUI() {
        // No-op: recent jobs UI is optional.
    }

    private fun autoSaveSettings(forceCommit: Boolean = false) {
        // No-op: settings persistence handled elsewhere.
    }

    private data class _VoiceOption(val id: String)

    private fun getSelectedVoiceOption(spinner: android.widget.Spinner, locale: String?): _VoiceOption? {
        val value = spinner.selectedItem?.toString() ?: return null
        if (value.isBlank()) return null
        return _VoiceOption(value)
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

        binding.tvBuildInfo.text = "Build: ${BuildConfig.BUILD_VERSION}"

        suppressAutoSave = true
        setupSettingsControls()
        loadSettingsToUI()
        suppressAutoSave = false
        clearAllStateOnServerSwitchIfNeeded()
        loadCachedVoicesAndStrategiesIntoUI()
        fetchVoicesAndStrategiesIfMissing()
        setupUI()
        handleIntent(intent)
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
                val savedLocale = prefs.getString("locale", null)
                val savedVoice = prefs.getString("voice", null)
                val savedTakeawaysLocale = prefs.getString("takeaways_locale", savedLocale)
                val savedTakeawaysVoice = prefs.getString("takeaways_voice", savedVoice)
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

        // Set loading states
        val loadingLocaleAdapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, listOf("Loading..."))
        loadingLocaleAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        binding.spinnerLocale.adapter = loadingLocaleAdapter
        binding.spinnerTakeawaysLocale.adapter = loadingLocaleAdapter

        val loadingVoiceAdapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, listOf("Select language"))
        loadingVoiceAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        binding.spinnerVoice.adapter = loadingVoiceAdapter
        binding.spinnerTakeawaysVoice.adapter = loadingVoiceAdapter

        binding.tvStrategyDesc.text = "Loading..."

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
            } catch (_: Exception) {
                Log.w(logTag, "METADATA_CACHE: voices_fetch_failed")
                apiLog(serverUrl, "metadata_voices_fetch_failed", mapOf("lang" to userLanguage))
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
            } catch (_: Exception) {
                Log.w(logTag, "METADATA_CACHE: strategies_fetch_failed")
                apiLog(serverUrl, "metadata_strategies_fetch_failed")
            }
        }

        runOnUiThread {
            loadCachedVoicesAndStrategiesIntoUI()
        }
    }

    override fun onResume() {
        super.onResume()
        refreshRecentJobsUI()
    }

    override fun onPause() {
        autoSaveSettings(forceCommit = true)
        super.onPause()
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        intent?.let { handleIntent(it) }
    }

    override fun onDestroy() {
        super.onDestroy()
        isPolling = false
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
            isPolling = false
            updateUI(if (currentVideoUrl != null) AppState.READY else AppState.NO_URL)
        }
        binding.btnWatch.setOnClickListener {
            currentJobId?.let { jobId -> openCurrentResult(jobId) }
        }

        // Default to condense mode
        binding.toggleMode.check(binding.btnModeCondense.id)
        switchMode("condense")
    }

    private fun switchMode(mode: String) {
        appMode = mode
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
            isPolling = false
            currentJobId = null
            updateUI(if (currentVideoUrl != null) AppState.READY else AppState.NO_URL)
        }
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
            }
        }
    }

    // -------------------------------------------------------------------------
    // Intent Handling — stores URL but does NOT auto-start condensing
    // -------------------------------------------------------------------------

    private fun handleIntent(intent: Intent) {
        // Stop any in-progress job when a new share arrives
        isPolling = false

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
        val voice = prefs.getString("voice", "") ?: ""
        val speechSpeed = prefs.getFloat("speech_speed", 1.10f)
        val videoMode = prefs.getString("video_mode", "slideshow") ?: "slideshow"
        val prependIntro = prefs.getBoolean("prepend_intro", false)

        currentVideoMode = videoMode
        currentJobType = "condense"
        currentOutputFormat = if (videoMode == "audio_only") "audio" else "video"

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
                val response = api.createJob(req)
                ensureServerMetadataLoadedAfterSuccessfulContact(serverUrl)
                currentJobId = response.id
                updateUI(AppState.PROCESSING, statusText = "Processing video...\nJob ID: ${response.id}")
                startPolling()
            } catch (e: Exception) {
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
        val topValue = takeawaysTopValues.getOrNull(binding.spinnerTakeawaysTop.selectedItemPosition) ?: "auto"
        val top = if (topValue == "auto") null else topValue.toIntOrNull()

        val format = takeawaysFormatValues.getOrNull(binding.spinnerTakeawaysFormat.selectedItemPosition) ?: "text"

        val voice = if (format == "audio") {
            val savedVoice = prefs.getString("takeaways_voice", null)
            val selectedLocale = binding.spinnerTakeawaysLocale.selectedItem as? String
            val selected = if (!savedVoice.isNullOrBlank()) savedVoice else getSelectedVoiceOption(binding.spinnerTakeawaysVoice, selectedLocale)?.id
            selected
        } else null

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
                val response = api.createJob(req)
                ensureServerMetadataLoadedAfterSuccessfulContact(serverUrl)
                currentJobId = response.id
                updateUI(AppState.PROCESSING, statusText = "Extracting takeaways...\nJob ID: ${response.id}")
                startPolling()
            } catch (e: Exception) {
                updateUI(AppState.ERROR, statusText = "Failed to submit: ${e.message}")
            }
        }
    }

    private fun startPolling() {
        isPolling = true

        lifecycleScope.launch {
            val api = createApi()
            ensureServerMetadataLoadedAfterSuccessfulContact(getServerUrl())
            while (isPolling) {
                try {
                    val job = api.getJob(currentJobId!!)
                    updateJobUI(job)
                } catch (e: Exception) {
                    // Check if it's a 404 error
                    if (e is retrofit2.HttpException && e.code() == 404) {
                        isPolling = false
                        val missingId = currentJobId
                        currentJobId = null
                        updateUI(
                            AppState.ERROR,
                            statusText = "Job ${missingId ?: "(unknown)"} not found on server"
                        )
                    }
                    // Keep polling on other network errors — mirrors Chrome popup behavior
                }

                if (isPolling) delay(3000)
            }
        }
    }

    private fun updateJobUI(job: JobResponse) {
        when (job.status) {
            "processing" -> {
                updateUI(AppState.PROCESSING, statusText = "Processing video...\nJob ID: ${job.id}")
            }
            "completed" -> {
                updateUI(AppState.COMPLETED, statusText = "✅ Ready!\nJob ID: ${job.id}")
            }
            "error" -> {
                updateUI(AppState.ERROR, statusText = "Processing failed: ${job.error ?: "Unknown error"}")
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
        getSharedPreferences(prefsName, Context.MODE_PRIVATE)
            .getString("server_url", ConciserApi.DEFAULT_URL) ?: ConciserApi.DEFAULT_URL

    private fun convertSpeedToRate(speed: Float): String {
        val percentage = ((speed - 1.0f) * 100).roundToInt()
        return if (percentage >= 0) "+${percentage}%" else "${percentage}%"
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
