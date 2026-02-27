package com.nbj

import android.content.Context
import android.content.Intent
import android.graphics.Typeface
import android.net.Uri
import android.os.Bundle
import android.util.TypedValue
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
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.roundToInt

class MainActivity : AppCompatActivity() {

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
    private var currentJobId: String? = null
    private var currentVideoMode: String = "slideshow"
    private var isPolling = false

    private var voices: List<VoiceItem> = emptyList()
    private var strategies: List<StrategyItem> = emptyList()

    private val videoModeValues = listOf("slideshow", "audio_only")
    private val videoModeLabels = listOf("Slideshow", "Audio Only (MP3)")

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

        setupSettingsControls()
        loadSettingsToUI()
        fetchVoicesAndStrategies()
        setupUI()
        handleIntent(intent)
    }

    override fun onResume() {
        super.onResume()
        refreshRecentJobsUI()
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
        binding.btnCondense.setOnClickListener {
            currentVideoUrl?.let { url -> submitCondense(url) }
        }
        binding.btnCancel.setOnClickListener {
            isPolling = false
            updateUI(if (currentVideoUrl != null) AppState.READY else AppState.NO_URL)
        }
        binding.btnWatch.setOnClickListener {
            currentJobId?.let { jobId -> playVideo(jobId) }
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
                binding.btnCondense.visibility = View.VISIBLE
                binding.btnCondense.isEnabled = false
                binding.layoutStatus.visibility = View.GONE
                binding.btnCancel.visibility = View.GONE
                binding.btnWatch.visibility = View.GONE
            }

            AppState.READY -> {
                binding.btnCondense.visibility = View.VISIBLE
                binding.btnCondense.isEnabled = true
                binding.layoutStatus.visibility = View.GONE
                binding.btnCancel.visibility = View.GONE
                binding.btnWatch.visibility = View.GONE
            }

            AppState.SUBMITTING -> {
                binding.btnCondense.visibility = View.VISIBLE
                binding.btnCondense.isEnabled = false
                binding.layoutStatus.visibility = View.VISIBLE
                binding.layoutStatus.setBackgroundColor(STATUS_BG_SUBMITTING)
                binding.tvStatus.text = statusText ?: "Submitting..."
                binding.tvProgress.visibility = View.GONE
                binding.btnCancel.visibility = View.VISIBLE
                binding.btnWatch.visibility = View.GONE
            }

            AppState.PROCESSING -> {
                binding.btnCondense.visibility = View.VISIBLE
                binding.btnCondense.isEnabled = false
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
                // btnCondense is GONE on completion — same as Chrome popup (display:none)
                binding.btnCondense.visibility = View.GONE
                binding.layoutStatus.visibility = View.VISIBLE
                binding.layoutStatus.setBackgroundColor(STATUS_BG_COMPLETED)
                binding.tvStatus.text = statusText ?: "✅ Video ready!\nJob ID: $currentJobId"
                binding.tvProgress.visibility = View.GONE
                binding.btnCancel.visibility = View.GONE
                binding.btnWatch.visibility = View.VISIBLE
            }

            AppState.ERROR -> {
                // Re-enable condense so user can retry — mirrors Chrome's resetButton()
                binding.btnCondense.visibility = View.VISIBLE
                binding.btnCondense.isEnabled = currentVideoUrl != null
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
            currentJobId = null
            val videoId = extractVideoId(url)
            binding.tvVideoInfo.text = if (videoId != null) "Video: $videoId" else url
            updateUI(AppState.READY)
            // Fetch title asynchronously and update below the ID
            lifecycleScope.launch {
                val title = ConciSerApi.fetchVideoTitle(url)
                if (title != null && currentVideoUrl == url) {
                    binding.tvVideoInfo.text = if (videoId != null) "Video: $videoId\n$title" else title
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

        val prefs = getSharedPreferences("nbj_prefs", Context.MODE_PRIVATE)
        val serverUrl = prefs.getString("server_url", ConciSerApi.DEFAULT_URL) ?: ConciSerApi.DEFAULT_URL
        val aggressiveness = prefs.getInt("aggressiveness", 5)
        val voice = prefs.getString("voice", "") ?: ""
        val speechSpeed = prefs.getFloat("speech_speed", 1.10f)
        val videoMode = prefs.getString("video_mode", "slideshow") ?: "slideshow"

        currentVideoMode = videoMode

        val request = CondenseRequest(
            url = url,
            aggressiveness = aggressiveness,
            voice = voice,
            speech_rate = convertSpeedToRate(speechSpeed),
            video_mode = videoMode
        )

        lifecycleScope.launch {
            try {
                val api = ConciSerApi.createService(serverUrl)
                val response = api.condenseVideo(request)
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

    private fun startPolling(jobId: String, serverUrl: String) {
        isPolling = true

        lifecycleScope.launch {
            val api = ConciSerApi.createService(serverUrl)
            while (isPolling) {
                try {
                    val status = api.getStatus(jobId)

                    when (status.status) {
                        "completed" -> {
                            isPolling = false
                            updateUI(AppState.COMPLETED)
                            addCurrentJobToRecents()
                            // Auto-launch player immediately — key Android difference vs extension
                            playVideo(jobId)
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
                                statusText = "Processing video...\nJob ID: $jobId",
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
                    // Keep polling on transient network errors — mirrors Chrome popup behavior
                }

                if (isPolling) delay(3000)
            }
        }
    }

    // -------------------------------------------------------------------------
    // Playback
    // -------------------------------------------------------------------------

    private fun playVideo(jobId: String) {
        val videoUrl = ConciSerApi.getFullDownloadUrl(getServerUrl(), jobId)
        val mimeType = if (currentVideoMode == "audio_only") "audio/mpeg" else "video/mp4"

        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(Uri.parse(videoUrl), mimeType)
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
        }

        try {
            startActivity(intent)
        } catch (e: Exception) {
            Toast.makeText(this, "No media player found. Please install a media player app.", Toast.LENGTH_LONG).show()
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

        binding.spinnerVoice.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
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
    }

    private fun loadSettingsToUI() {
        val prefs = getSharedPreferences("nbj_prefs", Context.MODE_PRIVATE)

        val videoMode = prefs.getString("video_mode", "slideshow") ?: "slideshow"
        binding.spinnerVideoMode.setSelection(videoModeValues.indexOf(videoMode).coerceAtLeast(0))

        val aggressiveness = prefs.getInt("aggressiveness", 5)
        binding.seekbarAggressiveness.progress = (aggressiveness - 1).coerceIn(0, 9)
        binding.tvAggressivenessValue.text = aggressiveness.toString()

        val speechSpeed = prefs.getFloat("speech_speed", 1.10f)
        val speedProgress = ((speechSpeed - 0.90f) / 0.01f).roundToInt().coerceIn(0, 110)
        binding.seekbarSpeechSpeed.progress = speedProgress
        binding.tvSpeechSpeedValue.text = String.format("%.2fx", speechSpeed)
    }

    private fun fetchVoicesAndStrategies() {
        val serverUrl = getServerUrl()
        val locale = Locale.getDefault().language
        val savedVoice = getSharedPreferences("nbj_prefs", Context.MODE_PRIVATE).getString("voice", "") ?: ""

        val loadingAdapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, listOf("Loading voices..."))
        loadingAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        binding.spinnerVoice.adapter = loadingAdapter
        binding.tvStrategyDesc.text = "Loading..."

        lifecycleScope.launch {
            val api = ConciSerApi.createService(serverUrl)

            try {
                val response = api.getVoices(locale)
                voices = response.voices

                val displayNames = voices.map { "${it.locale} - ${it.friendly_name}" }
                val voiceAdapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_item, displayNames)
                voiceAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
                binding.spinnerVoice.adapter = voiceAdapter

                if (savedVoice.isNotEmpty()) {
                    val idx = voices.indexOfFirst { it.name == savedVoice }
                    if (idx >= 0) binding.spinnerVoice.setSelection(idx)
                }
            } catch (e: Exception) {
                val errorAdapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_item, listOf("Error loading voices"))
                errorAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
                binding.spinnerVoice.adapter = errorAdapter
            }

            try {
                val response = api.getStrategies()
                strategies = response.strategies
                updateStrategyDesc(binding.seekbarAggressiveness.progress + 1)
            } catch (e: Exception) {
                binding.tvStrategyDesc.text = ""
            }
        }
    }

    private fun updateStrategyDesc(level: Int) {
        if (strategies.isEmpty()) return
        val strategy = strategies.find { it.level == level }
            ?: strategies.minByOrNull { kotlin.math.abs(it.level - level) }
            ?: return
        val match = Regex("""\(([^)]+)\)""").find(strategy.description)
        binding.tvStrategyDesc.text = match?.groupValues?.get(1) ?: strategy.description
    }

    private fun autoSaveSettings() {
        val prefs = getSharedPreferences("nbj_prefs", Context.MODE_PRIVATE)
        val videoMode = videoModeValues.getOrElse(binding.spinnerVideoMode.selectedItemPosition) { "slideshow" }
        val aggressiveness = binding.seekbarAggressiveness.progress + 1
        val speechSpeed = 0.90f + binding.seekbarSpeechSpeed.progress * 0.01f
        val voiceName = if (voices.isNotEmpty()) {
            voices.getOrNull(binding.spinnerVoice.selectedItemPosition)?.name ?: prefs.getString("voice", "") ?: ""
        } else {
            prefs.getString("voice", "") ?: ""
        }

        prefs.edit()
            .putString("video_mode", videoMode)
            .putInt("aggressiveness", aggressiveness)
            .putFloat("speech_speed", speechSpeed)
            .putString("voice", voiceName)
            .apply()
    }

    // -------------------------------------------------------------------------
    // Recent Jobs
    // -------------------------------------------------------------------------

    private fun addCurrentJobToRecents() {
        val jobId = currentJobId ?: return
        val title = binding.tvVideoInfo.text.toString()
        val job = RecentJob(
            jobId = jobId,
            title = title,
            videoMode = currentVideoMode,
            serverUrl = getServerUrl()
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
            Gson().fromJson(json, type) ?: emptyList()
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
                text = if (job.videoMode == "audio_only") "MP3" else "MP4"
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 9f)
                setTypeface(null, Typeface.BOLD)
                setTextColor(0xFFFFFFFF.toInt())
                val bg = if (job.videoMode == "audio_only") 0xFF6c757d.toInt() else 0xFF1a73e8.toInt()
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
            val surviving = jobs.filter { job ->
                val url = ConciSerApi.getFullDownloadUrl(job.serverUrl, job.jobId)
                ConciSerApi.checkFileExists(url)
            }
            if (surviving.size < jobs.size) {
                saveRecentJobs(surviving)
                refreshRecentJobsUI()
            }
        }
    }

    private fun openRecentJob(job: RecentJob) {
        val videoUrl = ConciSerApi.getFullDownloadUrl(job.serverUrl, job.jobId)
        val mimeType = if (job.videoMode == "audio_only") "audio/mpeg" else "video/mp4"
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(Uri.parse(videoUrl), mimeType)
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
        }
        try {
            startActivity(intent)
        } catch (e: Exception) {
            Toast.makeText(this, "No media player found.", Toast.LENGTH_SHORT).show()
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
        getSharedPreferences("nbj_prefs", Context.MODE_PRIVATE)
            .getString("server_url", ConciSerApi.DEFAULT_URL) ?: ConciSerApi.DEFAULT_URL

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
