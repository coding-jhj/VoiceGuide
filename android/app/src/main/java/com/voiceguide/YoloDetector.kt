package com.voiceguide

import android.content.Context
import android.graphics.Bitmap
import org.tensorflow.lite.Interpreter
import org.tensorflow.lite.gpu.GpuDelegate
import java.io.FileInputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.channels.FileChannel

data class Detection(
    val classKo: String,
    val confidence: Float,
    val cx: Float,   // [0, 1]
    val cy: Float,
    val w: Float,
    val h: Float
)

class YoloDetector(context: Context) {

    private val interpreter: Interpreter
    private val inputSize = 640
    private val confThreshold = 0.25f
    private val iouThreshold = 0.45f

    init {
        val fd = context.assets.openFd("yolo11n.tflite")
        val channel = FileInputStream(fd.fileDescriptor).channel
        val model = channel.map(FileChannel.MapMode.READ_ONLY, fd.startOffset, fd.declaredLength)

        val options = Interpreter.Options()
        try {
            options.addDelegate(GpuDelegate())
        } catch (_: Exception) { /* GPU 미지원 시 CPU 사용 */ }

        interpreter = Interpreter(model, options)
    }

    fun detect(bitmap: Bitmap): List<Detection> {
        val resized = Bitmap.createScaledBitmap(bitmap, inputSize, inputSize, true)
        val input = bitmapToBuffer(resized)
        resized.recycle()

        // 출력: [1, 84, 8400]
        val output = Array(1) { Array(84) { FloatArray(8400) } }
        interpreter.run(input, output)

        return postProcess(output[0])
    }

    private fun bitmapToBuffer(bitmap: Bitmap): ByteBuffer {
        val buf = ByteBuffer.allocateDirect(1 * inputSize * inputSize * 3 * 4)
        buf.order(ByteOrder.nativeOrder())
        val pixels = IntArray(inputSize * inputSize)
        bitmap.getPixels(pixels, 0, inputSize, 0, 0, inputSize, inputSize)
        for (px in pixels) {
            buf.putFloat(((px shr 16) and 0xFF) / 255f)
            buf.putFloat(((px shr 8)  and 0xFF) / 255f)
            buf.putFloat((px          and 0xFF) / 255f)
        }
        return buf
    }

    private fun postProcess(out: Array<FloatArray>): List<Detection> {
        val candidates = mutableListOf<Detection>()
        val n = out[0].size  // 8400

        for (i in 0 until n) {
            var maxScore = confThreshold
            var maxClass = -1
            for (c in 0 until 80) {
                val s = out[4 + c][i]
                if (s > maxScore) { maxScore = s; maxClass = c }
            }
            if (maxClass < 0) continue
            val name = COCO_KO[maxClass] ?: continue

            candidates.add(Detection(
                classKo    = name,
                confidence = maxScore,
                cx = out[0][i] / inputSize,
                cy = out[1][i] / inputSize,
                w  = out[2][i] / inputSize,
                h  = out[3][i] / inputSize
            ))
        }

        return nms(candidates.sortedByDescending { it.confidence }).take(2)
    }

    private fun nms(sorted: List<Detection>): List<Detection> {
        val keep = mutableListOf<Detection>()
        val skip = BooleanArray(sorted.size)
        for (i in sorted.indices) {
            if (skip[i]) continue
            keep.add(sorted[i])
            for (j in i + 1 until sorted.size) {
                if (!skip[j] && iou(sorted[i], sorted[j]) > iouThreshold) skip[j] = true
            }
        }
        return keep
    }

    private fun iou(a: Detection, b: Detection): Float {
        val ax1 = a.cx - a.w / 2; val ay1 = a.cy - a.h / 2
        val ax2 = a.cx + a.w / 2; val ay2 = a.cy + a.h / 2
        val bx1 = b.cx - b.w / 2; val by1 = b.cy - b.h / 2
        val bx2 = b.cx + b.w / 2; val by2 = b.cy + b.h / 2
        val iw = maxOf(0f, minOf(ax2, bx2) - maxOf(ax1, bx1))
        val ih = maxOf(0f, minOf(ay2, by2) - maxOf(ay1, by1))
        val inter = iw * ih
        val union = a.w * a.h + b.w * b.h - inter
        return if (union > 0) inter / union else 0f
    }
}
