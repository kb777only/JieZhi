package dev.jiezhi.client

import android.content.Context
import android.os.Build
import android.os.PowerManager
import com.geniex.sdk.LlmWrapper
import com.geniex.sdk.bean.*
import fi.iki.elonen.NanoHTTPD
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.buffer
import org.json.JSONArray
import org.json.JSONObject
import java.io.*
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread

/** Versioned loopback API, reached exclusively through an ADB USB forward. */
class BridgeServer(private val context: Context) : NanoHTTPD("127.0.0.1", 39471) {
    private val telemetry = Telemetry(context)
    private val random = SecureRandom()
    @Volatile var pairingCode = (100000 + random.nextInt(900000)).toString(); private set
    @Volatile var state = "Ready to pair"; private set
    @Volatile var loadedName = ""; private set
    private var token = ""
    private var paired = false
    private var attempts = 0
    private var attemptWindow = System.currentTimeMillis()
    private val root = File(context.filesDir, "models").apply { mkdirs() }
    private val busy = AtomicBoolean(false)
    private val cancel = AtomicBoolean(false)
    @Volatile private var closing = false
    @Volatile private var model: LlmWrapper? = null
    @Volatile private var loadedId = ""
    @Volatile private var compute = "npu"
    private val storageLock = Any()
    @Volatile var lastProfile = JSONObject(); private set
    @Volatile var contextSize = 2048; private set
    private val media = MediaEngine(context, { mediaBackend ->
        check(!closing && busy.compareAndSet(false, true)) { "Phone is busy; stop the current operation first" }
        try {
            model?.close(); model = null; loadedId = ""; loadedName = ""; lastProfile = JSONObject()
            compute = mediaBackend; state = "Generating media on $backendLabel"
        } catch (e: Throwable) { busy.set(false); throw e }
    }, { state = "Connected to desktop"; busy.set(false) })
    val backendLabel: String get() = if (compute == "npu") "Hexagon NPU" else "Phone CPU"
    private val activityLease = context.getSystemService(PowerManager::class.java)
        .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "JieZhi:usb-activity").apply { setReferenceCounted(false) }

    private fun json(value: JSONObject, status: Response.Status = Response.Status.OK): Response =
        newFixedLengthResponse(status, "application/json", value.toString()).apply {
            addHeader("Cache-Control", "no-store")
            // Some rejection paths intentionally do not consume an untrusted request body.
            if (status != Response.Status.OK) closeConnection(true)
        }
    private fun obj(vararg values: Pair<String, Any?>) = JSONObject().apply { values.forEach { put(it.first, it.second ?: JSONObject.NULL) } }
    private fun body(s: IHTTPSession): JSONObject {
        val size = s.headers["content-length"]?.toIntOrNull() ?: 0
        require(size in 1..262144) { "JSON body must be 1–262144 bytes" }
        return JSONObject(String(readBytes(s.inputStream, size), Charsets.UTF_8))
    }
    private fun readBytes(input: InputStream, size: Int): ByteArray {
        val bytes = ByteArray(size); var n = 0
        while (n < size) { val got = input.read(bytes, n, size - n); if (got < 0) throw EOFException("Incomplete request"); n += got }
        return bytes
    }
    private fun file(id: String, suffix: String): File {
        require(id.matches(Regex("[a-f0-9]{64}"))) { "Invalid model identifier" }
        return File(root, "$id.$suffix")
    }
    private fun equal(a: String, b: String) = MessageDigest.isEqual(a.toByteArray(), b.toByteArray())
    private fun exclusive(action: () -> Response): Response {
        check(!closing && busy.compareAndSet(false, true)) { "Client is busy; wait or cancel the active request" }
        try { return action() } finally { busy.set(false) }
    }
    override fun serve(s: IHTTPSession): Response = try {
        if (s.uri == "/v1/pair" && s.method == Method.POST) synchronized(this) {
            if (System.currentTimeMillis() - attemptWindow > 60_000) { attempts = 0; attemptWindow = System.currentTimeMillis() }
            check(!paired) { "Already paired. Stop and restart the phone client to pair again." }
            check(++attempts <= 5) { "Too many attempts; wait one minute" }
            require(equal(body(s).optString("code"), pairingCode)) { "Incorrect pairing code" }
            token = ByteArray(32).also(random::nextBytes).joinToString("") { "%02x".format(it) }
            paired = true; pairingCode = "Paired"; state = "Connected to desktop"
            activityLease.acquire(120_000)
            json(obj("token" to token, "protocol" to 1))
        } else if (!paired || !equal(s.headers["authorization"] ?: "", "Bearer $token")) {
            json(obj("error" to "Pair with the code shown on the phone"), Response.Status.UNAUTHORIZED)
        } else {
            activityLease.acquire(120_000)
            when {
            s.uri == "/v1/media" || s.uri.startsWith("/v1/media/") -> media.route(s)
            s.uri == "/v1/telemetry" && s.method == Method.GET -> json(telemetry.snapshot(state, loadedName, compute, lastProfile))
            s.uri == "/v1/status" && s.method == Method.GET -> {
                val models = synchronized(storageLock) { JSONArray().apply {
                    root.listFiles()?.filter { it.extension == "json" && File(root, "${it.nameWithoutExtension}.gguf").exists() }
                        ?.forEach { put(JSONObject(it.readText())) }
                } }
                val pm = context.getSystemService(PowerManager::class.java)
                json(obj("protocol" to 1, "phone" to "${Build.MANUFACTURER} ${Build.MODEL}",
                    "soc" to Build.SOC_MODEL, "android" to Build.VERSION.RELEASE,
                    "supported" to Build.SOC_MODEL.contains("8750"), "state" to state,
                    "busy" to busy.get(), "loaded_id" to loadedId, "loaded_name" to loadedName,
                    "context_size" to contextSize, "requested_backend" to compute, "backend_evidence" to "See native backend logs in desktop diagnostics",
                    "free_bytes" to root.usableSpace, "thermal_status" to pm.currentThermalStatus,
                    "models" to models, "last_profile" to lastProfile))
            }
            s.uri == "/v1/uploads" && s.method == Method.POST -> synchronized(storageLock) {
                val data = body(s); val id = data.getString("id"); val size = data.getLong("size")
                val name = data.getString("name").take(180)
                require(size in 24..(16L * 1024 * 1024 * 1024)) { "Model size must be below 16 GiB" }
                require(name.endsWith(".gguf", true)) { "V1 imports GGUF models" }
                val part = file(id, "part"); val complete = file(id, "gguf")
                if (complete.exists()) json(obj("offset" to size, "complete" to true)) else {
                    require(root.usableSpace > size - part.length() + 128 * 1024 * 1024) { "Not enough phone storage" }
                    file(id, "upload").writeText(obj("id" to id, "name" to name, "size" to size).toString())
                    json(obj("offset" to part.length(), "complete" to false))
                }
            }
            s.uri.startsWith("/v1/uploads/") && s.method == Method.PUT -> synchronized(storageLock) {
                val id = s.uri.removePrefix("/v1/uploads/"); val metadata = JSONObject(file(id, "upload").readText())
                val part = file(id, "part"); val offset = s.headers["x-offset"]?.toLongOrNull()
                require(offset == part.length()) { "Transfer offset mismatch; reconnect and resume" }
                val size = s.headers["content-length"]?.toIntOrNull() ?: 0
                require(size in 1..(4 * 1024 * 1024) && part.length() + size <= metadata.getLong("size")) { "Invalid chunk size" }
                val bytes = readBytes(s.inputStream, size)
                FileOutputStream(part, true).use { it.write(bytes); it.fd.sync() }
                json(obj("offset" to part.length()))
            }
            s.uri == "/v1/commit" && s.method == Method.POST -> exclusive { synchronized(storageLock) {
                val id = body(s).getString("id"); val part = file(id, "part")
                val metadata = JSONObject(file(id, "upload").readText())
                require(part.length() == metadata.getLong("size")) { "Transfer is incomplete" }
                state = "Verifying model integrity"
                try {
                    part.inputStream().use { require(String(readBytes(it, 4)) == "GGUF") { "Not a GGUF model" } }
                    val digest = MessageDigest.getInstance("SHA-256")
                    part.inputStream().use { input -> val buf = ByteArray(1024 * 1024); while (true) { val n = input.read(buf); if (n < 0) break; digest.update(buf, 0, n) } }
                    val actual = digest.digest().joinToString("") { "%02x".format(it) }
                    if (actual != id) { part.delete(); error("SHA-256 mismatch; import the model again") }
                    file(id, "json").writeText(metadata.toString())
                    check(part.renameTo(file(id, "gguf"))) { "Cannot commit model" }
                    file(id, "upload").delete()
                    json(obj("ok" to true))
                } finally { state = "Connected to desktop" }
            } }
            s.uri == "/v1/load" && s.method == Method.POST -> exclusive {
                val b = body(s); val id = b.getString("id"); val selected = b.optString("backend", "npu")
                require(selected in listOf("npu", "cpu")) { "V1 supports NPU and explicit CPU diagnostics" }
                require(Build.SOC_MODEL.contains("8750")) { "V1 targets Snapdragon 8 Elite (SM8750)" }
                require(file(id, "gguf").exists()) { "Model is not installed" }
                val ctx = b.optInt("context", 2048); require(ctx in 512..8192) { "Context must be 512–8192" }
                state = "Loading model on $selected"
                try {
                    model?.close(); model = null; loadedId = ""; loadedName = ""; lastProfile = JSONObject()
                    model = runBlocking { LlmWrapper.builder().llmCreateInput(LlmCreateInput(
                        model_path = file(id, "gguf").absolutePath,
                        config = ModelConfig(nCtx = ctx, nBatch = 256, nUBatch = 128, nThreads = 4, nThreadsBatch = 4),
                        runtime_id = "llama_cpp", compute_unit = selected)).build().getOrThrow() }
                    loadedId = id; loadedName = JSONObject(file(id, "json").readText()).getString("name"); compute = selected; contextSize = ctx
                    json(obj("ok" to true, "requested_backend" to selected))
                } finally { state = if (model == null) "Model load failed; see desktop diagnostics" else "Ready to chat" }
            }
            s.uri == "/v1/unload" && s.method == Method.POST -> exclusive {
                body(s)
                model?.close(); model = null; loadedId = ""; loadedName = ""; lastProfile = JSONObject(); state = "Connected to desktop"
                json(obj("ok" to true))
            }
            s.uri.startsWith("/v1/models/") && s.method == Method.DELETE -> exclusive { synchronized(storageLock) {
                val id = s.uri.removePrefix("/v1/models/"); check(id != loadedId) { "Unload this model before deleting it" }
                listOf("gguf", "json", "part", "upload").forEach { file(id, it).delete() }
                json(obj("ok" to true))
            } }
            s.uri == "/v1/cancel" && s.method == Method.POST -> {
                body(s)
                cancel.set(true); runBlocking { model?.stopStream() }; json(obj("ok" to true))
            }
            s.uri == "/v1/chat" && s.method == Method.POST -> generate(body(s))
            else -> json(obj("error" to "Unknown endpoint or method"), Response.Status.NOT_FOUND)
        }
        }
    } catch (e: Exception) {
        android.util.Log.w("JieZhi", "Request failed: ${e.message}")
        json(obj("error" to (e.message ?: "Request failed")), if (e is IllegalStateException) Response.Status.CONFLICT else Response.Status.BAD_REQUEST)
    }

    private fun generate(b: JSONObject): Response {
        val input = b.getJSONArray("messages"); require(input.length() in 1..100) { "Use 1–100 messages" }
        val messages = Array(input.length()) { i ->
            val m = input.getJSONObject(i); val role = m.getString("role")
            require(role in listOf("user", "assistant", "system")) { "Invalid role" }
            ChatMessage(role, m.getString("content"))
        }
        val maxTokens = b.optInt("max_tokens", 512); require(maxTokens in 1..2048)
        check(!closing && busy.compareAndSet(false, true)) { "Client is busy" }
        val llm = model ?: run { busy.set(false); error("Load a model first") }
        cancel.set(false)
        val pipe = PipedInputStream(65536); val output = PipedOutputStream(pipe)
        state = "Generating on $compute"; telemetry.begin()
        thread(name = "JieZhi-inference") {
            val wake = context.getSystemService(PowerManager::class.java).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "JieZhi:inference")
            fun emit(event: JSONObject) { output.write((event.toString() + "\n").toByteArray()); output.flush() }
            try {
                wake.acquire(10 * 60 * 1000L)
                runBlocking {
                    llm.reset()
                    val prompt = llm.applyChatTemplate(messages, null, false).getOrThrow().formattedText
                    emit(obj("type" to "start", "requested_backend" to compute))
                    llm.generateStreamFlow(prompt, GenerationConfig(maxTokens = maxTokens)).buffer(Channel.UNLIMITED).collect { event ->
                        when (event) {
                            is LlmStreamResult.Token -> { telemetry.token(); emit(obj("type" to "token", "text" to event.text)) }
                            is LlmStreamResult.Completed -> {
                                val p = event.profile
                                lastProfile = obj("ttft_ms" to p.ttftMs, "tokens_per_second" to p.decodingSpeed, "tokens" to p.generatedTokens)
                                emit(obj("type" to "done", "cancelled" to cancel.get(), "profile" to lastProfile))
                            }
                            is LlmStreamResult.Error -> throw event.throwable
                        }
                    }
                }
            } catch (e: Throwable) {
                runBlocking { llm.stopStream() }
                try { emit(obj("type" to "error", "error" to (e.message ?: "Inference failed"))) } catch (_: Exception) { }
            } finally {
                telemetry.end(); output.close(); if (wake.isHeld) wake.release()
                state = "Ready to chat"; busy.set(false)
            }
        }
        return newChunkedResponse(Response.Status.OK, "application/x-ndjson", pipe).apply { addHeader("Cache-Control", "no-store") }
    }
    fun shutdown() {
        media.cancel()
        closing = true; token = ""; cancel.set(true); stop()
        if (activityLease.isHeld) activityLease.release()
        thread { runBlocking { model?.stopStream() }; while (busy.get()) Thread.sleep(50); model?.close(); model = null }
    }
}
