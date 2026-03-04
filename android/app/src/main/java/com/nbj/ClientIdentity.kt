package com.nbj

import android.content.Context
import android.provider.Settings
import java.util.UUID

object ClientIdentity {
    private const val PREFS_NAME = "nbj_prefs"
    private const val KEY_USER_ID = "user_id"
    private const val ANDROID_ID_BLACKLIST = "9774d56d682e549c"

    fun getOrCreate(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.getString(KEY_USER_ID, null)?.let { return it }

        val androidId = Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID)
        val baseId = if (!androidId.isNullOrBlank() && androidId != ANDROID_ID_BLACKLIST) {
            "android-$androidId"
        } else {
            "android-${UUID.randomUUID()}"
        }

        prefs.edit().putString(KEY_USER_ID, baseId).apply()
        return baseId
    }
}
