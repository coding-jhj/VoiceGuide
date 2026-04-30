package com.voiceguide

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.media.AudioManager
import android.media.ToneGenerator
import android.net.wifi.WifiManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.util.Log
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

/**
 * VoiceGuide 메인 액티비티
 *
 * 앱의 모든 기능을 총괄합니다:
 *   - CameraX로 1초마다 이미지 캡처
 *   - ONNX 온디바이스 추론 (서버 없이 폰 단독 동작)
 *   - 서버 연동 시 Depth V2 정밀 거리 추정
 *   - STT로 음성 명령 인식 (11가지 모드)
 *   - TTS로 한국어 음성 안내
 *   - 위험도 낮은 알림은 비프음으로만 (경고 피로 방지)
 *   - 조도 센서로 어두운 환경 감지
 *   - 앱 시작 시 음성으로 자동 시작 확인
 *
 * 전체 흐름:
 *   onCreate → TTS 초기화 → "시작할까요?" 음성 → "네" → 카메라 권한 요청
 *   → 카메라 시작 → 1초마다 캡처 → ONNX 또는 서버 추론 → TTS 안내
 */
class MainActivity : AppCompatActivity(), TextToSpeech.OnInitListener, SensorEventListener {

    // ── UI 뷰 참조 ─────────────────────────────────────────────────────
    private lateinit var tts: TextToSpeech
    private lateinit var etServerUrl: EditText   // 서버 IP 입력 (없어도 온디바이스 동작)
    private lateinit var tvStatus: TextView      // 현재 안내 문장 표시
    private lateinit var tvMode: TextView        // 현재 모드 + 카메라 방향 표시
    private lateinit var btnToggle: Button       // 분석 시작/중지
    private lateinit var btnStt: Button          // 음성 명령 버튼
    private lateinit var previewView: PreviewView // 카메라 라이브 프리뷰
    private lateinit var boundingBoxOverlay: BoundingBoxOverlay // 디버그 바운드박스 오버레이

    // ── 카메라 & 분석 루프 ─────────────────────────────────────────────
    private var imageCapture: ImageCapture? = null
    // newSingleThreadExecutor: 카메라 캡처를 UI 스레드와 분리 (UI 멈춤 방지)
    private val cameraExecutor = Executors.newSingleThreadExecutor()
    // Handler: 메인 스레드에서 지연 작업 예약 (1초 간격 루프, Watchdog)
    private val handler = Handler(Looper.getMainLooper())
    // AtomicBoolean: 여러 스레드가 동시에 접근해도 안전한 boolean
    private val isAnalyzing = AtomicBoolean(false)
    private val isSending   = AtomicBoolean(false)
    private var lastSentence = ""
    // TTS 완전 잠금 — compareAndSet으로만 시작 가능, onDone 후 해제
    private val ttsBusy     = AtomicBoolean(false)

    // ── 온디바이스 투표(Voting) 버퍼 ─────────────────────────────────────
    // 최근 5프레임 탐지 결과를 기록해 3회 이상 등장한 사물만 안내
    // → 순간 오탐(인형·노트북 등)이 단발로 잡혀도 TTS 안내 안 됨
    private val detectionHistory = ArrayDeque<Set<String>>()
    private val VOTE_WINDOW    = 3
    private val VOTE_MIN_COUNT = 2  // 3프레임 중 2회 이상 등장해야 안내 (오탐 차단)
    private val ALWAYS_PASS    = setOf("자동차","오토바이","버스","트럭","기차","자전거",
                                       "칼","가위","개","말","곰","코끼리")

    private val classLastSpoken = mutableMapOf<String, Long>()
    private val CLASS_COOLDOWN_MS = 5000L  // 음성 안내 후 같은 사물 재발화 간격
    private val BEEP_AREA_THRESH  = 0.08f  // bbox 면적 8% 이상 = 가까이 있음

    private fun voteOnly(detections: List<Detection>): List<Detection> {
        val currentClasses = detections.map { it.classKo }.toSet()
        detectionHistory.addLast(currentClasses)
        if (detectionHistory.size > VOTE_WINDOW) detectionHistory.removeFirst()
        val counts = mutableMapOf<String, Int>()
        for (frame in detectionHistory) frame.forEach { counts[it] = (counts[it] ?: 0) + 1 }
        return detections.filter { d ->
            d.classKo in ALWAYS_PASS || (counts[d.classKo] ?: 0) >= VOTE_MIN_COUNT
        }
    }

    /**
     * 거리 기반 분류.
     *
     * 가까이(bbox 8%+) → voice  (음성 안내 — 이미 말했어도 아직 가까이면 계속 안내)
     * 멀리 있음        → beep   (있다는 것만 인지)
     * 위험 사물        → 항상 voice
     *
     * 경고 피로는 CLASS_COOLDOWN_MS + lastSentence 비교로 자연스럽게 방지됨.
     */
    private fun classify(voted: List<Detection>): Pair<List<Detection>, Boolean> {
        val voice = mutableListOf<Detection>()
        var shouldBeep = false
        for (d in voted) {
            val isClose = d.classKo in ALWAYS_PASS || d.w * d.h > BEEP_AREA_THRESH
            if (isClose) voice.add(d) else shouldBeep = true
        }
        return voice to (shouldBeep && voice.isEmpty())
    }

    private fun markClassesSpoken(detections: List<Detection>) {
        val now = System.currentTimeMillis()
        detections.forEach { classLastSpoken[it.classKo] = now }
    }

    /**
     * 같은 클래스에서 IoU 0.3 이상 겹치는 중복 bbox 제거.
     * confidence 높은 것을 우선 유지하고, 낮은 것을 중복으로 처리.
     * 원인: YOLO가 같은 물체를 인접한 위치에서 2개로 탐지하는 경우 발생.
     */
    private fun removeDuplicates(detections: List<Detection>): List<Detection> {
        val result = mutableListOf<Detection>()
        for (d in detections.sortedByDescending { it.confidence }) {
            val isDuplicate = result.any { existing ->
                existing.classKo == d.classKo && iouOverlap(existing, d) > 0.3f
            }
            if (!isDuplicate) result.add(d)
        }
        return result
    }

    /** 두 bbox의 IoU(교집합/합집합 비율) 계산. 0~1 범위. */
    private fun iouOverlap(a: Detection, b: Detection): Float {
        val ax1 = a.cx - a.w / 2f;  val ax2 = a.cx + a.w / 2f
        val ay1 = a.cy - a.h / 2f;  val ay2 = a.cy + a.h / 2f
        val bx1 = b.cx - b.w / 2f;  val bx2 = b.cx + b.w / 2f
        val by1 = b.cy - b.h / 2f;  val by2 = b.cy + b.h / 2f
        val ix1 = maxOf(ax1, bx1);  val ix2 = minOf(ax2, bx2)
        val iy1 = maxOf(ay1, by1);  val iy2 = minOf(ay2, by2)
        if (ix2 <= ix1 || iy2 <= iy1) return 0f
        val inter = (ix2 - ix1) * (iy2 - iy1)
        return inter / (a.w * a.h + b.w * b.h - inter)
    }
    // 질문 응답 직후 periodic TTS 억제 — 겹침 방지 (3초간 periodic silent 처리)
    @Volatile private var suppressPeriodicUntil = 0L
    // FPS 측정 — 마지막 요청 시각과 서버 응답시간(ms) 기록
    private var lastRequestTime = 0L
    @Volatile private var lastProcessMs = 0
    private var lastFpsText = ""      // 마지막 FPS 텍스트 — STT 중에도 유지
    private var lastFrameDoneTime = 0L  // FPS 계산용 — 직전 프레임 완료 시각
    private var currentFps = 0.0f      // 최근 계산된 FPS
    // FPS 스파크라인 그래프 (최근 10프레임)
    private val fpsHistory = ArrayDeque<Float>(10)
    private val SPARK = arrayOf("▁","▂","▃","▄","▅","▆","▇","█")
    private var debugVisible = false   // 디버그 오버레이 표시 여부

    // ── HTTP 클라이언트 (서버 연동 — 선택 사항) ────────────────────────
    // connectTimeout: 서버 연결 최대 대기 5초
    // readTimeout: 서버 응답 최대 대기 8초 (YOLO+Depth 추론 시간 고려)
    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .build()
    // AtomicInteger: 연속 실패 횟수 (3회 이상이면 경고 음성)
    private val consecutiveFails = AtomicInteger(0)
    private var lastSuccessTime  = System.currentTimeMillis()
    private var lastDetectionTime  = 0L   // 마지막으로 실제 장애물이 탐지된 시간
    private var lastCriticalTime   = 0L   // 마지막 critical TTS 발화 시간 (5초 쿨다운)
    @Volatile private var speakCooldownUntil = 0L  // TTS 종료 후 700ms 쉬어가기

    // ── 가속도 센서: 카메라 방향 자동 감지 ────────────────────────────
    private lateinit var sensorManager: SensorManager
    // @Volatile: 여러 스레드에서 읽을 때 최신값 보장
    @Volatile private var cameraOrientation = "front"  // front/back/left/right

    // ── STT 음성 명령 ──────────────────────────────────────────────────
    private lateinit var speechRecognizer: SpeechRecognizer
    @Volatile private var currentMode = "장애물"  // 현재 활성 모드
    @Volatile private var findTarget  = ""        // 찾기 모드에서 탐색할 물체 이름
    private var sttStartTime = 0L                 // STT 시작 시각 (지연 측정용)

    // ── 조도 센서 (빛 감지) ────────────────────────────────────────────
    @Volatile private var lastLux = 100f  // 이전 프레임 밝기 (lux 단위)
    // by lazy: 처음 사용 시에만 생성 (앱 시작 시 오디오 초기화 지연)
    // ToneGenerator: 짧은 비프음 재생기 (위험도 낮은 알림용)
    private val toneGen by lazy { ToneGenerator(AudioManager.STREAM_MUSIC, 100) }

    // ── 음성 자동 시작 ─────────────────────────────────────────────────
    private var awaitingStartConfirm = false
    @Volatile private var isListening = false      // STT 활성 중 → TTS 차단
    @Volatile private var autoListenEnabled = false // TTS 끝나면 자동 재청취

    // ── ElevenLabs MediaPlayer (겹침 방지용 단일 인스턴스) ───────────────
    private var currentMediaPlayer: android.media.MediaPlayer? = null
    @Volatile private var isElevenLabsSpeaking = false
    private val ttsExecutor = Executors.newSingleThreadExecutor()
    // 요청 ID: 네트워크 응답이 왔을 때 최신 요청인지 확인 (stale 재생 방지)
    private val ttsRequestId = java.util.concurrent.atomic.AtomicInteger(0)

    // ── 특정 버스 대기 ──────────────────────────────────────────────────
    @Volatile private var waitingBusNumber = ""  // 기다리는 버스 번호 ("37", "N37")

    // ── 보호자 SOS ──────────────────────────────────────────────────────
    private var guardianPhone = ""  // SharedPreferences에 저장된 보호자 번호

    // ── 낙상 감지 ────────────────────────────────────────────────────────
    @Volatile private var lastAccelTotal = 9.8f  // 직전 가속도 크기
    private var fallCheckJob: java.util.Timer? = null

    // ── 약 복용 알림 ─────────────────────────────────────────────────────
    private var medicationTimer: java.util.Timer? = null

    // ── GPS 하차 알림 + 현재 위치 (대시보드 지도용) ──────────────────────
    private var locationManager: android.location.LocationManager? = null
    private var targetBusStop: android.location.Location? = null
    @Volatile private var currentLat = 0.0  // 현재 GPS 위도 (서버 /detect 전송용)
    @Volatile private var currentLng = 0.0  // 현재 GPS 경도
    private val locationListener = android.location.LocationListener { loc ->
        // 현재 위치 항상 업데이트 (대시보드 지도 표시용)
        currentLat = loc.latitude
        currentLng = loc.longitude
        // 하차 알림 처리
        targetBusStop?.let { target ->
            if (loc.distanceTo(target) < 200f) {
                speak("내릴 정류장에 거의 다 왔어요. 준비하세요.")
                stopGpsTracking()
            }
        }
    }

    // ── ONNX 온디바이스 추론 ───────────────────────────────────────────
    private var yoloDetector: YoloDetector? = null

    companion object {
        private const val PERM_CODE          = 100  // 카메라 + 마이크 (앱 시작 시)
        private const val PERM_CODE_LOCATION = 101  // GPS — 하차알림 기능 사용 시
        private const val PERM_CODE_SMS      = 102  // SMS — SOS 설정 시
        private const val PREFS_NAME       = "voiceguide"  // SharedPreferences 이름
        private const val PREF_URL         = "server_url"  // 저장된 서버 URL 키
        private const val PREF_LOCATIONS   = "saved_locations"  // 저장 장소 JSON 배열 키
        private const val INTERVAL_MS      = 700L          // 캡처 간격: 0.7초 (발열·배터리 절감)
        private const val SILENCE_WARN_MS  = 6000L         // 6초 무응답 시 Watchdog 경고
        private const val FAIL_WARN_COUNT  = 3             // 연속 3회 실패 시 경고
        private const val CSV_LOG_ENABLED  = true          // 성능 CSV 로깅 (항상 활성화)
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
        boundingBoxOverlay  = findViewById(R.id.boundingBoxOverlay)

        // 디버그 오버레이 — tvMode 길게 누르면 토글
        val tvDebug = findViewById<android.widget.TextView>(R.id.tvDebug)
        tvMode.setOnLongClickListener {
            debugVisible = !debugVisible
            tvDebug.visibility = if (debugVisible) android.view.View.VISIBLE else android.view.View.GONE
            true
        }

        // 저장된 서버 URL 복원 (없어도 무관)
        etServerUrl.setText(
            getSharedPreferences(PREFS_NAME, MODE_PRIVATE).getString(PREF_URL, ""))

        sensorManager   = getSystemService(SENSOR_SERVICE) as SensorManager
        locationManager = getSystemService(LOCATION_SERVICE) as android.location.LocationManager
        initSpeechRecognizer()
        tryInitYoloDetector()

        // 보호자 번호 로드
        guardianPhone = getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
            .getString("guardian_phone", "") ?: ""

        // Google Assistant shortcut intent 처리
        when (intent?.action) {
            "com.voiceguide.ACTION_START" -> handler.postDelayed({ requestPermissions() }, 1500)
            "com.voiceguide.ACTION_SOS"   -> handler.postDelayed({ triggerSOS() }, 1500)
        }

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
        // 화면이 다시 보일 때마다 센서 리스너 등록
        sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)?.let {
            // SENSOR_DELAY_NORMAL: 약 200ms 간격 (배터리 절약, 방향 감지에 충분)
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL)
        }
        sensorManager.getDefaultSensor(Sensor.TYPE_LIGHT)?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL)
        }
    }

    override fun onPause() {
        super.onPause()
        // 화면 안 보일 때 센서 해제 → 배터리 절약
        sensorManager.unregisterListener(this)
    }

    override fun onDestroy() {
        // 앱 종료 시 모든 리소스 해제 (메모리 누수 방지)
        tts.shutdown()
        speechRecognizer.destroy()
        yoloDetector?.close()         // ONNX 세션 닫기
        cameraExecutor.shutdown()     // 카메라 스레드 종료
        handler.removeCallbacksAndMessages(null)  // 예약된 루프 전부 취소
        super.onDestroy()
    }

    // ── 센서 이벤트 처리 ───────────────────────────────────────────────

    override fun onSensorChanged(event: SensorEvent) {
        // 조도 센서: 밝기가 10 lux 미만으로 떨어지면 어두움 경고
        // 10 lux ≈ 촛불 수준, 일반 실내는 100~500 lux
        if (event.sensor.type == Sensor.TYPE_LIGHT) {
            val lux = event.values[0]
            if (lastLux >= 10f && lux < 10f && isAnalyzing.get()) {
                speak("주변이 많이 어두워요. 조심하세요.")
            }
            lastLux = lux
            return
        }

        if (event.sensor.type != Sensor.TYPE_ACCELEROMETER) return

        // ── 낙상 감지 ────────────────────────────────────────────────────
        // 가속도 크기(magnitude) = sqrt(x²+y²+z²)
        // 정상: 약 9.8 m/s² (중력)
        // 낙상: 자유낙하(~0) 직후 충격(>25) 패턴
        val ax = event.values[0]; val ay = event.values[1]; val az = event.values[2]
        val magnitude = kotlin.math.sqrt((ax*ax + ay*ay + az*az).toDouble()).toFloat()
        if (lastAccelTotal < 3.0f && magnitude > 25.0f) {
            // 자유낙하 후 충격 감지 → 낙상 의심
            scheduleFallCheck()
        }
        lastAccelTotal = magnitude

        val x = event.values[0]; val y = event.values[1]
        val prev = cameraOrientation
        cameraOrientation = when {
            // |y| >= |x|: 위아래로 더 많이 기울어짐 → 앞면 or 뒷면
            abs(y) >= abs(x) -> if (y >= 0) "front" else "back"
            x < 0            -> "left"   // 왼쪽으로 기울어짐
            else             -> "right"  // 오른쪽으로 기울어짐
        }
        // 방향이 바뀌었을 때만 UI 업데이트 (매 프레임 업데이트는 불필요)
        if (cameraOrientation != prev) {
            val label = mapOf("front" to "정면", "back" to "뒤", "left" to "왼쪽", "right" to "오른쪽")
            runOnUiThread { tvMode.text = "모드: $currentMode  |  방향: ${label[cameraOrientation]}" }
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}  // 정확도 변화 무시

    // ── STT 초기화 & 실행 ──────────────────────────────────────────────

    private fun initSpeechRecognizer() {
        speechRecognizer = SpeechRecognizer.createSpeechRecognizer(this)
        speechRecognizer.setRecognitionListener(object : RecognitionListener {
            override fun onResults(results: Bundle) {
                val candidates = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    ?.takeIf { it.isNotEmpty() } ?: return
                // 후보 중 실제 키워드가 매칭된 것 우선 선택, 없으면 첫 번째 사용
                val text = candidates.firstOrNull { classifyKeyword(it) != "unknown" }
                    ?: candidates.first()
                runOnUiThread {
                    btnStt.backgroundTintList = android.content.res.ColorStateList.valueOf(0xFF059669.toInt())
                }
                handleSttResult(text)
            }
            override fun onPartialResults(partialResults: Bundle?) {
                // 부분 인식 결과로 UI 즉시 반응 (사용자에게 인식 중임을 보여줌)
                val partial = partialResults
                    ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    ?.firstOrNull() ?: return
                if (partial.isNotEmpty()) {
                    runOnUiThread { tvMode.text = "🎤 \"$partial\"" }
                }
            }
            override fun onError(error: Int) {
                isListening = false
                val retryable = error in listOf(
                    SpeechRecognizer.ERROR_NO_MATCH,
                    SpeechRecognizer.ERROR_SPEECH_TIMEOUT,
                    SpeechRecognizer.ERROR_RECOGNIZER_BUSY
                )
                if (autoListenEnabled && retryable) {
                    runOnUiThread {
                        tvMode.text = "🎤 [$currentMode] 듣는 중...${if (lastFpsText.isNotEmpty()) "  $lastFpsText" else ""}"
                        btnStt.backgroundTintList = android.content.res.ColorStateList.valueOf(0xFF059669.toInt())
                    }
                    handler.postDelayed({ scheduleAutoListen() }, 800)
                } else {
                    runOnUiThread { tvMode.text = "음성 인식 실패. 다시 눌러주세요." }
                }
            }
            // 아래는 RecognitionListener 인터페이스 필수 구현 (사용하지 않음)
            override fun onReadyForSpeech(p: Bundle?) {}
            override fun onBeginningOfSpeech()         {}
            override fun onRmsChanged(v: Float)         {}
            override fun onBufferReceived(b: ByteArray?) {}
            override fun onEndOfSpeech()                {}
            override fun onEvent(t: Int, p: Bundle?)    {}
        })
    }

    private fun scheduleAutoListen() {
        if (!autoListenEnabled || isListening || awaitingStartConfirm) return
        handler.post(object : Runnable {
            override fun run() {
                if (!autoListenEnabled || isListening) return
                if (isSpeaking()) { handler.postDelayed(this, 200); return }
                startListening()
            }
        })
    }

    private fun startListening() {
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            tvMode.text = "음성 인식 미지원 기기"; return
        }
        // TTS 즉시 중단 후 STT 시작 (간섭 방지)
        tts.stop()
        currentMediaPlayer?.let { try { if (it.isPlaying) it.stop(); it.release() } catch (_: Exception) {} }
        currentMediaPlayer = null
        isElevenLabsSpeaking = false
        isListening = true
        val intent = android.content.Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            // WEB_SEARCH: 짧은 명령어에 최적화 (FREE_FORM보다 인식률 높음)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_WEB_SEARCH)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "ko-KR")
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)          // 후보 3개 → 키워드 매칭률 향상
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)   // 말하는 중간에도 결과 수신
            // 침묵 감지 시간 단축 → 명령어 말한 뒤 빠르게 인식 완료
            putExtra("android.speech.extra.DICTATION_MODE", false)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 700L)   // 말 끝 후 0.7초 → 인식 완료
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 500L)
        }
        // FPS 정보 유지하면서 듣는 중 표시
        sttStartTime = System.currentTimeMillis()
        Log.d("VG_STT", "STT started — mode=$currentMode")
        tvMode.text = "🎤 [$currentMode] 듣는 중...${if (lastFpsText.isNotEmpty()) "  $lastFpsText" else ""}"
        btnStt.backgroundTintList = android.content.res.ColorStateList.valueOf(0xFFDC2626.toInt())
        speechRecognizer.startListening(intent)
    }

    /** STT 결과 처리 — 이미지 분석 불필요 모드는 즉시 처리 */
    private fun handleSttResult(text: String) {
        isListening = false
        val sttElapsedMs = if (sttStartTime > 0L) System.currentTimeMillis() - sttStartTime else -1L
        val mode = classifyKeyword(text)
        Log.d("VG_STT", "STT result: \"$text\" → mode=$mode | elapsed=${sttElapsedMs}ms")
        runOnUiThread { tvMode.text = "모드: $mode  |  방향: 정면" }

        // 자동 시작 응답 처리
        if (awaitingStartConfirm) {
            awaitingStartConfirm = false
            if (text.contains("네") || text.contains("예") || text.contains("응")) {
                requestPermissions()
            } else {
                speak("알겠어요. 분석 시작 버튼을 누르시면 시작돼요.")
            }
            return
        }

        when (mode) {
            // ── 핵심 버그 수정: 질문 모드 즉시 캡처 ──────────────────────────
            // 기존 문제: "지금 뭐 있어?" → else 분기 → "장애물 모드." 말하고 끝
            // 수정: 즉시 이미지 캡처 → 서버에 mode="질문" 전송 → tracker 상태 포함 응답
            "질문" -> {
                speak("확인할게요.")
                captureAndProcessAsQuestion()
            }
            // ── 장애물/확인 모드도 즉시 캡처 ─────────────────────────────────
            // 사용자가 명시적으로 물어봤을 때 즉각 응답
            "장애물", "확인" -> {
                currentMode = mode
                captureAndProcess()
            }
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
                SentenceBuilder.clearStableClocks()
                speakBuiltIn("${findTarget.ifEmpty { "물건" }} 찾기 모드.")
            }
            "텍스트" -> {
                speakBuiltIn("텍스트를 인식할게요.")
                captureForOcr()
            }
            "바코드" -> {
                speakBuiltIn("바코드를 인식할게요.")
                captureForBarcode()
            }
            "색상" -> {
                speakBuiltIn("색상을 확인할게요.")
                currentMode = "색상"
                captureAndProcess()
            }
            "밝기" -> {
                val desc = when {
                    lastLux < 10  -> "매우 어두워요."
                    lastLux < 50  -> "조금 어두운 편이에요."
                    lastLux < 300 -> "적당히 밝아요."
                    else          -> "매우 밝아요."
                }
                speak("현재 밝기는 $desc")
            }
            "신호등" -> {
                speakBuiltIn("신호등을 확인할게요.")
                currentMode = "신호등"
                captureAndProcess()
            }
            "버스번호" -> {
                speakBuiltIn("버스 번호를 확인할게요.")
                captureForBusNumber()
            }
            "버스대기" -> {
                // "37번 버스 기다려줘" → "37" 추출
                val num = Regex("\\d{1,4}").find(text)?.value ?: ""
                if (num.isEmpty()) {
                    speak("몇 번 버스를 기다릴까요? 예) 37번 버스 기다려줘.")
                } else {
                    waitingBusNumber = num
                    speak("${num}번 버스를 기다릴게요. 가까이 오면 알려드릴게요.")
                }
            }
            "다시읽기" -> {
                if (lastSentence.isEmpty()) speak("아직 안내한 내용이 없어요.")
                else speak(lastSentence)
            }
            "볼륨업" -> {
                val am = getSystemService(AUDIO_SERVICE) as AudioManager
                am.adjustStreamVolume(AudioManager.STREAM_MUSIC,
                    AudioManager.ADJUST_RAISE, AudioManager.FLAG_SHOW_UI)
                speak("소리를 높였어요.")
            }
            "볼륨다운" -> {
                val am = getSystemService(AUDIO_SERVICE) as AudioManager
                am.adjustStreamVolume(AudioManager.STREAM_MUSIC,
                    AudioManager.ADJUST_LOWER, AudioManager.FLAG_SHOW_UI)
                speak("소리를 낮췄어요.")
            }
            "중지" -> {
                stopAnalysis()
                speak("분석을 잠깐 멈출게요.")
            }
            "재시작" -> {
                if (!isAnalyzing.get()) {
                    speak("다시 시작할게요.")
                    handler.postDelayed({ requestPermissions() }, 800)
                } else speak("이미 분석 중이에요.")
            }
            "긴급" -> requestSmsPermission { triggerSOS() }
            "식사" -> {
                currentMode = "식사"
                speak("식사 도우미 모드예요. 식기와 음식 위치를 알려드릴게요.")
                captureAndProcess()
            }
            "옷매칭" -> {
                speak("옷 매칭을 확인할게요.")
                captureForClothingAdvice("matching")
            }
            "옷패턴" -> {
                speak("옷 패턴을 확인할게요.")
                captureForClothingAdvice("pattern")
            }
            "돈" -> {
                speak("지폐를 확인할게요.")
                captureForCurrency()
            }
            "약알림" -> {
                // "8시에 약 먹어야 해" → 시간 추출
                val hour = Regex("(\\d{1,2})시").find(text)?.groupValues?.get(1)?.toIntOrNull()
                if (hour != null) setMedicationAlarm(hour)
                else speak("몇 시에 약을 드실 건가요? 예) 8시에 약 먹어야 해.")
            }
            "하차알림" -> requestLocationPermission {
                speak("현재 위치를 기준으로 200미터 이내에 도착하면 알려드릴게요.")
                startGpsTracking()
            }
            "unknown" -> speak("다시 말씀해 주세요.")
            else -> {
                currentMode = mode
                SentenceBuilder.clearStableClocks()
                speakBuiltIn("$mode 모드.")
            }
        }
    }

    /**
     * "글자 읽어줘" 명령 처리 — ML Kit OCR로 카메라 이미지의 텍스트 인식.
     */
    private fun captureForOcr() {
        val file = File.createTempFile("vg_ocr_", ".jpg", cacheDir)
        imageCapture?.takePicture(
            ImageCapture.OutputFileOptions.Builder(file).build(),
            cameraExecutor,
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                    Thread {
                        try {
                            val bmp = android.graphics.BitmapFactory.decodeFile(file.absolutePath)
                            val recognizer = com.google.mlkit.vision.text.korean.KoreanTextRecognizerOptions.Builder().build()
                                .let { com.google.mlkit.vision.text.TextRecognition.getClient(it) }
                            val image = com.google.mlkit.vision.common.InputImage.fromBitmap(bmp, 0)
                            recognizer.process(image)
                                .addOnSuccessListener { result ->
                                    val text = result.text.trim()
                                    if (text.isEmpty()) speak("텍스트를 찾지 못했어요.")
                                    else speak(text)
                                    file.delete()
                                }
                                .addOnFailureListener { speak("텍스트 인식에 실패했어요."); file.delete() }
                        } catch (_: Exception) { speak("텍스트 인식에 실패했어요."); file.delete() }
                    }.start()
                }
                override fun onError(e: ImageCaptureException) { speak("사진을 찍지 못했어요.") }
            })
    }

    /**
     * "바코드" 명령 처리 — ML Kit Barcode Scanning으로 상품 정보 인식.
     */
    private fun captureForBarcode() {
        val file = File.createTempFile("vg_bc_", ".jpg", cacheDir)
        imageCapture?.takePicture(
            ImageCapture.OutputFileOptions.Builder(file).build(),
            cameraExecutor,
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                    Thread {
                        try {
                            val bmp = android.graphics.BitmapFactory.decodeFile(file.absolutePath)
                            val scanner = com.google.mlkit.vision.barcode.BarcodeScanning.getClient()
                            val image = com.google.mlkit.vision.common.InputImage.fromBitmap(bmp, 0)
                            scanner.process(image)
                                .addOnSuccessListener { barcodes ->
                                    if (barcodes.isEmpty()) speak("바코드를 찾지 못했어요.")
                                    else speak("${barcodes[0].displayValue ?: "알 수 없는 상품"}이에요.")
                                    file.delete()
                                }
                                .addOnFailureListener { speak("바코드 인식에 실패했어요."); file.delete() }
                        } catch (_: Exception) { speak("바코드 인식에 실패했어요."); file.delete() }
                    }.start()
                }
                override fun onError(e: ImageCaptureException) { speak("사진을 찍지 못했어요.") }
            })
    }

    /**
     * "버스 번호 알려줘" 명령 처리.
     * 2단계: ML Kit OCR → 실패 시 서버 EasyOCR fallback
     */
    private fun captureForBusNumber() {
        val file = File.createTempFile("vg_bus_", ".jpg", cacheDir)
        imageCapture?.takePicture(
            ImageCapture.OutputFileOptions.Builder(file).build(),
            cameraExecutor,
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                    Thread {
                        try {
                            val origBmp = android.graphics.BitmapFactory.decodeFile(file.absolutePath)
                            val matrix = android.graphics.ColorMatrix().apply { setSaturation(0f) }
                            val contrastMatrix = android.graphics.ColorMatrix(floatArrayOf(
                                1.5f, 0f, 0f, 0f, -30f,
                                0f, 1.5f, 0f, 0f, -30f,
                                0f, 0f, 1.5f, 0f, -30f,
                                0f, 0f, 0f, 1f,   0f
                            ))
                            matrix.postConcat(contrastMatrix)
                            val paint = android.graphics.Paint().apply {
                                colorFilter = android.graphics.ColorMatrixColorFilter(matrix)
                            }
                            val processedBmp = android.graphics.Bitmap.createBitmap(
                                origBmp.width, origBmp.height, android.graphics.Bitmap.Config.ARGB_8888
                            )
                            android.graphics.Canvas(processedBmp).drawBitmap(origBmp, 0f, 0f, paint)
                            val recognizer = com.google.mlkit.vision.text.korean.KoreanTextRecognizerOptions.Builder().build()
                                .let { com.google.mlkit.vision.text.TextRecognition.getClient(it) }
                            val mlkitImage = com.google.mlkit.vision.common.InputImage.fromBitmap(processedBmp, 0)
                            recognizer.process(mlkitImage)
                                .addOnSuccessListener { result ->
                                    val numbers = result.textBlocks
                                        .flatMap { it.lines }
                                        .mapNotNull { line ->
                                            val clean = line.text.trim()
                                            if (clean.matches(Regex("[A-Za-z]?\\d{1,4}"))) clean else null
                                        }
                                        .distinct()
                                    if (numbers.isNotEmpty()) {
                                        val best = numbers.minByOrNull { it.length } ?: numbers[0]
                                        if (waitingBusNumber.isNotEmpty() && best == waitingBusNumber) {
                                            val vibrator = getSystemService(VIBRATOR_SERVICE) as android.os.Vibrator
                                            vibrator.vibrate(android.os.VibrationEffect.createWaveform(
                                                longArrayOf(0, 400, 100, 400, 100, 400), -1))
                                            speak("${best}번 버스 왔어요! 지금 손을 드세요!")
                                            waitingBusNumber = ""
                                        } else {
                                            speak("${best}번 버스예요.")
                                        }
                                        origBmp.recycle(); processedBmp.recycle(); file.delete()
                                    } else {
                                        origBmp.recycle(); processedBmp.recycle()
                                        sendBusOcrToServer(file)
                                    }
                                }
                                .addOnFailureListener {
                                    origBmp.recycle(); processedBmp.recycle()
                                    sendBusOcrToServer(file)
                                }
                        } catch (_: Exception) { speak("버스 번호 인식에 실패했어요."); file.delete() }
                    }.start()
                }
                override fun onError(e: ImageCaptureException) { speak("사진을 찍지 못했어요.") }
            })
    }

    private fun sendBusOcrToServer(imageFile: File) {
        val serverUrl = etServerUrl.text.toString().trim().trimEnd('/')
        if (serverUrl.isEmpty()) {
            speak("버스 번호를 읽지 못했어요. 서버를 연결하면 더 잘 인식돼요.")
            imageFile.delete()
            return
        }
        Thread {
            try {
                val body = okhttp3.MultipartBody.Builder().setType(okhttp3.MultipartBody.FORM)
                    .addFormDataPart("image", "bus.jpg",
                        imageFile.asRequestBody("image/jpeg".toMediaType()))
                    .build()
                val response = httpClient.newCall(
                    okhttp3.Request.Builder().url("$serverUrl/ocr/bus").post(body).build()
                ).execute()
                val json     = org.json.JSONObject(response.body?.string() ?: "{}")
                val sentence = json.optString("sentence", "버스 번호를 읽지 못했어요.")
                runOnUiThread { speak(sentence) }
            } catch (_: Exception) {
                runOnUiThread { speak("버스 번호 인식에 실패했어요.") }
            } finally {
                imageFile.delete()
            }
        }.start()
    }

    // ── SOS 긴급 호출 ──────────────────────────────────────────────────

    private fun triggerSOS() {
        val vibrator = getSystemService(VIBRATOR_SERVICE) as android.os.Vibrator
        vibrator.vibrate(android.os.VibrationEffect.createWaveform(
            longArrayOf(0, 500, 200, 500, 200, 500), -1))
        speak("보호자에게 도움을 요청할게요.")
        if (guardianPhone.isEmpty()) {
            speak("보호자 번호가 설정되어 있지 않아요. 설정에서 먼저 등록해 주세요.")
            return
        }
        if (!hasPerm(Manifest.permission.SEND_SMS)) {
            speak("문자 발송 권한이 없어요. 앱 설정에서 SMS 권한을 허용해 주세요.")
            return
        }
        try {
            val sms = android.telephony.SmsManager.getDefault()
            val msg = "[VoiceGuide 긴급] 도움이 필요합니다. 앱에서 자동 발송된 메시지입니다."
            sms.sendTextMessage(guardianPhone, null, msg, null, null)
            speak("${guardianPhone}으로 도움 요청 문자를 보냈어요.")
        } catch (_: Exception) {
            speak("문자 발송에 실패했어요. 직접 전화해 주세요.")
        }
    }

    // ── 낙상 감지 후처리 ───────────────────────────────────────────────

    private fun scheduleFallCheck() {
        fallCheckJob?.cancel()
        speak("괜찮으세요? 10초 안에 '괜찮아'라고 말씀해 주세요.")
        val confirmed = AtomicBoolean(false)
        val timer = java.util.Timer()
        timer.schedule(object : java.util.TimerTask() {
            override fun run() {
                if (!confirmed.get()) runOnUiThread { triggerSOS() }
            }
        }, 10_000)
        fallCheckJob = timer
        handler.postDelayed({
            startListeningForFallConfirm { confirmed.set(true); timer.cancel() }
        }, 1000)
    }

    private fun startListeningForFallConfirm(onOk: () -> Unit) {
        if (!SpeechRecognizer.isRecognitionAvailable(this)) return
        val intent = android.content.Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "ko-KR")
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        }
        val fallRecognizer = SpeechRecognizer.createSpeechRecognizer(this)
        fallRecognizer.setRecognitionListener(object : RecognitionListener {
            override fun onResults(results: Bundle) {
                val text = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    ?.firstOrNull() ?: ""
                if (text.contains("괜찮") || text.contains("없어") || text.contains("아니")) {
                    speak("다행이에요. 조심하세요.")
                    onOk()
                }
                fallRecognizer.destroy()
            }
            override fun onError(e: Int) { fallRecognizer.destroy() }
            override fun onReadyForSpeech(p: Bundle?) {}
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(v: Float) {}
            override fun onBufferReceived(b: ByteArray?) {}
            override fun onEndOfSpeech() {}
            override fun onPartialResults(p: Bundle?) {}
            override fun onEvent(t: Int, p: Bundle?) {}
        })
        fallRecognizer.startListening(intent)
    }

    // ── 옷 매칭·패턴 (서버 GPT Vision) ───────────────────────────────

    private fun captureForClothingAdvice(type: String) {
        val serverUrl = etServerUrl.text.toString().trim().trimEnd('/')
        if (serverUrl.isEmpty()) {
            speak("옷 분석은 서버 연결이 필요해요."); return
        }
        val file = File.createTempFile("vg_cloth_", ".jpg", cacheDir)
        imageCapture?.takePicture(
            ImageCapture.OutputFileOptions.Builder(file).build(), cameraExecutor,
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(o: ImageCapture.OutputFileResults) {
                    Thread {
                        try {
                            val body = okhttp3.MultipartBody.Builder().setType(okhttp3.MultipartBody.FORM)
                                .addFormDataPart("image", "cloth.jpg",
                                    file.asRequestBody("image/jpeg".toMediaType()))
                                .addFormDataPart("type", type)
                                .build()
                            val resp = httpClient.newCall(
                                okhttp3.Request.Builder().url("$serverUrl/vision/clothing").post(body).build()
                            ).execute()
                            val sentence = org.json.JSONObject(resp.body?.string() ?: "{}")
                                .optString("sentence", "분석하지 못했어요.")
                            runOnUiThread { speak(sentence) }
                        } catch (_: Exception) { runOnUiThread { speak("옷 분석에 실패했어요.") } }
                        finally { file.delete() }
                    }.start()
                }
                override fun onError(e: ImageCaptureException) { speak("사진을 찍지 못했어요.") }
            })
    }

    // ── 지폐 인식 (색상 기반) ─────────────────────────────────────────

    private fun captureForCurrency() {
        val file = File.createTempFile("vg_curr_", ".jpg", cacheDir)
        imageCapture?.takePicture(
            ImageCapture.OutputFileOptions.Builder(file).build(), cameraExecutor,
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(o: ImageCapture.OutputFileResults) {
                    Thread {
                        try {
                            val bmp = android.graphics.BitmapFactory.decodeFile(file.absolutePath)
                            val cx = bmp.width / 2; val cy = bmp.height / 2
                            val size = minOf(bmp.width, bmp.height) / 4
                            val pixels = IntArray(size * size)
                            bmp.getPixels(pixels, 0, size, cx - size/2, cy - size/2, size, size)
                            bmp.recycle()
                            var rSum = 0f; var gSum = 0f; var bSum = 0f
                            pixels.forEach { p ->
                                rSum += ((p shr 16) and 0xFF)
                                gSum += ((p shr 8)  and 0xFF)
                                bSum += (p and 0xFF)
                            }
                            val n = pixels.size.toFloat()
                            val r = rSum / n; val g = gSum / n; val b = bSum / n
                            val sentence = when {
                                r > 180 && g > 150 && b < 130 -> "50000원권 같아요."
                                r > g * 1.3f && r > b * 1.5f -> "5000원권 같아요."
                                g > b && g > r * 0.9f && r < 180 -> "10000원권 같아요."
                                b > r && b > g -> "1000원권 같아요."
                                else -> "지폐를 정확히 인식하지 못했어요. 카메라에 지폐를 가득 채워보세요."
                            }
                            runOnUiThread { speak(sentence) }
                        } catch (_: Exception) { runOnUiThread { speak("지폐 인식에 실패했어요.") } }
                        finally { file.delete() }
                    }.start()
                }
                override fun onError(e: ImageCaptureException) { speak("사진을 찍지 못했어요.") }
            })
    }

    // ── 약 복용 알림 ─────────────────────────────────────────────────

    private fun setMedicationAlarm(hour: Int) {
        medicationTimer?.cancel()
        val now = java.util.Calendar.getInstance()
        val target = java.util.Calendar.getInstance().apply {
            set(java.util.Calendar.HOUR_OF_DAY, hour)
            set(java.util.Calendar.MINUTE, 0)
            set(java.util.Calendar.SECOND, 0)
            if (before(now)) add(java.util.Calendar.DAY_OF_YEAR, 1)
        }
        val delayMs = target.timeInMillis - now.timeInMillis
        speak("매일 ${hour}시에 약 복용 알림을 설정했어요.")
        medicationTimer = java.util.Timer(true)
        medicationTimer?.schedule(object : java.util.TimerTask() {
            override fun run() {
                runOnUiThread {
                    speak("약 드실 시간이에요. ${hour}시 약 복용 알림이에요.")
                    val vibrator = getSystemService(VIBRATOR_SERVICE) as android.os.Vibrator
                    vibrator.vibrate(android.os.VibrationEffect.createWaveform(
                        longArrayOf(0, 300, 200, 300), -1))
                }
            }
        }, delayMs, 24 * 60 * 60 * 1000)
    }

    // ── GPS 하차 알림 ────────────────────────────────────────────────

    @Suppress("MissingPermission")
    private fun startGpsTracking() {
        try {
            locationManager?.requestLocationUpdates(
                android.location.LocationManager.GPS_PROVIDER,
                5000L, 50f, locationListener
            )
            val lastLoc = locationManager?.getLastKnownLocation(
                android.location.LocationManager.GPS_PROVIDER)
            if (lastLoc != null) {
                targetBusStop = lastLoc
                speak("현재 위치에서 200미터 이내로 돌아오면 알려드릴게요.")
            } else {
                speak("GPS 신호를 찾는 중이에요. 잠시 후 다시 시도해 주세요.")
            }
        } catch (_: Exception) {
            speak("GPS를 사용할 수 없어요.")
        }
    }

    private fun stopGpsTracking() {
        locationManager?.removeUpdates(locationListener)
        targetBusStop = null
    }

    /**
     * STT 텍스트 → 모드 분류.
     * VoiceGuideConstants.kt의 STT_KEYWORDS 맵에서 순서대로 검색.
     * 매칭 없으면 "unknown" 반환 → handleSttResult에서 "다시 말씀해 주세요" 처리.
     */
    private fun classifyKeyword(text: String): String {
        for ((mode, keywords) in STT_KEYWORDS) {
            if (keywords.any { text.contains(it) }) return mode
        }
        return "unknown"
    }

    // ── ONNX 온디바이스 추론 초기화 ────────────────────────────────────

    private fun tryInitYoloDetector() {
        // 백그라운드 스레드에서 초기화 (모델 로딩이 느려서 UI 스레드에서 하면 앱 멈춤)
        Thread {
            try {
                yoloDetector = YoloDetector(this)  // assets에서 ONNX 로드
                runOnUiThread { tvStatus.text = "온디바이스 준비 완료 — 분석 시작을 누르세요" }
            } catch (_: Exception) {
                // assets에 yolo11n.onnx 없는 경우 → 서버 모드 안내
                runOnUiThread { tvStatus.text = "ONNX 모델 없음 — 서버 URL을 입력하세요" }
            }
        }.start()
    }

    // ── 카메라 & 분석 루프 ──────────────────────────────────────────────

    // 권한 요청 콜백 저장 (비동기 결과 처리용)
    private var locationPermissionCallback: (() -> Unit)? = null
    private var smsPermissionCallback: (() -> Unit)? = null

    /** 앱 시작 시 필수 권한만 요청: 카메라 + 마이크 */
    private fun requestPermissions() {
        val needed = mutableListOf<String>()
        if (!hasPerm(Manifest.permission.CAMERA))       needed.add(Manifest.permission.CAMERA)
        if (!hasPerm(Manifest.permission.RECORD_AUDIO)) needed.add(Manifest.permission.RECORD_AUDIO)
        if (needed.isEmpty()) startCamera()
        else ActivityCompat.requestPermissions(this, needed.toTypedArray(), PERM_CODE)
    }

    /** GPS 기능(하차알림) 사용 시에만 위치 권한 요청 */
    private fun requestLocationPermission(onGranted: () -> Unit) {
        if (hasPerm(Manifest.permission.ACCESS_FINE_LOCATION)) { onGranted(); return }
        locationPermissionCallback = onGranted
        ActivityCompat.requestPermissions(this,
            arrayOf(Manifest.permission.ACCESS_FINE_LOCATION), PERM_CODE_LOCATION)
    }

    /** SOS 보호자 문자 설정 시에만 SMS 권한 요청 */
    private fun requestSmsPermission(onGranted: () -> Unit) {
        if (hasPerm(Manifest.permission.SEND_SMS)) { onGranted(); return }
        smsPermissionCallback = onGranted
        ActivityCompat.requestPermissions(this,
            arrayOf(Manifest.permission.SEND_SMS), PERM_CODE_SMS)
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
        autoListenEnabled = true
        SentenceBuilder.clearStableClocks()
        detectionHistory.clear()  // 재시작 시 이전 투표 버퍼 초기화
        lastSentence = ""
        consecutiveFails.set(0)
        lastSuccessTime = System.currentTimeMillis()
        btnToggle.text = "■ 분석 중지"
        btnToggle.backgroundTintList = android.content.res.ColorStateList.valueOf(0xFFDC2626.toInt())
        tvStatus.text  = "분석 중..."
        captureAndProcess()
        scheduleNext()
        scheduleWatchdog()
        scheduleAutoListen()
    }

    private fun stopAnalysis() {
        isAnalyzing.set(false)
        autoListenEnabled = false
        handler.removeCallbacksAndMessages(null)
        btnToggle.text = "▶ 분석 시작"
        btnToggle.backgroundTintList = android.content.res.ColorStateList.valueOf(0xFF2563EB.toInt())
        tvStatus.text  = "분석 중지됨"
        boundingBoxOverlay.clearDetections()
    }

    // ── 재방문 알림 ───────────────────────────────────────────────────────
    private var lastLocationCheckTime = 0L
    private var lastAnnouncedSsid     = ""  // 같은 장소 중복 알림 방지

    private fun checkRevisit() {
        val now = System.currentTimeMillis()
        if (now - lastLocationCheckTime < 30_000L) return  // 30초마다 체크
        lastLocationCheckTime = now
        val ssid = getWifiSsid()
        if (ssid.isEmpty() || ssid == lastAnnouncedSsid) return
        val match = getLocations().firstOrNull { it.second == ssid } ?: return
        lastAnnouncedSsid = ssid
        handler.post { speak("${match.first}에 도착했어요.") }
    }

    private fun scheduleNext() {
        handler.postDelayed({
            if (isAnalyzing.get()) {
                checkRevisit()
                captureAndProcess()  // isSending 플래그로 중복 방지
                scheduleNext()       // 100ms 후 다시 시도 (실제 FPS = 추론시간에 의해 결정)
            }
        }, INTERVAL_MS)
    }

    private fun scheduleWatchdog() {
        // Watchdog: 6초 동안 성공 응답이 없으면 음성으로 경고
        handler.postDelayed({
            if (!isAnalyzing.get()) return@postDelayed
            if (System.currentTimeMillis() - lastSuccessTime >= SILENCE_WARN_MS && !isSpeaking()) {
                speak("분석이 중단됐어요. 주의해서 이동하세요.")
                runOnUiThread { tvStatus.text = "⚠ 분석 중단 — 주의하세요" }
            }
            scheduleWatchdog()
        }, SILENCE_WARN_MS)
    }

    private fun captureAndProcess() {
        // isSending 체크: 이전 요청이 아직 진행 중이면 새 캡처 스킵 (중복 방지)
        if (isSending.get()) return
        val file = File.createTempFile("vg_", ".jpg", cacheDir)
        imageCapture?.takePicture(
            ImageCapture.OutputFileOptions.Builder(file).build(),
            cameraExecutor,
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                    isSending.set(true)
                    val serverUrl = etServerUrl.text.toString().trim()
                    when {
                        // 서버 URL이 있으면 서버 우선 (YOLO11m + Depth V2 + 공간기억 활용)
                        serverUrl.isNotEmpty() -> sendToServer(file)
                        // URL 없고 온디바이스 모델 있으면 폰 단독 추론
                        yoloDetector != null   -> processOnDevice(file)
                        // 둘 다 없으면 안내 후 종료
                        else -> {
                            isSending.set(false)
                            file.delete()
                            runOnUiThread { speak("서버 URL을 입력하거나 앱을 재시작해 주세요.") }
                        }
                    }
                }
                override fun onError(e: ImageCaptureException) {
                    isSending.set(false)
                    handleFail()
                }
            })
    }

    /**
     * 질문 모드 전용 즉시 캡처.
     * 서버에 mode="질문" 전송 → tracker 누적 상태 포함 포괄 응답을 받음.
     * isSending 체크를 우회해서 항상 즉시 실행 (사용자 직접 질문이므로).
     */
    private fun captureAndProcessAsQuestion() {
        val file = File.createTempFile("vg_q_", ".jpg", cacheDir)
        imageCapture?.takePicture(
            ImageCapture.OutputFileOptions.Builder(file).build(),
            cameraExecutor,
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                    sendToServerWithMode(file, "질문")
                }
                override fun onError(e: ImageCaptureException) {
                    speak("사진을 찍지 못했어요.")
                }
            })
    }

    /**
     * 특정 모드로 서버에 전송. 질문 모드 등 currentMode를 바꾸지 않고 1회성 전송 시 사용.
     */
    private fun sendToServerWithMode(imageFile: File, mode: String) {
        val serverUrl = etServerUrl.text.toString().trim().trimEnd('/')
        if (serverUrl.isEmpty()) {
            imageFile.delete()
            speak("서버가 연결되어 있지 않아요. 서버 URL을 입력해 주세요.")
            return
        }
        Thread {
            try {
                val body = MultipartBody.Builder().setType(MultipartBody.FORM)
                    .addFormDataPart("image", "frame.jpg",
                        imageFile.asRequestBody("image/jpeg".toMediaType()))
                    .addFormDataPart("camera_orientation", cameraOrientation)
                    .addFormDataPart("wifi_ssid", getWifiSsid())
                    .addFormDataPart("mode", mode)
                    .addFormDataPart("query_text", "")
                    .addFormDataPart("lat", currentLat.toString())
                    .addFormDataPart("lng", currentLng.toString())
                    .build()
                val response = httpClient.newCall(
                    Request.Builder().url("$serverUrl/detect").post(body).build()
                ).execute()
                val json     = JSONObject(response.body?.string() ?: "{}")
                val sentence = json.optString("sentence", "확인하지 못했어요.")
                // 질문 응답 후 3초간 periodic capture의 TTS 억제
                suppressPeriodicUntil = System.currentTimeMillis() + 3000L
                runOnUiThread { tvStatus.text = sentence; speak(sentence) }
            } catch (_: Exception) {
                runOnUiThread { speak("서버 연결에 실패했어요.") }
            } finally {
                imageFile.delete()
            }
        }.start()
    }

    /**
     * 서버 전송 전 이미지 최적화 — FPS 개선 핵심
     *
     * 원본 이미지(예: 4000×3000, JPEG 90%) → 640×480, JPEG 75%로 변환
     * 전송 크기 약 40~60% 감소 → 네트워크 지연 단축 → 체감 FPS 향상
     * YOLO 입력은 어차피 640×640으로 리사이즈되므로 품질 손실 없음
     */
    // Triple<최적화파일, 너비, 높이> 반환 — 크기를 따로 디코딩하지 않아도 됨
    private fun optimizeImageForUpload(file: File): Triple<File, Int, Int> {
        return try {
            val bmp = android.graphics.BitmapFactory.decodeFile(file.absolutePath)
                ?: return Triple(file, 0, 0)

            val maxW = 640
            val scaled = if (bmp.width > maxW) {
                val ratio = maxW.toFloat() / bmp.width
                val newH  = (bmp.height * ratio).toInt()
                android.graphics.Bitmap.createScaledBitmap(bmp, maxW, newH, true)
                    .also { if (it != bmp) bmp.recycle() }
            } else bmp

            val w = scaled.width
            val h = scaled.height
            val out = File.createTempFile("vg_opt_", ".jpg", cacheDir)
            out.outputStream().use { stream ->
                scaled.compress(android.graphics.Bitmap.CompressFormat.JPEG, 75, stream)
            }
            scaled.recycle()
            file.delete()
            Triple(out, w, h)
        } catch (_: Exception) {
            Triple(file, 0, 0)
        }
    }

    // ── 온디바이스 추론 ─────────────────────────────────────────────────

    private fun processOnDevice(imageFile: File) {
        Thread {
            val t0 = System.currentTimeMillis()
            var bmp: android.graphics.Bitmap? = null
            var usedServerFallback = false
            try {
                val tDecode = System.currentTimeMillis()
                bmp = decodeBitmapUpright(imageFile)
                val decodeMs = System.currentTimeMillis() - tDecode

                val imgW = bmp.width
                val imgH = bmp.height

                val tInfer = System.currentTimeMillis()
                val rawDetections = yoloDetector!!.detect(bmp)
                val inferMs = System.currentTimeMillis() - tInfer

                val tDedup = System.currentTimeMillis()
                // 투표 필터 → 같은 클래스 중복 bbox 제거(IoU 기반) 순서로 처리
                val voted = removeDuplicates(voteOnly(rawDetections))
                val dedupMs = System.currentTimeMillis() - tDedup

                val totalMs = System.currentTimeMillis() - t0

                // 구조화 성능 로그 — Logcat에서 tag:VG_PERF 로 필터
                android.util.Log.d("VG_PERF",
                    "decode|$decodeMs|infer|$inferMs|dedup|$dedupMs|total|$totalMs|objs|${voted.size}")

                // FPS < 10 이면 경고 로그
                val estimatedFps = if (totalMs > 0) 1000f / totalMs else 0f
                if (estimatedFps < 10f) {
                    android.util.Log.w("VG_PERF",
                        "⚠ FPS 미달: ${String.format("%.1f", estimatedFps)}fps (${totalMs}ms) — 모델 경량화 필요")
                }

                runOnUiThread {
                    val fps = calcFps()
                    val spark = buildSparkline()
                    lastFpsText = "${fps}fps $spark | 📱 ${inferMs}ms"
                    tvMode.text = "[$currentMode] $lastFpsText"
                    if (debugVisible) {
                        val tv = findViewById<android.widget.TextView>(R.id.tvDebug)
                        tv.text = "FPS    : ${fps}\n" +
                                  "디코딩 : ${decodeMs}ms\n" +
                                  "YOLO   : ${inferMs}ms\n" +
                                  "후처리 : ${dedupMs}ms\n" +
                                  "전체   : ${totalMs}ms\n" +
                                  "탐지수 : raw=${rawDetections.size} → ${voted.size}"
                    }
                }

                bmp.recycle(); bmp = null
                // imageFile은 finally에서 삭제 (catch의 서버 fallback이 먼저 파일 필요)

                Log.d("VG_DETECT", "=== 탐지 결과 ===")
                Log.d("VG_DETECT", "raw: ${rawDetections.size}개 → dedup: ${voted.size}개")
                voted.forEachIndexed { i, d ->
                    Log.d("VG_DETECT", "  [$i] ${d.classKo} | conf=${String.format("%.2f", d.confidence)} | cx=${String.format("%.2f", d.cx)} | w=${String.format("%.2f", d.w)} h=${String.format("%.2f", d.h)} | area=${String.format("%.3f", d.w * d.h)}")
                }

                runOnUiThread {
                    if (voted.isEmpty()) {
                        boundingBoxOverlay.clearDetections()  // 탐지 없을 때만 박스 제거
                    } else {
                        boundingBoxOverlay.setDetections(voted, imgW, imgH)
                    }
                }

                if (voted.isEmpty()) {
                    Log.d("VG_DETECT", "→ 장애물 없음")
                    handleSuccess("주변에 장애물이 없어요.")
                    return@Thread
                }

                val (voiceDetections, shouldBeep) = classify(voted)

                // 문장은 항상 전체 voted 기준 (가까운 것부터 정렬, 최대 3개)
                val sorted   = voted.sortedByDescending { it.w * it.h }
                val sentence = when (currentMode) {
                    "찾기" -> SentenceBuilder.buildFind(findTarget, sorted)
                    else  -> SentenceBuilder.build(sorted)
                }

                Log.d("VG_DETECT", "생성된 문장: \"$sentence\"")
                Log.d("VG_DETECT", "음성=${voiceDetections.size}개 | beep=$shouldBeep | mode=$currentMode")

                when {
                    voiceDetections.isNotEmpty() -> {
                        markClassesSpoken(voiceDetections)
                        val mode = when {
                            currentMode == "찾기"                              -> "critical"
                            voiceDetections.any { it.classKo in ALWAYS_PASS } -> "critical"
                            else                                               -> "normal"
                        }
                        Log.d("VG_DETECT", "→ 음성 출력 (mode=$mode)")
                        handleSuccess(sentence, mode)
                    }
                    shouldBeep -> {
                        Log.d("VG_DETECT", "→ 비프음")
                        handleSuccess(sentence, "beep")
                    }
                    else       -> {
                        Log.d("VG_DETECT", "→ 무음 (거리 멀거나 최근 안내 완료)")
                        handleSuccess("주변에 장애물이 없어요.")
                    }
                }
            } catch (_: Exception) {
                bmp?.recycle()
                // 온디바이스 실패 → 파일이 아직 존재하므로 서버로 fallback
                // (sendToServer가 finally에서 파일 삭제 담당)
                usedServerFallback = true
                sendToServer(imageFile)
            } finally {
                // 서버 fallback을 쓰지 않은 경우(정상 완료)에만 여기서 파일 삭제
                if (!usedServerFallback) imageFile.delete()
            }
        }.start()
    }

    /** JPEG 파일의 EXIF 회전 태그를 읽어 실제 화면 방향으로 비트맵을 회전한다. */
    private fun decodeBitmapUpright(file: File): android.graphics.Bitmap {
        val exif = android.media.ExifInterface(file.absolutePath)
        val degrees = when (exif.getAttributeInt(
            android.media.ExifInterface.TAG_ORIENTATION,
            android.media.ExifInterface.ORIENTATION_NORMAL
        )) {
            android.media.ExifInterface.ORIENTATION_ROTATE_90  -> 90f
            android.media.ExifInterface.ORIENTATION_ROTATE_180 -> 180f
            android.media.ExifInterface.ORIENTATION_ROTATE_270 -> 270f
            else -> 0f
        }
        val raw = android.graphics.BitmapFactory.decodeFile(file.absolutePath)
        if (degrees == 0f) return raw
        val matrix = android.graphics.Matrix().apply { postRotate(degrees) }
        val rotated = android.graphics.Bitmap.createBitmap(raw, 0, 0, raw.width, raw.height, matrix, true)
        raw.recycle()
        return rotated
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
            var sentImgW = 0
            var sentImgH = 0
            try {
                // FPS 측정 시작 — 요청 전송 시각 기록
                val reqStart = System.currentTimeMillis()
                lastRequestTime = reqStart

                // 이미지 최적화 + 크기를 동시에 반환 (별도 디코딩 불필요)
                val (optimized, w, h) = optimizeImageForUpload(imageFile)
                sentImgW = w.coerceAtLeast(1)
                sentImgH = h.coerceAtLeast(1)

                val body = MultipartBody.Builder().setType(MultipartBody.FORM)
                    .addFormDataPart("image", "frame.jpg",
                        optimized.asRequestBody("image/jpeg".toMediaType()))
                    .addFormDataPart("camera_orientation", cameraOrientation)
                    .addFormDataPart("wifi_ssid", getWifiSsid())
                    .addFormDataPart("mode", currentMode)
                    .addFormDataPart("query_text", findTarget)
                    .addFormDataPart("lat", currentLat.toString())
                    .addFormDataPart("lng", currentLng.toString())
                    .build()

                val response = httpClient.newCall(
                    Request.Builder().url("$serverUrl/detect").post(body).build()
                ).execute()

                // 전체 왕복 시간 = 네트워크 + 서버 처리
                val roundTripMs = System.currentTimeMillis() - reqStart
                val json        = JSONObject(response.body?.string() ?: "{}")
                val sentence    = json.optString("sentence", "주변에 장애물이 없어요.")
                val alertMode   = json.optString("alert_mode", "critical")
                val processMs   = json.optInt("process_ms", -1)  // 서버 내부 처리 시간
                lastProcessMs   = processMs

                checkWaitingBus(json)

                // 서버 탐지 결과로 바운딩박스 즉시 갱신 — 화면에서 물체 사라지면 박스도 제거
                val serverObjs = json.optJSONArray("objects")
                val detections = mutableListOf<Detection>()
                if (serverObjs != null && sentImgW > 0 && sentImgH > 0) {
                    for (i in 0 until serverObjs.length()) {
                        val obj  = serverObjs.getJSONObject(i)
                        val bbox = obj.optJSONArray("bbox") ?: continue
                        if (bbox.length() < 4) continue
                        val x1 = bbox.optDouble(0).toFloat()
                        val y1 = bbox.optDouble(1).toFloat()
                        val x2 = bbox.optDouble(2).toFloat()
                        val y2 = bbox.optDouble(3).toFloat()
                        detections.add(Detection(
                            classKo    = obj.optString("class_ko", "물체"),
                            confidence = obj.optDouble("conf", 0.5).toFloat(),
                            cx = ((x1 + x2) / 2f) / sentImgW,
                            cy = ((y1 + y2) / 2f) / sentImgH,
                            w  = (x2 - x1).coerceAtLeast(1f) / sentImgW,
                            h  = (y2 - y1).coerceAtLeast(1f) / sentImgH
                        ))
                    }
                }
                runOnUiThread {
                    if (detections.isEmpty()) boundingBoxOverlay.clearDetections()
                    else boundingBoxOverlay.setDetections(detections, sentImgW, sentImgH)
                }

                // FPS + 처리시간 UI 업데이트
                val netMs = if (processMs > 0) roundTripMs - processMs else roundTripMs
                android.util.Log.d("VG_PERF",
                    "mode|server|server_ms|$processMs|net_ms|$netMs|total|$roundTripMs")
                android.util.Log.d("VG_SERVER",
                    "OK url=$serverUrl | mode=$currentMode | sentence=\"$sentence\" | alert=$alertMode")
                runOnUiThread {
                    val fps   = calcFps()
                    val spark = buildSparkline()
                    val serverTag = if (processMs > 0) "☁ ${processMs}ms" else "☁ ${roundTripMs}ms"
                    lastFpsText = "${fps}fps $spark | $serverTag"
                    tvMode.text = "[$currentMode] $lastFpsText"
                    if (debugVisible) {
                        val tv = findViewById<android.widget.TextView>(R.id.tvDebug)
                        tv.text = "FPS      : ${fps}\n" +
                                  "서버처리 : ${if (processMs > 0) "${processMs}ms" else "-"}\n" +
                                  "네트워크 : ${netMs}ms\n" +
                                  "전체왕복 : ${roundTripMs}ms"
                    }
                }

                // CSV 성능 로그 (CSV_LOG_ENABLED=true 시 활성화)
                if (CSV_LOG_ENABLED) {
                    try {
                        val fps = currentFps
                        val line = "${System.currentTimeMillis()},fps=$fps," +
                            "total=${roundTripMs}ms,server=${processMs}ms,net=${netMs}ms\n"
                        java.io.File(getExternalFilesDir(null), "vg_perf.csv").appendText(line)
                    } catch (_: Exception) {}
                }

                handleSuccess(sentence, alertMode)
            } catch (e: Exception) {
                android.util.Log.e("VG_SERVER", "FAIL url=$serverUrl | ${e.javaClass.simpleName}: ${e.message}")
                handleFail()
            } finally {
                imageFile.delete()
                isSending.set(false)  // 예외로 handleFail 미호출 시 안전망
            }
        }.start()
    }

    // ── 결과 처리 & Failsafe ────────────────────────────────────────────

    private fun checkWaitingBus(json: org.json.JSONObject) {
        if (waitingBusNumber.isEmpty()) return
        val objects = json.optJSONArray("objects") ?: return
        for (i in 0 until objects.length()) {
            val obj = objects.getJSONObject(i)
            if (obj.optString("class") == "bus") {
                captureForBusNumber()
                return
            }
        }
    }

    private fun handleSuccess(sentence: String, alertMode: String = "critical") {
        consecutiveFails.set(0)
        lastSuccessTime = System.currentTimeMillis()
        isSending.set(false)
        if (!isAnalyzing.get()) return  // 분석 중지 후 in-flight 요청 결과 무시

        // 질문 응답 직후 periodic TTS 억제 — critical은 항상 통과
        val effectiveMode = if (alertMode != "critical" &&
            System.currentTimeMillis() < suppressPeriodicUntil) "silent" else alertMode

        runOnUiThread {
            if (sentence == "주변에 장애물이 없어요.") {
                // 마지막 탐지 후 6초 지난 경우에만 "장애물 없음"으로 교체
                // (투표 버퍼 재확정 시간 + 여유 고려)
                if (System.currentTimeMillis() - lastDetectionTime > 6000) {
                    tvStatus.text = "장애물 없음"
                }
                return@runOnUiThread
            }
            lastDetectionTime = System.currentTimeMillis()
            // tvStatus는 실제 발화/비프 시점에만 업데이트 — 텍스트·목소리 동기화
            when (effectiveMode) {
                "critical" -> {
                    val now = System.currentTimeMillis()
                    if (sentence != lastSentence || now - lastCriticalTime > 5000L) {
                        val isVehicleDanger = ALWAYS_PASS.any { sentence.contains(it) }
                        // 차량·계단 긴급이 아닌 경우 TTS 재생 중이면 끊지 않음
                        if (!isVehicleDanger && isSpeaking()) return@runOnUiThread
                        lastSentence     = sentence
                        lastCriticalTime = now
                        tvStatus.text    = sentence
                        tts.setSpeechRate(1.25f)
                        if (isVehicleDanger) {
                            speakBuiltIn(sentence, immediate = true)
                        } else {
                            speak(sentence)
                        }
                    }
                }
                "beep" -> {
                    // 사용자 인터뷰 Q11: "비프음보다 말로 설명하는 것이 편함"
                    // → 비프음 대신 거리 정보 포함 음성으로 전달 (lastSentence dedup 적용)
                    if (sentence != lastSentence && !isSpeaking()) {
                        lastSentence  = sentence
                        tvStatus.text = sentence
                        tts.setSpeechRate(1.0f)
                        speak(sentence)
                    }
                }
                "silent" -> { /* 무음 — 텍스트도 유지 */ }
                else -> {
                    if (sentence != lastSentence && !isSpeaking()) {
                        lastSentence  = sentence
                        tvStatus.text = sentence
                        tts.setSpeechRate(1.1f)
                        speak(sentence)
                    }
                }
            }
        }
    }

    private fun handleFail() {
        isSending.set(false)
        val fails = consecutiveFails.incrementAndGet()
        if (fails == FAIL_WARN_COUNT) {
            runOnUiThread {
                tvStatus.text = "⚠ 분석 실패 — 주의하세요"
                if (!isSpeaking()) speak("분석에 문제가 생겼어요. 주의해서 이동하세요.")
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
        // STT 중이면 먼저 취소하고 TTS 재생
        if (isListening) {
            try { speechRecognizer.cancel() } catch (_: Exception) {}
            isListening = false
        }
        speakBuiltIn(text)
    }

    private fun speakBuiltIn(text: String, immediate: Boolean = false) {
        if (!immediate && !ttsBusy.compareAndSet(false, true)) return  // 이미 재생 중 → 버림
        if (immediate) ttsBusy.set(true)  // 차량 긴급 — 강제 획득
        val params = Bundle()
        params.putInt(TextToSpeech.Engine.KEY_PARAM_STREAM, AudioManager.STREAM_MUSIC)
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, params, "vg")
    }

    private fun speakElevenLabs(text: String, serverUrl: String) {
        currentMediaPlayer?.let { try { if (it.isPlaying) it.stop(); it.release() } catch (_: Exception) {} }
        currentMediaPlayer = null
        isElevenLabsSpeaking = true
        val myId = ttsRequestId.incrementAndGet()
        ttsExecutor.execute {
            try {
                val body = okhttp3.FormBody.Builder().add("text", text).build()
                val req = okhttp3.Request.Builder().url("$serverUrl/tts").post(body).build()
                val resp = httpClient.newCall(req).execute()
                if (ttsRequestId.get() != myId) { isElevenLabsSpeaking = false; return@execute }
                if (!resp.isSuccessful) { isElevenLabsSpeaking = false; handler.post { speakBuiltIn(text) }; return@execute }
                val tmpFile = File(cacheDir, "tts_$myId.mp3")
                tmpFile.writeBytes(resp.body!!.bytes())
                if (ttsRequestId.get() != myId) { isElevenLabsSpeaking = false; tmpFile.delete(); return@execute }
                val mp = android.media.MediaPlayer()
                mp.setDataSource(tmpFile.absolutePath)
                mp.setAudioAttributes(android.media.AudioAttributes.Builder()
                    .setUsage(android.media.AudioAttributes.USAGE_MEDIA).build())
                mp.prepare()
                mp.setOnCompletionListener {
                    isElevenLabsSpeaking = false
                    tmpFile.delete()
                    it.release()
                    handler.post { scheduleAutoListen() }
                }
                currentMediaPlayer = mp
                mp.start()
            } catch (_: Exception) {
                isElevenLabsSpeaking = false
                if (ttsRequestId.get() == myId) handler.post { speakBuiltIn(text) }
            }
        }
    }

    private fun isSpeaking(): Boolean = ttsBusy.get() || isElevenLabsSpeaking

    /** 직전 프레임과의 시간 간격으로 FPS 계산 + 스파크라인 업데이트 */
    private fun calcFps(): String {
        val now = System.currentTimeMillis()
        val fps = if (lastFrameDoneTime > 0L && now > lastFrameDoneTime) {
            1000.0f / (now - lastFrameDoneTime)
        } else 0.0f
        lastFrameDoneTime = now
        currentFps = fps

        // 최근 10프레임 FPS 기록
        if (fpsHistory.size >= 10) fpsHistory.removeFirst()
        fpsHistory.addLast(fps)

        val fpsStr = if (fps >= 10f) "%.0f".format(fps) else "%.1f".format(fps)
        return fpsStr
    }

    /** FPS 히스토리를 Unicode 블록 문자 스파크라인으로 변환 */
    private fun buildSparkline(): String {
        if (fpsHistory.isEmpty()) return ""
        val maxFps = fpsHistory.max().coerceAtLeast(1f)
        return fpsHistory.joinToString("") { fps ->
            val idx = ((fps / maxFps) * 7).toInt().coerceIn(0, 7)
            SPARK[idx]
        }
    }

    override fun onInit(status: Int) {
        if (status == TextToSpeech.SUCCESS) {
            tts.setLanguage(Locale.KOREAN)
            tts.setSpeechRate(1.1f)
            // TTS 종료 후 700ms 침묵 — 말 끝나자마자 다음 말 시작 방지
            tts.setOnUtteranceProgressListener(object : android.speech.tts.UtteranceProgressListener() {
                override fun onStart(uid: String?) {}
                override fun onDone(uid: String?) {
                    speakCooldownUntil = System.currentTimeMillis() + 700L
                    handler.postDelayed({
                        ttsBusy.set(false)
                        scheduleAutoListen()
                    }, 700)
                }
                @Deprecated("Deprecated in Java")
                override fun onError(uid: String?) {}
            })
            handler.postDelayed({ promptAutoStart() }, 1000)
        }
    }

    private fun promptAutoStart() {
        awaitingStartConfirm = true
        speakBuiltIn("음성 안내를 시작할까요? 네 또는 아니오로 말씀해주세요.")
        handler.post(object : Runnable {
            override fun run() {
                if (tts.isSpeaking) {
                    handler.postDelayed(this, 200)
                } else {
                    handler.postDelayed({ if (awaitingStartConfirm) startListening() }, 600)
                }
            }
        })
    }

    override fun onRequestPermissionsResult(
        requestCode: Int, permissions: Array<out String>, grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        when (requestCode) {
            PERM_CODE -> if (grantResults.all { it == PackageManager.PERMISSION_GRANTED }) startCamera()
            PERM_CODE_LOCATION -> {
                if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) {
                    locationPermissionCallback?.invoke()
                } else {
                    speak("위치 권한이 없어요. 설정에서 허용해 주세요.")
                }
                locationPermissionCallback = null
            }
            PERM_CODE_SMS -> {
                if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) {
                    smsPermissionCallback?.invoke()
                } else {
                    speak("SMS 권한이 없어요. SOS 기능이 제한됩니다.")
                }
                smsPermissionCallback = null
            }
        }
    }
}