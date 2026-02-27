package com.nbj

import android.content.Context
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.nbj.databinding.ActivitySettingsBinding

class SettingsActivity : AppCompatActivity() {

    private lateinit var binding: ActivitySettingsBinding

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
    }

    private fun loadSettings() {
        val prefs = getSharedPreferences("nbj_prefs", Context.MODE_PRIVATE)
        binding.etServerUrl.setText(prefs.getString("server_url", ConciSerApi.DEFAULT_URL))
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

        Toast.makeText(this, "Settings saved", Toast.LENGTH_SHORT).show()
        finish()
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }
}
