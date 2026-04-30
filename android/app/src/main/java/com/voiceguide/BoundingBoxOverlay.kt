package com.voiceguide

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.View

/**
 * 바운드박스 오버레이 View.
 * 카메라 프리뷰 위에 겹쳐서 배치되며, YOLO 탐지 결과를
 * 위험도별 색상으로 시각화한다.
 *
 * 색상 체계 (sentence.py get_alert_mode와 동일):
 *   빨강 — critical (차량·계단·칼 등 즉각 위험)
 *   노랑 — caution  (칼·가위·바닥 장애물 등 주의)
 *   초록 — info     (키보드·마우스·TV 등 정보성)
 */
class BoundingBoxOverlay @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    // ── 위험도별 색상 ──────────────────────────────────────────────────────────
    private val COLOR_CRITICAL = Color.parseColor("#E53935")  // 빨강 — 긴급
    private val COLOR_CAUTION  = Color.parseColor("#FDD835")  // 노랑 — 주의
    private val COLOR_INFO     = Color.parseColor("#43A047")  // 초록 — 정보

    // sentence.py _VEHICLE_KO + 계단·낙차 위험 클래스
    private val CRITICAL_CLASSES = setOf(
        "자동차", "오토바이", "버스", "트럭", "기차", "자전거",
        "곰", "코끼리", "계단"
    )
    // 날카로운 물체 + 바닥 장애물
    private val CAUTION_CLASSES = setOf(
        "칼", "가위", "유리잔", "야구 방망이",
        "배낭", "핸드백", "여행가방", "공"
    )

    // ── Paint ─────────────────────────────────────────────────────────────────
    private val boxPaint = Paint().apply {
        style = Paint.Style.STROKE
        strokeWidth = 4f
        isAntiAlias = true
    }

    private val textPaint = Paint().apply {
        textSize = 36f
        isAntiAlias = true
        style = Paint.Style.FILL
        isFakeBoldText = true
    }

    private val bgPaint = Paint().apply {
        style = Paint.Style.FILL
        color = Color.argb(160, 0, 0, 0)
    }

    // ── 탐지 결과 ──────────────────────────────────────────────────────────────
    private var detections: List<Detection> = emptyList()
    private var imageWidth  = 0
    private var imageHeight = 0

    fun setDetections(detections: List<Detection>, imgW: Int, imgH: Int) {
        this.detections  = detections
        this.imageWidth  = imgW
        this.imageHeight = imgH
        invalidate()
    }

    fun clearDetections() {
        detections = emptyList()
        invalidate()
    }

    /** classKo를 기반으로 위험도 색상 반환. sentence.py 색상 체계와 동일하게 유지. */
    private fun hazardColor(classKo: String): Int = when {
        classKo in CRITICAL_CLASSES -> COLOR_CRITICAL
        classKo in CAUTION_CLASSES  -> COLOR_CAUTION
        else                        -> COLOR_INFO
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val vw = width.toFloat()
        val vh = height.toFloat()
        if (vw == 0f || vh == 0f || imageWidth == 0 || imageHeight == 0) return

        // PreviewView FILL_CENTER 변환
        val fillScale = maxOf(vw / imageWidth, vh / imageHeight)
        val displayW  = imageWidth  * fillScale
        val displayH  = imageHeight * fillScale
        val offsetX   = (vw - displayW) / 2f
        val offsetY   = (vh - displayH) / 2f

        detections.forEach { det ->
            val color = hazardColor(det.classKo)
            boxPaint.color  = color
            textPaint.color = color

            val left   = offsetX + (det.cx - det.w / 2f) * displayW
            val top    = offsetY + (det.cy - det.h / 2f) * displayH
            val right  = offsetX + (det.cx + det.w / 2f) * displayW
            val bottom = offsetY + (det.cy + det.h / 2f) * displayH

            canvas.drawRect(RectF(left, top, right, bottom), boxPaint)

            // 클래스명만 표시 (confidence % 제거 — 사용자에게 의미 없는 디버그 정보)
            val label = det.classKo
            val textH = textPaint.textSize
            val textW = textPaint.measureText(label)
            val labelY = if (top > textH + 8f) top - 4f else bottom + textH + 4f

            canvas.drawRect(left, labelY - textH - 2f, left + textW + 10f, labelY + 4f, bgPaint)
            canvas.drawText(label, left + 5f, labelY, textPaint)
        }
    }
}
