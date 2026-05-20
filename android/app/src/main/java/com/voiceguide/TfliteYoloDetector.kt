package com.voiceguide

import android.content.Context
import android.graphics.Bitmap
import android.graphics.PixelFormat
import androidx.camera.core.ImageProxy
import java.nio.ByteBuffer
import java.nio.ByteOrder
import org.tensorflow.lite.Interpreter
import org.tensorflow.lite.gpu.CompatibilityList
import org.tensorflow.lite.gpu.GpuDelegate

class TfliteYoloDetector(context: Context) {
    private var interpreter: Interpreter
    private var gpuDelegate: GpuDelegate? = null
    private val modelBuffer: ByteBuffer
    val modelName: String
    var executionProvider: String = "TFLite-XNNPACK"
        private set
    private val inputSize: Int
    private val outputRows: Int
    private val outputCols: Int
    // true: raw YOLO output [84, N] / false: end-to-end NMS output [N, 6]
    private val isRawOutput: Boolean
    private val confThreshold = 0.25f
    private val iouThreshold  = 0.70f
    private var outputShapeLogged = false
    private val inputBuffer: ByteBuffer
    private val outputBuffer: Array<Array<FloatArray>>
    private val bitmapPixels: IntArray
    private val rgbNorm = FloatArray(256) { it / 255f }
    private var lastInputLayoutKey: String? = null
    private var cachedPlan: SamplingPlan? = null


    init {
        modelName = listOf("yolo11n_320.tflite", "yolo26n_float32.tflite").firstOrNull { name ->
            try { context.assets.open(name).close(); true }
            catch (_: Exception) { false }
        } ?: throw IllegalStateException("TFLite 모델 파일이 없습니다. assets에 yolo26n_float32.tflite 또는 yolo11n_320.tflite가 필요합니다.")
        val modelBytes = context.assets.open(modelName).readBytes()
        modelBuffer = ByteBuffer.allocateDirect(modelBytes.size).order(ByteOrder.nativeOrder())
        modelBuffer.put(modelBytes)
        modelBuffer.rewind()

        interpreter = createInterpreter()

        val inputShape  = interpreter.getInputTensor(0).shape()
        inputSize       = inputShape.getOrNull(1) ?: 320
        val outputShape = interpreter.getOutputTensor(0).shape()
        outputRows = outputShape.getOrNull(1) ?: 300
        outputCols = outputShape.getOrNull(2) ?: 6
        // Raw YOLO is [1, 4 + class_count, anchors]. Fine-tuned models may add classes.
        isRawOutput = YoloOutputFormat.isRaw(outputRows, outputCols)
        inputBuffer = ByteBuffer.allocateDirect(4 * inputSize * inputSize * 3).order(ByteOrder.nativeOrder())
        outputBuffer = Array(1) { Array(outputRows) { FloatArray(outputCols) } }
        bitmapPixels = IntArray(inputSize * inputSize)
        android.util.Log.d(
            "VG_PERF",
            "YOLO input model=$modelName provider=$executionProvider size=${inputSize}x$inputSize shape=${inputShape.joinToString(prefix = "[", postfix = "]")}"
        )
    }

    @Synchronized
    fun detect(bitmap: Bitmap): TfliteDetectionResult {
        val tPreprocess = System.nanoTime()
        val origW = bitmap.width
        val origH = bitmap.height
        val scale = minOf(inputSize.toFloat() / origW, inputSize.toFloat() / origH)
        val scaledW = (origW * scale + 0.5f).toInt()
        val scaledH = (origH * scale + 0.5f).toInt()
        val padX    = (inputSize - scaledW) / 2
        val padY    = (inputSize - scaledH) / 2

        val letterboxed = Bitmap.createBitmap(inputSize, inputSize, Bitmap.Config.ARGB_8888)
        val canvas = android.graphics.Canvas(letterboxed)
        canvas.drawARGB(255, 0, 0, 0)
        val scaled = Bitmap.createScaledBitmap(bitmap, scaledW, scaledH, true)
        canvas.drawBitmap(scaled, padX.toFloat(), padY.toFloat(), null)
        scaled.recycle()

        prepareInputLayout("bitmap:$origW:$origH:$padX:$padY:$scaledW:$scaledH")
        bitmapToNHWC(letterboxed)
        letterboxed.recycle()
        val preprocessMs = elapsedMs(tPreprocess)
        return runModel(inputBuffer, padX, padY, scaledW, scaledH, preprocessMs)
    }

    @Synchronized
    fun detect(imageProxy: ImageProxy): TfliteDetectionResult {
        val tPreprocess = System.nanoTime()
        val rotation = ((imageProxy.imageInfo.rotationDegrees % 360) + 360) % 360
        val displayW = if (rotation % 180 == 0) imageProxy.width else imageProxy.height
        val displayH = if (rotation % 180 == 0) imageProxy.height else imageProxy.width
        val scale = minOf(inputSize.toFloat() / displayW, inputSize.toFloat() / displayH)
        val scaledW = (displayW * scale + 0.5f).toInt()
        val scaledH = (displayH * scale + 0.5f).toInt()
        val padX = (inputSize - scaledW) / 2
        val padY = (inputSize - scaledH) / 2

        prepareInputLayout("proxy:${imageProxy.width}:${imageProxy.height}:$rotation:$padX:$padY:$scaledW:$scaledH")
        if (imageProxy.format == PixelFormat.RGBA_8888) {
            rgbaToNHWC(imageProxy, rotation, displayW, displayH, scale, padX, padY, scaledW, scaledH)
        } else {
            yuvPlanesToNHWC(imageProxy, rotation, displayW, displayH, scale, padX, padY, scaledW, scaledH)
        }
        val preprocessMs = elapsedMs(tPreprocess)
        return runModel(inputBuffer, padX, padY, scaledW, scaledH, preprocessMs)
    }

    private fun runModel(
        inputBuffer: ByteBuffer,
        padX: Int,
        padY: Int,
        scaledW: Int,
        scaledH: Int,
        preprocessMs: Long
    ): TfliteDetectionResult {
        inputBuffer.rewind()
        val tInfer = System.nanoTime()
        try {
            interpreter.run(inputBuffer, outputBuffer)
        } catch (e: RuntimeException) {
            if (gpuDelegate == null) throw e
            android.util.Log.w("VG_PERF", "GPU delegate failed; falling back to XNNPACK", e)
            fallbackToXnnpack()
            inputBuffer.rewind()
            interpreter.run(inputBuffer, outputBuffer)
        }
        val inferMs = elapsedMs(tInfer)
        if (!outputShapeLogged) {
            outputShapeLogged = true
            android.util.Log.d("VG_PERF",
                "YOLO output model=$modelName provider=$executionProvider shape=[1, $outputRows, $outputCols]")
        }

        val tPostprocess = System.nanoTime()
        val detections = if (isRawOutput)
            postProcessRaw(outputBuffer[0], padX, padY, scaledW, scaledH)
        else
            postProcessEndToEnd(outputBuffer[0], padX, padY, scaledW, scaledH)
        val postprocessMs = elapsedMs(tPostprocess)
        return TfliteDetectionResult(detections, preprocessMs, inferMs, postprocessMs)
    }

    private fun createInterpreter(): Interpreter {
        val compatList = CompatibilityList()
        return try {
            if (compatList.isDelegateSupportedOnThisDevice) {
                val options = GpuDelegate.Options().apply {
                    setPrecisionLossAllowed(false)
                    setInferencePreference(GpuDelegate.Options.INFERENCE_PREFERENCE_SUSTAINED_SPEED)
                }
                gpuDelegate = GpuDelegate(options)
                executionProvider = "TFLite-GPU-FP32"
                modelBuffer.rewind()
                Interpreter(modelBuffer, Interpreter.Options().apply {
                    addDelegate(gpuDelegate)
                })
            } else {
                createXnnpackInterpreter()
            }
        } catch (e: Exception) {
            android.util.Log.w("VG_PERF", "GPU delegate init failed; using XNNPACK", e)
            gpuDelegate?.close()
            gpuDelegate = null
            createXnnpackInterpreter()
        } finally {
            compatList.close()
        }
    }

    private fun createXnnpackInterpreter(): Interpreter {
        executionProvider = "TFLite-XNNPACK"
        modelBuffer.rewind()
        return Interpreter(modelBuffer, Interpreter.Options().apply {
            setNumThreads(4)
            setUseXNNPACK(true)
        })
    }

    private fun fallbackToXnnpack() {
        interpreter.close()
        gpuDelegate?.close()
        gpuDelegate = null
        interpreter = createXnnpackInterpreter()
    }

    private fun bitmapToNHWC(bitmap: Bitmap) {
        bitmap.getPixels(bitmapPixels, 0, inputSize, 0, 0, inputSize, inputSize)
        inputBuffer.rewind()
        for (pixel in bitmapPixels) {
            inputBuffer.putFloat(rgbNorm[(pixel shr 16) and 0xFF])
            inputBuffer.putFloat(rgbNorm[(pixel shr 8) and 0xFF])
            inputBuffer.putFloat(rgbNorm[pixel and 0xFF])
        }
        inputBuffer.rewind()
    }

    private fun yuvPlanesToNHWC(
        imageProxy: ImageProxy,
        rotation: Int,
        displayWidth: Int,
        displayHeight: Int,
        scale: Float,
        padX: Int,
        padY: Int,
        scaledW: Int,
        scaledH: Int
    ) {
        val planes = imageProxy.planes
        val yPlane = planes[0]
        val uPlane = planes[1]
        val vPlane = planes[2]
        val yBuffer = yPlane.buffer
        val uBuffer = uPlane.buffer
        val vBuffer = vPlane.buffer
        val plan = samplingPlan(displayWidth, displayHeight, scale, padX, padY, scaledW, scaledH)

        for (y in padY until padY + scaledH) {
            val srcDisplayY = plan.srcDisplayY[y]
            for (x in padX until padX + scaledW) {
                val srcDisplayX = plan.srcDisplayX[x]
                val srcX: Int
                val srcY: Int
                when (rotation) {
                    90 -> {
                        srcX = srcDisplayY
                        srcY = imageProxy.height - 1 - srcDisplayX
                    }
                    180 -> {
                        srcX = imageProxy.width - 1 - srcDisplayX
                        srcY = imageProxy.height - 1 - srcDisplayY
                    }
                    270 -> {
                        srcX = imageProxy.width - 1 - srcDisplayY
                        srcY = srcDisplayX
                    }
                    else -> {
                        srcX = srcDisplayX
                        srcY = srcDisplayY
                    }
                }
                val yIndex = srcY * yPlane.rowStride + srcX * yPlane.pixelStride
                val uvX = srcX / 2
                val uvY = srcY / 2
                val uIndex = uvY * uPlane.rowStride + uvX * uPlane.pixelStride
                val vIndex = uvY * vPlane.rowStride + uvX * vPlane.pixelStride
                val yy = (yBuffer.get(yIndex).toInt() and 0xFF).coerceAtLeast(16)
                val uu = (uBuffer.get(uIndex).toInt() and 0xFF) - 128
                val vv = (vBuffer.get(vIndex).toInt() and 0xFF) - 128
                val c = yy - 16
                val r = ((298 * c + 409 * vv + 128) shr 8).coerceIn(0, 255)
                val g = ((298 * c - 100 * uu - 208 * vv + 128) shr 8).coerceIn(0, 255)
                val b = ((298 * c + 516 * uu + 128) shr 8).coerceIn(0, 255)
                val offset = (y * inputSize + x) * 3 * 4
                inputBuffer.putFloat(offset, rgbNorm[r])
                inputBuffer.putFloat(offset + 4, rgbNorm[g])
                inputBuffer.putFloat(offset + 8, rgbNorm[b])
            }
        }
        inputBuffer.rewind()
    }

    private fun rgbaToNHWC(
        imageProxy: ImageProxy,
        rotation: Int,
        displayWidth: Int,
        displayHeight: Int,
        scale: Float,
        padX: Int,
        padY: Int,
        scaledW: Int,
        scaledH: Int
    ) {
        val plane = imageProxy.planes[0]
        val buffer = plane.buffer
        val plan = samplingPlan(displayWidth, displayHeight, scale, padX, padY, scaledW, scaledH)

        for (y in padY until padY + scaledH) {
            val srcDisplayY = plan.srcDisplayY[y]
            for (x in padX until padX + scaledW) {
                val srcDisplayX = plan.srcDisplayX[x]
                val srcX: Int
                val srcY: Int
                when (rotation) {
                    90 -> {
                        srcX = srcDisplayY
                        srcY = imageProxy.height - 1 - srcDisplayX
                    }
                    180 -> {
                        srcX = imageProxy.width - 1 - srcDisplayX
                        srcY = imageProxy.height - 1 - srcDisplayY
                    }
                    270 -> {
                        srcX = imageProxy.width - 1 - srcDisplayY
                        srcY = srcDisplayX
                    }
                    else -> {
                        srcX = srcDisplayX
                        srcY = srcDisplayY
                    }
                }
                val rgbaIndex = srcY * plane.rowStride + srcX * plane.pixelStride
                val inputOffset = (y * inputSize + x) * 3 * 4
                inputBuffer.putFloat(inputOffset, rgbNorm[buffer.get(rgbaIndex).toInt() and 0xFF])
                inputBuffer.putFloat(inputOffset + 4, rgbNorm[buffer.get(rgbaIndex + 1).toInt() and 0xFF])
                inputBuffer.putFloat(inputOffset + 8, rgbNorm[buffer.get(rgbaIndex + 2).toInt() and 0xFF])
            }
        }
        inputBuffer.rewind()
    }

    private fun prepareInputLayout(key: String) {
        if (lastInputLayoutKey == key) return
        clearInputBuffer()
        lastInputLayoutKey = key
    }

    private fun clearInputBuffer() {
        var offset = 0
        repeat(inputSize * inputSize * 3) {
            inputBuffer.putFloat(offset, 0f)
            offset += 4
        }
        inputBuffer.rewind()
    }

    private fun samplingPlan(
        displayWidth: Int,
        displayHeight: Int,
        scale: Float,
        padX: Int,
        padY: Int,
        scaledW: Int,
        scaledH: Int
    ): SamplingPlan {
        val key = "$displayWidth:$displayHeight:$padX:$padY:$scaledW:$scaledH"
        cachedPlan?.let { if (it.key == key) return it }
        val srcDisplayX = IntArray(inputSize)
        val srcDisplayY = IntArray(inputSize)
        for (x in padX until padX + scaledW) {
            srcDisplayX[x] = ((x - padX) / scale).toInt().coerceIn(0, displayWidth - 1)
        }
        for (y in padY until padY + scaledH) {
            srcDisplayY[y] = ((y - padY) / scale).toInt().coerceIn(0, displayHeight - 1)
        }
        return SamplingPlan(key, srcDisplayX, srcDisplayY).also { cachedPlan = it }
    }

    // raw YOLO11 output: shape [84][N], rows 0-3=cx/cy/w/h (normalized 0-1), rows 4-83=class scores (sigmoid applied)
    private fun postProcessRaw(
        rawOutput: Array<FloatArray>,
        padX: Int, padY: Int,
        scaledW: Int, scaledH: Int
    ): List<Detection> {
        val numAnchors = rawOutput[0].size
        val candidates = mutableListOf<Detection>()
        for (i in 0 until numAnchors) {
            var maxScore = 0f
            var classId = -1
            for (c in 4 until rawOutput.size) {
                val s = rawOutput[c][i]
                if (s > maxScore) { maxScore = s; classId = c - 4 }
            }
            if (classId < 0) continue
            val name = voiceGuideClassKo(classId) ?: continue
            if (maxScore < confidenceThresholdFor(classId)) continue

            // coords are normalized [0,1] relative to inputSize
            val cx = rawOutput[0][i] * inputSize
            val cy = rawOutput[1][i] * inputSize
            val w  = rawOutput[2][i] * inputSize
            val h  = rawOutput[3][i] * inputSize
            val x1 = cx - w / 2f
            val y1 = cy - h / 2f
            val x2 = cx + w / 2f
            val y2 = cy + h / 2f

            val cxD = ((x1 + x2) / 2f - padX) / scaledW
            val cyD = ((y1 + y2) / 2f - padY) / scaledH
            val wD  = (x2 - x1) / scaledW
            val hD  = (y2 - y1) / scaledH
            if (cxD < 0f || cxD > 1f || cyD < 0f || cyD > 1f || wD <= 0f || hD <= 0f) continue

            candidates.add(Detection(classKo = name, confidence = maxScore,
                                     cx = cxD, cy = cyD, w = wD, h = hD))
        }
        return nms(candidates.sortedByDescending { it.confidence }).take(8)
    }

    private fun postProcessEndToEnd(
        rows: Array<FloatArray>,
        padX: Int, padY: Int,
        scaledW: Int, scaledH: Int
    ): List<Detection> {
        val candidates = mutableListOf<Detection>()
        for (row in rows) {
            if (row.size < 6) continue
            var x1 = row[0]; var y1 = row[1]
            var x2 = row[2]; var y2 = row[3]
            val score   = row[4]
            val classId = row[5].toInt()
            if (score < confidenceThresholdFor(classId)) continue
            val name = voiceGuideClassKo(classId) ?: continue

            if (maxOf(kotlin.math.abs(x1), kotlin.math.abs(y1),
                      kotlin.math.abs(x2), kotlin.math.abs(y2)) <= 2f) {
                x1 *= inputSize; y1 *= inputSize
                x2 *= inputSize; y2 *= inputSize
            }
            val cx = (((x1 + x2) / 2f) - padX) / scaledW
            val cy = (((y1 + y2) / 2f) - padY) / scaledH
            val w  = (x2 - x1) / scaledW
            val h  = (y2 - y1) / scaledH
            if (cx < 0f || cx > 1f || cy < 0f || cy > 1f || w <= 0f || h <= 0f) continue

            candidates.add(Detection(classKo = name, confidence = score,
                                     cx = cx, cy = cy, w = w, h = h))
        }
        return nms(candidates.sortedByDescending { it.confidence }).take(8)
    }

    private fun nms(sorted: List<Detection>): List<Detection> {
        val keep = mutableListOf<Detection>()
        val skip = BooleanArray(sorted.size)
        for (i in sorted.indices) {
            if (skip[i]) continue
            keep.add(sorted[i])
            for (j in i + 1 until sorted.size) {
                if (!skip[j] &&
                    sorted[i].classKo == sorted[j].classKo &&
                    iou(sorted[i], sorted[j]) > iouThreshold
                ) {
                    skip[j] = true
                }
            }
        }
        return keep
    }

    private fun confidenceThresholdFor(classId: Int): Float =
        when (classId) {
            80 -> 0.22f // stairs: keep recall, then stabilize with voting/tracking.
            81 -> 0.18f // door: fine-tuned logits are often lower than COCO classes.
            else -> confThreshold
        }

    private fun iou(a: Detection, b: Detection): Float {
        val ax1 = a.cx - a.w / 2f; val ax2 = a.cx + a.w / 2f
        val ay1 = a.cy - a.h / 2f; val ay2 = a.cy + a.h / 2f
        val bx1 = b.cx - b.w / 2f; val bx2 = b.cx + b.w / 2f
        val by1 = b.cy - b.h / 2f; val by2 = b.cy + b.h / 2f
        val iw    = maxOf(0f, minOf(ax2, bx2) - maxOf(ax1, bx1))
        val ih    = maxOf(0f, minOf(ay2, by2) - maxOf(ay1, by1))
        val inter = iw * ih
        val union = a.w * a.h + b.w * b.h - inter
        return if (union > 0f) inter / union else 0f
    }

    fun close() {
        interpreter.close()
        gpuDelegate?.close()
    }

    private data class SamplingPlan(
        val key: String,
        val srcDisplayX: IntArray,
        val srcDisplayY: IntArray
    )

    private fun elapsedMs(startNs: Long): Long =
        ((System.nanoTime() - startNs) / 1_000_000L).coerceAtLeast(0L)
}
