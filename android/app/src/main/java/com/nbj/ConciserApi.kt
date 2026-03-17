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
import retrofit2.HttpException

data class CreateJobRequest(
    val type: String,
    val url: String,
    val params: Map<String, Any?> = emptyMap()
)

data class CreateJobResponse(
    val id: String,
    val status: String,
    val type: String,
    val created_at: String? = null
)

data class ActiveJobInfo(
    val id: String? = null,
    val status: String? = null,
    val type: String? = null,
    val created_at: String? = null
)

data class ActiveJobErrorResponse(
    val error: String? = null,
    val active_job: ActiveJobInfo? = null
)

class ActiveJobInProgressException(
    message: String,
    val activeJobId: String? = null,
    val activeJobStatus: String? = null
) : Exception(message)

data class JobResponse(
    val id: String,
    val type: String,
    val url: String,
    val title: String? = null,
    val status: String,
    val progress: String? = null,
    val queue_position: Int? = null,
    val params: Map<String, Any?>? = null,
    val error: String? = null,
    val created_at: String? = null,
    val completed_at: String? = null
)

data class ArtifactItem(
    val name: String,
    val ext: String,
    val kind: String? = null,
    val mime: String? = null,
    val filename: String? = null,
    val raw_url: String,
    val render_url: String? = null,
)

data class ArtifactsResponse(
    val artifacts: List<ArtifactItem>,
    val share_id: String? = null
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
    @POST("api/jobs")
    suspend fun createJob(@Body request: CreateJobRequest): CreateJobResponse

    @GET("api/jobs/{jobId}")
    suspend fun getJob(@Path("jobId") jobId: String): JobResponse

    @GET("api/jobs/{jobId}/artifacts")
    suspend fun getArtifacts(@Path("jobId") jobId: String): ArtifactsResponse

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
    val jobs: List<JobResponse>
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

    suspend fun createJobWithActiveJobHandling(
        api: ConciserApiService,
        request: CreateJobRequest
    ): CreateJobResponse {
        try {
            return api.createJob(request)
        } catch (e: HttpException) {
            if (e.code() == 429) {
                val body = try {
                    e.response()?.errorBody()?.string()
                } catch (_: Exception) {
                    null
                }
                val parsed = try {
                    body?.let { Gson().fromJson(it, ActiveJobErrorResponse::class.java) }
                } catch (_: Exception) {
                    null
                }
                val activeId = parsed?.active_job?.id
                val activeStatus = parsed?.active_job?.status
                val msg = parsed?.error ?: "Client already has an active job"
                throw ActiveJobInProgressException(msg, activeId, activeStatus)
            }
            throw e
        }
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

    fun getFullDeleteUrl(baseUrl: String, jobId: String): String {
        return "$baseUrl/api/jobs/$jobId"
    }
}
