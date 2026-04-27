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

    // ── 카메라 & 분석 루프 ─────────────────────────────────────────────
    private var imageCapture: ImageCapture? = null
    // newSingleThreadExecutor: 카메라 캡처를 UI 스레드와 분리 (UI 멈춤 방지)
    private val cameraExecutor = Executors.newSingleThreadExecutor()
    // Handler: 메인 스레드에서 지연 작업 예약 (1초 간격 루프, Watchdog)
    private val handler = Handler(Looper.getMainLooper())
    // AtomicBoolean: 여러 스레드가 동시에 접근해도 안전한 boolean
    private val isAnalyzing = AtomicBoolean(false) // 분석 중인지 여부
    private val isSending   = AtomicBoolean(false) // 현재 요청 전송 중인지 (중복 방지)
    private var lastSentence = ""                  // 직전 안내 문장 (반복 방지)

    // ── HTTP 클라이언트 (서버 연동 — 선택 사항) ────────────────────────
    // connectTimeout: 서버 연결 최대 대기 5초
    // readTimeout: 서버 응답 최대 대기 8초 (YOLO+Depth 추론 시간 고려)
    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(8, TimeUnit.SECONDS)
        .build()
    // AtomicInteger: 연속 실패 횟수 (3회 이상이면 경고 음성)
    private val consecutiveFails = AtomicInteger(0)
    private var lastSuccessTime  = System.currentTimeMillis()

    // ── 가속도 센서: 카메라 방향 자동 감지 ────────────────────────────
    private lateinit var sensorManager: SensorManager
    // @Volatile: 여러 스레드에서 읽을 때 최신값 보장
    @Volatile private var cameraOrientation = "front"  // front/back/left/right

    // ── STT 음성 명령 ──────────────────────────────────────────────────
    private lateinit var speechRecognizer: SpeechRecognizer
    @Volatile private var currentMode = "장애물"  // 현재 활성 모드
    @Volatile private var findTarget  = ""        // 찾기 모드에서 탐색할 물체 이름

    // ── 조도 센서 (빛 감지) ────────────────────────────────────────────
    @Volatile private var lastLux = 100f  // 이전 프레임 밝기 (lux 단위)
    // by lazy: 처음 사용 시에만 생성 (앱 시작 시 오디오 초기화 지연)
    // ToneGenerator: 짧은 비프음 재생기 (위험도 낮은 알림용)
    private val toneGen by lazy { ToneGenerator(AudioManager.STREAM_MUSIC, 60) }

    // ── 음성 자동 시작 ─────────────────────────────────────────────────
    // true: "음성 안내를 시작할까요?" 에 대한 답변 대기 중
    private var awaitingStartConfirm = false

    // ── ONNX 온디바이스 추론 ───────────────────────────────────────────
    // null이면 서버 모드, null이 아니면 온디바이스 모드
    private var yoloDetector: YoloDetector? = null

    companion object {
        private const val PERM_CODE        = 100           // 권한 요청 코드 (임의 숫자)
        private const val PREFS_NAME       = "voiceguide"  // SharedPreferences 이름
        private const val PREF_URL         = "server_url"  // 저장된 서버 URL 키
        private const val PREF_LOCATIONS   = "saved_locations"  // 저장 장소 JSON 배열 키
        private const val INTERVAL_MS      = 1000L         // 캡처 간격: 1초
        private const val SILENCE_WARN_MS  = 6000L         // 6초 무응답 시 Watchdog 경고
        private const val FAIL_WARN_COUNT  = 3             // 연속 3회 실패 시 경고
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

        // 가속도 센서로 폰 기울기 판단:
        //   x: 좌우 기울기 (양수=오른쪽, 음수=왼쪽)
        //   y: 앞뒤 기울기 (양수=앞, 음수=뒤)
        //   중력(9.8m/s²)이 지배적 → 가만히 있어도 값이 있음
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
                // RESULTS_RECOGNITION: 인식된 텍스트 후보 배열 (확신도 높은 순)
                val text = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    ?.firstOrNull() ?: return  // 가장 확신도 높은 1개 사용
                handleSttResult(text)
            }
            override fun onError(error: Int) {
                // 소음, 타임아웃, 네트워크 오류 등 → 재시도 안내
                runOnUiThread { tvMode.text = "음성 인식 실패. 다시 눌러주세요." }
            }
            // 아래는 RecognitionListener 인터페이스 필수 구현 (사용하지 않음)
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
            "텍스트" -> {
                speak("텍스트를 인식할게요.")
                captureForOcr()
            }
            "바코드" -> {
                speak("바코드를 인식할게요.")
                captureForBarcode()
            }
            "색상" -> {
                speak("색상을 확인할게요.")
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
                speak("신호등을 확인할게요.")
                currentMode = "신호등"
                captureAndProcess()
            }
            else -> {
                currentMode = mode
                speak("$mode 모드.")
            }
        }
    }

    /**
     * "글자 읽어줘" 명령 처리 — ML Kit OCR로 카메라 이미지의 텍스트 인식.
     *
     * KoreanTextRecognizerOptions: 한국어 인식 최적화 옵션
     * InputImage.fromBitmap(bmp, 0): 두 번째 파라미터 0 = 회전 없음
     * ML Kit는 온디바이스 처리 → 인터넷 불필요
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
                                    else speak(text)  // 인식된 텍스트 전체를 TTS로 읽음
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
     *
     * BarcodeScanning.getClient(): 기본 클라이언트 (EAN, QR 등 모든 포맷 지원)
     * displayValue: 바코드의 텍스트 값 (상품명이 아닌 원시 바코드 값일 수 있음)
     *   → 정확한 상품명은 외부 API(Open Food Facts 등) 연동 필요 (향후 개선 과제)
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
     * STT 텍스트 → 모드 분류.
     * VoiceGuideConstants.kt의 STT_KEYWORDS 맵에서 순서대로 검색.
     * 어떤 키워드에도 안 걸리면 "장애물" 반환 → 안내 누락 없음.
     */
    private fun classifyKeyword(text: String): String {
        for ((mode, keywords) in STT_KEYWORDS) {
            if (keywords.any { text.contains(it) }) return mode
        }
        return "장애물"  // fallback: 무슨 말을 해도 기본 모드로 동작
    }

    // ── ONNX 온디바이스 추론 초기화 ────────────────────────────────────

    private fun tryInitYoloDetector() {
        // 백그라운드 스레드에서 초기화 (모델 로딩이 느려서 UI 스레드에서 하면 앱 멈춤)
        Thread {
            try {
                yoloDetector = YoloDetector(this)  // assets에서 ONNX 로드
                runOnUiThread { tvStatus.text = "온디바이스 준비 완료 — 분석 시작을 누르세요" }
            } catch (_: Exception) {
                // yolo11m.onnx 파일이 assets에 없는 경우 → 서버 모드 안내
                runOnUiThread { tvStatus.text = "ONNX 모델 없음 — 서버 URL을 입력하세요" }
            }
        }.start()
    }

    // ── 카메라 & 분석 루프 ──────────────────────────────────────────────

    private fun requestPermissions() {
        val needed = mutableListOf<String>()
        // 카메라와 마이크 권한이 없으면 요청 목록에 추가
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
    }

    private fun scheduleNext() {
        // postDelayed: INTERVAL_MS(1초) 후에 실행, 재귀 호출로 루프 구성
        // isAnalyzing 체크: 분석 중지 버튼을 누르면 루프 종료
        handler.postDelayed({
            if (isAnalyzing.get()) { captureAndProcess(); scheduleNext() }
        }, INTERVAL_MS)
    }

    private fun scheduleWatchdog() {
        // Watchdog: 6초 동안 성공 응답이 없으면 음성으로 경고
        // 이유: 네트워크 끊김, 서버 다운 등으로 조용히 멈추는 상황 방지
        // tts.isSpeaking 체크: 이미 말 중이면 경고 안 함 (겹침 방지)
        handler.postDelayed({
            if (!isAnalyzing.get()) return@postDelayed
            if (System.currentTimeMillis() - lastSuccessTime >= SILENCE_WARN_MS && !tts.isSpeaking) {
                speak("분석이 중단됐어요. 주의해서 이동하세요.")
                runOnUiThread { tvStatus.text = "⚠ 분석 중단 — 주의하세요" }
            }
            scheduleWatchdog()  // 재귀 호출로 계속 감시
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
                    // yoloDetector 있으면 온디바이스, 없으면 서버로
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
        // 백그라운드 스레드: 추론이 느려서 UI 스레드에서 하면 앱 멈춤
        Thread {
            try {
                // BitmapFactory: EXIF 회전 정보를 자동 적용 (서버의 cv2.imdecode와 다른 점)
                val bmp        = android.graphics.BitmapFactory.decodeFile(imageFile.absolutePath)
                val detections = yoloDetector!!.detect(bmp)
                bmp.recycle()      // 메모리 해제 (Android Bitmap 누수 방지)
                imageFile.delete() // 임시 파일 삭제

                val sentence = when (currentMode) {
                    "찾기"  -> SentenceBuilder.buildFind(findTarget, detections)
                    else   -> SentenceBuilder.build(detections)
                }
                handleSuccess(sentence)
            } catch (_: Exception) {
                imageFile.delete()
                // 온디바이스 실패(모델 오류 등) → 서버로 fallback 시도
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
                val beep     = json.optBoolean("beep", false)
                handleSuccess(sentence, beep)
            } catch (_: Exception) {
                handleFail()
            } finally {
                imageFile.delete()
            }
        }.start()
    }

    // ── 결과 처리 & Failsafe ────────────────────────────────────────────

    private fun handleSuccess(sentence: String, beep: Boolean = false) {
        consecutiveFails.set(0)
        lastSuccessTime = System.currentTimeMillis()
        isSending.set(false)

        runOnUiThread {
            if (sentence == "주변에 장애물이 없어요.") {
                tvStatus.text = "장애물 없음"
            } else if (sentence != lastSentence && !tts.isSpeaking) {
                lastSentence = sentence
                tvStatus.text = sentence
                if (beep) {
                    toneGen.startTone(ToneGenerator.TONE_PROP_BEEP, 120)
                } else {
                    speak(sentence)
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
            handler.postDelayed({ promptAutoStart() }, 1000)
        }
    }

    private fun promptAutoStart() {
        awaitingStartConfirm = true
        speak("음성 안내를 시작할까요? 네 또는 아니오로 말씀해주세요.")
        handler.postDelayed({ if (awaitingStartConfirm) startListening() }, 2500)
    }

    override fun onRequestPermissionsResult(
        requestCode: Int, permissions: Array<out String>, grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == PERM_CODE &&
            grantResults.all { it == PackageManager.PERMISSION_GRANTED }) startCamera()
    }
}
