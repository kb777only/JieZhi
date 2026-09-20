package dev.jiezhi.client

import android.app.ActivityManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.Debug
import android.os.PowerManager
import android.os.SystemClock
import org.json.JSONObject
import java.util.ArrayDeque

/** Public app APIs only. CPU/thermal HAL diagnostics are read separately over ADB. */
class Telemetry(private val context: Context) {
    private val tokens = ArrayDeque<Long>()
    private var generation = 0L
    private var active = false
    private var count = 0L
    private var started = 0L
    private var firstToken = 0L
    private var pssAt = 0L
    private var pss = 0L
    @Synchronized fun begin() {
        generation++; active = true; count = 0; started = SystemClock.elapsedRealtime(); firstToken = 0; tokens.clear()
    }
    @Synchronized fun token() {
        val now = SystemClock.elapsedRealtime()
        if (firstToken == 0L) firstToken = now
        count++; tokens.addLast(now); trim(now)
    }
    @Synchronized fun end() { active = false }
    private fun trim(now: Long) { while (tokens.isNotEmpty() && tokens.first <= now - 2000) tokens.removeFirst() }
    @Synchronized fun snapshot(state: String, model: String, backend: String, profile: JSONObject): JSONObject {
        val now = SystemClock.elapsedRealtime(); trim(now)
        val battery = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val level = battery?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = battery?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
        val temperature = battery?.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, Int.MIN_VALUE) ?: Int.MIN_VALUE
        val memory = ActivityManager.MemoryInfo()
        context.getSystemService(ActivityManager::class.java).getMemoryInfo(memory)
        if (now - pssAt > 5000) { pss = Debug.getPss().toLong() * 1024; pssAt = now }
        return JSONObject().apply {
            put("schema", 1); put("uptime_ms", now); put("state", state); put("model", model)
            put("requested_backend", backend); put("generation", generation); put("generating", active)
            put("stream_events", count); put("stream_rate", tokens.size / 2.0)
            put("rate_basis", "SDK token callbacks in the last 2 seconds; approximate until final runtime profile")
            put("first_token_ms", if (firstToken > 0) firstToken - started else JSONObject.NULL)
            put("last_profile", profile)
            put("battery_percent", if (level >= 0 && scale > 0) level * 100.0 / scale else JSONObject.NULL)
            put("battery_c", if (temperature != Int.MIN_VALUE) temperature / 10.0 else JSONObject.NULL)
            put("plugged", battery?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) != 0)
            put("memory_total_bytes", memory.totalMem); put("memory_available_bytes", memory.availMem)
            put("app_pss_bytes", pss); put("app_pss_sample_uptime_ms", pssAt)
            put("thermal_status", context.getSystemService(PowerManager::class.java).currentThermalStatus)
        }
    }
}
