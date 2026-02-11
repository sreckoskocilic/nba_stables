package com.nbastables.widget

import android.content.Context
import android.content.Intent
import android.widget.RemoteViews
import android.widget.RemoteViewsService
import com.google.gson.Gson
import com.google.gson.annotations.SerializedName
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit

class WidgetUpdateService : RemoteViewsService() {
    override fun onGetViewFactory(intent: Intent): RemoteViewsFactory {
        return GamesRemoteViewsFactory(applicationContext)
    }
}

class GamesRemoteViewsFactory(private val context: Context) : RemoteViewsService.RemoteViewsFactory {

    private var games: List<Game> = emptyList()
    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()
    private val gson = Gson()

    override fun onCreate() {}

    override fun onDataSetChanged() {
        try {
            val request = Request.Builder()
                .url("https://nbastables.com/api/scoreboard")
                .build()

            val response = client.newCall(request).execute()
            if (response.isSuccessful) {
                val json = response.body?.string()
                val scoreboardResponse = gson.fromJson(json, ScoreboardResponse::class.java)
                games = scoreboardResponse.games
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    override fun onDestroy() {
        games = emptyList()
    }

    override fun getCount(): Int = games.size

    override fun getViewAt(position: Int): RemoteViews {
        val views = RemoteViews(context.packageName, R.layout.widget_game_item)

        if (position < games.size) {
            val game = games[position]
            views.setTextViewText(R.id.game_status, game.status)
            views.setTextViewText(R.id.away_team, game.awayTeam.tricode)
            views.setTextViewText(R.id.away_score, game.awayTeam.score.toString())
            views.setTextViewText(R.id.home_team, game.homeTeam.tricode)
            views.setTextViewText(R.id.home_score, game.homeTeam.score.toString())
        }

        return views
    }

    override fun getLoadingView(): RemoteViews? = null
    override fun getViewTypeCount(): Int = 1
    override fun getItemId(position: Int): Long = position.toLong()
    override fun hasStableIds(): Boolean = true
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
