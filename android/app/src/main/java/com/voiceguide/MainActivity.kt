package com.voiceguide

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.media.AudioManager
import android.net.wifi.WifiManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.widget.Button
import android.widget.EditText
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
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import org.json.JSONObject
import java.io.File
import java.util.Locale
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import kotlin.math.abs

class MainActivity : AppCompatActivity(), TextToSpeech.OnInitListener, SensorEventListener {

    // ── UI ──────────────────────────────────────────────────────────────
    private lateinit var tts: TextToSpeech
    private lateinit var etServerUrl: EditText
    private lateinit var tvStatus: TextView
    private lateinit var tvMode: TextView
    private lateinit var btnToggle: Button
    private lateinit var btnStt: Button
    private lateinit var previewView: PreviewView

    // ── Camera ──────────────────────────────────────────────────────────
    private var imageCapture: ImageCapture? = null
    private val cameraExecutor = Executors.newSingleThreadExecutor()
    private val handler = Handler(Looper.getMainLooper())
    private val isAnalyzing = AtomicBoolean(false)
    private val isSending   = AtomicBoolean(false)
    private var lastSentence = ""

    // ── Network ─────────────────────────────────────────────────────────
    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)   // 5초 타임아웃 (기존 15초)
        .readTimeout(8, TimeUnit.SECONDS)       // 8초 타임아웃 (기존 30초)
        .build()

    // ── 연속 오류 감지 & Failsafe ────────────────────────────────────────
    private val consecutiveFails = AtomicInteger(0)
    private var lastSuccessTime  = System.currentTimeMillis()
    private val FAIL_WARN_COUNT  = 3    // 이 횟수 이상 실패 시 경고
    private val SILENCE_WARN_MS  = 6000L  // 이 시간(ms) 이상 결과 없으면 경고

    // ── 센서: 카메라 방향 자동 감지 ────────────────────────────────────
    private lateinit var sensorManager: SensorManager
    @Volatile private var cameraOrientation = "front"

    // ── STT: 음성 명령 ──────────────────────────────────────────────────
    private lateinit var speechRecognizer: SpeechRecognizer
    @Volatile private var currentMode = "장애물"

    // ── ONNX 온디바이스 추론 ────────────────────────────────────────────
    private var yoloDetector: YoloDetector? = null

    companion object {
        private const val PERM_CODE   = 100
        private const val PREFS_NAME  = "voiceguide"
        private const val PREF_URL    = "server_url"
        private const val INTERVAL_MS = 1000L   // 1초 캡처 (기존 2초)
    }

    // ── 생명주기 ─────────────────────────────────────────────────────────

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        tts = TextToSpeech(this, this)

        etServerUrl = findViewById(R.id.etServerUrl)
        tvStatus    = findViewById(R.id.tvStatus)
        tvMode      = findViewById(R.id.tvMode)
        btnToggle   = findViewById(R.id.btnToggle)
        btnStt      = findViewById(R.id.btnStt)
        previewView = findViewById(R.id.previewView)

        etServerUrl.setText(
            getSharedPreferences(PREFS_NAME, MODE_PRIVATE).getString(PREF_URL, ""))

        sensorManager = getSystemService(SENSOR_SERVICE) as SensorManager
        initSpeechRecognizer()
        tryInitYoloDetector()

        btnToggle.setOnClickListener {
            if (isAnalyzing.get()) stopAnalysis()
            else {
                val url = etServerUrl.text.toString().trim()
                if (url.isEmpty()) { tvStatus.text = "서버 URL을 먼저 입력하세요"; return@setOnClickListener }
                getSharedPreferences(PREFS_NAME, MODE_PRIVATE).edit().putString(PREF_URL, url).apply()
                requestPermissions()
            }
        }
        btnStt.setOnClickListener { startListening() }
    }

    override fun onResume() {
        super.onResume()
        sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL)
        }
    }

    override fun onPause() {
        super.onPause()
        sensorManager.unregisterListener(this)
    }

    override fun onDestroy() {
        tts.shutdown()
        speechRecognizer.destroy()
        yoloDetector?.close()
        cameraExecutor.shutdown()
        handler.removeCallbacksAndMessages(null)
        super.onDestroy()
    }

    // ── 센서: 카메라 방향 자동 감지 ────────────────────────────────────

    override fun onSensorChanged(event: SensorEvent) {
        if (event.sensor.type != Sensor.TYPE_ACCELEROMETER) return
        val x = event.values[0]
        val y = event.values[1]
        val prev = cameraOrientation
        cameraOrientation = when {
            abs(y) >= abs(x) -> if (y >= 0) "front" else "back"
            x < 0            -> "left"
            else             -> "right"
        }
        if (cameraOrientation != prev) {
            val label = mapOf("front" to "정면", "back" to "뒤", "left" to "왼쪽", "right" to "오른쪽")
            runOnUiThread { tvMode.text = "모드: $currentMode  |  방향: ${label[cameraOrientation]}" }
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    // ── STT 초기화 & 실행 ──────────────────────────────────────────────

    private fun initSpeechRecognizer() {
        speechRecognizer = SpeechRecognizer.createSpeechRecognizer(this)
        speechRecognizer.setRecognitionListener(object : RecognitionListener {
            override fun onResults(results: Bundle) {
                val text = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    ?.firstOrNull() ?: return
                val mode = classifyKeyword(text)
                currentMode = mode
                runOnUiThread { tvMode.text = "모드: $mode  |  방향: 정면" }
                speak("$mode 모드.")
            }
            override fun onError(error: Int) {
                runOnUiThread { tvMode.text = "음성 인식 실패. 다시 눌러주세요." }
            }
            override fun onReadyForSpeech(p: Bundle?) {}
            override fun onBeginningOfSpeech()        {}
            override fun onRmsChanged(v: Float)        {}
            override fun onBufferReceived(b: ByteArray?) {}
            override fun onEndOfSpeech()               {}
            override fun onPartialResults(p: Bundle?)  {}
            override fun onEvent(t: Int, p: Bundle?)   {}
        })
    }

    private fun startListening() {
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            tvMode.text = "음성 인식 미지원 기기"; return
        }
        val intent = android.content.Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "ko-KR")
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        }
        tvMode.text = "듣는 중..."
        speechRecognizer.startListening(intent)
    }

    private fun classifyKeyword(text: String): String = when {
        listOf("앞에 뭐 있어", "주변 알려줘", "뭐 있어", "장애물").any { text.contains(it) } -> "장애물"
        listOf("찾아줘", "어디있어", "어디 있어").any { text.contains(it) }                  -> "찾기"
        listOf("이거 뭐야", "이게 뭐야", "뭐야").any { text.contains(it) }                   -> "확인"
        else -> "장애물"
    }

    // ── ONNX 온디바이스 추론 초기화 ────────────────────────────────────

    private fun tryInitYoloDetector() {
        Thread {
            try {
                yoloDetector = YoloDetector(this)
                runOnUiThread { tvMode.text = "온디바이스 추론 준비 완료" }
            } catch (_: Exception) { /* 모델 없으면 서버 모드 */ }
        }.start()
    }

    // ── 카메라 & 분석 루프 ──────────────────────────────────────────────

    private fun requestPermissions() {
        val needed = mutableListOf<String>()
        if (!hasPerm(Manifest.permission.CAMERA))       needed.add(Manifest.permission.CAMERA)
        if (!hasPerm(Manifest.permission.RECORD_AUDIO)) needed.add(Manifest.permission.RECORD_AUDIO)
        if (needed.isEmpty()) startCamera()
        else ActivityCompat.requestPermissions(this, needed.toTypedArray(), PERM_CODE)
    }

    private fun hasPerm(p: String) =
        ContextCompat.checkSelfPermission(this, p) == PackageManager.PERMISSION_GRANTED

    private fun startCamera() {
        val future = ProcessCameraProvider.getInstance(this)
        future.addListener({
            val provider = future.get()
            val preview = Preview.Builder().build().also { it.setSurfaceProvider(previewView.surfaceProvider) }
            imageCapture = ImageCapture.Builder()
                .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY).build()
            try {
                provider.unbindAll()
                provider.bindToLifecycle(this, CameraSelector.DEFAULT_BACK_CAMERA, preview, imageCapture)
                startAnalysis()
            } catch (e: Exception) {
                tvStatus.text = "카메라 오류: ${e.message}"
                speak("카메라를 사용할 수 없어요. 주의하세요.")
            }
        }, ContextCompat.getMainExecutor(this))
    }

    private fun startAnalysis() {
        isAnalyzing.set(true)
        lastSentence = ""
        consecutiveFails.set(0)
        lastSuccessTime = System.currentTimeMillis()
        btnToggle.text = "분석 중지"
        tvStatus.text  = "분석 중..."
        captureAndProcess()
        scheduleNext()
        scheduleWatchdog()  // 무음 감지 감시 시작
    }

    private fun stopAnalysis() {
        isAnalyzing.set(false)
        handler.removeCallbacksAndMessages(null)
        btnToggle.text = "분석 시작"
        tvStatus.text  = "분석 중지됨"
    }

    private fun scheduleNext() {
        handler.postDelayed({
            if (isAnalyzing.get()) { captureAndProcess(); scheduleNext() }
        }, INTERVAL_MS)
    }

    // 결과가 너무 오래 안 오면 사용자에게 경고
    private fun scheduleWatchdog() {
        handler.postDelayed({
            if (!isAnalyzing.get()) return@postDelayed
            val elapsed = System.currentTimeMillis() - lastSuccessTime
            if (elapsed >= SILENCE_WARN_MS && !tts.isSpeaking) {
                speak("분석이 중단됐어요. 주의해서 이동하세요.")
                runOnUiThread { tvStatus.text = "⚠ 연결 끊김 — 주의하세요" }
            }
            scheduleWatchdog()
        }, SILENCE_WARN_MS)
    }

    private fun captureAndProcess() {
        if (isSending.get()) return
        val file = File.createTempFile("vg_", ".jpg", cacheDir)
        imageCapture?.takePicture(ImageCapture.OutputFileOptions.Builder(file).build(),
            cameraExecutor, object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                    isSending.set(true)
                    if (yoloDetector != null) processOnDevice(file)
                    else sendToServer(file)
                }
                override fun onError(e: ImageCaptureException) {
                    isSending.set(false)
                    handleFail()
                }
            })
    }

    // ── 온디바이스 추론 ─────────────────────────────────────────────────

    private fun processOnDevice(imageFile: File) {
        Thread {
            try {
                val bmp = android.graphics.BitmapFactory.decodeFile(imageFile.absolutePath)
                val detections = yoloDetector!!.detect(bmp)
                val sentence   = SentenceBuilder.build(detections)
                bmp.recycle()
                handleSuccess(sentence)
            } catch (_: Exception) {
                sendToServer(imageFile)  // 온디바이스 실패 → 서버 시도
            }
        }.start()
    }

    // ── 서버 전송 ───────────────────────────────────────────────────────

    private fun sendToServer(imageFile: File) {
        val serverUrl = etServerUrl.text.toString().trim().trimEnd('/')
        if (serverUrl.isEmpty()) { handleFail(); return }

        Thread {
            try {
                val body = MultipartBody.Builder().setType(MultipartBody.FORM)
                    .addFormDataPart("image", "frame.jpg",
                        imageFile.asRequestBody("image/jpeg".toMediaType()))
                    .addFormDataPart("camera_orientation", cameraOrientation)
                    .addFormDataPart("wifi_ssid", getWifiSsid())
                    .addFormDataPart("mode", currentMode)
                    .build()

                val response = httpClient.newCall(
                    Request.Builder().url("$serverUrl/detect").post(body).build()
                ).execute()

                val json     = JSONObject(response.body?.string() ?: "{}")
                val sentence = json.optString("sentence", "주변에 장애물이 없어요.")
                handleSuccess(sentence)
            } catch (_: Exception) {
                handleFail()
            } finally {
                imageFile.delete()
            }
        }.start()
    }

    // ── 결과 처리 & Failsafe ────────────────────────────────────────────

    private fun handleSuccess(sentence: String) {
        consecutiveFails.set(0)
        lastSuccessTime = System.currentTimeMillis()
        isSending.set(false)

        runOnUiThread {
            if (sentence == "주변에 장애물이 없어요.") {
                tvStatus.text = "장애물 없음"
            } else if (sentence != lastSentence && !tts.isSpeaking) {
                lastSentence = sentence
                tvStatus.text = sentence
                speak(sentence)
            }
        }
    }

    private fun handleFail() {
        isSending.set(false)
        val fails = consecutiveFails.incrementAndGet()

        // 연속 3회 실패 시 음성 경고
        if (fails == FAIL_WARN_COUNT) {
            runOnUiThread {
                tvStatus.text = "⚠ 서버 연결 실패 — 주의하세요"
                if (!tts.isSpeaking) speak("서버 연결이 끊겼어요. 주의해서 이동하세요.")
            }
        }
        // 온디바이스 모드로 전환 시도
        if (fails >= FAIL_WARN_COUNT && yoloDetector != null) {
            runOnUiThread { tvMode.text = "온디바이스 모드 전환됨" }
        }
    }

    // ── 유틸리티 ────────────────────────────────────────────────────────

    @Suppress("MissingPermission")
    private fun getWifiSsid(): String = try {
        val wm = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
        wm.connectionInfo.ssid?.replace("\"", "") ?: ""
    } catch (_: Exception) { "" }

    private fun speak(text: String) {
        val params = Bundle()
        params.putInt(TextToSpeech.Engine.KEY_PARAM_STREAM, AudioManager.STREAM_MUSIC)
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, params, "vg")
    }

    override fun onInit(status: Int) {
        if (status == TextToSpeech.SUCCESS) {
            tts.setLanguage(Locale.KOREAN)
            tts.setSpeechRate(1.1f)  // 약간 빠르게 (긴박한 상황 대응)
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int, permissions: Array<out String>, grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == PERM_CODE &&
            grantResults.all { it == PackageManager.PERMISSION_GRANTED }) startCamera()
    }
}
