package dev.jiezhi.client

import android.content.Context
import android.os.PowerManager
import fi.iki.elonen.NanoHTTPD
import org.json.JSONObject
import org.json.JSONArray
import java.io.File
import java.io.FileOutputStream
import java.security.MessageDigest
import java.util.UUID
import kotlin.concurrent.thread

/** Native diffusion runs in a separate Android process, never in the desktop. */
class MediaEngine(private val context: Context, private val claim: (String) -> Unit, private val release: () -> Unit) {
    private val root=File(context.filesDir,"media").apply { mkdirs() }
    private val outputs=File(context.filesDir,"media-results").apply { mkdirs() }
    private val lock=Any()
    @Volatile private var process:Process?=null
    @Volatile private var current=JSONObject().put("state","idle")
    @Volatile private var stopped=false
    @Volatile private var npuVideo=false
    private val binary get()=File(context.applicationInfo.nativeLibraryDir,"libjiezhi_diffusion.so")
    private fun json(value:JSONObject)=NanoHTTPD.newFixedLengthResponse(NanoHTTPD.Response.Status.OK,"application/json",value.toString())
    private fun id(value:String):String { require(value.matches(Regex("[a-f0-9]{64}"))) { "Invalid media ID" };return value }
    private fun file(value:String,ext:String)=File(root,"${id(value)}.$ext")
    private fun body(s:NanoHTTPD.IHTTPSession):JSONObject {
        val size=s.headers["content-length"]?.toIntOrNull()?:0;require(size in 1..262144)
        return JSONObject(String(bytes(s,size),Charsets.UTF_8))
    }
    private fun bytes(s:NanoHTTPD.IHTTPSession,size:Int):ByteArray {
        val data=ByteArray(size);var offset=0
        while(offset<size) { val n=s.inputStream.read(data,offset,size-offset);check(n>0) { "Incomplete request" };offset+=n }
        return data
    }
    private fun sha(f:File):String {
        val hash=MessageDigest.getInstance("SHA-256");f.inputStream().use { input -> val buffer=ByteArray(1024*1024);while(true){val n=input.read(buffer);if(n<0)break;hash.update(buffer,0,n)} }
        return hash.digest().joinToString(""){"%02x".format(it)}
    }
    private fun weights(value:String):File {
        val meta=JSONObject(file(value,"json").readText());return file(value,meta.getString("format")).also { require(it.exists()) { "Media weights missing" } }
    }
    private fun library()=JSONArray().apply { synchronized(lock) { root.listFiles()?.filter { it.extension=="json" }?.forEach { put(JSONObject(it.readText())) } } }
    fun cancel() { stopped=true;if(npuVideo)context.stopService(android.content.Intent(context,NpuVideoService::class.java));process?.destroy();process?.let { p -> thread { Thread.sleep(500);if(p.isAlive)p.destroyForcibly() } } }
    fun route(s:NanoHTTPD.IHTTPSession):NanoHTTPD.Response {
        return when {
            s.uri=="/v1/media" && s.method==NanoHTTPD.Method.GET -> json(JSONObject().put("available",binary.exists()).put("backends",JSONArray(listOf("cpu","npu"))).put("backend","cpu").put("models",library()).put("job",current))
            s.uri=="/v1/media/images" && s.method==NanoHTTPD.Method.POST -> {
                val size=s.headers["content-length"]?.toIntOrNull()?:0;require(size in 8..(16*1024*1024)) {"Image must be at most 16 MiB"}
                val data=bytes(s,size);val options=android.graphics.BitmapFactory.Options().apply {inJustDecodeBounds=true}
                android.graphics.BitmapFactory.decodeByteArray(data,0,data.size,options)
                require(options.outWidth in 1..2048 && options.outHeight in 1..2048) {"Input images are limited to 2048 pixels per side"}
                val bitmap=android.graphics.BitmapFactory.decodeByteArray(data,0,data.size)?:error("Invalid image")
                val name=UUID.randomUUID().toString().replace("-","")+".png"
                try {File(outputs,name).outputStream().use {check(bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG,100,it))}} finally {bitmap.recycle()}
                json(JSONObject().put("phone_result",name))
            }
            s.uri=="/v1/media/uploads" && s.method==NanoHTTPD.Method.POST -> synchronized(lock) {
                val b=body(s);val key=id(b.getString("id"));val size=b.getLong("size");val format=b.getString("format")
                require(size in 16..(16L*1024*1024*1024));require(format in listOf("gguf","safetensors","qnn","data"))
                if(file(key,"json").exists())json(JSONObject().put("complete",true).put("offset",size))
                else {
                    val part=file(key,"part");val upload=file(key,"upload")
                    if(upload.exists()) { val old=JSONObject(upload.readText());require(old.getLong("size")==size && old.getString("format")==format) { "Upload metadata mismatch" } }
                    require(root.usableSpace>=size-part.length()+64*1024*1024) { "Not enough phone storage" }
                    upload.writeText(JSONObject().put("id",key).put("name",b.getString("name").take(180)).put("format",format).put("size",size).toString())
                    json(JSONObject().put("complete",false).put("offset",part.length()))
                }
            }
            s.uri.startsWith("/v1/media/uploads/") && s.method==NanoHTTPD.Method.PUT -> synchronized(lock) {
                val key=id(s.uri.substringAfterLast('/'));val metadata=JSONObject(file(key,"upload").readText());val part=file(key,"part")
                val size=s.headers["content-length"]?.toIntOrNull()?:0;require(size in 1..(4*1024*1024));require(s.headers["x-offset"]?.toLongOrNull()==part.length());require(part.length()+size<=metadata.getLong("size"))
                FileOutputStream(part,true).use { it.write(bytes(s,size));it.fd.sync() };json(JSONObject().put("offset",part.length()))
            }
            s.uri=="/v1/media/commit" && s.method==NanoHTTPD.Method.POST -> synchronized(lock) {
                val key=id(body(s).getString("id"));val part=file(key,"part");val metadata=JSONObject(file(key,"upload").readText())
                require(part.length()==metadata.getLong("size"));require(sha(part)==key) { "Media checksum mismatch" }
                val prefix=ByteArray(8);java.io.DataInputStream(part.inputStream()).use { it.readFully(prefix) }
                if(metadata.getString("format")=="gguf")require(String(prefix.copyOfRange(0,4))=="GGUF") { "Invalid GGUF" }
                else if(metadata.getString("format")=="safetensors") {
                    val header=java.nio.ByteBuffer.wrap(prefix).order(java.nio.ByteOrder.LITTLE_ENDIAN).long
                    require(header in 2..(64L*1024*1024) && header+8<part.length()) { "Invalid safetensors header" }
                }
                if(metadata.getString("format")=="qnn") {extractQnn(part,key);part.delete()} else check(part.renameTo(file(key,metadata.getString("format"))));file(key,"json").writeText(metadata.toString());file(key,"upload").delete();json(JSONObject().put("models",library()))
            }
            s.uri=="/v1/media/bundles" && s.method==NanoHTTPD.Method.POST -> registerBundle(body(s))
            s.uri=="/v1/media/generate" && s.method==NanoHTTPD.Method.POST -> start(body(s))
            s.uri=="/v1/media/job" && s.method==NanoHTTPD.Method.GET -> json(current)
            s.uri=="/v1/media/cancel" && s.method==NanoHTTPD.Method.POST -> {body(s);cancel();json(JSONObject().put("ok",true))}
            s.uri.startsWith("/v1/media/results/") && s.method==NanoHTTPD.Method.GET -> {
                val key=s.uri.substringAfterLast('/');require(key.matches(Regex("[a-f0-9]{32}\\.(png|avi|mp4)")))
                val output=File(outputs,key);require(output.isFile);NanoHTTPD.newFixedLengthResponse(NanoHTTPD.Response.Status.OK,if(key.endsWith("png"))"image/png" else if(key.endsWith("mp4"))"video/mp4" else "video/x-msvideo",output.inputStream(),output.length())
            }
            else -> error("Unknown media endpoint")
        }
    }
    private fun start(b:JSONObject):NanoHTTPD.Response {
        if(b.optString("backend")=="npu")return startNpu(b)
        require(binary.exists()) { "Install the media-enabled Android client" }
        val kind=b.getString("kind");require(kind in listOf("image","video"));require(b.optString("backend","cpu")=="cpu") { "This media build supports phone CPU; it does not claim NPU acceleration" }
        val prompt=b.getString("prompt");require(prompt.length in 1..16000)
        val width=b.optInt("width",256);val height=b.optInt("height",256);val steps=b.optInt("steps",8);val frames=b.optInt("frames",9);val fps=b.optInt("fps",8)
        require(width in 128..1024 && height in 128..1024 && width%64==0 && height%64==0);require(steps in 1..50)
        if(kind=="video")require(width<=512 && height<=512 && frames in 5..81 && frames%4==1 && fps in 1..30)
        val cfg=b.optDouble("cfg",7.0);require(cfg.isFinite() && cfg in 1.0..20.0)
        val key=UUID.randomUUID().toString().replace("-","");val output=File(outputs,key+if(kind=="image")".png" else ".avi")
        val args=mutableListOf(binary.absolutePath,"--backend","cpu","-t","4","-p",prompt,"-n",b.optString("negative","").take(16000),"-W",width.toString(),"-H",height.toString(),"--steps",steps.toString(),"--seed",b.optLong("seed",42).toString(),"--cfg-scale",cfg.toString(),"--sampling-method","euler","-o",output.absolutePath)
        val model=weights(b.getString("model_id"))
        if(kind=="image")args.addAll(listOf("-m",model.absolutePath))
        else {
            args.addAll(listOf("-M","vid_gen","--diffusion-model",model.absolutePath,"--vae",weights(b.getString("vae_id")).absolutePath,"--t5xxl",weights(b.getString("encoder_id")).absolutePath,"--video-frames",frames.toString(),"--fps",fps.toString(),"--flow-shift","3.0","--diffusion-fa"))
            if(b.optString("vision_id").isNotEmpty())args.addAll(listOf("--clip_vision",weights(b.getString("vision_id")).absolutePath))
        }
        val initial=b.optString("init_result")
        if(initial.isNotEmpty()) {
            require(initial.matches(Regex("[a-f0-9]{32}\\.png")));val image=File(outputs,initial);require(image.isFile);args.addAll(listOf("-i",image.absolutePath))
        }
        claim("cpu");stopped=false;current=JSONObject().put("id",key).put("state","running").put("kind",kind).put("backend","phone-cpu").put("log","Loading media model…")
        thread(name="JieZhi-media") {
            val wake=context.getSystemService(PowerManager::class.java).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,"JieZhi:media")
            try {
                wake.acquire(60*60*1000L)
                val p=ProcessBuilder(args).redirectErrorStream(true).directory(outputs).start();process=p
                if(stopped)p.destroy()
                thread(isDaemon=true) { Thread.sleep(30*60*1000L);if(process===p && p.isAlive){stopped=true;p.destroyForcibly()} }
                val log=ArrayDeque<String>()
                p.inputStream.bufferedReader().useLines { lines -> lines.forEach { line ->
                    if(log.size>=60)log.removeFirst();log.addLast(line.takeLast(500));current=JSONObject(current.toString()).put("log",log.joinToString("\n").takeLast(12000))
                } }
                val code=p.waitFor()
                val completed=JSONObject(current.toString()).put("exit_code",code)
                if(!stopped && code==0 && output.exists())completed.put("result",output.name).put("size",output.length()).put("sha256",sha(output))
                completed.put("state",if(stopped)"cancelled" else if(completed.has("result"))"complete" else "failed")
                current=completed
            } catch(e:Throwable) { current=JSONObject(current.toString()).put("state",if(stopped)"cancelled" else "failed").put("error",e.message?:"Media inference failed") }
            finally {process=null;if(wake.isHeld)wake.release();release()}
        }
        return json(current)
    }
    private fun extractQnn(archive:File,key:String) {
        val stage=File(root,"$key.extract");stage.deleteRecursively();stage.mkdirs();var total=0L;val names=mutableSetOf<String>()
        val wake=context.getSystemService(PowerManager::class.java).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,"JieZhi:QNN-import");wake.acquire(10*60*1000L)
        try {
            java.util.zip.ZipInputStream(archive.inputStream().buffered()).use { zip ->
                while(true) {
                    val entry=zip.nextEntry?:break
                    require(!entry.name.startsWith('/') && !entry.name.contains('\\') && entry.name.split('/').none {it==".."}) {"Unsafe archive path"}
                    if(entry.isDirectory)continue
                    val name=entry.name.substringAfterLast('/');require(name.matches(Regex("[A-Za-z0-9_.-]{1,100}")) && name.substringAfterLast('.') in listOf("bin","mnn","json","patch","txt")) {"Unsupported QNN archive entry"}
                    require(names.add(name) && names.size<=100) {"Duplicate or excessive archive files"}
                    File(stage,name).outputStream().use { out ->
                        val buf=ByteArray(1024*1024)
                        while(true){val n=zip.read(buf);if(n<0)break;total+=n;require(total<=8L*1024*1024*1024 && root.usableSpace>64*1024*1024) {"QNN archive exceeds storage limit"};out.write(buf,0,n)}
                    }
                }
            }
            require(listOf("unet.bin","vae_decoder.bin","tokenizer.json","clip_v2.mnn").all {File(stage,it).isFile}) {"Use an SD 1.5 QNN package with CLIP v2, UNet, VAE and tokenizer"}
            val target=File(root,"$key.bundle");target.deleteRecursively();check(stage.renameTo(target))
        } catch(e:Throwable) {stage.deleteRecursively();throw e}
        finally {if(wake.isHeld)wake.release()}
    }
    private fun registerBundle(b:JSONObject):NanoHTTPD.Response = synchronized(lock) {
        require(b.getString("kind")=="neodragon");val entries=b.getJSONArray("files");require(entries.length()==21)
        val canonical=JSONArray();val seen=mutableSetOf<String>();var size=0L
        for(i in 0 until entries.length()) {
            val e=entries.getJSONObject(i);val path=e.getString("path");require(path.matches(Regex("(ctx|assets)/[A-Za-z0-9_.-]{1,100}")) && seen.add(path)) {"Invalid bundle path"}
            val key=id(e.getString("id"));val f=weights(key);size+=f.length();canonical.put(JSONObject().put("id",key).put("path",path))
        }
        val key=MessageDigest.getInstance("SHA-256").digest(canonical.toString().toByteArray()).joinToString(""){"%02x".format(it)}
        val dir=File(root,"$key.bundle").apply {mkdirs()}
        val wake=context.getSystemService(PowerManager::class.java).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,"JieZhi:video-import");wake.acquire(10*60*1000L)
        try {for(i in 0 until canonical.length()) {
            val e=canonical.getJSONObject(i);val src=weights(e.getString("id"));val dst=File(dir,e.getString("path"));dst.parentFile!!.mkdirs()
            if(!dst.isFile || dst.length()!=src.length()) {
                require(root.usableSpace>src.length()+64*1024*1024) {"Not enough phone storage to assemble the video bundle"}
                val tmp=File(dst.parentFile,dst.name+".tmp")
                try {
                    src.inputStream().use {input -> FileOutputStream(tmp).use {out -> input.copyTo(out,1024*1024);out.fd.sync()} }
                    check(tmp.length()==src.length() && tmp.renameTo(dst)) {"Could not complete video component"}
                } finally {tmp.delete()}
            }
        }} finally {if(wake.isHeld)wake.release()}
        val graphs=com.abrah.nightmare.npu.Video.requiredModels()
        require(graphs.all {g -> File(dir,"ctx").listFiles()?.any {it.name.startsWith("${g}_v79") && it.extension=="bin"}==true}) {"Missing Neodragon graph"}
        require(com.abrah.nightmare.npu.NpuFiles.ASSETS.all {File(dir,"assets/$it").isFile}) {"Missing Neodragon asset"}
        val meta=JSONObject().put("id",key).put("name","Neodragon · Hexagon NPU").put("format","neodragon").put("size",size)
        file(key,"json").writeText(meta.toString());json(meta)
    }
    private fun startNpu(b:JSONObject):NanoHTTPD.Response {
        val kind=b.getString("kind");require(kind in listOf("image","video"))
        val prompt=b.getString("prompt");require(prompt.length in 1..16000)
        val key=UUID.randomUUID().toString().replace("-","");val modelId=id(b.getString("model_id"));val meta=JSONObject(file(modelId,"json").readText())
        val upscale=kind=="image" && b.optString("operation")=="upscale"
        val modelDir=File(root,"$modelId.bundle");require(upscale || modelDir.isDirectory)
        val width=b.optInt("width",512);val height=b.optInt("height",512)
        if(upscale)require(meta.getString("format")=="neodragon" || (meta.getString("format")=="data" && meta.getString("name").contains("quicksrm"))) {"Select a QuickSRNet model for NPU upscaling"}
        else if(kind=="image") {
            require(b.optString("operation","generate") in listOf("generate","expand"))
            val strength=b.optDouble("strength",0.65);require(strength.isFinite() && strength in 0.0..1.0)
            require(meta.getString("format")=="qnn" && width==512 && height==512) {"QNN image models use 512×512 in this build"}
            require(b.optInt("steps",20) in 1..50);val cfg=b.optDouble("cfg",7.0);require(cfg.isFinite() && cfg in 1.0..20.0)
        } else require(meta.getString("format")=="neodragon" && width==1024 && height==640 && b.optInt("frames",49)==49 && b.optInt("fps",24) in 1..30) {"Neodragon generates 49 frames at 1024×640"}
        val initial=b.optString("init_result");val initialFile=if(initial.isEmpty())null else {require(initial.matches(Regex("[a-f0-9]{32}\\.png")));File(outputs,initial).also {require(it.isFile)}}
        require((!upscale && b.optString("operation")!="expand") || initialFile!=null) {"This action needs an input image"}
        val output=File(outputs,key+if(kind=="image")".png" else ".mp4")
        claim("npu");stopped=false;npuVideo=kind=="video" || upscale;current=JSONObject().put("id",key).put("state","running").put("kind",kind).put("backend","phone-npu").put("log","Loading Hexagon NPU runtime…")
        thread(name="JieZhi-QNN") {
            val wake=context.getSystemService(PowerManager::class.java).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,"JieZhi:QNN");val logs=ArrayDeque<String>()
            fun log(line:String) {synchronized(logs) {if(logs.size>=40)logs.removeFirst();logs.addLast(line.takeLast(500));if(current.optString("id")==key)current=JSONObject(current.toString()).put("log",logs.joinToString("\n").takeLast(12000))}}
            try {
                wake.acquire(31*60*1000L)
                if(kind=="image" && !upscale) QnnRuntime.image(context,modelDir,b,output,initialFile,{stopped},{process=it},::log)
                else {
                    val job=File(outputs,key).apply {mkdirs()};File(job,"request.json").writeText(b.toString())
                    context.startForegroundService(android.content.Intent(context,NpuVideoService::class.java).putExtra("job",key))
                    val start=System.currentTimeMillis();var finished=false
                    while(!finished) {
                        check(!stopped) {"Generation cancelled"};check(System.currentTimeMillis()-start<30*60*1000L) {"Video generation timed out"}
                        val status=File(job,"status.json")
                        if(status.isFile) {
                            val info=JSONObject(status.readText());log(info.optString("log"))
                            if(info.optString("state")=="running" && info.optInt("pid")>0) {
                                try {android.system.Os.kill(info.getInt("pid"),0)}
                                catch(e:android.system.ErrnoException) {if(e.errno==android.system.OsConstants.ESRCH)error("NPU video process stopped unexpectedly; retry with the phone unlocked") else throw e}
                            }
                            when(info.getString("state")) {"complete"->finished=true;"failed","cancelled"->error(info.optString("error","NPU video failed"))}
                        }
                        check(status.isFile || System.currentTimeMillis()-start<60000) {"NPU video service did not start"}
                        if(!finished)Thread.sleep(400)
                    }
                }
                check(!stopped && output.isFile) {"Generation cancelled or output missing"}
                current=JSONObject(current.toString()).put("result",output.name).put("size",output.length()).put("sha256",sha(output)).put("state","complete")
            } catch(e:Throwable) {current=JSONObject(current.toString()).put("state",if(stopped)"cancelled" else "failed").put("error",e.message?:"QNN failed")}
            finally {if(npuVideo)context.stopService(android.content.Intent(context,NpuVideoService::class.java));npuVideo=false;process=null;if(wake.isHeld)wake.release();release()}
        }
        return json(current)
    }

}
