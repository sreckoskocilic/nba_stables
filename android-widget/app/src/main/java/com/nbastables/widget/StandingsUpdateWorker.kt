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

class StandingsUpdateWorker(
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
            val standings = fetchStandings()
            updateAllWidgets(standings)
            Result.success()
        } catch (e: Exception) {
            e.printStackTrace()
            updateAllWidgets("Error loading standings")
            Result.retry()
        }
    }

    private fun fetchStandings(): String {
        val request = Request.Builder()
            .url("https://nbastables.com/api/standings")
            .build()

        val response = client.newCall(request).execute()
        if (!response.isSuccessful) {
            return "Error: ${response.code}"
        }

        val json = response.body?.string() ?: return "No data"
        val data = gson.fromJson(json, StandingsResponse::class.java)

        val sb = StringBuilder()
        sb.append("EAST          W-L\n")
        data.east.take(5).forEach { team ->
            sb.append(String.format("%-12s %d-%d\n", team.team.take(12), team.wins, team.losses))
        }
        sb.append("\nWEST          W-L\n")
        data.west.take(5).forEach { team ->
            sb.append(String.format("%-12s %d-%d\n", team.team.take(12), team.wins, team.losses))
        }

        return sb.toString().trim()
    }

    private fun updateAllWidgets(text: String) {
        val appWidgetManager = AppWidgetManager.getInstance(context)
        val widgetComponent = ComponentName(context, StandingsWidgetProvider::class.java)
        val appWidgetIds = appWidgetManager.getAppWidgetIds(widgetComponent)

        for (appWidgetId in appWidgetIds) {
            val views = RemoteViews(context.packageName, R.layout.widget_standings)
            views.setTextViewText(R.id.standings_text, text)
            appWidgetManager.updateAppWidget(appWidgetId, views)
        }
    }
}

data class StandingsResponse(
    val east: List<TeamStanding>,
    val west: List<TeamStanding>
)

data class TeamStanding(
    val rank: Int,
    val team: String,
    val wins: Int,
    val losses: Int,
    val pct: String,
    val gb: String
)
