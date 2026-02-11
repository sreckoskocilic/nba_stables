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

class WidgetUpdateWorker(
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
            val scores = fetchScores()
            updateAllWidgets(scores)
            Result.success()
        } catch (e: Exception) {
            e.printStackTrace()
            updateAllWidgets("Error loading scores")
            Result.retry()
        }
    }

    private fun fetchScores(): String {
        val request = Request.Builder()
            .url("https://nbastables.com/api/scoreboard")
            .build()

        val response = client.newCall(request).execute()
        if (!response.isSuccessful) {
            return "Error: ${response.code}"
        }

        val json = response.body?.string() ?: return "No data"
        val data = gson.fromJson(json, ScoreboardResponse::class.java)

        if (data.games.isEmpty()) {
            return "No games today"
        }

        return data.games.take(8).joinToString("\n") { game ->
            val awayScore = if (game.awayTeam.score > 0) game.awayTeam.score.toString() else "-"
            val homeScore = if (game.homeTeam.score > 0) game.homeTeam.score.toString() else "-"
            "${game.awayTeam.tricode} $awayScore - $homeScore ${game.homeTeam.tricode}  ${game.status}"
        }
    }

    private fun updateAllWidgets(text: String) {
        val appWidgetManager = AppWidgetManager.getInstance(context)
        val widgetComponent = ComponentName(context, ScoresWidgetProvider::class.java)
        val appWidgetIds = appWidgetManager.getAppWidgetIds(widgetComponent)

        for (appWidgetId in appWidgetIds) {
            val views = RemoteViews(context.packageName, R.layout.widget_scores)
            views.setTextViewText(R.id.scores_text, text)
            appWidgetManager.updateAppWidget(appWidgetId, views)
        }
    }
}

// Data classes
data class ScoreboardResponse(
    val games: List<Game>,
    val date: String
)

data class Game(
    val gameId: String,
    val status: String,
    val homeTeam: Team,
    val awayTeam: Team
)

data class Team(
    val name: String,
    val tricode: String,
    val score: Int,
    val leader: Leader
)

data class Leader(
    val name: String,
    val points: Int,
    val rebounds: Int,
    val assists: Int
)
