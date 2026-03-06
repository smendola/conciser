package com.nbj

import android.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.os.Bundle
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

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySettingsBinding.inflate(layoutInflater)
        setContentView(binding.root)

        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        title = getString(R.string.settings)

        loadSettings()

        binding.btnSave.setOnClickListener {
            saveSettings()
        }

        binding.btnResetState.setOnClickListener {
            showResetConfirmationDialog()
        }
    }

    private fun loadSettings() {
        val prefs = getSharedPreferences("nbj_prefs", Context.MODE_PRIVATE)
        val savedUrl = prefs.getString("server_url", ConciserApi.DEFAULT_URL)
        binding.etServerUrl.setText(savedUrl)
        schedulePing(savedUrl.orEmpty())
    }

    private fun saveSettings() {
        val serverUrl = binding.etServerUrl.text.toString().trim()

        if (serverUrl.isEmpty() || !serverUrl.startsWith("http")) {
            Toast.makeText(this, "Please enter a valid URL", Toast.LENGTH_SHORT).show()
            return
        }

        getSharedPreferences("nbj_prefs", Context.MODE_PRIVATE).edit()
            .putString("server_url", serverUrl)
            .apply()

        schedulePing(serverUrl)

        Toast.makeText(this, "Settings saved", Toast.LENGTH_SHORT).show()
        finish()
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
            val healthUrl = "$normalized/health"
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
