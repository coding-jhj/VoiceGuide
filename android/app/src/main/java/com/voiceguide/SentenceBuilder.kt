package com.voiceguide

import kotlin.math.sqrt

object SentenceBuilder {

    // ── 장애물 안내 (기본 모드) ───────────────────────────────────────────

    fun build(detections: List<Detection>): String {
        if (detections.isEmpty()) return "주변에 장애물이 없어요."

        // 계단 최우선
        val stairs = detections.firstOrNull { it.classKo == "계단" }
        if (stairs != null) {
            val clock  = getClock(stairs.cx)
            val action = DIRECTION_ACTION[clock] ?: "조심하세요"
            return "조심! 앞에 계단이 있어요. $action."
        }

        val parts = detections.take(2).mapIndexed { idx, det ->
            val clock    = getClock(det.cx)
            val dir      = CLOCK_TO_DIRECTION[clock] ?: clock
            val distStr  = formatDist(det.w, det.h)
            val ig       = josaIGa(det.classKo)
            val action   = DIRECTION_ACTION[clock] ?: ""
            val areaRatio = det.w * det.h

            val base = when {
                areaRatio > 0.25f -> "위험! ${dir}에 ${det.classKo}${ig} 있어요. $distStr. $action."
                areaRatio > 0.12f -> "${dir}에 ${det.classKo}${ig} 있어요. $distStr. $action."
                else              -> "${dir}에 ${det.classKo}${ig} 있어요. $distStr."
            }
            if (idx == 0) base
            else base.replace("${det.classKo}${ig}", "${det.classKo}도")
        }

        return parts.joinToString(" ")
    }

    // ── 찾기 모드: 특정 물체를 타깃으로 탐색 ─────────────────────────────

    fun buildFind(target: String, detections: List<Detection>): String {
        if (target.isEmpty()) return build(detections)

        val found = detections.firstOrNull { it.classKo.contains(target) }
        if (found != null) {
            val clock   = getClock(found.cx)
            val dir     = CLOCK_TO_DIRECTION[clock] ?: clock
            val distStr = formatDist(found.w, found.h)
            val un      = josaUnNeun(target)
            return "${target}${un} ${dir}에 있어요. $distStr."
        }

        val un = josaUnNeun(target)
        return if (detections.isNotEmpty()) {
            val scene = build(detections.take(1))
            "${target}${un} 보이지 않아요. 카메라를 천천히 돌려보세요. $scene"
        } else {
            "${target}${un} 보이지 않아요. 카메라를 천천히 돌려보세요."
        }
    }

    // ── 개인 네비게이팅 안내 문장 ─────────────────────────────────────────

    fun buildNavigation(action: String, label: String, locations: List<String> = emptyList()): String {
        return when (action) {
            "save"       -> "${label}${josaEulReul(label)} 저장했어요."
            "found_here" -> "${label}${josaIGa(label)} 저장된 위치예요! 도착했어요."
            "not_found"  -> "${label}${josaUnNeun(label)} 저장된 장소에 없어요. 먼저 그 곳에서 저장해 주세요."
            "deleted"    -> "${label}${josaEulReul(label)} 삭제했어요."
            "list"       -> if (locations.isEmpty()) {
                "저장된 장소가 없어요. '여기 저장해줘' 라고 말해보세요."
            } else {
                val names  = locations.take(5).joinToString(", ")
                val suffix = if (locations.size > 5) " 외 ${locations.size - 5}곳" else ""
                "저장된 장소는 $names$suffix 이에요."
            }
            else -> "안내를 처리하지 못했어요."
        }
    }

    // ── 유틸 ────────────────────────────────────────────────────────────

    fun getClock(cx: Float): String {
        for ((boundary, label) in ZONE_BOUNDARIES) {
            if (cx <= boundary) return label
        }
        return "4시"
    }

    fun formatDist(w: Float, h: Float): String {
        val area  = w * h
        val distM = if (area > 0) sqrt(0.12f / area) else 99f
        return if (distM < 1f) "약 ${(distM * 100 / 10).toInt() * 10}센티미터"
               else            "약 ${"%.1f".format(distM)}미터"
    }

    fun josaIGa(word: String): String {
        if (word.isEmpty()) return "이"
        val last = word.last()
        return if (last in '가'..'힣' && (last.code - 0xAC00) % 28 != 0) "이" else "가"
    }

    fun josaUnNeun(word: String): String {
        if (word.isEmpty()) return "은"
        val last = word.last()
        return if (last in '가'..'힣' && (last.code - 0xAC00) % 28 != 0) "은" else "는"
    }

    fun josaEulReul(word: String): String {
        if (word.isEmpty()) return "을"
        val last = word.last()
        return if (last in '가'..'힣' && (last.code - 0xAC00) % 28 != 0) "을" else "를"
    }

    fun extractLabel(text: String): String {
        val remove = listOf(
            "여기 저장해줘", "저장해줘", "여기 기억해줘", "기억해줘",
            "여기 저장", "저장해", "여기야", "여기 등록해줘", "등록해줘",
            "여기 표시해줘", "마킹해줘", "위치 저장", "여기 이름"
        )
        var label = text
        remove.forEach { label = label.replace(it, "") }
        return label.trim()
    }

    fun extractFindTarget(text: String): String {
        val remove = listOf(
            "찾아줘", "찾아", "어디있어", "어디 있어", "어디야",
            "어딘지", "어디에 있어", "어디에 있나", "있는지 알려줘"
        )
        var target = text
        remove.forEach { target = target.replace(it, "") }
        return target.trim()
    }
}
