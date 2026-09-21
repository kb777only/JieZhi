package dev.jiezhi.client

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Rect
import com.abrah.nightmare.npu.QnnRunner
import java.io.File

/** QuickSRNet 2x, tiled around its fixed 512x320 NPU input with a 16-pixel halo. */
object NpuImageOps {
    fun upscale(runner:QnnRunner,model:File,input:File,output:File,log:(String)->Unit) {
        val source=BitmapFactory.decodeFile(input.absolutePath)?:error("Cannot decode input image")
        require(source.width in 1..2048 && source.height in 1..2048)
        val result=Bitmap.createBitmap(source.width*2,source.height*2,Bitmap.Config.ARGB_8888);val canvas=Canvas(result)
        val plane=512*320;var tile=0;val total=((source.width+479)/480)*((source.height+287)/288)
        try {
            for(y in 0 until source.height step 288)for(x in 0 until source.width step 480) {
                log("Hexagon NPU · Upscaling tile ${++tile}/$total")
                val values=FloatArray(plane*3)
                for(v in 0 until 320)for(u in 0 until 512) {
                    val pixel=source.getPixel((x+u-16).coerceIn(0,source.width-1),(y+v-16).coerceIn(0,source.height-1));val i=v*512+u
                    values[i]=((pixel shr 16) and 255)/255f;values[plane+i]=((pixel shr 8) and 255)/255f;values[plane*2+i]=(pixel and 255)/255f
                }
                val up=runner.run(model,mapOf("frame" to values)).values.first();val p=1024*640;require(up.size==p*3)
                val pixels=IntArray(p) {i -> (255 shl 24) or ((up[i]*255).toInt().coerceIn(0,255) shl 16) or ((up[p+i]*255).toInt().coerceIn(0,255) shl 8) or (up[p*2+i]*255).toInt().coerceIn(0,255)}
                val bmp=Bitmap.createBitmap(pixels,1024,640,Bitmap.Config.ARGB_8888);val w=minOf(480,source.width-x)*2;val h=minOf(288,source.height-y)*2
                canvas.drawBitmap(bmp,Rect(32,32,32+w,32+h),Rect(x*2,y*2,x*2+w,y*2+h),null);bmp.recycle()
            }
            output.outputStream().use {check(result.compress(Bitmap.CompressFormat.PNG,100,it))}
        } finally {source.recycle();result.recycle();runner.release(model)}
    }
}
