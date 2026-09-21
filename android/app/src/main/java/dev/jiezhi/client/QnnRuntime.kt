package dev.jiezhi.client

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.Base64
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.ServerSocket
import java.net.URL
import kotlin.concurrent.thread

/** A separate QNN runtime directory prevents collisions with GenieX's text libraries. */
object QnnRuntime {
    @Synchronized fun prepare(context:Context):File {
        val dir=File(context.filesDir,"media-qnn-1.5.533").apply { mkdirs() }
        for(name in context.assets.list("qnnlibs").orEmpty()) {
            val dst=File(dir,name)
            if(!dst.isFile) {
                val tmp=File(dir,"$name.tmp")
                context.assets.open("qnnlibs/$name").use { input -> tmp.outputStream().use { input.copyTo(it) } }
                tmp.setReadable(true,false);check(tmp.renameTo(dst))
            }
        }
        return dir
    }
    fun image(context:Context,modelDir:File,b:JSONObject,output:File,initial:File?,stopped:()->Boolean,
              process:(Process)->Unit,log:(String)->Unit) {
        val runtime=prepare(context);val native=context.applicationInfo.nativeLibraryDir
        val port=ServerSocket(0,1,java.net.InetAddress.getLoopbackAddress()).use { it.localPort }
        val pb=ProcessBuilder(File(native,"libstable_diffusion_core.so").absolutePath,"--type","sd15npu","--model_dir",modelDir.absolutePath,"--lib_dir",runtime.absolutePath,"--port",port.toString())
            .directory(runtime).redirectErrorStream(true)
        pb.environment()["LD_LIBRARY_PATH"]="${runtime.absolutePath}:$native:/system/lib64:/vendor/lib64"
        pb.environment()["DSP_LIBRARY_PATH"]=runtime.absolutePath
        pb.environment()["ADSP_LIBRARY_PATH"]="${runtime.absolutePath};/vendor/lib/rfsa/adsp;/vendor/dsp/cdsp;/dsp"
        val p=pb.start();process(p)
        thread(isDaemon=true) {
            try {p.inputStream.bufferedReader().useLines { lines -> lines.forEach {log(it.takeLast(500))} } }
            catch(_:java.io.IOException) { /* Closing/cancelling the child closes its output pipe. */ }
        }
        var ready=false
        try {
            repeat(240) {
                if(!ready) {
                    check(!stopped()) {"Generation cancelled"};check(p.isAlive) {"QNN image backend exited during load"}
                    try { val c=URL("http://127.0.0.1:$port/health").openConnection() as HttpURLConnection;c.connectTimeout=500;c.readTimeout=500;ready=c.responseCode==200;c.disconnect() } catch(_:Exception) {}
                    if(!ready)Thread.sleep(250)
                }
            }
            check(ready) {"QNN image backend did not become ready"}
            val request=JSONObject().put("prompt",b.getString("prompt")).put("negative_prompt",b.optString("negative"))
                .put("steps",b.optInt("steps",20)).put("cfg",b.optDouble("cfg",7.0)).put("seed",b.optLong("seed",42))
                .put("width",512).put("height",512).put("scheduler","dpm").put("output_format","png")
            if(initial!=null) {
                val source=BitmapFactory.decodeFile(initial.absolutePath)?:error("Invalid input image")
                val bmp=Bitmap.createBitmap(512,512,Bitmap.Config.ARGB_8888);val canvas=android.graphics.Canvas(bmp)
                val expand=b.optString("operation")=="expand";val edge=if(expand)384 else 512
                val scale=minOf(edge.toFloat()/source.width,edge.toFloat()/source.height);val w=(source.width*scale).toInt().coerceAtLeast(1);val h=(source.height*scale).toInt().coerceAtLeast(1)
                val rect=android.graphics.Rect((512-w)/2,(512-h)/2,(512+w)/2,(512+h)/2)
                canvas.drawColor(android.graphics.Color.WHITE)
                if(expand)canvas.drawBitmap(source,null,android.graphics.Rect(0,0,512,512),android.graphics.Paint(android.graphics.Paint.FILTER_BITMAP_FLAG))
                canvas.drawBitmap(source,null,rect,android.graphics.Paint(android.graphics.Paint.FILTER_BITMAP_FLAG))
                fun encode(image:Bitmap):String {val bytes=java.io.ByteArrayOutputStream();image.compress(Bitmap.CompressFormat.PNG,100,bytes);return Base64.encodeToString(bytes.toByteArray(),Base64.NO_WRAP)}
                request.put("image",encode(bmp)).put("denoise_strength",if(expand)1.0 else b.optDouble("strength",0.65))
                if(expand) {
                    val mask=Bitmap.createBitmap(512,512,Bitmap.Config.ARGB_8888);val m=android.graphics.Canvas(mask);m.drawColor(android.graphics.Color.WHITE)
                    m.drawRect(rect,android.graphics.Paint().apply {color=android.graphics.Color.BLACK});request.put("mask",encode(mask));mask.recycle()
                    request.put("prompt",b.getString("prompt")+", continuous scene, seamless background to the edges")
                    request.put("negative_prompt",b.optString("negative")+", white border, blank margins, picture frame")
                }
                source.recycle();bmp.recycle()
            }
            val c=URL("http://127.0.0.1:$port/generate").openConnection() as HttpURLConnection
            c.requestMethod="POST";c.doOutput=true;c.connectTimeout=5000;c.readTimeout=120000;c.setRequestProperty("Content-Type","application/json")
            c.outputStream.use { it.write(request.toString().toByteArray()) }
            var saved=false
            try { c.inputStream.bufferedReader().useLines { lines -> lines.forEach { line ->
                check(!stopped()) {"Generation cancelled"}
                if(line.startsWith("data: ")) {
                    val event=JSONObject(line.substring(6))
                    when(event.optString("type")) {
                        "progress" -> log("Hexagon NPU · step ${event.optInt("step")} / ${event.optInt("total_steps")}")
                        "error" -> error(event.toString())
                        "complete" -> {
                            val data=Base64.decode(event.getString("image"),Base64.DEFAULT)
                            if(data.size>=8 && data[0]==137.toByte() && data[1]==80.toByte())output.writeBytes(data)
                            else {
                                val w=event.optInt("width",512);val h=event.optInt("height",512);val channels=event.optInt("channels",3)
                                check(w==512 && h==512 && channels in 3..4 && data.size==w*h*channels) {"Unexpected QNN image data"}
                                val px=IntArray(w*h) {i -> (255 shl 24) or ((data[i*channels].toInt() and 255) shl 16) or ((data[i*channels+1].toInt() and 255) shl 8) or (data[i*channels+2].toInt() and 255)}
                                output.outputStream().use { Bitmap.createBitmap(px,w,h,Bitmap.Config.ARGB_8888).compress(Bitmap.CompressFormat.PNG,100,it) }
                            };saved=true
                        }
                    }
                }
            } } } finally {c.disconnect()}
            check(saved) {"QNN returned no image"}
        } finally {p.destroy();if(!p.waitFor(1,java.util.concurrent.TimeUnit.SECONDS))p.destroyForcibly()}
    }
}
