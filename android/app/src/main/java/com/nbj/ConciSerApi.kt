package com.nbj

import okhttp3.OkHttpClient
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
    val video_mode: String = "slideshow"
)

data class CondenseResponse(
    val job_id: String,
    val status: String,
    val message: String
)

data class StatusResponse(
    val job_id: String,
    val status: String,
    val progress: String? = null,
    val download_url: String? = null,
    val error: String? = null,
    val created_at: String? = null,
    val completed_at: String? = null
)

data class VoiceItem(
    val name: String,
    val locale: String,
    val friendly_name: String
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

interface ConciSerApiService {
    @POST("api/condense")
    suspend fun condenseVideo(@Body request: CondenseRequest): CondenseResponse

    @GET("api/status/{jobId}")
    suspend fun getStatus(@Path("jobId") jobId: String): StatusResponse

    @GET("api/voices")
    suspend fun getVoices(@Query("locale") locale: String): VoicesResponse

    @GET("api/strategies")
    suspend fun getStrategies(): StrategiesResponse
}

object ConciSerApi {
    const val DEFAULT_URL = "https://conciser-aurora.ngrok.dev/"

    private val loggingInterceptor = HttpLoggingInterceptor().apply {
        level = HttpLoggingInterceptor.Level.BODY
    }

    private val client = OkHttpClient.Builder()
        .addInterceptor(loggingInterceptor)
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    fun createService(baseUrl: String): ConciSerApiService {
        val url = if (baseUrl.endsWith("/")) baseUrl else "$baseUrl/"
        return Retrofit.Builder()
            .baseUrl(url)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(ConciSerApiService::class.java)
    }

    fun getFullDownloadUrl(baseUrl: String, jobId: String): String {
        val base = if (baseUrl.endsWith("/")) baseUrl else "$baseUrl/"
        return "${base}api/download/$jobId"
    }
}
