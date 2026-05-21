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
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
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
 *   - TFLite 온디바이스 추론 (서버 없이 폰 단독 동작)
 *   - 서버 연동 시 온디바이스 탐지 결과 JSON 동기화
 *   - STT로 음성 명령 인식 (11가지 모드)
 *   - TTS로 한국어 음성 안내
 *   - 위험도 낮은 알림은 비프음으로만 (경고 피로 방지)
 *   - 조도 센서로 어두운 환경 감지
 *   - 앱 시작 시 음성으로 자동 시작 확인
 *
 * 전체 흐름:
 *   onCreate → TTS 초기화 → "시작할까요?" 음성 → "네" → 카메라 권한 요청
 *   → 카메라 시작 → 1초마다 캡처 → TFLite 온디바이스 추론 → TTS 안내
 */
class MainActivity : AppCompatActivity(), TextToSpeech.OnInitListener, SensorEventListener {

    // ── UI 뷰 참조 ─────────────────────────────────────────────────────
    private lateinit var tts: TextToSpeech
    private var toneGen: ToneGenerator? = null
    private lateinit var tvStatus: TextView      // 현재 안내 문장 표시
    private lateinit var tvDetected: TextView    // 탐지된 물체 목록 표시
    private lateinit var tvMode: TextView        // 현재 모드 + 카메라 방향 표시
    private lateinit var btnToggle: Button       // 분석 시작/중지
    private lateinit var btnStt: Button          // 음성 명령 버튼
    private lateinit var previewView: PreviewView // 카메라 라이브 프리뷰
    private lateinit var boundingBoxOverlay: BoundingBoxOverlay // 디버그 바운드박스 오버레이

    // ── 카메라 & 분석 루프 ─────────────────────────────────────────────
    private var imageCapture: ImageCapture? = null
    private var imageAnalysis: ImageAnalysis? = null
    private var lastStreamFrameTime = 0L
    private var lastStreamSkipLogTime = 0L
    @Volatile private var pendingImmediateMode: String? = null
    @Volatile private var temporaryDisplayMode: String? = null
    @Volatile private var temporaryDisplayModeUntil = 0L
    // newSingleThreadExecutor: 카메라 캡처를 UI 스레드와 분리 (UI 멈춤 방지)
    private val cameraExecutor = Executors.newSingleThreadExecutor()
    private val perfLogExecutor = Executors.newSingleThreadExecutor()
    // Handler: 메인 스레드에서 지연 작업 예약 (1초 간격 루프, Watchdog)
    private val handler = Handler(Looper.getMainLooper())
    // AtomicBoolean: 여러 스레드가 동시에 접근해도 안전한 boolean
    private val isAnalyzing  = AtomicBoolean(false)
    private val inFlightCount = AtomicInteger(0)  // 동시 분석/서버 요청 수
    // 카메라 바인딩 완료 여부 — true면 재시작 시 unbindAll() 없이 startAnalysis()만 호출
    private var isCameraReady = false
    private var lastSentence = ""
    // TTS 완전 잠금 — compareAndSet으로만 시작 가능, onDone 후 해제
    private val ttsBusy        = AtomicBoolean(false)
    private val frameSeq       = AtomicInteger(0)
    private val lastAppliedSeq = AtomicInteger(0)  // 마지막으로 UI에 반영한 응답 seq

    // ── 온디바이스 투표(Voting) 버퍼 ─────────────────────────────────────
    // 최근 5프레임 탐지 결과를 기록해 3회 이상 등장한 사물만 안내
    // → 순간 오탐(인형·노트북 등)이 단발로 잡혀도 TTS 안내 안 됨
    private val detectionHistory = ArrayDeque<Set<String>>()
    private val VOTE_WINDOW    = 3
    private val VOTE_MIN_COUNT = 2
    @Volatile private var lastMvpUpdateTime = 0L
    @Volatile private var lastMvpSignature = ""

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
            d.classKo in VoicePolicy.voteBypassKo() || (counts[d.classKo] ?: 0) >= VOTE_MIN_COUNT
        }
    }

    private fun shouldRunMvpUpdate(mode: String, overrideMode: String?, now: Long): Boolean {
        if (overrideMode != null || mode == "질문" || mode == "들고있는것") return true
        if (lastMvpUpdateTime == 0L || now - lastMvpUpdateTime >= MVP_UPDATE_INTERVAL_MS) {
            lastMvpUpdateTime = now
            return true
        }
        return false
    }

    private fun buildMvpSignature(detections: List<Detection>, mode: String): String {
        if (detections.isEmpty()) return "$mode:$findTarget:empty"
        return detections.take(3).joinToString(
            separator = "|",
            prefix = "$mode:$findTarget:"
        ) { d ->
            val xBucket = (d.cx * 8f).toInt()
            val yBucket = (d.cy * 8f).toInt()
            val areaBucket = (d.w * d.h * 20f).toInt()
            "${d.classKo}:$xBucket:$yBucket:$areaBucket"
        }
    }

    private fun consumeMvpChange(signature: String, force: Boolean): Boolean {
        if (!force && signature == lastMvpSignature) return false
        lastMvpSignature = signature
        return true
    }

    /**
     * 거리 기반 분류.
     *
     * 가까이(bbox 8%+) → voice  (음성 안내 — 같은 클래스는 쿨다운 후 재안내)
     * 멀리 있음        → beep   (있다는 것만 인지)
     * 위험 사물        → 항상 voice
     *
     * 경고 피로는 CLASS_COOLDOWN_MS + lastSentence 비교로 자연스럽게 방지됨.
     */
    private fun classify(voted: List<Detection>): Pair<List<Detection>, Boolean> {
        val voice = mutableListOf<Detection>()
        var shouldBeep = false
        val now = System.currentTimeMillis()
        for (d in voted) {
            val isClose = d.classKo in VoicePolicy.voteBypassKo() || d.w * d.h > BEEP_AREA_THRESH
            val lastSpokenAt = classLastSpoken[d.classKo] ?: 0L
            val recentlySpoken = now - lastSpokenAt < CLASS_COOLDOWN_MS
            if (isClose && !recentlySpoken) voice.add(d) else if (!isClose) shouldBeep = true
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

    private fun compactForServer(detections: List<Detection>): List<Detection> {
        return detections
            .filter { it.confidence >= SERVER_CONFIDENCE_MIN || it.classKo in VoicePolicy.voteBypassKo() }
            .sortedWith(compareByDescending<Detection> { if (it.classKo in VoicePolicy.voteBypassKo()) 1 else 0 }
                .thenByDescending { it.w * it.h }
                .thenByDescending { it.confidence })
            .take(SERVER_OBJECT_LIMIT)
    }

    private fun detectionUploadSignature(detections: List<Detection>): String {
        return detections.joinToString("|") { d ->
            val areaBucket = ((d.w * d.h) * 100f).toInt()
            val xBucket = (d.cx * 10f).toInt()
            "${d.classKo}:$xBucket:$areaBucket"
        }
    }

    private fun shouldUploadDetectionJson(detections: List<Detection>, mode: String): Boolean {
        val now = System.currentTimeMillis()
        val signature = detectionUploadSignature(detections)
        if (mode == "질문" || mode == "찾기" || mode == "들고있는것" ||
            frameSeq.get() % SERVER_FORCE_SEND_FRAMES == 0) {
            lastDetectionUploadSignature = signature
            lastDetectionUploadTime = now
            return true
        }
        if (now - lastDetectionUploadTime < SERVER_UPLOAD_INTERVAL_MS) return false

        if (signature == lastDetectionUploadSignature) return false

        lastDetectionUploadSignature = signature
        lastDetectionUploadTime = now
        return true
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
    private val perfLogFile: File by lazy {
        File(getExternalFilesDir("perf") ?: File(filesDir, "perf"), "voiceguide_perf.csv")
    }

    // ── HTTP 클라이언트 (서버 연동 — 선택 사항) ────────────────────────
    // connectTimeout: 서버 연결 최대 대기 5초
    // readTimeout: 서버 응답 최대 대기 8초 (JSON 저장/대시보드 갱신 시간 고려)
    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(8, TimeUnit.SECONDS)
        .build()
    // AtomicInteger: 연속 실패 횟수 (3회 이상이면 경고 음성)
    private val consecutiveFails = AtomicInteger(0)
    private var lastSuccessTime  = System.currentTimeMillis()
    private var lastDetectionTime  = 0L   // 마지막으로 실제 장애물이 탐지된 시간
    private var lastCriticalTime   = 0L   // 마지막 critical TTS 발화 시간 (5초 쿨다운)
    private var lastBeepTime       = 0L   // 마지막 beep TTS 발화 시간 (10초 쿨다운)
    @Volatile private var speakCooldownUntil = 0L  // TTS 종료 후 700ms 쉬어가기

    // ── 가속도 센서: 카메라 방향 자동 감지 ────────────────────────────
    private lateinit var sensorManager: SensorManager
    // @Volatile: 여러 스레드에서 읽을 때 최신값 보장
    @Volatile private var cameraOrientation = "front"  // front/back/left/right

    // ── STT 음성 명령 ──────────────────────────────────────────────────
    private lateinit var speechRecognizer: SpeechRecognizer
    @Volatile private var currentMode = "일반"  // 현재 활성 모드
    @Volatile private var findTarget  = ""        // 찾기 모드에서 탐색할 물체 이름
    private var sttStartTime = 0L                 // STT 시작 시각 (지연 측정용)
    @Volatile private var waitingBusNumber: String = ""  // 버스 대기 모드에서 기다리는 버스 번호

    // ── 조도 센서 (빛 감지) ────────────────────────────────────────────
    @Volatile private var lastLux = 100f  // 이전 프레임 밝기 (lux 단위)
    // ── 음성 자동 시작 ─────────────────────────────────────────────────
    private var awaitingStartConfirm = false
    @Volatile private var isListening = false      // STT 활성 중 → TTS 차단
    @Volatile private var autoListenEnabled = false // TTS 끝나면 자동 재청취
    @Volatile private var pendingStartupCommand: String? = null

    @Volatile private var pendingStatusText = ""  // TTS 재생 시작 시점에 tvStatus 동기화

    // ── 특정 버스 대기 ──────────────────────────────────────────────────

    // ── 낙상 감지 ────────────────────────────────────────────────────────
    @Volatile private var lastAccelTotal = 9.8f  // 직전 가속도 크기
    private var fallCheckJob: java.util.Timer? = null

    // ── 약 복용 알림 ─────────────────────────────────────────────────────
    // 약 복용 알림 타이머: 사용자가 "약 알림 설정해줘"라고 말하면 30분 후 알림
    private var medicineReminderJob: java.util.Timer? = null
    @Volatile private var medicineReminderMinutes = 30  // 기본 30분 후 알림
    // ── GPS 현재 위치 (서버 /detect 전송용) ──────────────────────────────────
    @Volatile private var currentLat = 0.0  // 현재 GPS 위도 (서버 /detect 전송용)
    @Volatile private var currentLng = 0.0  // 현재 GPS 경도
    @Volatile private var lastGpsSentTime = 0L
    @Volatile private var lastDetectionUploadTime = 0L
    @Volatile private var lastDetectionUploadSignature = ""
    private var locationManager: android.location.LocationManager? = null
    private lateinit var fusedLocationClient: com.google.android.gms.location.FusedLocationProviderClient
    private val locationListener = android.location.LocationListener { loc ->
        updateCurrentLocation(loc, "listener:${loc.provider}")
    }

    // ── TFLite 온디바이스 추론 ─────────────────────────────────────────
    private var tfliteDetector: TfliteYoloDetector? = null
    private val mvpPipeline = MvpPipeline()

    companion object {
        private const val PERM_CODE          = 100  // 카메라 + 마이크 (앱 시작 시)
        private const val PERM_CODE_LOCATION = 101  // GPS — 위치 권한 요청 시
        private const val PREFS_NAME       = "voiceguide"  // SharedPreferences 이름
        private const val PREF_URL         = "server_url"  // 저장된 서버 URL 키
        private const val PREF_FORCE_ON_DEVICE = "force_on_device"  // 서버 URL이 있어도 온디바이스 우선
        private const val PREF_DEVICE_ID   = "device_id"   // 앱 설치별 대시보드 세션 ID
        private const val DEFAULT_SERVER_URL =
            "https://voiceguide-1063164560758.asia-northeast3.run.app"
        private const val PREF_LOCATIONS   = "saved_locations"  // 저장 장소 JSON 배열 키
        private const val INTERVAL_MS      = 50L           // 캡처 간격: 50ms — isSending 게이트가 실제 fps 제어
        private const val MAX_ON_DEVICE_IN_FLIGHT = 1      // TFLite 안정성 우선: 단일 in-flight
        private const val MAX_SERVER_IN_FLIGHT    = 4      // 서버 동시 요청 최대 수
        private const val SILENCE_WARN_MS  = 6000L         // 6초 무응답 시 Watchdog 경고
        private const val FAIL_WARN_COUNT  = 3             // 연속 3회 실패 시 경고
        private const val GPS_SEND_INTERVAL_MS = 3000L     // 대시보드 위치 갱신 최소 간격
        private const val ENABLE_ANDROID_GPS_UPLOAD = false // 데모·포트폴리오 기본값: 실제 사용자 위치 전송 금지
        private const val MVP_UPDATE_INTERVAL_MS = 750L    // vote/dedup/MVP/TTS/JSON 갱신 주기
        private const val SERVER_UPLOAD_INTERVAL_MS = 250L // 서버 JSON 최소 전송 간격
        private const val SERVER_FORCE_SEND_FRAMES = 5     // 변화가 없어도 N프레임마다 대시보드 갱신
        private const val SERVER_OBJECT_LIMIT = 5          // Android -> 서버 객체 수 상한
        private const val SERVER_CONFIDENCE_MIN = 0.45f    // 낮은 확신도 객체 전송 차단
        private const val CSV_LOG_ENABLED  = true          // 성능 CSV 로깅 (항상 활성화)
    }

    // ── 생명주기 ─────────────────────────────────────────────────────────

    @Suppress("DEPRECATION")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        VoicePolicy.init(applicationContext)

        tts = TextToSpeech(this, this)
        toneGen = ToneGenerator(AudioManager.STREAM_NOTIFICATION, 80)

        tvStatus    = findViewById(R.id.tvStatus)
        tvDetected  = findViewById(R.id.tvDetected)
        tvMode      = findViewById(R.id.tvMode)
        btnToggle   = findViewById(R.id.btnToggle)
        btnStt      = findViewById(R.id.btnStt)
        previewView         = findViewById(R.id.previewView)
        boundingBoxOverlay  = findViewById(R.id.boundingBoxOverlay)

        // 우상단 설정 아이콘 — 서버 URL 입력 + 디버그 모드 토글
        findViewById<android.widget.Button>(R.id.btnSettings).setOnClickListener {
            showSettingsDialog()
        }
        findViewById<android.widget.Button>(R.id.btnSettings).setOnLongClickListener {
            debugVisible = !debugVisible
            findViewById<android.widget.TextView>(R.id.tvDebug).visibility =
                if (debugVisible) android.view.View.VISIBLE else android.view.View.GONE
            android.widget.Toast.makeText(
                this,
                if (debugVisible) "디버그 모드 켜짐" else "디버그 모드 꺼짐",
                android.widget.Toast.LENGTH_SHORT
            ).show()
            true
        }

        sensorManager   = getSystemService(SENSOR_SERVICE) as SensorManager
        fusedLocationClient = com.google.android.gms.location.LocationServices
            .getFusedLocationProviderClient(this)
        initSpeechRecognizer()
        tryInitTfliteDetector()
        refreshPolicyFromServerAsync()

        // Google Assistant shortcut intent 처리
        when (intent?.action) {
            "com.voiceguide.ACTION_START" -> handler.postDelayed({ requestPermissions() }, 1500)
        }

        btnToggle.setOnClickListener {
            if (isAnalyzing.get()) stopAnalysis() else requestPermissions()
        }
        btnStt.setOnClickListener { startListening() }

        // Phase 7 — 롱프레스 진동 피드백: 저시력·시각장애인 사용자가 버튼 위치를 촉각으로 학습
        btnStt.setOnLongClickListener {
            val vib = getSystemService(VIBRATOR_SERVICE) as android.os.Vibrator
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
                // 두 번 짧게 진동 (50ms on, 50ms off, 50ms on) — "여기 음성 명령 버튼"
                vib.vibrate(android.os.VibrationEffect.createWaveform(
                    longArrayOf(0, 50, 50, 50), -1
                ))
            } else {
                @Suppress("DEPRECATION")
                vib.vibrate(longArrayOf(0, 50, 50, 50), -1)
            }
            speak("음성 명령 버튼입니다. 짧게 누르면 음성 인식이 시작됩니다.")
            true
        }
    }

    /** GET /api/policy — SSOT 갱신(실패 시 기존 캐시·기본값 유지). */
    private fun refreshPolicyFromServerAsync() {
        val base = getSavedServerUrl().trimEnd('/')
        if (base.isEmpty()) return
        Executors.newSingleThreadExecutor().execute {
            try {
                val req = Request.Builder().url("$base/api/policy").get().build()
                httpClient.newCall(req).execute().use { resp ->
                    if (!resp.isSuccessful) return@execute
                    val body = resp.body?.string() ?: return@execute
                    VoicePolicy.applyFromServerJson(applicationContext, body)
                    Log.d("VG_POLICY", "policy.json 동기화 완료")
                }
            } catch (e: Exception) {
                Log.d("VG_POLICY", "policy fetch skip: ${e.message}")
            }
        }
    }

    private fun getSavedServerUrl(): String {
        val saved = getSharedPreferences(PREFS_NAME, MODE_PRIVATE).getString(PREF_URL, "") ?: ""
        return saved.ifBlank { DEFAULT_SERVER_URL }
    }

    private fun getConfiguredServerUrl(): String {
        val saved = getSharedPreferences(PREFS_NAME, MODE_PRIVATE).getString(PREF_URL, "")?.trim() ?: ""
        return saved.ifBlank { DEFAULT_SERVER_URL }
    }

    private fun isForceOnDeviceEnabled(): Boolean =
        getSharedPreferences(PREFS_NAME, MODE_PRIVATE).getBoolean(PREF_FORCE_ON_DEVICE, false)

    private fun getDeviceSessionId(): String {
        val prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
        val saved = prefs.getString(PREF_DEVICE_ID, "") ?: ""
        if (saved.isNotBlank()) return saved
        val generated = "android-${java.util.UUID.randomUUID().toString().take(8)}"
        prefs.edit().putString(PREF_DEVICE_ID, generated).apply()
        return generated
    }

    private fun showSettingsDialog() {
        val ctx = this
        val layout = android.widget.LinearLayout(ctx).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setPadding(64, 32, 64, 16)
        }

        val etUrl = android.widget.EditText(ctx).apply {
            hint = "서버 URL (비우면 온디바이스 모드)"
            inputType = android.text.InputType.TYPE_TEXT_VARIATION_URI
            setText(getConfiguredServerUrl())
            setSingleLine(true)
        }
        val tvUrlLabel = android.widget.TextView(ctx).apply { text = "서버 URL" }

        val swDebug = android.widget.Switch(ctx).apply {
            text = "디버그 모드 (FPS / 추론속도)"
            isChecked = debugVisible
        }
        val swForceOnDevice = android.widget.Switch(ctx).apply {
            text = "온디바이스 우선"
            isChecked = isForceOnDeviceEnabled()
        }
        layout.addView(tvUrlLabel)
        layout.addView(etUrl)
        layout.addView(android.widget.Space(ctx).apply {
            minimumHeight = 32
        })
        layout.addView(swDebug)
        layout.addView(swForceOnDevice)

        try {
            androidx.appcompat.app.AlertDialog.Builder(ctx)
                .setTitle("설정")
                .setView(layout)
                .setPositiveButton("저장") { _, _ ->
                    val url = etUrl.text.toString().trim()
                    getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
                        .edit()
                        .putString(PREF_URL, url)
                        .putBoolean(PREF_FORCE_ON_DEVICE, swForceOnDevice.isChecked)
                        .apply()
                    debugVisible = swDebug.isChecked
                    val tvDebug = findViewById<android.widget.TextView>(R.id.tvDebug)
                    tvDebug.visibility = if (debugVisible) android.view.View.VISIBLE else android.view.View.GONE
                    android.widget.Toast.makeText(ctx, "설정을 저장했어요.", android.widget.Toast.LENGTH_SHORT).show()
                    refreshPolicyFromServerAsync()
                }
                .setNegativeButton("취소", null)
                .show()
        } catch (e: Exception) {
            Log.e("VG_SETTINGS", "Failed to show settings dialog", e)
            android.widget.Toast.makeText(ctx, "설정 창을 열 수 없어요: ${e.message}", android.widget.Toast.LENGTH_LONG).show()
        }
    }

    private fun recordPerfSample(
        requestId: String,
        detector: TfliteYoloDetector,
        fps: Float,
        preprocessMs: Long,
        inferMs: Long,
        postprocessMs: Long,
        totalMs: Long,
        endToEndMs: Long,
        rawObjects: Int,
        votedObjects: Int,
        mode: String
    ) {
        if (!CSV_LOG_ENABLED) return
        val sample = PerfSample(
            timestampMs = System.currentTimeMillis(),
            requestId = requestId,
            route = "on_device",
            model = detector.modelName,
            provider = detector.executionProvider,
            fps = fps,
            preprocessMs = preprocessMs,
            inferMs = inferMs,
            postprocessMs = postprocessMs,
            totalMs = totalMs,
            endToEndMs = endToEndMs,
            rawObjects = rawObjects,
            votedObjects = votedObjects,
            mode = mode
        )
        perfLogExecutor.execute {
            try {
                PerfCsvLogger.append(perfLogFile, sample)
            } catch (e: Exception) {
                Log.w("VG_PERF", "CSV logging failed: ${e.message}")
            }
        }
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
        tfliteDetector?.close()
        cameraExecutor.shutdown()     // 카메라 스레드 종료
        perfLogExecutor.shutdown()
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
            runOnUiThread { tvMode.text = "모드: ${displayMode(currentMode)}  |  방향: ${label[cameraOrientation]}" }
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
                        tvMode.text = "🎤 [${displayMode(currentMode)}] 듣는 중...${if (lastFpsText.isNotEmpty()) "  $lastFpsText" else ""}"
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
        tvMode.text = "🎤 [${displayMode(currentMode)}] 듣는 중...${if (lastFpsText.isNotEmpty()) "  $lastFpsText" else ""}"
        btnStt.backgroundTintList = android.content.res.ColorStateList.valueOf(0xFFDC2626.toInt())
        speechRecognizer.startListening(intent)
    }

    /** STT 결과 처리 — 이미지 분석 불필요 모드는 즉시 처리 */
    private fun handleSttResult(text: String) {
        isListening = false
        val sttElapsedMs = if (sttStartTime > 0L) System.currentTimeMillis() - sttStartTime else -1L
        val mode = classifyKeyword(text)
        Log.d("VG_STT", "STT result: \"$text\" → mode=$mode | elapsed=${sttElapsedMs}ms")
        runOnUiThread { tvMode.text = "모드: ${displayMode(mode)}  |  방향: 정면" }

        // 자동 시작 응답 처리
        if (awaitingStartConfirm) {
            awaitingStartConfirm = false
            if (text.contains("네") || text.contains("예") || text.contains("응")) {
                requestPermissions()
            } else if (mode != "unknown") {
                pendingStartupCommand = text
                requestPermissions()
            } else {
                speak("알겠어요. 분석 시작 버튼을 누르시면 시작돼요.")
            }
            return
        }

        when (mode) {
            "들고있는것" -> {
                holdDisplayMode("들고있는것")
                tvStatus.text = "확인 중..."
                captureAndProcessAsHeld()
            }
            // ── 핵심 버그 수정: 질문 모드 즉시 캡처 ──────────────────────────
            // 기존 문제: "지금 뭐 있어?" → else 분기 → "장애물 모드." 말하고 끝
            // 수정: 즉시 이미지 캡처 → 서버에 mode="질문" 전송 → tracker 상태 포함 응답
            "질문" -> {
                holdDisplayMode("질문")
                tvStatus.text = "확인 중..."
                captureAndProcessAsQuestion()
            }
            // ── 장애물 모드: 즉시 캡처 ───────────────────────────────────────
            "장애물" -> {
                currentMode = mode
                captureAndProcess()
            }
            // ── 찾기 모드 (확인 의도 통합) ────────────────────────────────────
            // target 있음 → "X 찾기 모드." 안내 후 주기적 캡처
            // target 없음 (이거 뭐야 등) → 안내음을 끼우지 않고 즉시 캡처
            "찾기" -> {
                findTarget  = SentenceBuilder.extractFindTarget(text)
                currentMode = "찾기"
                SentenceBuilder.clearStableClocks()
                if (findTarget.isEmpty()) {
                    tvStatus.text = "확인 중..."
                    captureAndProcess()
                } else {
                    speakBuiltIn("${findTarget} 찾기 모드.")
                }
            }
            "신호등" -> {
                speakBuiltIn("신호등을 확인할게요.")
                currentMode = "신호등"
                captureAndProcess()
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
                autoListenEnabled = true  // 중지 후에도 '다시 시작' 음성 명령을 받기 위해 STT 유지
                speak("분석을 잠깐 멈출게요. 다시 시작하려면 '다시 시작'이라고 말해주세요.")
            }
            "재시작" -> {
                if (!isAnalyzing.get()) {
                    speak("다시 시작할게요.")
                    handler.postDelayed({ requestPermissions() }, 800)
                } else speak("이미 분석 중이에요.")
            }
            "버스대기" -> {
                startBusWaiting(text)
            }
            "약알림" -> {
                scheduleMedicineReminder(text)
            }
            "unknown" -> speak("다시 말씀해 주세요.")
            else -> {
                currentMode = mode
                SentenceBuilder.clearStableClocks()
                speakBuiltIn("$mode 모드.")
            }
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
                if (!confirmed.get()) runOnUiThread {
                    speak("자동 응급 알림이 비활성화되어 있어요. 필요하면 직접 보호자에게 연락하세요.")
                }
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

    /**
     * STT 텍스트 → 모드 분류.
     * VoiceGuideConstants.kt의 STT_KEYWORDS 맵에서 순서대로 검색.
     * 매칭 없으면 "unknown" 반환 → handleSttResult에서 "다시 말씀해 주세요" 처리.
     */
    private fun classifyKeyword(text: String): String {
        val normalized = text.replace("\\s+".toRegex(), "").lowercase(Locale.KOREAN)
        if (listOf("이거뭐", "이게뭐", "이건뭐", "손에든", "손에뭐", "들고있는", "바로앞뭐")
                .any { normalized.contains(it) }) {
            return "들고있는것"
        }
        if (listOf("찾아", "어디있", "어딨", "어디야", "위치")
                .any { normalized.contains(it) }) {
            return "찾기"
        }
        if (listOf("지금뭐", "뭐가있", "주변", "상황", "앞에뭐")
                .any { normalized.contains(it) }) {
            return "질문"
        }
        if (listOf("멈춰", "그만", "중지", "스톱", "일시정지")
                .any { normalized.contains(it) }) {
            return "중지"
        }
        if (listOf("다시시작", "계속", "재시작")
                .any { normalized.contains(it) }) {
            return "재시작"
        }
        for ((mode, keywords) in STT_KEYWORDS) {
            if (keywords.any { text.contains(it) }) return mode
        }
        return "unknown"
    }

    // ── TFLite 온디바이스 추론 초기화 ──────────────────────────────────

    private fun tryInitTfliteDetector() {
        // 백그라운드 스레드에서 초기화 (모델 로딩이 느려서 UI 스레드에서 하면 앱 멈춤)
        Thread {
            try {
                tfliteDetector = TfliteYoloDetector(this)
                runOnUiThread {
                    tvStatus.text = "온디바이스 준비 완료 — 분석 시작을 누르세요"
                }
            } catch (e: Exception) {
                // assets에 yolo26n_float32.tflite가 없는 경우 → 온디바이스 추론 불가
                Log.e("VG_PERF", "YOLO detector init failed", e)
                runOnUiThread { tvStatus.text = "온디바이스 모델 없음 — assets 모델 파일을 확인하세요" }
            }
        }.start()
    }

    // ── 카메라 & 분석 루프 ──────────────────────────────────────────────

    // 권한 요청 콜백 저장 (비동기 결과 처리용)
    private var locationPermissionCallback: (() -> Unit)? = null

    /** 앱 시작 시 필수 권한만 요청: 카메라 + 마이크 */
    private fun requestPermissions() {
        val needed = mutableListOf<String>()
        if (!hasPerm(Manifest.permission.CAMERA))       needed.add(Manifest.permission.CAMERA)
        if (!hasPerm(Manifest.permission.RECORD_AUDIO)) needed.add(Manifest.permission.RECORD_AUDIO)
        if (needed.isEmpty()) {
            // 카메라가 이미 바인딩된 경우 재바인딩 없이 분석만 재개 → FPS 안정
            if (isCameraReady) startAnalysis() else startCamera()
        } else ActivityCompat.requestPermissions(this, needed.toTypedArray(), PERM_CODE)
    }

    /** 분석 시작 시 GPS 위치 업데이트 시작 */
    private fun startGpsUpdates() {
        if (!ENABLE_ANDROID_GPS_UPLOAD) {
            Log.d("VG_GPS", "Android GPS upload disabled; use tools/simulator.py for demo route")
            return
        }
        requestLocationPermission {
            try {
                val lm = getSystemService(Context.LOCATION_SERVICE) as android.location.LocationManager
                locationManager = lm
                if (!hasLocationPerm()) return@requestLocationPermission

                val providers = listOf(
                    android.location.LocationManager.GPS_PROVIDER,
                    android.location.LocationManager.NETWORK_PROVIDER
                ).filter { provider -> lm.isProviderEnabled(provider) }

                if (providers.isEmpty()) {
                    Log.w("VG_GPS", "no location provider available; trying fused location")
                }

                @Suppress("MissingPermission")
                providers.forEach { provider ->
                    lm.requestLocationUpdates(provider, 3000L, 0f, locationListener)
                    Log.d("VG_GPS", "requestLocationUpdates provider=$provider")
                }

                // 마지막 알려진 위치로 즉시 초기화 (GPS fix 전까지 사용)
                @Suppress("MissingPermission")
                val lastKnown = providers
                    .mapNotNull { provider -> lm.getLastKnownLocation(provider) }
                    .maxByOrNull { it.time }
                if (lastKnown != null) {
                    updateCurrentLocation(lastKnown, "lastKnown:${lastKnown.provider}")
                } else {
                    Log.w("VG_GPS", "last known location is null providers=$providers")
                }

                requestFusedLocation()
                Log.d("VG_GPS", "GPS updates started providers=$providers")
            } catch (e: Exception) {
                Log.e("VG_GPS", "startGpsUpdates failed", e)
            }
        }
    }

    private fun updateCurrentLocation(loc: android.location.Location, source: String) {
        if (loc.latitude == 0.0 && loc.longitude == 0.0) {
            Log.w("VG_GPS", "ignore zero location source=$source provider=${loc.provider}")
            return
        }
        currentLat = loc.latitude
        currentLng = loc.longitude
        Log.d(
            "VG_GPS",
            "source=$source provider=${loc.provider} lat=$currentLat lng=$currentLng accuracy=${loc.accuracy}"
        )
        sendGpsHeartbeat(source)
    }

    private fun requestFusedLocation() {
        if (!hasLocationPerm()) return
        @Suppress("MissingPermission")
        fusedLocationClient.lastLocation
            .addOnSuccessListener { loc ->
                if (loc != null) updateCurrentLocation(loc, "fusedLast")
                else Log.w("VG_GPS", "fused lastLocation is null")
            }
            .addOnFailureListener { e -> Log.e("VG_GPS", "fused lastLocation failed", e) }

        val priority = if (hasPerm(Manifest.permission.ACCESS_FINE_LOCATION)) {
            com.google.android.gms.location.Priority.PRIORITY_HIGH_ACCURACY
        } else {
            com.google.android.gms.location.Priority.PRIORITY_BALANCED_POWER_ACCURACY
        }
        val tokenSource = com.google.android.gms.tasks.CancellationTokenSource()
        @Suppress("MissingPermission")
        fusedLocationClient.getCurrentLocation(priority, tokenSource.token)
            .addOnSuccessListener { loc ->
                if (loc != null) updateCurrentLocation(loc, "fusedCurrent")
                else Log.w("VG_GPS", "fused currentLocation is null")
            }
            .addOnFailureListener { e -> Log.e("VG_GPS", "fused currentLocation failed", e) }
    }

    /** 분석 중지 시 GPS 위치 업데이트 중단 (배터리 절약) */
    private fun stopGpsUpdates() {
        try {
            locationManager?.removeUpdates(locationListener)
            Log.d("VG_GPS", "GPS updates stopped")
        } catch (_: Exception) {}
        locationManager = null
    }

    private fun sendGpsHeartbeat(source: String) {
        if (!ENABLE_ANDROID_GPS_UPLOAD) {
            Log.d("VG_GPS", "skip heartbeat source=$source disabled")
            return
        }
        if (!isAnalyzing.get()) return
        if (!hasValidLocation()) {
            Log.d("VG_GPS", "skip heartbeat source=$source empty location lat=$currentLat lng=$currentLng")
            return
        }

        val now = System.currentTimeMillis()
        if (now - lastGpsSentTime < GPS_SEND_INTERVAL_MS) return
        lastGpsSentTime = now

        val serverUrl = getSavedServerUrl().trimEnd('/')
        if (serverUrl.isEmpty() || !isNetworkAvailable()) {
            Log.d("VG_GPS", "skip heartbeat source=$source network=${isNetworkAvailable()} server=$serverUrl")
            return
        }

        val lat = currentLat
        val lng = currentLng
        val deviceId = getDeviceSessionId()
        val requestId = "gps-$now"
        Thread {
            try {
                val body = okhttp3.FormBody.Builder()
                    .add("wifi_ssid", getWifiSsid())
                    .add("device_id", deviceId)
                    .add("lat", lat.toString())
                    .add("lng", lng.toString())
                    .add("request_id", requestId)
                    .build()
                val response = httpClient.newCall(
                    Request.Builder().url("$serverUrl/gps").post(body).build()
                ).execute()
                Log.d(
                    "VG_GPS",
                    "heartbeat source=$source session=$deviceId request_id=$requestId status=${response.code} lat=$lat lng=$lng"
                )
                response.close()
            } catch (e: Exception) {
                Log.e("VG_GPS", "heartbeat failed source=$source request_id=$requestId", e)
            }
        }.start()
    }

    /** GPS 위치 권한 요청 */
    private fun requestLocationPermission(onGranted: () -> Unit) {
        if (hasLocationPerm()) { onGranted(); return }
        locationPermissionCallback = onGranted
        ActivityCompat.requestPermissions(this,
            arrayOf(
                Manifest.permission.ACCESS_FINE_LOCATION,
                Manifest.permission.ACCESS_COARSE_LOCATION
            ), PERM_CODE_LOCATION)
    }

    private fun hasPerm(p: String) =
        ContextCompat.checkSelfPermission(this, p) == PackageManager.PERMISSION_GRANTED

    private fun hasLocationPerm(): Boolean =
        hasPerm(Manifest.permission.ACCESS_FINE_LOCATION) ||
            hasPerm(Manifest.permission.ACCESS_COARSE_LOCATION)

    @Suppress("DEPRECATION")
    private fun startCamera() {
        val future = ProcessCameraProvider.getInstance(this)
        future.addListener({
            val provider = future.get()
            val preview  = Preview.Builder().build()
                .also { it.setSurfaceProvider(previewView.surfaceProvider) }
            imageCapture = ImageCapture.Builder()
                .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY).build()
            imageAnalysis = ImageAnalysis.Builder()
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
                .setTargetResolution(android.util.Size(640, 480))
                .build()
                .also { analysis ->
                    analysis.setAnalyzer(cameraExecutor) { imageProxy ->
                        analyzeStreamFrame(imageProxy)
                    }
                }
            try {
                provider.unbindAll()
                provider.bindToLifecycle(
                    this,
                    CameraSelector.DEFAULT_BACK_CAMERA,
                    preview,
                    imageCapture,
                    imageAnalysis
                )
                isCameraReady = true  // 바인딩 성공 — 다음 재시작부터 rebind 생략
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
        detectionHistory.clear()
        lastSentence = ""
        consecutiveFails.set(0)
        lastGpsSentTime = 0L
        lastSuccessTime = System.currentTimeMillis()
        lastStreamFrameTime = 0L   // 재시작 시 첫 프레임 즉시 처리 (초기 지연 방지)
        inFlightCount.set(0)       // stuck in-flight 요청 초기화 (카메라 재바인딩 없는 재시작 대비)
        btnToggle.text = "■ 분석 중지"
        btnToggle.backgroundTintList = android.content.res.ColorStateList.valueOf(0xFFDC2626.toInt())
        tvStatus.text  = "분석 중..."
        startGpsUpdates()
        scheduleWatchdog()
        val startupCommand = pendingStartupCommand
        if (startupCommand != null) {
            pendingStartupCommand = null
            handler.postDelayed({ handleSttResult(startupCommand) }, 300L)
        } else {
            scheduleAutoListen()
        }
    }

    private fun stopAnalysis() {
        isAnalyzing.set(false)
        autoListenEnabled = false
        handler.removeCallbacksAndMessages(null)
        stopGpsUpdates()
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

    private fun analyzeStreamFrame(imageProxy: ImageProxy) {
        var acquiredInFlight = false
        try {
            if (!isAnalyzing.get()) return
            checkRevisit()

            val now = System.currentTimeMillis()
            val immediateMode = pendingImmediateMode
            val forceImmediate = immediateMode != null
            if (!forceImmediate && now - lastStreamFrameTime < INTERVAL_MS) return
            val route = if (shouldUseOnDeviceDetector()) "on_device" else "unavailable"
            val maxInFlight = MAX_ON_DEVICE_IN_FLIGHT
            if (inFlightCount.getAndIncrement() >= maxInFlight) {
                inFlightCount.decrementAndGet()
                if (now - lastStreamSkipLogTime > 1000L) {
                    lastStreamSkipLogTime = now
                    Log.d("VG_FLOW", "stream frame skipped: route=$route inFlight=${inFlightCount.get()}/$maxInFlight")
                }
                return
            }
            acquiredInFlight = true
            if (forceImmediate) pendingImmediateMode = null
            lastStreamFrameTime = now

            val requestId = nextRequestId()
            val modeForFrame = immediateMode ?: currentMode
            Log.d("VG_FLOW", "request_id=$requestId route=$route mode=$modeForFrame stream=${imageProxy.width}x${imageProxy.height} format=${imageProxy.format} rotation=${imageProxy.imageInfo.rotationDegrees}")
            if (route == "on_device") processOnDevice(imageProxy, requestId, immediateMode, tFrameArrival = now)
            else {
                handleFail()
            }
        } catch (e: Exception) {
            Log.e("VG_FLOW", "stream analysis failed", e)
            if (acquiredInFlight) handleFail()
        } finally {
            imageProxy.close()
        }
    }

    private fun captureAndProcess() {
        if (requestImmediateStreamFrame(currentMode)) return
        // 일회성 STT 캡처: stream 요청이 진행 중이면 스킵 (중복 방지)
        if (inFlightCount.get() > 0) {
            Log.d("VG_FLOW", "capture skipped: inFlight=${inFlightCount.get()}")
            return
        }
        val file = File.createTempFile("vg_", ".jpg", cacheDir)
        imageCapture?.takePicture(
            ImageCapture.OutputFileOptions.Builder(file).build(),
            cameraExecutor,
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                    inFlightCount.incrementAndGet()
                    val requestId = nextRequestId()
                    val route = if (shouldUseOnDeviceDetector()) "on_device" else "unavailable"
                    Log.d("VG_FLOW", "request_id=$requestId route=$route mode=$currentMode file=${file.length()}B")
                    if (route == "on_device") processOnDevice(file, requestId)
                    else {
                        file.delete()
                        handleFail()
                    }
                }
                override fun onError(e: ImageCaptureException) {
                    Log.e("VG_FLOW", "capture failed", e)
                    handleFail()
                }
            })
    }

    private fun nextRequestId(): String =
        "and-${System.currentTimeMillis()}-${frameSeq.incrementAndGet()}"

    private fun shouldUseOnDeviceDetector(): Boolean {
        if (tfliteDetector == null) return false
        if (isForceOnDeviceEnabled()) return true
        return true
    }

    private fun rejectServerInferenceFallback(imageFile: File, requestId: String) {
        Log.w("VG_FLOW", "request_id=$requestId server image inference disabled; waiting for on-device detector")
        imageFile.delete()
        handleFail()
    }

    private fun isNetworkAvailable(): Boolean {
        val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as android.net.ConnectivityManager
        val network = cm.activeNetwork ?: return false
        val caps = cm.getNetworkCapabilities(network) ?: return false
        return caps.hasCapability(android.net.NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    private fun isServerFallbackAvailable(): Boolean =
        isNetworkAvailable() && getConfiguredServerUrl().isNotBlank()

    private fun hasValidLocation(): Boolean =
        ENABLE_ANDROID_GPS_UPLOAD && (currentLat != 0.0 || currentLng != 0.0)

    /**
     * 질문 모드 전용 즉시 캡처.
     * 온디바이스로 탐지한 뒤 JSON을 서버에 전송하고, 서버가 없으면 로컬 안내를 사용한다.
     */
    private fun captureAndProcessAsQuestion() {
        if (requestImmediateStreamFrame("질문")) return
        val file = File.createTempFile("vg_q_", ".jpg", cacheDir)
        imageCapture?.takePicture(
            ImageCapture.OutputFileOptions.Builder(file).build(),
            cameraExecutor,
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                    inFlightCount.incrementAndGet()
                    processOnDevice(file, nextRequestId(), "질문")
                }
                override fun onError(e: ImageCaptureException) {
                    file.delete()
                    speak("사진을 찍지 못했어요.")
                }
            })
    }

    /**
     * 들고있는것 모드 전용 즉시 캡처.
     * 서버에 mode="들고있는것" 전송 → 가장 가까운 물건 기준 응답을 받음.
     */
    private fun captureAndProcessAsHeld() {
        if (requestImmediateStreamFrame("들고있는것")) return
        val file = File.createTempFile("vg_h_", ".jpg", cacheDir)
        imageCapture?.takePicture(
            ImageCapture.OutputFileOptions.Builder(file).build(),
            cameraExecutor,
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                    val requestId = nextRequestId()
                    inFlightCount.incrementAndGet()
                    processOnDevice(file, requestId, "들고있는것")
                }
                override fun onError(e: ImageCaptureException) {
                    file.delete()
                    speak("사진을 찍지 못했어요.")
                }
            })
    }

    private fun requestImmediateStreamFrame(mode: String): Boolean {
        if (!isAnalyzing.get() || imageAnalysis == null || !shouldUseOnDeviceDetector()) return false
        pendingImmediateMode = mode
        lastStreamFrameTime = 0L
        Log.d("VG_FLOW", "request immediate stream frame mode=$mode")
        return true
    }

    private fun displayMode(mode: String): String = when (mode) {
        "들고있는것" -> "물건 확인"
        "질문" -> "주변 확인"
        "일반" -> "일반 안내"
        else -> mode
    }

    private fun holdDisplayMode(mode: String, durationMs: Long = 2500L) {
        temporaryDisplayMode = mode
        temporaryDisplayModeUntil = System.currentTimeMillis() + durationMs
    }

    private fun visibleDisplayMode(mode: String): String {
        val temporary = temporaryDisplayMode
        return if (temporary != null && System.currentTimeMillis() < temporaryDisplayModeUntil) {
            displayMode(temporary)
        } else {
            temporaryDisplayMode = null
            displayMode(mode)
        }
    }

    // ── 온디바이스 추론 ─────────────────────────────────────────────────

    private fun processOnDevice(imageFile: File, requestId: String, overrideMode: String? = null) {
        processOnDeviceInternal(imageFile, null, requestId, 0L, overrideMode)
    }

    private fun processOnDevice(imageProxy: ImageProxy, requestId: String, overrideMode: String? = null, tFrameArrival: Long = 0L) {
        processOnDeviceInternal(null, imageProxy, requestId, 0L, overrideMode, tFrameArrival)
    }

    private fun processOnDeviceInternal(
        imageFile: File?,
        imageProxy: ImageProxy?,
        requestId: String,
        initialPreprocessMs: Long,
        overrideMode: String? = null,
        tFrameArrival: Long = 0L
    ) {
        val work = Runnable {
            var bmp: android.graphics.Bitmap? = null
            try {
                val effectiveMode = overrideMode ?: currentMode
                val tDecode = System.currentTimeMillis()
                val frameBitmap = if (imageProxy == null) {
                    decodeBitmapUpright(imageFile ?: throw IllegalStateException("missing image file"))
                } else {
                    null
                }
                bmp = frameBitmap
                val decodeMs = initialPreprocessMs + if (frameBitmap != null) {
                    System.currentTimeMillis() - tDecode
                } else {
                    0L
                }

                val rotation = imageProxy?.imageInfo?.rotationDegrees ?: 0
                val imgW = if (imageProxy != null) {
                    if (rotation % 180 == 0) imageProxy.width else imageProxy.height
                } else {
                    frameBitmap!!.width
                }
                val imgH = if (imageProxy != null) {
                    if (rotation % 180 == 0) imageProxy.height else imageProxy.width
                } else {
                    frameBitmap!!.height
                }

                val detector = tfliteDetector
                    ?: throw IllegalStateException("YOLO detector is not initialized")
                val detectorResult = if (imageProxy != null) {
                    detector.detect(imageProxy)
                } else {
                    detector.detect(frameBitmap!!)
                }
                val preprocessMs = decodeMs + detectorResult.preprocessMs
                val yoloDetections = detectorResult.detections
                val rawDetections = yoloDetections
                val inferMs = detectorResult.inferMs

                val now = System.currentTimeMillis()
                val shouldRunMvp = shouldRunMvpUpdate(effectiveMode, overrideMode, now)
                val tMvp = System.currentTimeMillis()
                val mvpFrame = if (shouldRunMvp) {
                    // YOLO postprocess(NMS)는 매 프레임, 안정화/vote/dedup/MVP는 주기적으로만 수행한다.
                    mvpPipeline.update(removeDuplicates(voteOnly(rawDetections)))
                } else {
                    null
                }
                val voted = mvpFrame?.detections ?: rawDetections
                // 버스 대기 모드: 탐지된 객체 중 버스가 있으면 알림
                if (waitingBusNumber.isNotEmpty()) checkBusArrival(voted)
                val mvpMs = if (shouldRunMvp) System.currentTimeMillis() - tMvp else 0L
                val dedupMs = detectorResult.postprocessMs + mvpMs

                val totalMs = preprocessMs + inferMs + dedupMs
                val e2eMs = if (tFrameArrival > 0L) System.currentTimeMillis() - tFrameArrival else -1L
                // 구조화 성능 로그 — Logcat에서 tag:VG_PERF 로 필터
                android.util.Log.d("VG_PERF",
                    "request_id|$requestId|route|on_device|model|${detector.modelName}|provider|${detector.executionProvider}|preprocess|$preprocessMs|infer|$inferMs|postprocess|$dedupMs|mvp|${if (shouldRunMvp) "run" else "skip"}|total|$totalMs|e2e|$e2eMs|objs|${voted.size}")

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
                    tvMode.text = "[${visibleDisplayMode(effectiveMode)}] $lastFpsText"
                    recordPerfSample(
                        requestId = requestId,
                        detector = detector,
                        fps = currentFps,
                        preprocessMs = preprocessMs,
                        inferMs = inferMs,
                        postprocessMs = dedupMs,
                        totalMs = totalMs,
                        endToEndMs = e2eMs,
                        rawObjects = rawDetections.size,
                        votedObjects = voted.size,
                        mode = effectiveMode
                    )
                    if (debugVisible) {
                        val tv = findViewById<android.widget.TextView>(R.id.tvDebug)
                        tv.text = "경로   : ${detector.executionProvider}\n" +
                                  "요청ID : ${requestId.takeLast(6)}\n" +
                                  "모델   : ${detector.modelName}\n" +
                                  "FPS    : ${fps}\n" +
                                  "전처리 : ${preprocessMs}ms\n" +
                                  "추론   : ${inferMs}ms\n" +
                                  "후처리 : ${dedupMs}ms\n" +
                                  "전체   : ${totalMs}ms\n" +
                                  "탐지수 : raw=${rawDetections.size} → ${voted.size}\n" +
                                  "CSV    : ${perfLogFile.name}"
                    }
                }

                bmp?.recycle(); bmp = null
                // imageFile은 finally에서 삭제 (catch의 서버 fallback이 먼저 파일 필요)

                Log.d("VG_DETECT", "=== 탐지 결과 ===")
                Log.d("VG_DETECT", "raw: ${rawDetections.size}개(yolo=${yoloDetections.size}) → dedup: ${voted.size}개")
                voted.forEachIndexed { i, d ->
                    Log.d("VG_DETECT", "  [$i] ${d.classKo} | conf=${String.format("%.2f", d.confidence)} | cx=${String.format("%.2f", d.cx)} | w=${String.format("%.2f", d.w)} h=${String.format("%.2f", d.h)} | area=${String.format("%.3f", d.w * d.h)}")
                }

                // 찾기 모드에서 대상 물체에 흰색 박스 표시
                val markedDetections = if (effectiveMode == "찾기" && findTarget.isNotEmpty()) {
                    voted.map { it.copy(isFound = it.classKo.contains(findTarget)) }
                } else voted
                runOnUiThread {
                    if (markedDetections.isEmpty()) {
                        boundingBoxOverlay.clearDetections()
                    } else {
                        boundingBoxOverlay.setDetections(markedDetections, imgW, imgH)
                    }
                }

                if (!shouldRunMvp) {
                    imageFile?.delete()
                    finishOnDeviceFrameWithoutNotification(requestId, "mvp_throttled")
                    return@Runnable
                }

                val stableMvpFrame = mvpFrame ?: throw IllegalStateException("missing MVP frame")
                val mvpSignature = buildMvpSignature(voted, effectiveMode)
                val mvpChanged = consumeMvpChange(mvpSignature, force = overrideMode != null)
                if (!mvpChanged) {
                    Log.d("VG_DETECT", "→ MVP unchanged; skip SentenceBuilder/TTS/vibration/server JSON")
                    imageFile?.delete()
                    finishOnDeviceFrameWithoutNotification(requestId, "mvp_unchanged")
                    return@Runnable
                }

                if (voted.isEmpty()) {
                    Log.d("VG_DETECT", "→ 장애물 없음")
                    imageFile?.delete()
                    handleSuccess("주변에 장애물이 없어요.", "silent")
                    return@Runnable
                }

                val (voiceDetections, shouldBeep) = classify(voted)

                // 문장은 안정화된 위험도 기준으로 정렬한다. 같은 위험도에서는 큰 물체를 먼저 안내한다.
                val sorted = voted.sortedWith(
                    compareByDescending<Detection> { it.riskScore }
                        .thenByDescending { it.w * it.h }
                )
                val sentence = when (effectiveMode) {
                    "찾기" -> SentenceBuilder.buildFind(findTarget, sorted)
                    "들고있는것" -> SentenceBuilder.buildHeld(sorted)
                    else  -> SentenceBuilder.build(sorted)
                }

                Log.d("VG_DETECT", "생성된 문장: \"$sentence\"")
                Log.d("VG_DETECT", "음성=${voiceDetections.size}개 | beep=$shouldBeep | mode=$effectiveMode")

                when {
                    effectiveMode == "들고있는것" -> {
                        Log.d("VG_DETECT", "→ 물건 확인 응답")
                        performVibrationFeedback(stableMvpFrame.vibrationPattern)
                        sendDetectionJsonToServer(
                            voted,
                            effectiveMode,
                            requestId,
                            imgW,
                            imgH,
                            preprocessMs,
                            inferMs,
                            dedupMs,
                            totalMs,
                            sentence,
                            "critical",
                            forceSpeak = true
                        )
                    }
                    voiceDetections.isNotEmpty() -> {
                        markClassesSpoken(voiceDetections)
                        val mode = when {
                            effectiveMode == "찾기"                              -> "critical"
                            voiceDetections.any { it.classKo in VoicePolicy.voteBypassKo() } -> "critical"
                            else                                               -> "normal"
                        }
                        Log.d("VG_DETECT", "→ 음성 출력 (mode=$mode)")
                        performVibrationFeedback(stableMvpFrame.vibrationPattern)
                        sendDetectionJsonToServer(voted, effectiveMode, requestId, imgW, imgH, preprocessMs, inferMs, dedupMs, totalMs, sentence, mode)
                    }
                    shouldBeep -> {
                        Log.d("VG_DETECT", "→ 비프음")
                        performVibrationFeedback(stableMvpFrame.vibrationPattern)
                        sendDetectionJsonToServer(voted, effectiveMode, requestId, imgW, imgH, preprocessMs, inferMs, dedupMs, totalMs, sentence, "beep")
                    }
                    else       -> {
                        Log.d("VG_DETECT", "→ 무음 (거리 멀거나 최근 안내 완료)")
                        sendDetectionJsonToServer(voted, effectiveMode, requestId, imgW, imgH, preprocessMs, inferMs, dedupMs, totalMs, sentence, "silent")
                    }
                }

                imageFile?.delete()
            } catch (e: Exception) {
                Log.e("VG_DETECT", "request_id=$requestId On-device detection failed", e)
                bmp?.recycle()
                imageFile?.delete()
                handleFail()
            }
        }
        if (imageProxy != null) work.run() else Thread(work).start()
    }

    private fun sendDetectionJsonToServer(
        detections: List<Detection>,
        mode: String,
        requestId: String,
        imgW: Int,
        imgH: Int,
        decodeMs: Long,
        inferMs: Long,
        dedupMs: Long,
        totalMs: Long,
        fallbackSentence: String,
        fallbackAlertMode: String,
        forceUpload: Boolean = true,
        forceSpeak: Boolean = false,
    ) {
        val serverUrl = getSavedServerUrl().trimEnd('/')
        if (serverUrl.isEmpty() || !isNetworkAvailable()) {
            handleSuccess(fallbackSentence, fallbackAlertMode, forceSpeak)
            return
        }

        try {
            val serverDetections = compactForServer(detections)
            if (!forceUpload && !shouldUploadDetectionJson(serverDetections, mode)) {
                Log.d("VG_LINK", "request_id=$requestId skip unchanged detection upload objects=${serverDetections.size}")
                handleSuccess(fallbackSentence, fallbackAlertMode, forceSpeak)
                return
            }
            if (forceUpload) {
                lastDetectionUploadSignature = detectionUploadSignature(serverDetections)
                lastDetectionUploadTime = System.currentTimeMillis()
            }

            handleSuccess(fallbackSentence, fallbackAlertMode, forceSpeak)
            Thread {
                uploadDetectionJson(
                    serverUrl = serverUrl,
                    detections = detections,
                    serverDetections = serverDetections,
                    mode = mode,
                    requestId = requestId,
                    imgW = imgW,
                    imgH = imgH,
                    decodeMs = decodeMs,
                    inferMs = inferMs,
                    dedupMs = dedupMs,
                    totalMs = totalMs,
                )
            }.start()
        } catch (e: Exception) {
            Log.e("VG_LINK", "request_id=$requestId detection JSON scheduling failed", e)
            handleSuccess(fallbackSentence, fallbackAlertMode, forceSpeak)
        }
    }

    private fun uploadDetectionJson(
        serverUrl: String,
        detections: List<Detection>,
        serverDetections: List<Detection>,
        mode: String,
        requestId: String,
        imgW: Int,
        imgH: Int,
        decodeMs: Long,
        inferMs: Long,
        dedupMs: Long,
        totalMs: Long,
    ) {
        try {

            val objects = JSONArray()
            serverDetections.forEach { d ->
                val x = (d.cx - d.w / 2f).coerceIn(0f, 1f)
                val y = (d.cy - d.h / 2f).coerceIn(0f, 1f)
                val w = d.w.coerceIn(0f, 1f)
                val h = d.h.coerceIn(0f, 1f)
                objects.put(JSONObject()
                    .put("class_ko", d.classKo)
                    .put("confidence", d.confidence.toDouble())
                    .put("cx", d.cx.toDouble())
                    .put("cy", d.cy.toDouble())
                    .put("w", d.w.toDouble())
                    .put("h", d.h.toDouble())
                    .put("bbox_norm_xywh", JSONArray(listOf(x, y, w, h)))
                    .put("distance_m", if (d.distanceM > 0f) d.distanceM.toDouble() else VoicePolicy.calcDistBboxM(d.classKo, d.w, d.h))
                    .put("risk_score", d.riskScore.toDouble())
                    .put("track_id", d.trackId)
                    .put("vibration_pattern", d.vibrationPattern)
                    .put("depth_source", "on_device_bbox"))
            }

            val payload = JSONObject()
                .put("event_id", requestId)
                .put("request_id", requestId)
                .put("device_id", getDeviceSessionId())
                .put("wifi_ssid", getWifiSsid())
                .put("mode", mode)
                .put("camera_orientation", cameraOrientation)
                .put("query_text", if (mode == "찾기") findTarget else "")
                .put("image_width", imgW)
                .put("image_height", imgH)
                .put("objects", objects)
                .put("hazards", JSONArray())
                .put("scene", JSONObject())
                .put("client_perf", JSONObject()
                    .put("decode_ms", decodeMs)
                    .put("infer_ms", inferMs)
                    .put("dedup_ms", dedupMs)
                    .put("total_ms", totalMs))
            if (hasValidLocation()) {
                payload.put("lat", currentLat)
                payload.put("lng", currentLng)
            }

            val reqStart = System.currentTimeMillis()
            val body = payload.toString().toRequestBody("application/json; charset=utf-8".toMediaType())
            val response = httpClient.newCall(
                Request.Builder().url("$serverUrl/detect").post(body).build()
            ).execute()
            val roundTripMs = System.currentTimeMillis() - reqStart
            sendGpsHeartbeat("detect-json")
            val json = JSONObject(response.body?.string() ?: "{}")
            val processMs = json.optInt("process_ms", -1)
            lastProcessMs = processMs
            Log.d("VG_LINK",
                "request_id=$requestId route=json status=${response.code} total=${roundTripMs}ms " +
                "server=${processMs}ms objects=${serverDetections.size}/${detections.size}")
        } catch (e: Exception) {
            Log.e("VG_LINK", "request_id=$requestId detection JSON upload failed", e)
        }
    }

    /** JPEG 파일의 EXIF 회전 태그를 읽어 실제 화면 방향으로 비트맵을 회전한다. */
    @Suppress("DEPRECATION")
    private fun performVibrationFeedback(pattern: VibrationPattern) {
        if (pattern == VibrationPattern.NONE) return
        val timings = when (pattern) {
            VibrationPattern.SHORT -> longArrayOf(0, 45)
            VibrationPattern.DOUBLE -> longArrayOf(0, 55, 65, 55)
            VibrationPattern.URGENT -> longArrayOf(0, 90, 60, 90, 60, 140)
            VibrationPattern.NONE -> return
        }
        val vibrator = getSystemService(VIBRATOR_SERVICE) as android.os.Vibrator
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
            vibrator.vibrate(android.os.VibrationEffect.createWaveform(timings, -1))
        } else {
            @Suppress("DEPRECATION")
            vibrator.vibrate(timings, -1)
        }
    }

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

    // ── 온디바이스 탐지 결과 JSON 전송 (새 아키텍처) ─────────────────────────

    /**
     * 온디바이스 추론 결과를 JSON으로 서버에 비동기 전송.
     * TTS 흐름을 차단하지 않도록 fire & forget 방식으로 실행.
     * 서버는 이미지 처리 없이 DB 저장 + tracker 업데이트만 수행.
     */
    private fun sendDetectionsJson(detections: List<Detection>, requestId: String) {
        val serverUrl = getConfiguredServerUrl().trimEnd('/').ifBlank { return }
        Thread {
            try {
                val body = org.json.JSONObject().apply {
                    put("device_id",   getDeviceSessionId())
                    put("session_id",  getDeviceSessionId())
                    put("wifi_ssid",   getWifiSsid())
                    put("request_id",  requestId)
                    put("mode",        currentMode)
                    put("camera_orientation", cameraOrientation)
                    if (hasValidLocation()) {
                        put("lat", currentLat)
                        put("lng", currentLng)
                    }
                    put("detections", org.json.JSONArray().also { arr ->
                        detections.forEach { d ->
                            arr.put(org.json.JSONObject().apply {
                                put("class_ko",   d.classKo)
                                put("confidence", d.confidence.toDouble())
                                put("cx",         d.cx.toDouble())
                                put("cy",         d.cy.toDouble())
                                put("w",          d.w.toDouble())
                                put("h",          d.h.toDouble())
                                put("zone",       SentenceBuilder.getClock(d.cx))
                                put("dist_m",     if (d.distanceM > 0f) d.distanceM.toDouble() else VoicePolicy.calcDistBboxM(d.classKo, d.w, d.h))
                                put("track_id",   d.trackId)
                                put("risk_score", d.riskScore.toDouble())
                                put("vibration_pattern", d.vibrationPattern)
                                put("is_vehicle", d.classKo in VoicePolicy.vehicleKo())
                                put("is_animal",  d.classKo in VoicePolicy.animalKo())
                            })
                        }
                    })
                }
                val reqBody = body.toString()
                    .toByteArray(Charsets.UTF_8)
                    .toRequestBody("application/json; charset=utf-8".toMediaType())
                httpClient.newCall(
                    Request.Builder()
                        .url("$serverUrl/detect_json")
                        .post(reqBody)
                        .build()
                ).execute().close()
            } catch (e: Exception) {
                Log.d("VG_JSON", "detect_json 전송 실패 (무시): ${e.message}")
            }
        }.start()
    }

    // ── 결과 처리 & Failsafe ────────────────────────────────────────────

    private fun releaseInFlight() {
        while (true) {
            val current = inFlightCount.get()
            if (current <= 0) return
            if (inFlightCount.compareAndSet(current, current - 1)) return
        }
    }

    private fun finishOnDeviceFrameWithoutNotification(requestId: String, reason: String) {
        consecutiveFails.set(0)
        lastSuccessTime = System.currentTimeMillis()
        releaseInFlight()
        Log.d("VG_FLOW", "request_id=$requestId finish without side effects reason=$reason")
    }

    private fun handleSuccess(sentence: String, alertMode: String = "critical", forceSpeak: Boolean = false) {
        consecutiveFails.set(0)
        lastSuccessTime = System.currentTimeMillis()
        releaseInFlight()
        if (!isAnalyzing.get() && !forceSpeak) return  // 분석 중지 후 in-flight 요청 결과 무시
        Log.d("VG_TTS", "handleSuccess alert=$alertMode force=$forceSpeak analyzing=${isAnalyzing.get()} sentence=$sentence")

        // 질문 응답 직후 periodic TTS 억제 — critical은 항상 통과
        val effectiveMode = if (alertMode != "critical" &&
            System.currentTimeMillis() < suppressPeriodicUntil) "silent" else alertMode

        runOnUiThread {
            tvDetected.text = "인식: $sentence"
            if (sentence == "주변에 장애물이 없어요.") {
                tvStatus.text = "장애물 없음"
                return@runOnUiThread
            }
            lastDetectionTime = System.currentTimeMillis()
            // tvStatus는 항상 최신 탐지 결과로 업데이트 — silent여도 텍스트는 표시
            tvStatus.text = sentence
            when (effectiveMode) {
                "critical" -> {
                    val now = System.currentTimeMillis()
                    if (forceSpeak || sentence != lastSentence || now - lastCriticalTime > 8000L) {
                        val isVehicleDanger = VoicePolicy.voteBypassKo().any { sentence.contains(it) }
                        if (!forceSpeak && !isVehicleDanger && isSpeaking()) return@runOnUiThread
                        lastSentence     = sentence
                        lastCriticalTime = now
                        pendingStatusText = sentence
                        tts.setSpeechRate(1.0f)
                        if (forceSpeak || isVehicleDanger) {
                            speakBuiltIn(sentence, immediate = true)
                        } else {
                            speak(sentence)
                        }
                    }
                }
                "beep" -> {
                    if (sentence != lastSentence && !isSpeaking()) {
                        lastSentence      = sentence
                        pendingStatusText = sentence
                        tts.setSpeechRate(1.0f)
                        speak(sentence)
                    }
                }
                "silent" -> { /* TTS 억제 — tvStatus는 위에서 이미 업데이트됨 */ }
                else -> {
                    if (sentence != lastSentence && !isSpeaking()) {
                        lastSentence      = sentence
                        pendingStatusText = sentence
                        tts.setSpeechRate(1.1f)
                        speak(sentence)
                    }
                }
            }
        }
    }

    private fun handleFail() {
        releaseInFlight()
        val fails = consecutiveFails.incrementAndGet()
        if (fails == FAIL_WARN_COUNT) {
            runOnUiThread {
                tvDetected.text = "인식: 실패"
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

    @Suppress("MissingPermission", "DEPRECATION")
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
        if (!immediate && !ttsBusy.compareAndSet(false, true)) {
            Log.d("VG_TTS", "drop busy immediate=false text=$text")
            return
        }
        if (immediate) ttsBusy.set(true)  // 차량 긴급 — 강제 획득
        val params = Bundle()
        params.putInt(TextToSpeech.Engine.KEY_PARAM_STREAM, AudioManager.STREAM_MUSIC)
        val utteranceId = "vg-${System.currentTimeMillis()}"
        Log.d("VG_TTS", "speak immediate=$immediate id=$utteranceId text=$text")
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, params, utteranceId)
    }

    private fun isSpeaking(): Boolean = ttsBusy.get()

    /** 직전 프레임과의 시간 간격으로 FPS 계산 + 스파크라인 업데이트 */
    private fun calcFps(): String {
        val now = System.currentTimeMillis()
        val instant = if (lastFrameDoneTime > 0L && now > lastFrameDoneTime) {
            1000.0f / (now - lastFrameDoneTime)
        } else 0.0f
        lastFrameDoneTime = now

        // 최근 10프레임 이동평균 — 동시 요청으로 인한 순간 spike 완화
        if (fpsHistory.size >= 10) fpsHistory.removeFirst()
        fpsHistory.addLast(instant)
        val fps = fpsHistory.average().toFloat()
        currentFps = fps

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
                override fun onStart(uid: String?) {
                    Log.d("VG_TTS", "start id=$uid")
                    val text = pendingStatusText
                    if (text.isNotEmpty()) {
                        pendingStatusText = ""
                        runOnUiThread { tvStatus.text = text }
                    }
                }
                override fun onDone(uid: String?) {
                    Log.d("VG_TTS", "done id=$uid")
                    speakCooldownUntil = System.currentTimeMillis() + 700L
                    handler.postDelayed({
                        ttsBusy.set(false)
                        if (awaitingStartConfirm) {
                            handler.postDelayed({
                                if (awaitingStartConfirm && !isListening) startListening()
                            }, 600L)
                        } else {
                            scheduleAutoListen()
                        }
                    }, 700)
                }
                @Deprecated("Deprecated in Java")
                override fun onError(uid: String?) {
                    Log.w("VG_TTS", "error id=$uid")
                    ttsBusy.set(false)
                    if (awaitingStartConfirm && !isListening) {
                        handler.postDelayed({ startListening() }, 600L)
                    }
                }
            })
            handler.postDelayed({ promptAutoStart() }, 1000)
        }
    }

    private fun promptAutoStart() {
        awaitingStartConfirm = true
        speakBuiltIn(
            "보이스가이드예요. " +
            "'찾기', '장애물' 같은 음성 명령도 사용할 수 있어요." +
            "시작 버튼을 누르거나 '네'라고 말하면 일반 안내를 시작해요."
        )
    }

    override fun onRequestPermissionsResult(
        requestCode: Int, permissions: Array<out String>, grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        when (requestCode) {
            PERM_CODE -> if (grantResults.all { it == PackageManager.PERMISSION_GRANTED }) startCamera()
            PERM_CODE_LOCATION -> {
                if (hasLocationPerm()) {
                    Log.d("VG_GPS", "location permission granted fine=${hasPerm(Manifest.permission.ACCESS_FINE_LOCATION)} coarse=${hasPerm(Manifest.permission.ACCESS_COARSE_LOCATION)}")
                    locationPermissionCallback?.invoke()
                } else {
                    Log.w("VG_GPS", "location permission denied")
                    speak("위치 권한이 없어요. 설정에서 허용해 주세요.")
                }
                locationPermissionCallback = null
            }
        }
    }

    private fun startBusWaiting(text: String) {
        val number = text.replace("버스대기", "").replace("번", "").trim()
        waitingBusNumber = number
        if (number.isEmpty()) {
            speak("몇 번 버스를 기다릴까요?")
        } else {
            speak("${number}번 버스를 기다릴게요. 버스가 보이면 알려드릴게요.")
        }
    }

    @Suppress("UNUSED_PARAMETER")
    private fun scheduleMedicineReminder(text: String) {
        speak("약 알림 기능은 현재 준비 중이에요.")
    }

    private fun checkBusArrival(detections: List<Detection>) {
        if (waitingBusNumber.isEmpty()) return
        val busDetected = detections.any { it.classKo == "버스" || it.classKo == "bus" }
        if (busDetected) {
            speak("버스가 왔어요! ${waitingBusNumber}번 버스인지 확인해 주세요.")
            waitingBusNumber = ""
        }
    }
}
