package dev.jiezhi.client

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.*
import android.view.View
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.widget.*

class MainActivity : Activity() {
    private val handler = Handler(Looper.getMainLooper())
    private val dark get() = getPreferences(MODE_PRIVATE).getBoolean("dark", false)
    private val ink get() = if (dark) Color.rgb(230, 236, 250) else Color.rgb(27, 40, 62)
    private val muted get() = if (dark) Color.rgb(158, 175, 201) else Color.rgb(109, 123, 146)
    private val blue get() = if (dark) Color.rgb(129, 162, 255) else Color.rgb(56, 107, 255)
    private val surface get() = if (dark) Color.rgb(29, 37, 57) else Color.WHITE
    private val accent get() = if (dark) Color.rgb(40, 52, 81) else Color.rgb(231, 238, 255)
    private lateinit var pairing: TextView
    private lateinit var connection: TextView
    private lateinit var model: TextView
    private lateinit var metrics: TextView
    private lateinit var pairHelp: TextView
    private lateinit var startButton: Button
    private lateinit var stopButton: Button
    private val update = object : Runnable {
        override fun run() {
            val service = AssistantService.instance
            val server = service?.server
            connection.text = server?.state ?: if (service != null) "Preparing runtime…" else "Client stopped"
            pairing.text = server?.pairingCode ?: "— — —"
            pairing.textSize = if (server?.pairingCode == "Paired") 32f else 42f
            pairHelp.text = if (server?.pairingCode == "Paired") "Your desktop is paired with this session."
                else "Enter this code in the JieZhi desktop app."
            model.text = server?.loadedName?.takeIf { it.isNotEmpty() } ?: "Ready for your first model"
            val profile = server?.lastProfile
            metrics.text = if (server?.loadedName?.isNotEmpty() == true) {
                "${server.backendLabel} requested · ${server.contextSize} token context" +
                    if (profile != null && profile.has("tokens_per_second"))
                        "\n%.1f tokens/s · %.2fs first token".format(profile.optDouble("tokens_per_second"), profile.optDouble("ttft_ms") / 1000)
                    else "\nWaiting for a conversation from your desktop."
            } else if (server?.state?.startsWith("Generating media") == true) "${server.backendLabel} · Image or video generation\nFollow progress in your desktop Flow canvas." else "Text · Image · Video\nChoose a model or media workflow from your desktop."
            startButton.isEnabled = service == null
            stopButton.isEnabled = service != null
            handler.postDelayed(this, 1000)
        }
    }
    private fun dp(n: Int) = (n * resources.displayMetrics.density).toInt()
    private fun rounded(color: Int, radius: Int = 24) = GradientDrawable().apply {
        setColor(color); cornerRadius = dp(radius).toFloat()
    }
    private fun text(value: String, size: Float = 15f, color: Int = ink, bold: Boolean = false) = TextView(this).apply {
        text = value; textSize = size; setTextColor(color)
        if (bold) typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
        setPadding(0, dp(5), 0, dp(5))
    }
    private fun card(parent: LinearLayout, tint: Int = surface, build: LinearLayout.() -> Unit) {
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; background = rounded(tint); setPadding(dp(22), dp(17), dp(22), dp(19)); build()
        }
        parent.addView(box, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(16) })
    }
    private fun action(value: String, primary: Boolean = false, callback: () -> Unit) = Button(this).apply {
        text = value; isAllCaps = false; textSize = 15f
        setTextColor(if (primary) Color.WHITE else blue)
        background = rounded(if (primary) Color.rgb(56, 107, 255) else accent, 16)
        minHeight = dp(52); elevation = 0f
        setOnClickListener { callback() }
        layoutParams = LinearLayout.LayoutParams(-1, dp(52)).apply { topMargin = dp(10) }
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val scroll = ScrollView(this).apply { setBackgroundColor(if (dark) Color.rgb(17, 21, 34) else Color.rgb(243, 245, 250)); isFillViewport = true; clipToPadding = false }
        scroll.setOnApplyWindowInsetsListener { view, insets ->
            val bars = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom); insets
        }
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setPadding(dp(24), dp(24), dp(24), dp(24))
        }
        val heading = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = android.view.Gravity.CENTER_VERTICAL }
        heading.addView(text("借智  JieZhi", 32f, blue, true), LinearLayout.LayoutParams(0, -2, 1f))
        heading.addView(action(if (dark) "☀" else "☾") {
            getPreferences(MODE_PRIVATE).edit().putBoolean("dark", !dark).apply(); recreate()
        }.apply { contentDescription = "Toggle color theme"; layoutParams = LinearLayout.LayoutParams(dp(52), dp(52)) })
        layout.addView(heading)
        layout.addView(text("A little intelligence. A closer connection.", 14f, muted).apply { setPadding(0, 0, 0, dp(24)) })
        card(layout) {
            addView(text("●  USB ASSISTANT", 12f, Color.rgb(238, 133, 64), true))
            connection = text("Starting…", 24f, ink, true); addView(connection)
            addView(text("${Build.MANUFACTURER.replaceFirstChar { it.uppercase() }} ${Build.MODEL}\n${Build.SOC_MODEL} · Android ${Build.VERSION.RELEASE}", 14f, muted))
        }
        card(layout, accent) {
            background = GradientDrawable(GradientDrawable.Orientation.TL_BR, if (dark) intArrayOf(Color.rgb(38, 48, 83), Color.rgb(57, 38, 81)) else intArrayOf(Color.rgb(220, 231, 255), Color.rgb(237, 224, 255))).apply { cornerRadius = dp(24).toFloat() }
            addView(text("DESKTOP PAIRING", 12f, blue, true))
            pairing = text("— — —", 42f, blue, true).apply { letterSpacing = 0.1f; setTextIsSelectable(true) }; addView(pairing)
            pairHelp = text("Enter this code in the JieZhi desktop app.", 14f, muted); addView(pairHelp)
        }
        card(layout) {
            addView(text("ON-DEVICE INTELLIGENCE", 12f, muted, true))
            model = text("Ready for your first model", 21f, ink, true); addView(model)
            metrics = text("Choose a model from your desktop.", 14f, muted); addView(metrics)
        }
        startButton = action("Start USB assistant", true) { startClient() }; layout.addView(startButton)
        stopButton = action("Stop and disconnect") { stopService(Intent(this, AssistantService::class.java)) }; layout.addView(stopButton)
        layout.addView(action("Battery & app settings ↗") {
            startActivity(Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS, android.net.Uri.parse("package:$packageName")))
        })
        layout.addView(text("On Xiaomi, set Battery saver to No restrictions to keep the assistant available in the background.", 12f, muted).apply { setPadding(0, dp(18), 0, dp(10)) })
        layout.addView(text("USB connection · Inference stays on this phone", 12f, blue))
        scroll.addView(layout); setContentView(scroll)
        window.insetsController?.setSystemBarsAppearance(
            if (dark) 0 else WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS or WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS,
            WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS or WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS)
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission("android.permission.POST_NOTIFICATIONS") != 0)
            requestPermissions(arrayOf("android.permission.POST_NOTIFICATIONS"), 1)
        startClient()
    }
    private fun startClient() { startForegroundService(Intent(this, AssistantService::class.java)) }
    override fun onResume() { super.onResume(); handler.post(update) }
    override fun onPause() { handler.removeCallbacks(update); super.onPause() }
}
