package com.voiceguide

import kotlin.math.sqrt

/**
 * VoiceGuide 온디바이스 문장 생성기
 *
 * 서버 없이 폰 단독으로 동작할 때 사용.
 * 서버 모드에서는 Python sentence.py가 문장을 생성하고,
 * 온디바이스 모드에서는 이 파일이 문장을 생성함.
 *
 * 두 파일의 로직이 동일해야 사용자 경험이 일관됨.
 * → 서버/온디바이스 전환 시 다른 문장이 나오지 않도록 주의.
 */
object SentenceBuilder {

    // object = 싱글톤 (인스턴스 생성 없이 SentenceBuilder.build() 로 바로 호출)

    // 차량: 이동 중이라 같은 거리라도 의자보다 훨씬 위험 → 별도 처리
    private val VEHICLE_CLASSES = setOf("자동차", "오토바이", "버스", "트럭", "기차", "자전거")
    private val ANIMAL_CLASSES  = setOf("개", "말")

    // ── 방향 안정화 (hysteresis) ───────────────────────────────────────────
    // 문제: cx 값이 프레임마다 조금씩 달라져 "오른쪽" ↔ "오른쪽 앞" 등이 반복 전환되면
    //       sentence != lastSentence 조건으로 TTS가 매 프레임 발화됨.
    // 해결: 클래스별 마지막 안정 방향을 캐싱하고, 새 방향이 2칸 이상 벗어날 때만 갱신.
    private val stableClock = mutableMapOf<String, String>()

    // ZONE_BOUNDARIES 순서와 동일하게 유지해야 clockDistance()가 정확함
    private val CLOCK_ORDER = listOf("8시", "9시", "10시", "11시", "12시", "1시", "2시", "3시", "4시")

    /** 방향 캐시 거리 계산 (두 클락 간 존 개수 차이) */
    private fun clockDistance(a: String, b: String): Int {
        val ai = CLOCK_ORDER.indexOf(a)
        val bi = CLOCK_ORDER.indexOf(b)
        return if (ai < 0 || bi < 0) 0 else kotlin.math.abs(ai - bi)
    }

    /**
     * 흔들림 방지 방향 조회.
     * 이전 방향에서 2존(약 22% 화면 폭) 이상 벗어나야 방향 갱신.
     * 경계 근처에서 cx 값이 조금씩 달라져도 방향이 고정됨.
     */
    private fun getStableClock(classKo: String, cx: Float): String {
        val newClock = getClock(cx)
        val prev = stableClock[classKo]
        if (prev == null || clockDistance(prev, newClock) >= 2) {
            stableClock[classKo] = newClock
        }
        return stableClock[classKo]!!
    }

    /** 모드 전환·분석 재시작 시 방향 캐시 초기화 */
    fun clearStableClocks() { stableClock.clear() }

    // ── 장애물 안내 문장 (기본 장애물 모드) ───────────────────────────────────

    /**
     * 탐지된 물체 목록에서 안내 문장을 생성.
     * 우선순위: 가까운 차량 > 일반 장애물 (최대 3개)
     *
     * @param detections 투표 필터를 통과한 Detection 목록
     * @return TTS로 읽을 한국어 문장
     */
    fun build(detections: List<Detection>): String {
        if (detections.isEmpty()) return "주변에 장애물이 없어요."

        // 1순위: bbox 면적 4% 이상인 가까운 차량 (야외 최고 위험)
        val nearVehicle = detections.firstOrNull {
            it.classKo in VEHICLE_CLASSES && it.w * it.h > 0.04f
        }
        if (nearVehicle != null) {
            val clock   = getStableClock(nearVehicle.classKo, nearVehicle.cx)
            val dir     = CLOCK_TO_DIRECTION[clock] ?: clock
            val action  = DIRECTION_ACTION[clock] ?: "즉시 멈추세요"
            val distStr = formatDist(nearVehicle.w, nearVehicle.h)
            val ig      = josaIGa(nearVehicle.classKo)
            return "위험! ${dir} ${distStr}에 ${nearVehicle.classKo}${ig} 있어요! 즉시 $action!"
        }

        // 2순위: 일반 장애물 — 상위 3개까지 문장 생성
        val parts = detections.take(3).mapIndexed { idx, det ->
            val clock     = getStableClock(det.classKo, det.cx)
            val dir       = CLOCK_TO_DIRECTION[clock] ?: clock
            val distStr   = formatDist(det.w, det.h)
            val ig        = josaIGa(det.classKo)
            val action    = DIRECTION_ACTION[clock] ?: ""
            val areaRatio = det.w * det.h  // bbox 면적 비율 (거리 판단 기준)
            val isAnimal  = det.classKo in ANIMAL_CLASSES

            val base = when {
                // 차량: 멀어도 "접근 중" 경고
                det.classKo in VEHICLE_CLASSES ->
                    "조심! ${dir} ${distStr}에 ${det.classKo}${ig} 접근 중이에요. $action."
                // 동물: "천천히" 어조
                isAnimal ->
                    "조심! ${dir} ${distStr}에 ${det.classKo}${ig} 있어요. 천천히 $action."
                // 면적 25% 이상 = 바로 코앞 → "위험!" 긴박
                areaRatio > 0.25f ->
                    "위험! ${dir} ${distStr}에 ${det.classKo}${ig} 있어요. $action."
                // 면적 12% 이상 = 가까이 → 방향 + 거리 + 행동
                areaRatio > 0.12f ->
                    "${dir} ${distStr}에 ${det.classKo}${ig} 있어요. $action."
                // 그 외 = 멀리 → 방향 + 거리만
                else ->
                    "${dir} ${distStr}에 ${det.classKo}${ig} 있어요."
            }

            // 두 번째 물체는 "~도 있어요" 형태 (첫 번째와 구분)
            if (idx == 0) base
            else base.replace("${det.classKo}${ig}", "${det.classKo}도")
        }

        return parts.joinToString(" ")
    }

    // ── 찾기 모드: 특정 물체 찾기 ────────────────────────────────────────────

    /**
     * "의자 찾아줘" → 의자가 보이면 방향/거리, 없으면 없다고 안내.
     *
     * @param target 찾을 물체 한국어 이름 ("의자", "가방" 등)
     * @param detections 탐지된 물체 목록
     */
    fun buildFind(target: String, detections: List<Detection>): String {
        if (target.isEmpty()) return build(detections)

        // target 이름을 포함하는 물체 검색 (부분 일치: "의자" ⊂ "휠체어" 도 매칭)
        val found = detections.firstOrNull { it.classKo.contains(target) }
        if (found != null) {
            val clock   = getStableClock(found.classKo, found.cx)
            val dir     = CLOCK_TO_DIRECTION[clock] ?: clock
            val distStr = formatDist(found.w, found.h)
            val un      = josaUnNeun(target)
            val base    = "${target}${un} ${dir}에 있어요. $distStr."

            // target을 찾았어도 더 가까운 위험 물체가 있으면 경고 추가.
            // 조건: target이 아닌 물체이면서, target보다 면적(=거리) 50% 이상 크고, 12% 이상인 것
            val targetArea   = found.w * found.h
            val closerHazard = detections.firstOrNull { d ->
                !d.classKo.contains(target) &&
                d.w * d.h > targetArea * 1.5f &&
                d.w * d.h > 0.12f
            }
            return if (closerHazard != null) {
                val hClock   = getStableClock(closerHazard.classKo, closerHazard.cx)
                val hDir     = CLOCK_TO_DIRECTION[hClock] ?: hClock
                val hDistStr = formatDist(closerHazard.w, closerHazard.h)
                val hIg      = josaIGa(closerHazard.classKo)
                "$base 단, ${hDir} ${hDistStr}에 ${closerHazard.classKo}${hIg} 있으니 주의하세요."
            } else {
                base
            }
        }

        // 못 찾음 → 없다고 하고 주변 상황 안내
        val un = josaUnNeun(target)
        return if (detections.isNotEmpty()) {
            val scene = build(detections.take(1))
            "${target}${un} 보이지 않아요. 카메라를 천천히 돌려보세요. $scene"
        } else {
            "${target}${un} 보이지 않아요. 카메라를 천천히 돌려보세요."
        }
    }

    // ── 개인 네비게이팅 안내 ──────────────────────────────────────────────────

    /**
     * 저장/목록/찾기/삭제 등 네비게이팅 관련 안내 문장 생성.
     *
     * @param action  "save" | "found_here" | "not_found" | "deleted" | "list"
     * @param label   장소 이름 ("편의점", "화장실" 등)
     * @param locations 저장된 장소 목록 (list 액션에서 사용)
     */
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

    // ── 유틸리티 ──────────────────────────────────────────────────────────────

    /**
     * 바운딩 박스 중심 X값 → 시계 방향 문자열 변환.
     * VoiceGuideConstants.kt의 ZONE_BOUNDARIES 기준.
     * cx = 0.0(왼쪽 끝) ~ 1.0(오른쪽 끝)
     */
    fun getClock(cx: Float): String {
        for ((boundary, label) in ZONE_BOUNDARIES) {
            if (cx <= boundary) return label
        }
        return "4시"  // 오른쪽 끝 기본값
    }

    /**
     * 거리를 상대 표현으로 변환.
     * 서버(sentence.py)의 _format_dist와 동일한 표현 사용.
     * 카메라 단안으로 정확한 미터 측정 불가 → 상대 표현이 더 정직함.
     */
    fun formatDist(w: Float, h: Float): String {
        // bbox 면적 기반 거리 근사 (calib=0.12 가정 — 보통 물체 기준)
        val area  = w * h
        val distM = if (area > 0) sqrt(0.12f / area) else 99f
        return when {
            distM < 0.5f -> "바로 코앞"
            distM < 1.0f -> "매우 가까이"
            distM < 2.5f -> "가까이"
            distM < 5.0f -> "조금 멀리"
            else         -> "멀리"
        }
    }

    // ── 한국어 조사 자동화 ────────────────────────────────────────────────────
    // 받침 판별 원리:
    //   한국어 유니코드: 0xAC00(가) ~ 0xD7A3(힣)
    //   (글자코드 - 0xAC00) % 28 == 0 이면 받침 없음
    //   예) 의자(0xC758, 자=0xC790): (51088-44032)%28 = 0 → 받침 없음 → "가"
    //   예) 책(0xCC45):              (52293-44032)%28 = 1 → 받침 있음 → "이"

    /** 이/가 조사: "의자가", "책이" */
    fun josaIGa(word: String): String {
        if (word.isEmpty()) return "이"
        val last = word.last()
        return if (last in '가'..'힣' && (last.code - 0xAC00) % 28 != 0) "이" else "가"
    }

    /** 은/는 조사: "의자는", "책은" */
    fun josaUnNeun(word: String): String {
        if (word.isEmpty()) return "은"
        val last = word.last()
        return if (last in '가'..'힣' && (last.code - 0xAC00) % 28 != 0) "은" else "는"
    }

    /** 을/를 조사: "의자를", "책을" */
    fun josaEulReul(word: String): String {
        if (word.isEmpty()) return "을"
        val last = word.last()
        return if (last in '가'..'힣' && (last.code - 0xAC00) % 28 != 0) "을" else "를"
    }

    // ── STT 텍스트 파싱 유틸 ─────────────────────────────────────────────────

    /** "여기 저장해줘 편의점" → "편의점" 추출 */
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

    /** "의자 찾아줘" / "의자 찾아 줘" → "의자" 추출 */
    fun extractFindTarget(text: String): String {
        val remove = listOf(
            "찾아줘", "찾아 줘", "찾아", "어디있어", "어디 있어", "어디야",
            "어딘지", "어디에 있어", "어디에 있나", "있는지 알려줘",
            "어디 있나", "어딨어", "어딨나", "위치", "알려줘"
        )
        // 공백 정규화 후 키워드 제거
        var target = text.replace("\\s+".toRegex(), " ").trim()
        remove.sortedByDescending { it.length }  // 긴 키워드부터 제거 (부분 겹침 방지)
              .forEach { target = target.replace(it, "") }
        return target.trim()
    }
}
