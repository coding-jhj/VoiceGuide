package com.voiceguide

val VOICEGUIDE_EXTRA_KO = mapOf(
    80 to "\uACC4\uB2E8",
    81 to "\uBB38"
)

fun voiceGuideClassKo(classId: Int): String? =
    COCO_KO[classId] ?: VOICEGUIDE_EXTRA_KO[classId]
