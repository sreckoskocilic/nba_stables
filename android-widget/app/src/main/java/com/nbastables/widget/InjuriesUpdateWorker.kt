package com.nbastables.widget

import android.appwidget.AppWidgetManager
import android.content.ComponentName
import android.content.Context
import android.widget.RemoteViews
import androidx.work.Worker
import androidx.work.WorkerParameters
import com.google.gson.Gson
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit

class InjuriesUpdateWorker(
    private val context: Context,
    workerParams: WorkerParameters
) : Worker(context, workerParams) {

    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()
    private val gson = Gson()

    override fun doWork(): Result {
        return try {
            val injuries = fetchInjuries()
            updateAllWidgets(injuries)
            Result.success()
        } catch (e: Exception) {
            e.printStackTrace()
            updateAllWidgets("Error loading injuries")
            Result.retry()
        }
    }

    private fun fetchInjuries(): String {
        val request = Request.Builder()
            .url("https://nbastables.com/api/injuries?source=espn")
            .build()

        val response = client.newCall(request).execute()
        if (!response.isSuccessful) {
            return "Error: ${response.code}"
        }

        val json = response.body?.string() ?: return "No data"
        val data = gson.fromJson(json, InjuriesResponse::class.java)

        if (data.injuries.isEmpty()) {
            return "No injuries reported"
        }

        // Flatten and show top injuries
        val allInjuries = mutableListOf<String>()
        for (team in data.injuries) {
            for (player in team.players.take(2)) {
                val status = when {
                    player.status.contains("Out", ignoreCase = true) -> "OUT"
                    player.status.contains("Day", ignoreCase = true) -> "GTD"
                    else -> player.status.take(8)
                }
                allInjuries.add("${player.name.split(" ").last()} (${team.team.split(" ").last().take(3)}) $status")
            }
        }

        return allInjuries.take(12).joinToString("\n")
    }

    private fun updateAllWidgets(text: String) {
        val appWidgetManager = AppWidgetManager.getInstance(context)
        val widgetComponent = ComponentName(context, InjuriesWidgetProvider::class.java)
        val appWidgetIds = appWidgetManager.getAppWidgetIds(widgetComponent)

        for (appWidgetId in appWidgetIds) {
            val views = RemoteViews(context.packageName, R.layout.widget_injuries)
            views.setTextViewText(R.id.injuries_text, text)
            appWidgetManager.updateAppWidget(appWidgetId, views)
        }
    }
}

data class InjuriesResponse(
    val injuries: List<TeamInjuries>,
    val source: String,
    val lastUpdated: String
)

data class TeamInjuries(
    val team: String,
    val players: List<PlayerInjury>
)

data class PlayerInjury(
    val name: String,
    val updated: String,
    val injury: String,
    val status: String
)
