package com.nbastables.widget

import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.Context
import android.widget.RemoteViews
import androidx.work.*
import java.util.concurrent.TimeUnit

class InjuriesWidgetProvider : AppWidgetProvider() {

    override fun onUpdate(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetIds: IntArray
    ) {
        for (appWidgetId in appWidgetIds) {
            updateWidget(context, appWidgetManager, appWidgetId)
        }
        scheduleUpdate(context)
    }

    override fun onEnabled(context: Context) {
        scheduleUpdate(context)
    }

    override fun onDisabled(context: Context) {
        WorkManager.getInstance(context).cancelUniqueWork("injuries_widget_update")
    }

    private fun scheduleUpdate(context: Context) {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()

        val updateRequest = PeriodicWorkRequestBuilder<InjuriesUpdateWorker>(
            30, TimeUnit.MINUTES
        ).setConstraints(constraints).build()

        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            "injuries_widget_update",
            ExistingPeriodicWorkPolicy.REPLACE,
            updateRequest
        )

        // Run once immediately
        val immediateRequest = OneTimeWorkRequestBuilder<InjuriesUpdateWorker>()
            .setConstraints(constraints)
            .build()
        WorkManager.getInstance(context).enqueue(immediateRequest)
    }

    companion object {
        fun updateWidget(
            context: Context,
            appWidgetManager: AppWidgetManager,
            appWidgetId: Int
        ) {
            val views = RemoteViews(context.packageName, R.layout.widget_injuries)
            views.setTextViewText(R.id.injuries_text, "Loading injuries...")
            appWidgetManager.updateAppWidget(appWidgetId, views)
        }
    }
}
