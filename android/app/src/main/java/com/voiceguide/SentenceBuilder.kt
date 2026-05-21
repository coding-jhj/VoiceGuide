package com.voiceguide

/**
 * VoiceGuide 온디바이스 문장 생성기
 */
object SentenceBuilder {

    private val stableClock = mutableMapOf<String, String>()
    private val CLOCK_ORDER = listOf("8시", "9시", "10시", "11시", "12시", "1시", "2시", "3시", "4시")

    private fun clockDistance(a: String, b: String): Int {
        val ai = CLOCK_ORDER.indexOf(a)
        val bi = CLOCK_ORDER.indexOf(b)
        return if (ai < 0 || bi < 0) 0 else kotlin.math.abs(ai - bi)
    }

    /** 흔들림 방지: 화면 내 고유 인덱스를 포함하여 개별 물체를 독립적으로 추적 */
    private fun getStableClock(classKo: String, cx: Float, index: Int): String {
        val newClock = getClock(cx)
        val uniqueKey = "${classKo}_$index"
        val prev = stableClock[uniqueKey]
        if (prev == null || clockDistance(prev, newClock) >= 2) {
            stableClock[uniqueKey] = newClock
        }
        return stableClock[uniqueKey]!!
    }

    fun clearStableClocks() { stableClock.clear() }

    private fun directionFor(clock: String): String =
        if (clock == "12시") "정면" else (CLOCK_TO_DIRECTION[clock] ?: clock)

    private fun locationPhrase(clock: String, det: Detection): String {
        val distStr = formatDist(det)
        val dir = directionFor(clock)
        return when {
            clock == "12시" && (distStr == "코앞" || det.distanceM in 0.01f..0.75f) -> "바로 앞"
            distStr == "코앞" -> "$dir 코앞"
            else -> "$dir $distStr"
        }
    }

    fun build(detections: List<Detection>): String {
        if (detections.isEmpty()) return "주변에 장애물이 없어요."

        // 화면 왼쪽부터 오른쪽 순서대로 정렬하여 고유 인덱스 부여 (도플갱어 버그 해결)
        val sortedByX = detections.sortedBy { it.cx }

        val nearVehicle = detections.firstOrNull {
            it.classKo in VoicePolicy.vehicleKo() &&
                it.w * it.h > VoicePolicy.nearVehicleAreaRatio()
        }
        
        if (nearVehicle != null) {
            val idx   = sortedByX.indexOf(nearVehicle)
            val clock = getStableClock(nearVehicle.classKo, nearVehicle.cx, idx)
            val dir   = directionFor(clock)
            return "위험! ${dir} ${nearVehicle.classKo}. 조심! 멈추세요!"
        }

        val parts = detections.take(2).mapIndexed { originalIdx, det ->
            val idx       = sortedByX.indexOf(det)
            val clock     = getStableClock(det.classKo, det.cx, idx)
            val dir       = directionFor(clock)
            val locStr    = locationPhrase(clock, det)
            val ig        = josaIGa(det.classKo)
            val action    = DIRECTION_ACTION[clock] ?: ""
            val areaRatio = det.w * det.h
            val isAnimal  = det.classKo in VoicePolicy.animalKo()
            val isCaution = det.classKo in VoicePolicy.cautionKo()

            val base = when {
                det.classKo in VoicePolicy.vehicleKo() ->
                    "위험! ${dir} ${det.classKo}. 조심! 멈추세요!"
                isAnimal ->
                    "조심하세요. ${locStr}에 ${det.classKo}${ig} 있어요. 천천히 $action."
                det.classKo in VoicePolicy.everydayKo() ->
                    "${locStr}에 ${det.classKo}${ig} 있어요."
                isCaution ->
                    "${locStr}에 ${det.classKo}${ig} 있어요. $action."
                areaRatio > VoicePolicy.cautionAreaRatio() ->
                    "${locStr}에 ${det.classKo}${ig} 있어요. $action."
                else ->
                    "${locStr}에 ${det.classKo}${ig} 있어요."
            }

            if (originalIdx == 0) base
            else base.replace("${det.classKo}${ig}", "${det.classKo}도")
        }

        return parts.joinToString(" ")
    }

    fun buildFind(target: String, detections: List<Detection>): String {
        if (target.isEmpty()) return build(detections)

        val sortedByX = detections.sortedBy { it.cx }
        val found = detections.firstOrNull { it.classKo.contains(target) }
        if (found != null) {
            val idx     = sortedByX.indexOf(found)
            val clock   = getStableClock(found.classKo, found.cx, idx)
            val locStr  = locationPhrase(clock, found)
            val un      = josaUnNeun(target)
            val base    = "${target}${un} ${locStr}에 있어요."

            val targetArea   = found.w * found.h
            val closerHazard = detections.firstOrNull { d ->
                !d.classKo.contains(target) &&
                d.w * d.h > targetArea * VoicePolicy.findHazardAreaMultiplier() &&
                d.w * d.h > VoicePolicy.findHazardAreaRatio()
            }
            return if (closerHazard != null) {
                val hIdx     = sortedByX.indexOf(closerHazard)
                val hClock   = getStableClock(closerHazard.classKo, closerHazard.cx, hIdx)
                val hLocStr  = locationPhrase(hClock, closerHazard)
                val hIg      = josaIGa(closerHazard.classKo)
                "$base 단, ${hLocStr}에 ${closerHazard.classKo}${hIg} 있으니 주의하세요."
            } else {
                base
            }
        }

        val ig = josaIGa(target)
        return if (detections.isNotEmpty()) {
            val scene = build(detections.take(1))
            "${target}${ig} 없어요. 다른 곳을 보여주세요. $scene"
        } else {
            "${target}${ig} 없어요. 다른 곳을 보여주세요."
        }
    }

    fun buildHeld(detections: List<Detection>): String {
        if (detections.isEmpty()) return "손에 든 물건이나 바로 앞에 뭔가 없어 보여요."

        val closest = detections.maxByOrNull { it.w * it.h } ?: return "손에 든 물건이나 바로 앞에 뭔가 없어 보여요."
        val area = closest.w * closest.h
        val name = closest.classKo
        val ig   = josaIGa(name)
        val ie   = josaIEyo(name)

        return when {
            area > VoicePolicy.heldAreaInHand()  -> "손에 들고 있는 건 ${name}${ie}."
            area > VoicePolicy.heldAreaFront()   -> "바로 앞에 ${name}${ig} 있어요."
            area > VoicePolicy.heldAreaNear()    -> "가까이에 ${name}${ig} 있어요."
            else -> "손에 든 물건이나 바로 앞에 뭔가 없어 보여요."
        }
    }

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

    fun getClock(cx: Float): String {
        for ((boundary, label) in ZONE_BOUNDARIES) {
            if (cx <= boundary) return label
        }
        return "4시"
    }

    fun formatDist(det: Detection): String =
        if (det.distanceM > 0f) VoicePolicy.formatDistMeters(det.distanceM.toDouble())
        else VoicePolicy.formatDistBbox(det.classKo, det.w, det.h)

    fun formatDist(w: Float, h: Float): String = VoicePolicy.formatDistBbox(w, h)

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

    fun josaIEyo(word: String): String {
        if (word.isEmpty()) return "이에요"
        val last = word.last()
        return if (last in '가'..'힣' && (last.code - 0xAC00) % 28 != 0) "이에요" else "예요"
    }

    fun josaEulReul(word: String): String {
        if (word.isEmpty()) return "을"
        val last = word.last()
        return if (last in '가'..'힣' && (last.code - 0xAC00) % 28 != 0) "을" else "를"
    }

    fun extractLabel(text: String): String {
        val remove = listOf("여기 저장해줘", "저장해줘", "여기 기억해줘", "기억해줘", "여기 저장", "저장해", "여기야", "여기 등록해줘", "등록해줘", "여기 표시해줘", "마킹해줘", "위치 저장", "여기 이름")
        var label = text
        remove.forEach { label = label.replace(it, "") }
        return label.trim()
    }

    fun extractFindTarget(text: String): String {
        val remove = listOf(
            "찾아줘", "찾아 줘", "찾아", "어디있어", "어디 있어", "어디야",
            "어딘지", "어디에 있어", "어디에 있나", "있는지 알려줘",
            "어디 있나", "어딨어", "어딨나", "위치", "알려줘",
            // 확인 의도 키워드 — 제거 후 target="" 이 됨 → build_sentence() fallback
            "이건 뭐야", "이게 뭐", "이거 뭐", "뭔지", "뭔데", "뭐지", "뭐야",
            "이거", "이게", "이건",
        )
        // 공백 정규화 후 긴 패턴부터 제거 (부분 겹침 방지)
        var target = text.replace("\\s+".toRegex(), " ").trim()
        remove.sortedByDescending { it.length }
              .forEach { target = target.replace(it, "") }
        return target.trim()
    }
}