package com.voiceguide

import kotlin.math.sqrt

object SentenceBuilder {

    fun build(detections: List<Detection>): String {
        if (detections.isEmpty()) return "주변에 장애물이 없어요."

        val parts = detections.take(2).mapIndexed { idx, det ->
            val direction = getDirection(det.cx)
            val distStr   = formatDist(det.w, det.h)
            val ig        = josaIGa(det.classKo)
            val action    = DIRECTION_ACTION[direction] ?: ""

            val areaRatio = det.w * det.h
            when {
                areaRatio > 0.25f -> "$action! ${direction}에 ${det.classKo}${ig} 있어요. $distStr 거리예요."
                areaRatio > 0.12f -> "${direction}에 ${det.classKo}${ig} 있어요. $distStr 거리예요. $action."
                else              -> "${direction}에 ${det.classKo}${ig} 있어요. ${distStr}예요."
            }.let { if (idx == 0) it else it.replace(Regex("${det.classKo}${ig}"), "${det.classKo}도") }
        }

        return parts.joinToString(" ")
    }

    private fun getDirection(cx: Float): String {
        for ((boundary, label) in ZONE_BOUNDARIES) {
            if (cx <= boundary) return label
        }
        return "오른쪽"
    }

    private fun formatDist(w: Float, h: Float): String {
        val area = w * h
        val distM = if (area > 0) sqrt(0.12f / area) else 99f
        return if (distM < 1f) "약 ${(distM * 100 / 10).toInt() * 10}센티미터"
               else            "약 ${"%.1f".format(distM)}미터"
    }

    private fun josaIGa(word: String): String {
        if (word.isEmpty()) return "이"
        val last = word.last()
        return if (last in '가'..'힣' && (last.code - 0xAC00) % 28 != 0) "이" else "가"
    }
}
