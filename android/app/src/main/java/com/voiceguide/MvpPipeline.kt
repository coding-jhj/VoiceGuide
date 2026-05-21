package com.voiceguide

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

enum class VibrationPattern {
    NONE,
    SHORT,
    DOUBLE,
    URGENT
}

data class MvpFrame(
    val detections: List<Detection>,
    val maxRisk: Float,
    val vibrationPattern: VibrationPattern
)

class MvpPipeline {
    private data class Track(
        val id: Int,
        var cls: String,
        var cx: Float,
        var cy: Float,
        var w: Float,
        var h: Float,
        var distanceM: Float,
        var risk: Float,
        var missed: Int = 0
    )

    private val tracks = mutableListOf<Track>()
    private var nextTrackId = 1

    @Synchronized
    fun update(detections: List<Detection>): MvpFrame {
        tracks.forEach { it.missed += 1 }

        val assignedTrackIds = mutableSetOf<Int>()
        val assignedDetectionIds = mutableSetOf<Int>()
        val output = mutableListOf<Detection>()

        val scoredPairs = mutableListOf<Triple<Float, Int, Int>>()
        for (di in detections.indices) {
            for (ti in tracks.indices) {
                val tr = tracks[ti]
                if (tr.cls != detections[di].classKo) continue
                val score = iou(detections[di], tr)
                if (score >= IOU_MATCH_THRESHOLD) scoredPairs.add(Triple(score, di, ti))
            }
        }

        for ((_, di, ti) in scoredPairs.sortedByDescending { it.first }) {
            if (di in assignedDetectionIds) continue
            val track = tracks[ti]
            if (track.id in assignedTrackIds) continue
            assignedDetectionIds.add(di)
            assignedTrackIds.add(track.id)
            output.add(updateTrack(track, detections[di]))
        }

        for (di in detections.indices) {
            if (di in assignedDetectionIds) continue
            val det = detections[di]
            val risk = computeRisk(det)
            val distanceM = bboxDistanceM(det)
            val track = Track(
                id = nextTrackId++,
                cls = det.classKo,
                cx = det.cx,
                cy = det.cy,
                w = det.w,
                h = det.h,
                distanceM = distanceM,
                risk = risk,
                missed = 0
            )
            tracks.add(track)
            output.add(withMvpFields(det, track.id, distanceM, risk))
        }

        tracks.removeAll { it.missed > MAX_MISSED_FRAMES }

        val sorted = output.sortedWith(
            compareByDescending<Detection> { it.riskScore }
                .thenByDescending { it.w * it.h }
        )
        val maxRisk = sorted.maxOfOrNull { it.riskScore } ?: 0f
        return MvpFrame(
            detections = sorted,
            maxRisk = maxRisk,
            vibrationPattern = patternFor(maxRisk, sorted.firstOrNull())
        )
    }

    private fun updateTrack(track: Track, det: Detection): Detection {
        val rawDistance = bboxDistanceM(det)
        val rawRisk = computeRisk(det)

        track.cx = EMA_ALPHA * det.cx + (1f - EMA_ALPHA) * track.cx
        track.cy = EMA_ALPHA * det.cy + (1f - EMA_ALPHA) * track.cy
        track.w = EMA_ALPHA * det.w + (1f - EMA_ALPHA) * track.w
        track.h = EMA_ALPHA * det.h + (1f - EMA_ALPHA) * track.h
        track.distanceM = EMA_ALPHA * rawDistance + (1f - EMA_ALPHA) * track.distanceM
        track.risk = EMA_ALPHA * rawRisk + (1f - EMA_ALPHA) * track.risk
        track.missed = 0

        return withMvpFields(
            det.copy(cx = track.cx, cy = track.cy, w = track.w, h = track.h),
            track.id,
            track.distanceM,
            track.risk
        )
    }

    private fun withMvpFields(
        det: Detection,
        trackId: Int,
        distanceM: Float,
        risk: Float
    ): Detection {
        return det.copy(
            trackId = trackId,
            riskScore = risk.coerceIn(0f, 1f),
            vibrationPattern = patternFor(risk, det).name,
            distanceM = distanceM
        )
    }

    private fun bboxDistanceM(det: Detection): Float {
        return VoicePolicy.calcDistBboxM(det.classKo, det.w, det.h).toFloat().coerceIn(0.2f, 15f)
    }

    private fun computeRisk(det: Detection): Float {
        val distanceM = bboxDistanceM(det)
        val area = det.w * det.h
        val centerWeight = 1f - min(0.6f, abs(det.cx - 0.5f) * 1.2f)
        val distanceWeight = when {
            distanceM <= 0.8f -> 1.0f
            distanceM <= 1.5f -> 0.85f
            distanceM <= 2.5f -> 0.65f
            distanceM <= 4.0f -> 0.35f
            else -> 0.15f
        }
        val classWeight = when {
            det.classKo in VoicePolicy.vehicleKo() -> 1.0f
            det.classKo in VoicePolicy.animalKo() -> 0.85f
            det.classKo in VoicePolicy.criticalKo() -> 0.9f
            det.classKo in VoicePolicy.cautionKo() -> 0.65f
            else -> 0.45f
        }
        val sizeBoost = min(0.25f, area * 1.8f)
        return (centerWeight * distanceWeight * classWeight + sizeBoost).coerceIn(0f, 1f)
    }

    private fun patternFor(risk: Float, det: Detection?): VibrationPattern {
        if (det != null && det.classKo in VoicePolicy.vehicleKo() && risk >= 0.55f) {
            return VibrationPattern.URGENT
        }
        if (det != null && det.classKo in VoicePolicy.everydayKo()) {
            return VibrationPattern.NONE
        }
        return when {
            risk >= 0.75f -> VibrationPattern.URGENT
            risk >= 0.55f -> VibrationPattern.DOUBLE
            risk >= 0.35f -> VibrationPattern.SHORT
            else -> VibrationPattern.NONE
        }
    }

    private fun iou(det: Detection, track: Track): Float {
        val ax1 = det.cx - det.w / 2f
        val ay1 = det.cy - det.h / 2f
        val ax2 = det.cx + det.w / 2f
        val ay2 = det.cy + det.h / 2f
        val bx1 = track.cx - track.w / 2f
        val by1 = track.cy - track.h / 2f
        val bx2 = track.cx + track.w / 2f
        val by2 = track.cy + track.h / 2f

        val ix = max(0f, min(ax2, bx2) - max(ax1, bx1))
        val iy = max(0f, min(ay2, by2) - max(ay1, by1))
        val inter = ix * iy
        val union = det.w * det.h + track.w * track.h - inter
        return if (union > 0f) inter / union else 0f
    }

    companion object {
        private const val IOU_MATCH_THRESHOLD = 0.25f
        private const val MAX_MISSED_FRAMES = 12
        private const val EMA_ALPHA = 0.55f
    }
}
