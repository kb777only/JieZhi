package dev.jiezhi.client

import android.app.*
import android.content.Intent
import android.os.*
import com.geniex.sdk.GenieXSdk

class AssistantService : Service() {
    companion object { @Volatile var instance: AssistantService? = null }
    @Volatile var server: BridgeServer? = null
    override fun onBind(intent: Intent?) = null
    override fun onCreate() {
        super.onCreate(); instance = this
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel("assistant", "USB assistant", NotificationManager.IMPORTANCE_LOW))
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        val stop = PendingIntent.getService(this, 1, Intent(this, AssistantService::class.java).setAction("stop"), PendingIntent.FLAG_IMMUTABLE)
        startForeground(1, Notification.Builder(this, "assistant").setContentTitle("JieZhi USB assistant")
            .setContentText("Ready for desktop requests · tap to manage")
            .setSmallIcon(android.R.drawable.stat_notify_sync).setContentIntent(open)
            .addAction(Notification.Action.Builder(null, "Stop", stop).build()).build())
        Thread {
            try {
                GenieXSdk.getInstance().init(this)
                val bridge = BridgeServer(this)
                if (instance === this) { server = bridge; bridge.start(60_000, false) }
            } catch (e: Throwable) { android.util.Log.e("JieZhi", "Client startup failed", e); stopSelf() }
        }.start()
    }
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == "stop") stopSelf()
        return START_NOT_STICKY
    }
    override fun onDestroy() {
        instance = null
        server?.shutdown(); server = null
        super.onDestroy()
    }
}
