package com.nbj

import android.net.Uri
import com.google.gson.Gson
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Interceptor
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.*
import java.util.concurrent.TimeUnit

data class CondenseRequest(
    val url: String,
    val aggressiveness: Int = 5,
    val voice: String = "",
    val speech_rate: String = "+10%",
    val video_mode: String = "slideshow",
    val prepend_intro: Boolean = false
)

data class CondenseResponse(
    val job_id: String,
    val status: String,
    val message: String
)

data class TakeawaysRequest(
    val url: String,
    val top: Int? = null,  // null = auto
    val format: String = "text",  // "text" or "audio"
    val voice: String? = null  // only used if format="audio"
)

data class TakeawaysResponse(
    val job_id: String,
    val status: String,
    val message: String
)

data class StatusResponse(
    val job_id: String,
    val status: String,
    val progress: String? = null,
    val open_url: String? = null,
    val download_url: String? = null,
    val error: String? = null,
    val created_at: String? = null,
    val completed_at: String? = null
)

data class VoiceItem(
    val name: String,
    val locale: String,
    val friendly_name: String,
    val gender: String? = null
)

data class VoicesResponse(
    val voices: List<VoiceItem>
)

data class StrategyItem(
    val level: Int,
    val name: String,
    val description: String
)

data class StrategiesResponse(
    val strategies: List<StrategyItem>
)

interface ConciserApiService {
    @POST("api/condense")
    suspend fun condenseVideo(@Body request: CondenseRequest): CondenseResponse

    @POST("api/takeaways")
    suspend fun extractTakeaways(@Body request: TakeawaysRequest): TakeawaysResponse

    @GET("api/status/{jobId}")
    suspend fun getStatus(@Path("jobId") jobId: String): StatusResponse

    @GET("api/voices")
    suspend fun getVoices(@Query("locale") locale: String): VoicesResponse

    @GET("api/strategies")
    suspend fun getStrategies(): StrategiesResponse

    @GET("api/jobs")
    suspend fun getJobs(): JobsResponse

    @DELETE("api/jobs/{jobId}")
    suspend fun deleteJob(@Path("jobId") jobId: String): retrofit2.Response<okhttp3.ResponseBody>
}

data class JobsResponse(
    val jobs: List<JobSummary>,
    val currently_processing: String?
)

data class JobSummary(
    val job_id: String,
    val url: String,
    val title: String?,
    val status: String,
    val job_type: String,
    val file_exists: Boolean,
    val created_at: String
)

data class OEmbedResponse(val title: String)

data class RecentJob(
    val jobId: String,
    val title: String,
    val videoMode: String,
    val serverUrl: String,
    val addedAt: Long = System.currentTimeMillis(),
    val jobType: String = "condense",  // "condense" or "takeaways"
    val outputFormat: String = "video"  // "video", "audio", "text"
)

object ConciserApi {
    val DEFAULT_URL = BuildConfig.DEFAULT_SERVER_URL

    private val loggingInterceptor = HttpLoggingInterceptor().apply {
        level = HttpLoggingInterceptor.Level.BODY
    }

    private val httpClient: OkHttpClient by lazy {
        baseClient().build()
    }

    private fun baseClient(): OkHttpClient.Builder = OkHttpClient.Builder()
        .addInterceptor(loggingInterceptor)
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)

    fun createService(baseUrl: String, clientId: String? = null): ConciserApiService {
        val url = if (baseUrl.endsWith("/")) baseUrl else "$baseUrl/"
        val builder = baseClient()
        if (!clientId.isNullOrBlank()) {
            builder.addInterceptor(Interceptor { chain ->
                val request = chain.request().newBuilder()
                    .header("X-User-Id", clientId)
                    .build()
                chain.proceed(request)
            })
        }
        return Retrofit.Builder()
            .baseUrl(url)
            .client(builder.build())
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(ConciserApiService::class.java)
    }

    suspend fun fetchVideoTitle(videoUrl: String): String? = withContext(Dispatchers.IO) {
        try {
            val oEmbedUrl = "https://www.youtube.com/oembed?url=${videoUrl}&format=json"
            val request = Request.Builder().url(oEmbedUrl).build()
            val body = httpClient.newCall(request).execute().use { it.body?.string() }
            body?.let { Gson().fromJson(it, OEmbedResponse::class.java)?.title }
        } catch (e: Exception) {
            null
        }
    }

    /** Returns true if the file is reachable; false only on a definitive 404/410. Network errors return true (don't prune). */
    suspend fun checkFileExists(url: String): Boolean = withContext(Dispatchers.IO) {
        try {
            val request = Request.Builder().url(url).head().build()
            val code = httpClient.newCall(request).execute().use { it.code }
            code != 404 && code != 410
        } catch (e: Exception) {
            true
        }
    }

    fun getFullDownloadUrl(baseUrl: String, jobId: String, clientId: String? = null): String {
        val base = if (baseUrl.endsWith("/")) baseUrl else "$baseUrl/"
        val cidParam = clientId?.takeIf { it.isNotBlank() }?.let { "?cid=${Uri.encode(it)}" } ?: ""
        return "${base}api/download/$jobId$cidParam"
    }

    fun getFullOpenUrl(baseUrl: String, jobId: String, clientId: String): String {
        return "$baseUrl/api/open/$jobId?cid=${java.net.URLEncoder.encode(clientId, "UTF-8")}";
    }

    fun getFullDeleteUrl(baseUrl: String, jobId: String): String {
        return "$baseUrl/api/jobs/$jobId"
    }

    suspend fun postDebugLog(baseUrl: String, clientId: String?, payload: Map<String, Any?>) = withContext(Dispatchers.IO) {
        try {
            val base = if (baseUrl.endsWith("/")) baseUrl else "$baseUrl/"
            val requestJson = Gson().toJson(payload)
            val requestBuilder = Request.Builder()
                .url("${base}api/log")
                .post(requestJson.toRequestBody("application/json; charset=utf-8".toMediaType()))
            if (!clientId.isNullOrBlank()) {
                requestBuilder.header("X-User-Id", clientId)
            }
            httpClient.newCall(requestBuilder.build()).execute().use { }
        } catch (e: Exception) {
        }
    }
}
