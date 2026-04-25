package com.voiceguide

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.media.AudioManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import java.io.File
import java.util.Locale
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

class MainActivity : AppCompatActivity(), TextToSpeech.OnInitListener {

    private lateinit var tts: TextToSpeech
    private lateinit var tvStatus: TextView
    private lateinit var btnToggle: Button
    private lateinit var previewView: PreviewView
    private lateinit var detector: YoloDetector

    private var imageCapture: ImageCapture? = null
    private val cameraExecutor = Executors.newSingleThreadExecutor()
    private val handler = Handler(Looper.getMainLooper())
    private val isAnalyzing = AtomicBoolean(false)
    private val isSending = AtomicBoolean(false)
    private var lastSentence = ""

    companion object {
        private const val CAMERA_PERMISSION_CODE = 100
        private const val INTERVAL_MS = 2000L
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        tts      = TextToSpeech(this, this)
        detector = YoloDetector(this)

        tvStatus    = findViewById(R.id.tvStatus)
        btnToggle   = findViewById(R.id.btnToggle)
        previewView = findViewById(R.id.previewView)

        btnToggle.setOnClickListener {
            if (isAnalyzing.get()) stopAnalysis() else requestCameraPermission()
        }
    }

    private fun requestCameraPermission() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            == PackageManager.PERMISSION_GRANTED
        ) startCamera()
        else ActivityCompat.requestPermissions(
            this, arrayOf(Manifest.permission.CAMERA), CAMERA_PERMISSION_CODE
        )
    }

    private fun startCamera() {
        val future = ProcessCameraProvider.getInstance(this)
        future.addListener({
            val provider = future.get()
            val preview  = Preview.Builder().build().also {
                it.setSurfaceProvider(previewView.surfaceProvider)
            }
            imageCapture = ImageCapture.Builder()
                .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
                .build()
            try {
                provider.unbindAll()
                provider.bindToLifecycle(this, CameraSelector.DEFAULT_BACK_CAMERA, preview, imageCapture)
                startAnalysis()
            } catch (e: Exception) {
                tvStatus.text = "카메라 오류: ${e.message}"
            }
        }, ContextCompat.getMainExecutor(this))
    }

    private fun startAnalysis() {
        isAnalyzing.set(true)
        lastSentence = ""
        btnToggle.text = "분석 중지"
        tvStatus.text  = "분석 중..."
        captureAndAnalyze()
        scheduleNext()
    }

    private fun stopAnalysis() {
        isAnalyzing.set(false)
        handler.removeCallbacksAndMessages(null)
        btnToggle.text = "분석 시작"
        tvStatus.text  = "분석이 중지되었어요."
    }

    private fun scheduleNext() {
        handler.postDelayed({
            if (isAnalyzing.get()) {
                captureAndAnalyze()
                scheduleNext()
            }
        }, INTERVAL_MS)
    }

    private fun captureAndAnalyze() {
        if (isSending.get()) return
        val file = File.createTempFile("vg_", ".jpg", cacheDir)
        val options = ImageCapture.OutputFileOptions.Builder(file).build()

        imageCapture?.takePicture(options, cameraExecutor,
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                    isSending.set(true)
                    try {
                        val bitmap = BitmapFactory.decodeFile(file.absolutePath) ?: return
                        val detections = detector.detect(bitmap)
                        bitmap.recycle()
                        val sentence = SentenceBuilder.build(detections)
                        runOnUiThread { handleResult(sentence) }
                    } catch (e: Exception) {
                        runOnUiThread { tvStatus.text = "오류: ${e.message}" }
                    } finally {
                        isSending.set(false)
                        file.delete()
                    }
                }
                override fun onError(e: ImageCaptureException) {
                    isSending.set(false)
                    runOnUiThread { tvStatus.text = "카메라 오류: ${e.message}" }
                }
            })
    }

    private fun handleResult(sentence: String) {
        if (sentence == "주변에 장애물이 없어요.") {
            tvStatus.text = "장애물 없음"
        } else if (sentence != lastSentence && !tts.isSpeaking) {
            lastSentence = sentence
            tvStatus.text = sentence
            speak(sentence)
        }
    }

    private fun speak(text: String) {
        val params = Bundle()
        params.putInt(TextToSpeech.Engine.KEY_PARAM_STREAM, AudioManager.STREAM_MUSIC)
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, params, "vg")
    }

    override fun onInit(status: Int) {
        if (status == TextToSpeech.SUCCESS) tts.setLanguage(Locale.KOREAN)
    }

    override fun onRequestPermissionsResult(
        requestCode: Int, permissions: Array<out String>, grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == CAMERA_PERMISSION_CODE &&
            grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) startCamera()
    }

    override fun onDestroy() {
        tts.shutdown()
        cameraExecutor.shutdown()
        handler.removeCallbacksAndMessages(null)
        super.onDestroy()
    }
}
