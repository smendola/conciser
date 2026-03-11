package com.nbj

import android.content.Context
import android.content.Intent
import android.graphics.Typeface
import android.text.SpannableString
import android.text.Spanned
import android.text.style.StyleSpan
import android.net.Uri
import android.os.Bundle
import android.os.SystemClock
import android.util.TypedValue
import android.util.Log
import android.view.Gravity
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.LinearLayout
import android.widget.SeekBar
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import com.nbj.databinding.ActivityMainBinding
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import retrofit2.HttpException
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

        // Display build timestamp
        binding.tvBuildInfo.text = "Build: ${BuildConfig.BUILD_TIMESTAMP}"

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

                Log.i(logTag, "METADATA_CACHE: restore_settings condenseLocale=$savedLocale condenseVoice=$savedVoice takeawaysLocale=$savedTakeawaysLocale takeawaysVoice=$savedTakeawaysVoice")
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

        val request = CondenseRequest(
            url = url,
            aggressiveness = aggressiveness,
            voice = voice,
            speech_rate = convertSpeedToRate(speechSpeed),
            video_mode = videoMode,
            prepend_intro = prependIntro
        )

        lifecycleScope.launch {
            try {
                val api = ConciserApi.createService(serverUrl, clientId)
                val response = api.condenseVideo(request)
                ensureServerMetadataLoadedAfterSuccessfulContact(serverUrl)
                currentJobId = response.job_id

                updateUI(
                    AppState.PROCESSING,
                    statusText = "Processing video...\nJob ID: ${response.job_id}"
                )
                startPolling(response.job_id, serverUrl)

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

        val request = TakeawaysRequest(
            url = url,
            top = top,
            format = format,
            voice = voice
        )

        lifecycleScope.launch {
            try {
                val api = ConciserApi.createService(serverUrl, clientId)
                val response = api.extractTakeaways(request)
                ensureServerMetadataLoadedAfterSuccessfulContact(serverUrl)
                currentJobId = response.job_id

                updateUI(
                    AppState.PROCESSING,
                    statusText = "Extracting takeaways...\nJob ID: ${response.job_id}"
                )
                startPolling(response.job_id, serverUrl)

            } catch (e: Exception) {
                updateUI(AppState.ERROR, statusText = "Failed to submit: ${e.message}")
            }
        }
    }

    private fun startPolling(jobId: String, serverUrl: String) {
        isPolling = true

        lifecycleScope.launch {
            val api = ConciserApi.createService(serverUrl, ClientIdentity.getOrCreate(this@MainActivity))
            ensureServerMetadataLoadedAfterSuccessfulContact(serverUrl)
            while (isPolling) {
                try {
                    val status = api.getStatus(jobId)

                    when (status.status) {
                        "completed" -> {
                            isPolling = false
                            updateUI(AppState.COMPLETED)
                            addCurrentJobToRecents()
                        }
                        "error" -> {
                            isPolling = false
                            updateUI(
                                AppState.ERROR,
                                statusText = "Processing failed: ${status.error ?: "Unknown error"}"
                            )
                        }
                        "processing" -> {
                            updateUI(
                                AppState.PROCESSING,
                                statusText = if (currentJobType == "takeaways") {
                                    "Extracting takeaways...\nJob ID: $jobId"
                                } else {
                                    "Processing video...\nJob ID: $jobId"
                                },
                                progressText = status.progress
                            )
                        }
                        else -> {
                            updateUI(
                                AppState.PROCESSING,
                                statusText = "Status: ${status.status}",
                                progressText = null
                            )
                        }
                    }
                } catch (e: Exception) {
                    // Check if it's a 404 error
                    if (e is retrofit2.HttpException && e.code() == 404) {
                        isPolling = false
                        currentJobId = null
                        updateUI(
                            AppState.ERROR,
                            statusText = "Job $jobId not found on server"
                        )
                    }
                    // Keep polling on other network errors — mirrors Chrome popup behavior
                }

                if (isPolling) delay(3000)
            }
        }
    }

    // -------------------------------------------------------------------------
    // Playback
    // -------------------------------------------------------------------------

    private fun openCurrentResult(jobId: String) {
        val clientId = ClientIdentity.getOrCreate(this)
        val videoUrl = ConciserApi.getFullOpenUrl(getServerUrl(), jobId, clientId)

        val intent = Intent(Intent.ACTION_VIEW).apply {
            data = Uri.parse(videoUrl)
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
        }

        try {
            startActivity(intent)
        } catch (e: Exception) {
            val msg = if (currentOutputFormat == "text") {
                "No browser found."
            } else {
                "No media player found. Please install a media player app."
            }
            Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
        }
    }

    // -------------------------------------------------------------------------
    // Settings Controls
    // -------------------------------------------------------------------------

    private fun setupSettingsControls() {
        val adapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, videoModeLabels)
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        binding.spinnerVideoMode.adapter = adapter
        binding.spinnerVideoMode.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                autoSaveSettings()
            }
            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }

        binding.spinnerLocale.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                val selectedLocale = parent?.getItemAtPosition(position) as? String
                if (selectedLocale != null) {
                    if (shouldIgnoreVoiceSelectionCallbacks()) return
                    updateVoiceSpinner(selectedLocale, binding.spinnerVoice)
                    autoSaveSettings()
                }
            }
            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }

        binding.spinnerVoice.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                if (shouldIgnoreVoiceSelectionCallbacks()) return
                persistVoiceSelection("locale", "voice", binding.spinnerLocale.selectedItem as? String, position)
                autoSaveSettings()
            }
            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }

        binding.seekbarAggressiveness.max = 9
        binding.seekbarAggressiveness.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                val level = progress + 1
                binding.tvAggressivenessValue.text = level.toString()
                updateStrategyDesc(level)
                if (fromUser) autoSaveSettings()
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) {}
        })

        binding.seekbarSpeechSpeed.max = 110
        binding.seekbarSpeechSpeed.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                val speed = 0.90f + progress * 0.01f
                binding.tvSpeechSpeedValue.text = String.format("%.2fx", speed)
                if (fromUser) autoSaveSettings()
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) {}
        })

        binding.switchPrependIntro.setOnCheckedChangeListener { _, _ -> autoSaveSettings() }

        // Takeaways settings
        val topAdapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, takeawaysTopLabels)
        topAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        binding.spinnerTakeawaysTop.adapter = topAdapter
        binding.spinnerTakeawaysTop.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                autoSaveSettings()
            }
            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }

        val formatAdapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, takeawaysFormatLabels)
        formatAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        binding.spinnerTakeawaysFormat.adapter = formatAdapter
        binding.spinnerTakeawaysFormat.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                // Show/hide voice selector based on format
                val isAudio = takeawaysFormatValues.getOrNull(position) == "audio"
                binding.layoutTakeawaysVoice.visibility = if (isAudio) View.VISIBLE else View.GONE
                autoSaveSettings()
            }
            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }

        binding.spinnerTakeawaysLocale.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                val selectedLocale = parent?.getItemAtPosition(position) as? String
                if (selectedLocale != null) {
                    if (shouldIgnoreTakeawaysVoiceCallbacks()) return
                    updateVoiceSpinner(selectedLocale, binding.spinnerTakeawaysVoice)
                    autoSaveSettings()
                }
            }
            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }

        // Takeaways voice shares same list as condense voice
        binding.spinnerTakeawaysVoice.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                if (shouldIgnoreTakeawaysVoiceCallbacks()) return
                persistVoiceSelection("takeaways_locale", "takeaways_voice", binding.spinnerTakeawaysLocale.selectedItem as? String, position)
                autoSaveSettings()
            }
            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }
    }

    private fun loadSettingsToUI() {
        val prefs = getSharedPreferences(prefsName, Context.MODE_PRIVATE)

        val videoMode = prefs.getString("video_mode", "slideshow") ?: "slideshow"
        binding.spinnerVideoMode.setSelection(videoModeValues.indexOf(videoMode).coerceAtLeast(0))

        val aggressiveness = prefs.getInt("aggressiveness", 5)
        binding.seekbarAggressiveness.progress = (aggressiveness - 1).coerceIn(0, 9)
        binding.tvAggressivenessValue.text = aggressiveness.toString()

        val speechSpeed = prefs.getFloat("speech_speed", 1.10f)
        val speedProgress = ((speechSpeed - 0.90f) / 0.01f).roundToInt().coerceIn(0, 110)
        binding.seekbarSpeechSpeed.progress = speedProgress
        binding.tvSpeechSpeedValue.text = String.format("%.2fx", speechSpeed)

        binding.switchPrependIntro.isChecked = prefs.getBoolean("prepend_intro", false)

        val takeawaysTop = prefs.getString("takeaways_top", "auto") ?: "auto"
        binding.spinnerTakeawaysTop.setSelection(takeawaysTopValues.indexOf(takeawaysTop).coerceAtLeast(0))

        val takeawaysFormat = prefs.getString("takeaways_format", "text") ?: "text"
        val takeawaysFormatIndex = takeawaysFormatValues.indexOf(takeawaysFormat).coerceAtLeast(0)
        binding.spinnerTakeawaysFormat.setSelection(takeawaysFormatIndex)

        val isAudio = takeawaysFormatValues.getOrNull(takeawaysFormatIndex) == "audio"
        binding.layoutTakeawaysVoice.visibility = if (isAudio) View.VISIBLE else View.GONE
    }

    // Voices/strategies are loaded from local cache on start; if missing they are fetched once and persisted.

    private fun updateStrategyDesc(level: Int) {
        if (strategies.isEmpty()) return
        val strategy = strategies.find { it.level == level }
            ?: strategies.minByOrNull { kotlin.math.abs(it.level - level) }
            ?: return
        val match = Regex("""\(([^)]+)\)""").find(strategy.description)
        binding.tvStrategyDesc.text = match?.groupValues?.get(1) ?: strategy.description
    }

    private fun populateLocaleSpinners() {
        val locales = voices.map { it.locale }.toSortedSet().toList()
        if (locales.isEmpty()) return

        val localeAdapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, locales)
        localeAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)

        binding.spinnerLocale.adapter = localeAdapter
        binding.spinnerTakeawaysLocale.adapter = localeAdapter
    }

    private fun updateVoiceSpinner(locale: String, spinner: android.widget.Spinner) {
        val voiceNames = getVoiceOptionsForLocale(locale).map { it.displayName }
        val adapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, voiceNames)
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        spinner.adapter = adapter
    }

    private fun restoreLocaleAndVoiceSelection(
        localeSpinner: android.widget.Spinner,
        voiceSpinner: android.widget.Spinner,
        savedLocale: String?,
        savedVoice: String?
    ) {
        val locales = voices.map { it.locale }.toSortedSet().toList()
        if (locales.isEmpty()) return

        val savedVoiceItem = savedVoice?.let { voiceName ->
            voices.find { it.name == voiceName }
        }
        val localeToSelect = when {
            savedVoiceItem != null && locales.contains(savedVoiceItem.locale) -> savedVoiceItem.locale
            savedLocale != null && locales.contains(savedLocale) -> savedLocale
            savedLocale != null -> locales.find { it.startsWith(savedLocale.substringBefore("-")) }
            else -> locales.find { it.startsWith(Locale.getDefault().language) }
        } ?: locales.first()

        val localeIndex = locales.indexOf(localeToSelect)
        localeSpinner.setSelection(localeIndex)

        if (savedVoiceItem != null) {
            val voiceOptions = getVoiceOptionsForLocale(localeToSelect)
            val voiceIndex = findSavedVoiceOptionIndex(voiceOptions, savedVoiceItem)
            if (voiceIndex >= 0) {
                voiceSpinner.setSelection(voiceIndex)
            }
        }
    }

    private fun findSavedVoiceOptionIndex(
        voiceOptions: List<VoiceOption>,
        savedVoiceItem: VoiceItem
    ): Int {
        val savedId = savedVoiceItem.name
        val exactIdIndex = voiceOptions.indexOfFirst { it.id == savedId }
        if (exactIdIndex >= 0) return exactIdIndex

        val savedDisplayName = buildVoiceDisplayName(savedVoiceItem)
        return voiceOptions.indexOfFirst { it.displayName == savedDisplayName }
    }

    private fun getSelectedVoiceOption(
        spinner: android.widget.Spinner,
        locale: String?
    ): VoiceOption? {
        if (locale.isNullOrBlank()) return null
        val selectedDisplayName = spinner.selectedItem as? String ?: return null
        val selected = getVoiceOptionsForLocale(locale).firstOrNull { it.displayName == selectedDisplayName }
        return selected
    }

    private fun persistVoiceSelection(
        localeKey: String,
        voiceKey: String,
        locale: String?,
        position: Int
    ) {
        if (suppressAutoSave || shouldIgnoreVoiceSelectionCallbacks() || locale.isNullOrBlank()) return
        val selectedVoiceOption = getVoiceOptionsForLocale(locale).getOrNull(position) ?: return
        getSharedPreferences(prefsName, Context.MODE_PRIVATE)
            .edit()
            .putString(localeKey, selectedVoiceOption.voice.locale)
            .putString(voiceKey, selectedVoiceOption.id)
            .apply()
    }

    private fun shouldIgnoreVoiceSelectionCallbacks(): Boolean {
        return restoringVoiceSelections || SystemClock.elapsedRealtime() < blockVoiceSelectionCallbacksUntilMs
    }

    private fun shouldIgnoreTakeawaysVoiceCallbacks(): Boolean {
        if (shouldIgnoreVoiceSelectionCallbacks()) return true
        val isAudio = takeawaysFormatValues.getOrNull(binding.spinnerTakeawaysFormat.selectedItemPosition) == "audio"
        return !isAudio || binding.layoutTakeawaysVoice.visibility != View.VISIBLE
    }

    private fun getVoiceOptionsForLocale(locale: String): List<VoiceOption> {
        val seenDisplayNames = TreeSet(String.CASE_INSENSITIVE_ORDER)

        return voices
            .asSequence()
            .filter { it.locale == locale }
            .sortedWith(
                compareBy<VoiceItem> { normalizeFriendlyVoiceName(it.friendly_name) }
                    .thenBy { normalizeGender(it.gender) }
                    .thenBy { it.name }
            )
            .map { voice ->
                VoiceOption(
                    id = voice.name,
                    displayName = buildVoiceDisplayName(voice),
                    voice = voice
                )
            }
            .filter { seenDisplayNames.add(it.displayName) }
            .toList()
    }

    private fun buildVoiceDisplayName(voice: VoiceItem): String {
        val baseName = normalizeFriendlyVoiceName(voice.friendly_name)
        val gender = normalizeGender(voice.gender)
        return if (gender.isEmpty()) baseName else "$baseName ($gender)"
    }

    private fun normalizeFriendlyVoiceName(name: String): String {
        return name.trim().replace(Regex("\\s+"), " ")
    }

    private fun normalizeGender(gender: String?): String {
        return when (gender?.trim()?.lowercase()) {
            "male" -> "Male"
            "female" -> "Female"
            else -> gender?.trim().orEmpty()
        }
    }

    private fun autoSaveSettings(forceCommit: Boolean = false) {
        if (suppressAutoSave) return

        val prefs = getSharedPreferences(prefsName, Context.MODE_PRIVATE).edit()
        val availableLocales = voices.map { it.locale }.toSet()

        // Condense settings
        prefs.putString("video_mode", videoModeValues.getOrElse(binding.spinnerVideoMode.selectedItemPosition) { "slideshow" })
        prefs.putInt("aggressiveness", binding.seekbarAggressiveness.progress + 1)
        prefs.putFloat("speech_speed", 0.90f + binding.seekbarSpeechSpeed.progress * 0.01f)
        prefs.putBoolean("prepend_intro", binding.switchPrependIntro.isChecked)

        val selectedLocale = binding.spinnerLocale.selectedItem as? String
        val selectedVoiceOption = selectedLocale
            ?.takeIf { it in availableLocales }
            ?.let { locale -> getSelectedVoiceOption(binding.spinnerVoice, locale) }
        if (selectedVoiceOption != null) {
            prefs.putString("locale", selectedVoiceOption.voice.locale)
            prefs.putString("voice", selectedVoiceOption.id)
        } else if (selectedLocale != null && selectedLocale in availableLocales) {
            prefs.putString("locale", selectedLocale)
        }

        // Takeaways settings
        prefs.putString("takeaways_top", takeawaysTopValues.getOrElse(binding.spinnerTakeawaysTop.selectedItemPosition) { "auto" })
        prefs.putString("takeaways_format", takeawaysFormatValues.getOrElse(binding.spinnerTakeawaysFormat.selectedItemPosition) { "text" })

        val selectedTakeawaysLocale = binding.spinnerTakeawaysLocale.selectedItem as? String
        val selectedTakeawaysVoiceOption = selectedTakeawaysLocale
            ?.takeIf { it in availableLocales }
            ?.let { locale -> getSelectedVoiceOption(binding.spinnerTakeawaysVoice, locale) }
        if (selectedTakeawaysVoiceOption != null) {
            prefs.putString("takeaways_locale", selectedTakeawaysVoiceOption.voice.locale)
            prefs.putString("takeaways_voice", selectedTakeawaysVoiceOption.id)
        } else if (selectedTakeawaysLocale != null && selectedTakeawaysLocale in availableLocales) {
            prefs.putString("takeaways_locale", selectedTakeawaysLocale)
        }

        if (forceCommit) {
            prefs.commit()
        } else {
            prefs.apply()
        }
    }

    // -------------------------------------------------------------------------
    // Recent Jobs
    // -------------------------------------------------------------------------

    private fun addCurrentJobToRecents() {
        val jobId = currentJobId ?: return
        val videoId = currentVideoUrl?.let { extractVideoId(it) }
        val title = currentVideoTitle ?: (if (videoId != null) "Video: $videoId" else currentVideoUrl ?: jobId)
        val job = RecentJob(
            jobId = jobId,
            title = title,
            videoMode = currentVideoMode,
            serverUrl = getServerUrl(),
            jobType = currentJobType,
            outputFormat = currentOutputFormat
        )
        val jobs = loadRecentJobs().toMutableList()
        jobs.removeAll { it.jobId == jobId }  // de-dupe
        jobs.add(0, job)
        saveRecentJobs(jobs.take(10))
        refreshRecentJobsUI()
    }

    private fun loadRecentJobs(): List<RecentJob> {
        val json = getSharedPreferences("nbj_prefs", Context.MODE_PRIVATE)
            .getString("recent_jobs", null) ?: return emptyList()
        return try {
            val type = object : TypeToken<List<RecentJob>>() {}.type
            (Gson().fromJson<List<RecentJob>>(json, type) ?: emptyList())
                .sortedByDescending { it.addedAt }
        } catch (e: Exception) {
            emptyList()
        }
    }

    private fun saveRecentJobs(jobs: List<RecentJob>) {
        getSharedPreferences("nbj_prefs", Context.MODE_PRIVATE).edit()
            .putString("recent_jobs", Gson().toJson(jobs))
            .apply()
    }

    private fun refreshRecentJobsUI() {
        val jobs = loadRecentJobs()
        val container = binding.layoutRecentJobs
        container.removeAllViews()

        if (jobs.isEmpty()) {
            binding.tvRecentJobsHeader.visibility = View.GONE
            return
        }
        binding.tvRecentJobsHeader.visibility = View.VISIBLE

        val dp = resources.displayMetrics.density
        val dateFormat = SimpleDateFormat("MMM d, h:mm a", Locale.getDefault())

        for (job in jobs) {
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(0, (10 * dp).toInt(), 0, (10 * dp).toInt())
                isClickable = true
                isFocusable = true
                val tv = TypedValue()
                context.theme.resolveAttribute(android.R.attr.selectableItemBackground, tv, true)
                setBackgroundResource(tv.resourceId)
                setOnClickListener { openRecentJob(job) }
            }

            // Mode badge
            val badge = TextView(this).apply {
                text = when (job.outputFormat) {
                    "text" -> "TXT"
                    "audio" -> "MP3"
                    else -> "MP4"
                }
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 9f)
                setTypeface(null, Typeface.BOLD)
                setTextColor(0xFFFFFFFF.toInt())
                val bg = when (job.outputFormat) {
                    "text" -> 0xFF212121.toInt()
                    "audio" -> 0xFF28a745.toInt()
                    else -> 0xFF1a73e8.toInt()
                }
                setBackgroundColor(bg)
                setPadding((4 * dp).toInt(), (2 * dp).toInt(), (4 * dp).toInt(), (2 * dp).toInt())
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.WRAP_CONTENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).also { it.marginEnd = (8 * dp).toInt() }
            }

            // Title + timestamp stacked vertically
            val textCol = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            }
            val titleView = TextView(this).apply {
                text = job.title
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
                setTextColor(0xFF212121.toInt())
                maxLines = 1
                ellipsize = android.text.TextUtils.TruncateAt.END
            }
            val timeView = TextView(this).apply {
                text = dateFormat.format(Date(job.addedAt))
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 10f)
                setTextColor(0xFF757575.toInt())
            }
            textCol.addView(titleView)
            textCol.addView(timeView)

            row.addView(badge)
            row.addView(textCol)

            val deleteBtn = TextView(this).apply {
                text = "×"
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
                setTextColor(0xFF999999.toInt())
                setPadding((8 * dp).toInt(), (0 * dp).toInt(), (8 * dp).toInt(), (0 * dp).toInt())
                isClickable = true
                isFocusable = true
                contentDescription = "Delete"
                setOnClickListener {
                    lifecycleScope.launch {
                        try {
                            val clientId = ClientIdentity.getOrCreate(this@MainActivity)
                            val service = ConciserApi.createService(job.serverUrl, clientId)
                            service.deleteJob(job.jobId)
                        } catch (e: Exception) {
                            // ignore
                        }

                        val updated = loadRecentJobs().filterNot { it.jobId == job.jobId }
                        saveRecentJobs(updated)
                        refreshRecentJobsUI()
                    }
                }
                setOnTouchListener { v, event ->
                    v.onTouchEvent(event)
                    true
                }
            }

            row.addView(deleteBtn)
            container.addView(row)

            // Divider (except after last row)
            if (job != jobs.last()) {
                val divider = View(this).apply {
                    layoutParams = LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT, (1 * dp).toInt()
                    )
                    setBackgroundColor(0xFFEEEEEE.toInt())
                }
                container.addView(divider)
            }
        }

        // Background: prune deleted files silently
        lifecycleScope.launch {
            val clientId = ClientIdentity.getOrCreate(this@MainActivity)
            val surviving = jobs.filter { job ->
                val url = ConciserApi.getFullDownloadUrl(job.serverUrl, job.jobId, clientId)
                ConciserApi.checkFileExists(url)
            }
            if (surviving.size < jobs.size) {
                saveRecentJobs(surviving)
                refreshRecentJobsUI()
            }
        }
    }

    private fun openRecentJob(job: RecentJob) {
        val clientId = ClientIdentity.getOrCreate(this)
        val videoUrl = ConciserApi.getFullOpenUrl(job.serverUrl, job.jobId, clientId)
        val intent = Intent(Intent.ACTION_VIEW).apply {
            data = Uri.parse(videoUrl)
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
        }
        try {
            startActivity(intent)
        } catch (e: Exception) {
            val msg = if (job.outputFormat == "text") "No browser found." else "No media player found."
            Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
        }
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
