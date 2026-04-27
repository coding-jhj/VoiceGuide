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
import org.json.JSONArray
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
    private lateinit var boundingBoxOverlay: BoundingBoxOverlay // 디버그 바운드박스 오버레이

    // ── Camera ──────────────────────────────────────────────────────────
    private var imageCapture: ImageCapture? = null
    private val cameraExecutor = Executors.newSingleThreadExecutor()
    private val handler = Handler(Looper.getMainLooper())
    private val isAnalyzing = AtomicBoolean(false)
    private val isSending   = AtomicBoolean(false)
    private var lastSentence = ""

    // ── 네트워크 (선택 — 서버 없어도 동작) ──────────────────────────────
    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(8, TimeUnit.SECONDS)
        .build()
    private val consecutiveFails = AtomicInteger(0)
    private var lastSuccessTime  = System.currentTimeMillis()

    // ── 센서: 카메라 방향 자동 감지 ────────────────────────────────────
    private lateinit var sensorManager: SensorManager
    @Volatile private var cameraOrientation = "front"

    // ── STT 음성 명령 ───────────────────────────────────────────────────
    private lateinit var speechRecognizer: SpeechRecognizer
    @Volatile private var currentMode  = "장애물"
    @Volatile private var findTarget   = ""   // 찾기 모드에서 탐색할 물체

    // ── ONNX 온디바이스 추론 ────────────────────────────────────────────
    private var yoloDetector: YoloDetector? = null

    companion object {
        private const val PERM_CODE        = 100
        private const val PREFS_NAME       = "voiceguide"
        private const val PREF_URL         = "server_url"
        private const val PREF_LOCATIONS   = "saved_locations"   // JSON 배열
        private const val INTERVAL_MS      = 1000L
        private const val SILENCE_WARN_MS  = 6000L
        private const val FAIL_WARN_COUNT  = 3
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
        previewView         = findViewById(R.id.previewView)
        boundingBoxOverlay  = findViewById(R.id.boundingBoxOverlay) // 디버그 오버레이 바인딩

        // 저장된 서버 URL 복원 (없어도 무관)
        etServerUrl.setText(
            getSharedPreferences(PREFS_NAME, MODE_PRIVATE).getString(PREF_URL, ""))

        sensorManager = getSystemService(SENSOR_SERVICE) as SensorManager
        initSpeechRecognizer()
        tryInitYoloDetector()

        // 서버 URL 유무와 관계없이 바로 시작 가능
        btnToggle.setOnClickListener {
            if (isAnalyzing.get()) {
                stopAnalysis()
            } else {
                val url = etServerUrl.text.toString().trim()
                if (url.isNotEmpty()) {
                    getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
                        .edit().putString(PREF_URL, url).apply()
                }
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

    // ── 센서: 카메라 방향 ───────────────────────────────────────────────

    override fun onSensorChanged(event: SensorEvent) {
        if (event.sensor.type != Sensor.TYPE_ACCELEROMETER) return
        val x = event.values[0]; val y = event.values[1]
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
                handleSttResult(text)
            }
            override fun onError(error: Int) {
                runOnUiThread { tvMode.text = "음성 인식 실패. 다시 눌러주세요." }
            }
            override fun onReadyForSpeech(p: Bundle?) {}
            override fun onBeginningOfSpeech()         {}
            override fun onRmsChanged(v: Float)         {}
            override fun onBufferReceived(b: ByteArray?) {}
            override fun onEndOfSpeech()                {}
            override fun onPartialResults(p: Bundle?)   {}
            override fun onEvent(t: Int, p: Bundle?)    {}
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

    /** STT 결과 처리 — 이미지 분석 불필요 모드는 즉시 처리 */
    private fun handleSttResult(text: String) {
        val mode = classifyKeyword(text)
        runOnUiThread { tvMode.text = "모드: $mode  |  방향: 정면" }

        when (mode) {
            "저장" -> {
                // 이미지 불필요 — 즉시 위치 저장
                val label = SentenceBuilder.extractLabel(text)
                    .ifEmpty { "위치_${System.currentTimeMillis() / 1000 % 10000}" }
                val ssid  = getWifiSsid()
                if (ssid.isEmpty()) {
                    speak("WiFi에 연결되어 있지 않아 저장할 수 없어요.")
                } else {
                    saveLocation(label, ssid)
                    speak(SentenceBuilder.buildNavigation("save", label))
                }
                currentMode = "장애물"
            }
            "위치목록" -> {
                // 이미지 불필요 — 즉시 목록 읽어주기
                val locs = getLocations()
                speak(SentenceBuilder.buildNavigation("list", "", locs.map { it.first }))
                currentMode = "장애물"
            }
            "찾기" -> {
                findTarget  = SentenceBuilder.extractFindTarget(text)
                currentMode = "찾기"
                speak("${findTarget.ifEmpty { "물건" }} 찾기 모드.")
            }
            else -> {
                currentMode = mode
                speak("$mode 모드.")
            }
        }
    }

    /** STT 텍스트 → 모드 분류. 미매칭 시 장애물(기본) */
    private fun classifyKeyword(text: String): String {
        for ((mode, keywords) in STT_KEYWORDS) {
            if (keywords.any { text.contains(it) }) return mode
        }
        return "장애물"
    }

    // ── ONNX 온디바이스 추론 초기화 ────────────────────────────────────

    private fun tryInitYoloDetector() {
        Thread {
            try {
                yoloDetector = YoloDetector(this)
                runOnUiThread { tvStatus.text = "온디바이스 준비 완료 — 분석 시작을 누르세요" }
            } catch (_: Exception) {
                runOnUiThread { tvStatus.text = "ONNX 모델 없음 — 서버 URL을 입력하세요" }
            }
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
            val preview  = Preview.Builder().build()
                .also { it.setSurfaceProvider(previewView.surfaceProvider) }
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
        scheduleWatchdog()
    }

    private fun stopAnalysis() {
        isAnalyzing.set(false)
        handler.removeCallbacksAndMessages(null)
        btnToggle.text = "분석 시작"
        tvStatus.text  = "분석 중지됨"
        boundingBoxOverlay.clearDetections() // 분석 중지 시 바운드박스 제거
    }

    private fun scheduleNext() {
        handler.postDelayed({
            if (isAnalyzing.get()) { captureAndProcess(); scheduleNext() }
        }, INTERVAL_MS)
    }

    private fun scheduleWatchdog() {
        handler.postDelayed({
            if (!isAnalyzing.get()) return@postDelayed
            if (System.currentTimeMillis() - lastSuccessTime >= SILENCE_WARN_MS && !tts.isSpeaking) {
                speak("분석이 중단됐어요. 주의해서 이동하세요.")
                runOnUiThread { tvStatus.text = "⚠ 분석 중단 — 주의하세요" }
            }
            scheduleWatchdog()
        }, SILENCE_WARN_MS)
    }

    private fun captureAndProcess() {
        if (isSending.get()) return
        val file = File.createTempFile("vg_", ".jpg", cacheDir)
        imageCapture?.takePicture(
            ImageCapture.OutputFileOptions.Builder(file).build(),
            cameraExecutor,
            object : ImageCapture.OnImageSavedCallback {
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

    // ── 온디바이스 추론 (기본) ──────────────────────────────────────────

    private fun processOnDevice(imageFile: File) {
        Thread {
            try {
                val bmp        = android.graphics.BitmapFactory.decodeFile(imageFile.absolutePath)
                val detections = yoloDetector!!.detect(bmp)
                bmp.recycle()
                imageFile.delete()

                // 디버그: 탐지된 물체의 바운드박스를 프리뷰 위에 표시
                runOnUiThread { boundingBoxOverlay.setDetections(detections) }

                val sentence = when (currentMode) {
                    "찾기"  -> SentenceBuilder.buildFind(findTarget, detections)
                    else   -> SentenceBuilder.build(detections)
                }
                handleSuccess(sentence)
            } catch (_: Exception) {
                imageFile.delete()
                // 온디바이스 실패 → 서버로 fallback
                val file2 = File.createTempFile("vg_fb_", ".jpg", cacheDir)
                try {
                    sendToServer(File(imageFile.absolutePath))
                } catch (_: Exception) {
                    handleFail()
                }
            }
        }.start()
    }

    // ── 서버 전송 (선택 — URL 입력 시 Depth V2 정확도 향상) ──────────────

    private fun sendToServer(imageFile: File) {
        val serverUrl = etServerUrl.text.toString().trim().trimEnd('/')
        if (serverUrl.isEmpty()) {
            imageFile.delete()
            handleFail()
            return
        }

        Thread {
            try {
                val body = MultipartBody.Builder().setType(MultipartBody.FORM)
                    .addFormDataPart("image", "frame.jpg",
                        imageFile.asRequestBody("image/jpeg".toMediaType()))
                    .addFormDataPart("camera_orientation", cameraOrientation)
                    .addFormDataPart("wifi_ssid", getWifiSsid())
                    .addFormDataPart("mode", currentMode)
                    .addFormDataPart("query_text", findTarget)
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
        if (fails == FAIL_WARN_COUNT) {
            runOnUiThread {
                tvStatus.text = "⚠ 분석 실패 — 주의하세요"
                if (!tts.isSpeaking) speak("분석에 문제가 생겼어요. 주의해서 이동하세요.")
            }
        }
    }

    // ── 개인 네비게이팅: 장소 저장/조회 (SharedPreferences) ───────────────

    private fun saveLocation(label: String, ssid: String) {
        val prefs   = getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
        val arr     = JSONArray(prefs.getString(PREF_LOCATIONS, "[]"))
        val obj     = JSONObject().put("label", label).put("ssid", ssid)
            .put("ts", System.currentTimeMillis())
        arr.put(obj)
        prefs.edit().putString(PREF_LOCATIONS, arr.toString()).apply()
    }

    /** 저장된 장소 목록. 반환: List<Pair<label, ssid>> */
    private fun getLocations(): List<Pair<String, String>> {
        val prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
        val arr   = JSONArray(prefs.getString(PREF_LOCATIONS, "[]"))
        return (0 until arr.length()).map {
            val o = arr.getJSONObject(it)
            o.getString("label") to o.getString("ssid")
        }
    }

    /** 현재 WiFi SSID와 일치하는 저장 장소 찾기 */
    fun findNearbyLocation(label: String): String? {
        val ssid = getWifiSsid()
        return getLocations().firstOrNull {
            it.first.contains(label) && it.second == ssid
        }?.first
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
            tts.setSpeechRate(1.1f)
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
