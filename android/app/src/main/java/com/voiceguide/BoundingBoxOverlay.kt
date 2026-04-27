package com.voiceguide

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.View

/**
 * 디버깅용 바운드박스 오버레이 View.
 * 카메라 프리뷰 위에 겹쳐서 배치되며, YOLO 탐지 결과를
 * 사각형과 레이블(클래스명 + 신뢰도)로 시각화한다.
 */
class BoundingBoxOverlay @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    // 바운드박스 테두리용 Paint (외곽선만 그림)
    private val boxPaint = Paint().apply {
        style = Paint.Style.STROKE
        strokeWidth = 4f
        isAntiAlias = true
    }

    // 클래스명 + 신뢰도 텍스트용 Paint
    private val textPaint = Paint().apply {
        textSize = 36f
        isAntiAlias = true
        style = Paint.Style.FILL
        isFakeBoldText = true
    }

    // 텍스트 뒤에 깔리는 반투명 검정 배경 Paint (가독성 향상)
    private val bgPaint = Paint().apply {
        style = Paint.Style.FILL
        color = Color.argb(160, 0, 0, 0)
    }

    // 탐지 결과가 여러 개일 때 각 박스를 구별하기 위한 색상 팔레트
    private val colors = intArrayOf(
        Color.RED,
        Color.GREEN,
        Color.CYAN,
        Color.YELLOW,
        Color.MAGENTA,
        Color.WHITE
    )

    // 현재 화면에 그릴 탐지 결과 목록
    private var detections: List<Detection> = emptyList()

    /**
     * 새 탐지 결과를 받아 화면을 다시 그린다.
     * YoloDetector.detect() 결과를 processOnDevice()에서 호출.
     */
    fun setDetections(detections: List<Detection>) {
        this.detections = detections
        invalidate() // onDraw() 재호출 요청
    }

    /** 분석 중지 시 오버레이를 비운다. */
    fun clearDetections() {
        detections = emptyList()
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val vw = width.toFloat()
        val vh = height.toFloat()
        if (vw == 0f || vh == 0f) return

        detections.forEachIndexed { i, det ->
            val color = colors[i % colors.size] // 탐지 순서별 색상 할당
            boxPaint.color = color
            textPaint.color = color

            // Detection 좌표는 [0, 1] 정규화 값 → View의 실제 픽셀로 변환
            // cx, cy는 중심점, w/h는 너비/높이 (모두 비율 값)
            val left   = (det.cx - det.w / 2f) * vw
            val top    = (det.cy - det.h / 2f) * vh
            val right  = (det.cx + det.w / 2f) * vw
            val bottom = (det.cy + det.h / 2f) * vh

            // 바운드박스 사각형 그리기
            canvas.drawRect(RectF(left, top, right, bottom), boxPaint)

            // 레이블: "클래스명 신뢰도%" 형식 (예: "사람 87%")
            val label = "${det.classKo} ${"%.0f".format(det.confidence * 100)}%"
            val textH = textPaint.textSize
            val textW = textPaint.measureText(label)

            // 박스 상단에 공간이 있으면 위쪽에, 없으면 박스 아래쪽에 레이블 표시
            val labelY = if (top > textH + 8f) top - 4f else bottom + textH + 4f

            // 텍스트 배경 (반투명 검정)
            canvas.drawRect(
                left, labelY - textH - 2f,
                left + textW + 10f, labelY + 4f,
                bgPaint
            )
            // 레이블 텍스트
            canvas.drawText(label, left + 5f, labelY, textPaint)
        }
    }
}
