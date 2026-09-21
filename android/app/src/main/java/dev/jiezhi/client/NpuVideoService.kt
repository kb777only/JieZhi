package dev.jiezhi.client

import android.app.*
import android.content.Intent
import android.os.*
import android.graphics.BitmapFactory
import com.abrah.nightmare.npu.*
import org.json.JSONObject
import java.io.File
import kotlin.concurrent.thread

/** Isolated from the GenieX process, including QNN globals and native failures. */
class NpuVideoService:Service() {
    @Volatile private var running=false
    override fun onBind(intent:Intent?)=null
    override fun onDestroy() {super.onDestroy();android.os.Process.killProcess(android.os.Process.myPid())}
    override fun onStartCommand(intent:Intent?,flags:Int,startId:Int):Int {
        if(running)return START_NOT_STICKY
        val key=intent?.getStringExtra("job")?:return START_NOT_STICKY
        require(key.matches(Regex("[a-f0-9]{32}")));running=true
        val manager=getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel("media","NPU media generation",NotificationManager.IMPORTANCE_LOW))
        startForeground(2,Notification.Builder(this,"media").setContentTitle("JieZhi · NPU media").setContentText("Generating on this phone").setSmallIcon(android.R.drawable.stat_notify_sync).build())
        thread(name="JieZhi-NPU-video") {
            val job=File(filesDir,"media-results/$key");val status=File(job,"status.json");val cancel=File(job,"cancel");val runner=QnnRunner(this)
            fun write(value:JSONObject) {val tmp=File(job,"status.tmp");tmp.writeText(value.put("pid",android.os.Process.myPid()).toString());check(tmp.renameTo(status))}
            fun log(message:String) {check(!cancel.exists()) {"Generation cancelled"};write(JSONObject().put("state","running").put("log",message))}
            try {
                val b=JSONObject(File(job,"request.json").readText());log("Checking Hexagon NPU arithmetic…")
                val verdict=NpuCanary.run(this,runner);check(verdict is NpuCanary.Result.Ok) {verdict.summary};log(verdict.summary)
                if(!b.optBoolean("probe")) {
                    val modelId=b.getString("model_id");require(modelId.matches(Regex("[a-f0-9]{64}")))
                    if(b.optString("operation")=="upscale") {
                        val meta=JSONObject(File(filesDir,"media/$modelId.json").readText())
                        val model=if(meta.getString("format")=="neodragon")File(filesDir,"media/$modelId.bundle/ctx/quicksrm2x_v79.bin") else File(filesDir,"media/$modelId.data")
                        val source=b.getString("init_result");require(source.matches(Regex("[a-f0-9]{32}\\.png")))
                        NpuImageOps.upscale(runner,model,File(filesDir,"media-results/$source"),File(filesDir,"media-results/$key.png"),::log)
                        write(JSONObject().put("state","complete").put("log","Upscaled 2× on Hexagon NPU"))
                    } else {
                    NpuFiles.selectedRoot=File(filesDir,"media/$modelId.bundle")
                    val missing=NpuFiles.missing(this,Video.requiredModels())+NpuFiles.missingAssets(this);check(missing.isEmpty()) {"Missing video components: $missing"}
                    val initial=b.optString("init_result");val bitmap=if(initial.isNotEmpty()) {require(initial.matches(Regex("[a-f0-9]{32}\\.png")));BitmapFactory.decodeFile(File(filesDir,"media-results/$initial").absolutePath)} else null
                    val video=Video(this,runner,::log).generate(b.getString("prompt"),b.optLong("seed",42),bitmap) {stage,step,total -> log("Hexagon NPU · $stage · $step/$total")}
                    val output=File(filesDir,"media-results/$key.mp4");VideoWriter.encode(this,video.frames,b.optInt("fps",24),output,::log)
                    video.frames.forEach {it.recycle()};write(JSONObject().put("state","complete").put("log","49 frames generated on Hexagon NPU").put("seconds",video.seconds))
                    }
                } else write(JSONObject().put("state","complete").put("log",verdict.summary))
            } catch(e:Throwable) {write(JSONObject().put("state",if(cancel.exists())"cancelled" else "failed").put("error",e.message?:"NPU generation failed"))}
            finally {runner.releaseAll();stopSelf();android.os.Process.killProcess(android.os.Process.myPid())}
        }
        return START_NOT_STICKY
    }
}
