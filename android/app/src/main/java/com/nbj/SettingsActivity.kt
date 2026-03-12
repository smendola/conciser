package com.nbj

import android.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.widget.addTextChangedListener
import androidx.lifecycle.lifecycleScope
import com.nbj.databinding.ActivitySettingsBinding
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class SettingsActivity : AppCompatActivity() {

    private lateinit var binding: ActivitySettingsBinding
    private var pingJob: Job? = null
    private val httpClient: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(5, TimeUnit.SECONDS)
            .readTimeout(5, TimeUnit.SECONDS)
            .build()
    }

    private val presetUrls = listOf(
        "https://x13.puma-garibaldi.ts.net",
        "https://cuda-linux.puma-garibaldi.ts.net"
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySettingsBinding.inflate(layoutInflater)
        setContentView(binding.root)

        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        title = getString(R.string.settings)

        setupSpinner()
        loadSettings()


        binding.btnResetState.setOnClickListener {
            showResetConfirmationDialog()
        }

        binding.etServerUrl.setOnFocusChangeListener { _, hasFocus ->
            if (!hasFocus) {
                val url = binding.etServerUrl.text.toString().trim()
                autoSave(url)
            }
        }
    }

    private fun setupSpinner() {
        val adapter = ArrayAdapter.createFromResource(
            this,
            R.array.server_url_options,
            android.R.layout.simple_spinner_item
        )
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        binding.spinnerServerUrl.adapter = adapter

        binding.spinnerServerUrl.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                when (position) {
                    0 -> {
                        // "Select a server or enter custom URL..."
                        binding.etServerUrl.visibility = View.GONE
                        binding.etServerUrl.setText("")
                    }
                    in 1..3 -> {
                        // Preset URLs
                        binding.etServerUrl.visibility = View.GONE
                        binding.etServerUrl.setText("")
                        val selectedUrl = presetUrls[position - 1]
                        autoSave(selectedUrl)
                    }
                    4 -> {
                        // "Custom URL..."
                        binding.etServerUrl.visibility = View.VISIBLE
                        binding.etServerUrl.requestFocus()
                    }
                }
            }

            override fun onNothingSelected(parent: AdapterView<*>?) {
                // Do nothing
            }
        }
    }

    private fun loadSettings() {
        val prefs = getSharedPreferences("nbj_prefs", Context.MODE_PRIVATE)
        val savedUrl = prefs.getString("server_url", ConciserApi.DEFAULT_URL).orEmpty()

        // Check if the saved URL is one of the presets
        val presetIndex = presetUrls.indexOf(savedUrl)
        if (presetIndex >= 0) {
            // Select the preset (add 1 to account for the first "Select..." option)
            binding.spinnerServerUrl.setSelection(presetIndex + 1)
            binding.etServerUrl.visibility = View.GONE
        } else if (savedUrl.isNotEmpty()) {
            // Custom URL
            binding.spinnerServerUrl.setSelection(4) // "Custom URL..."
            binding.etServerUrl.setText(savedUrl)
            binding.etServerUrl.visibility = View.VISIBLE
        } else {
            // No URL set
            binding.spinnerServerUrl.setSelection(0)
            binding.etServerUrl.visibility = View.GONE
        }

        if (savedUrl.isNotEmpty()) {
            schedulePing(savedUrl)
        }
    }

    private fun autoSave(serverUrl: String) {
        if (serverUrl.isEmpty()) {
            // Don't save an empty URL, but clear the status
            updateServerStatus("", R.color.text_secondary)
            return
        }

        if (!serverUrl.startsWith("http")) {
            updateServerStatus(getString(R.string.server_status_invalid), R.color.error)
            // Still save the invalid URL
        }

        val prefs = getSharedPreferences("nbj_prefs", Context.MODE_PRIVATE)
        val previous = prefs.getString("server_url", "").orEmpty()
        if (previous.isNotEmpty() && previous != serverUrl) {
            prefs.edit().clear().apply()
            getSharedPreferences("client_identity", Context.MODE_PRIVATE).edit().clear().apply()
        }
        prefs.edit().putString("server_url", serverUrl).apply()

        // Always ping, even if the URL seems invalid, to give feedback
        schedulePing(serverUrl)

        // Optional: Show a brief "Saved" message if needed, but auto-save should be silent
        // Toast.makeText(this, "Saved", Toast.LENGTH_SHORT).show()
    }

    private fun schedulePing(rawUrl: String) {
        val trimmed = rawUrl.trim()
        if (trimmed.isEmpty() || !trimmed.startsWith("http")) {
            updateServerStatus(getString(R.string.server_status_invalid), R.color.text_secondary)
            return
        }

        pingJob?.cancel()
        updateServerStatus(getString(R.string.server_status_checking), R.color.primary)

        pingJob = lifecycleScope.launch {
            delay(500)
            performHealthCheck(trimmed)
        }
    }

    private suspend fun performHealthCheck(rawUrl: String) {
        val result = withContext(Dispatchers.IO) {
            val normalized = normalizeServerUrl(rawUrl)
            val healthUrl = "$normalized/api/health"
            try {
                val request = Request.Builder().url(healthUrl).get().build()
                httpClient.newCall(request).execute().use { response ->
                    if (!response.isSuccessful) {
                        HealthResult.HttpError(response.code)
                    } else {
                        val body = response.body?.string().orEmpty()
                        val status = try {
                            JSONObject(body).optString("status")
                        } catch (e: Exception) {
                            ""
                        }
                        if (status.isNotBlank() && status.lowercase() != "ok") {
                            HealthResult.ReportedIssue(status)
                        } else {
                            HealthResult.Ok
                        }
                    }
                }
            } catch (e: Exception) {
                HealthResult.Unreachable
            }
        }

        when (result) {
            is HealthResult.Ok -> updateServerStatus(getString(R.string.server_status_ok), R.color.success)
            is HealthResult.HttpError -> updateServerStatus(
                getString(R.string.server_status_http_error, result.code),
                R.color.error
            )
            is HealthResult.ReportedIssue -> updateServerStatus(
                getString(R.string.server_status_reported_issue, result.status),
                R.color.error
            )
            is HealthResult.Unreachable -> updateServerStatus(getString(R.string.server_status_unreachable), R.color.error)
        }
    }

    private fun updateServerStatus(message: String, colorRes: Int) {
        binding.tvServerStatus.text = message
        binding.tvServerStatus.setTextColor(ContextCompat.getColor(this, colorRes))
    }

    private fun normalizeServerUrl(value: String): String {
        val trimmed = value.trim()
        if (trimmed.isEmpty()) return trimmed
        return trimmed.trimEnd('/')
    }

    private sealed class HealthResult {
        object Ok : HealthResult()
        data class HttpError(val code: Int) : HealthResult()
        data class ReportedIssue(val status: String) : HealthResult()
        object Unreachable : HealthResult()
    }

    private fun showResetConfirmationDialog() {
        AlertDialog.Builder(this)
            .setTitle("Reset All State")
            .setMessage("Are you sure you want to reset all state? This will clear:\n\n• All active and completed jobs\n• All settings\n• Cached voices and strategies\n• Client ID\n\nThis cannot be undone.")
            .setPositiveButton("Reset") { _, _ ->
                resetAllState()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun resetAllState() {
        // Clear all SharedPreferences
        getSharedPreferences("nbj_prefs", Context.MODE_PRIVATE).edit().clear().apply()
        
        // Clear client ID
        getSharedPreferences("client_identity", Context.MODE_PRIVATE).edit().clear().apply()
        
        Toast.makeText(this, "All state has been reset", Toast.LENGTH_SHORT).show()
        
        // Go back to main activity to refresh everything
        val intent = Intent(this, MainActivity::class.java)
        intent.flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_NEW_TASK
        startActivity(intent)
        finish()
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }
}
