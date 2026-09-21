package dev.jiezhi.client

import android.app.Instrumentation
import android.os.Bundle
import fi.iki.elonen.NanoHTTPD
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** Device-only integration harness. This class is absent from the distributed APK. */
class MediaInstrumentation:Instrumentation() {
    private lateinit var args:Bundle
    override fun onCreate(arguments:Bundle?) {super.onCreate(arguments);args=arguments?:Bundle();start()}
    override fun onStart() {
        val token=args.getString("token")?:error("Provide an ephemeral test token")
        require(token.length>=32);val done=CountDownLatch(1);val engine=MediaEngine(targetContext,{},{})
        val server=object:NanoHTTPD("127.0.0.1",0) {
            override fun serve(session:IHTTPSession):Response {
                if(session.headers["x-jiezhi-test"]!=token)return newFixedLengthResponse(Response.Status.UNAUTHORIZED,"text/plain","Unauthorized")
                if(session.uri=="/test/stop") {done.countDown();return newFixedLengthResponse("Stopped")}
                if(session.uri=="/test/probe") {
                    val key=java.util.UUID.randomUUID().toString().replace("-","")
                    val job=java.io.File(targetContext.filesDir,"media-results/$key").apply {mkdirs()}
                    java.io.File(job,"request.json").writeText("{\"probe\":true}")
                    targetContext.startForegroundService(android.content.Intent(targetContext,NpuVideoService::class.java).putExtra("job",key))
                    val end=System.currentTimeMillis()+90000
                    while(System.currentTimeMillis()<end) {
                        val file=java.io.File(job,"status.json")
                        if(file.isFile) {val info=org.json.JSONObject(file.readText());if(info.optString("state")!="running")return newFixedLengthResponse(Response.Status.OK,"application/json",info.toString())}
                        Thread.sleep(250)
                    }
                    return newFixedLengthResponse(Response.Status.INTERNAL_ERROR,"application/json","{\"error\":\"NPU probe timed out\"}")
                }
                return try {engine.route(session)} catch(e:Throwable) {newFixedLengthResponse(Response.Status.BAD_REQUEST,"application/json",org.json.JSONObject().put("error",e.message).toString())}
            }
        }
        try {
            server.start(60000,false);sendStatus(1,Bundle().apply {putString("port",server.listeningPort.toString())})
            done.await(40,TimeUnit.MINUTES)
        } finally {engine.cancel();server.stop();finish(android.app.Activity.RESULT_OK,Bundle())}
    }
}
