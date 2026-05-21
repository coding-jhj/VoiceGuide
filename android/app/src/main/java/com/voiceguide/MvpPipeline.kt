package com.voiceguide

import android.util.Log
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

enum class VibrationPattern { NONE, SHORT, DOUBLE, URGENT }

data class MvpFrame(
    val detections: List<Detection>,
    val maxRisk: Float,
    val vibrationPattern: VibrationPattern
)

/**
 * ByteTrack-style multi-object tracker for Android.
 *
 * Replaces the previous EMA-only smoother with a full Kalman-filter + two-stage IoU association.
 * Runs entirely on-device; no external libraries required.
 *
 * Algorithm:
 *   1. Predict all track positions one frame forward via Kalman filter.
 *   2. Stage-1: match active tracks ↔ high-confidence detections (IoU greedy).
 *   3. Stage-2: match remaining active tracks ↔ low-confidence detections.
 *   4. Stage-3: match lost tracks ↔ remaining high-confidence detections.
 *   5. Unmatched high-confidence detections → new tentative tracks.
 *   6. NEW tracks that fail to match in their second frame are discarded (noise filter).
 */
class MvpPipeline {

    private enum class TrackState { NEW, TRACKED, LOST, REMOVED }

    private class Track(
        val id: Int,
        val cls: String,
        det: Detection,
        initDistM: Float,
        initRisk: Float
    ) {
        val kf = ByteTrackKalmanFilter()
        var state     = TrackState.NEW
        var missedFrames = 0
        var isActivated  = false
        var confidence   = det.confidence
        var distanceM    = initDistM
        var risk         = initRisk

        init { kf.initiate(det.cx, det.cy, det.w, det.h) }

        /** Returns the Kalman-predicted [cx, cy, w, h] for IoU computation. */
        fun predictedBox(): FloatArray = kf.state().let { s ->
            floatArrayOf(s[0], s[1], max(0.001f, s[2]), max(0.001f, s[3]))
        }
    }

    private val tracks = mutableListOf<Track>()
    private var nextId = 1

    @Synchronized
    fun update(detections: List<Detection>): MvpFrame {
        Log.d("VG_BYTETRACK", "update: input=${detections.size} dets, tracks=${tracks.size}")
        val highDets = detections.filter { it.confidence >= HIGH_CONF }
        val lowDets  = detections.filter { it.confidence >= LOW_CONF && it.confidence < HIGH_CONF }

        // Predict all tracks one step forward
        tracks.forEach { it.kf.predict() }

        val active = tracks.filter { it.state == TrackState.TRACKED || it.state == TrackState.NEW }
        val lost   = tracks.filter { it.state == TrackState.LOST }

        // Stage 1: active tracks ↔ high-confidence detections
        val a1 = associate(active, highDets, IOU_HIGH)
        for ((ti, di) in a1.matched) applyUpdate(active[ti], highDets[di])

        // Stage 2: unmatched active tracks ↔ low-confidence detections
        val remainActive = a1.unmatchedTracks.map { active[it] }
        val a2 = associate(remainActive, lowDets, IOU_LOW)
        for ((ti, di) in a2.matched) applyUpdate(remainActive[ti], lowDets[di])

        // Unmatched active tracks → lost (NEW ones never confirmed → discard immediately)
        for (i in a2.unmatchedTracks) {
            val t = remainActive[i]
            if (t.state == TrackState.NEW) t.state = TrackState.REMOVED
            else { t.state = TrackState.LOST; t.missedFrames++ }
        }

        // Stage 3: lost tracks ↔ remaining high-confidence detections
        val unassignedHigh = a1.unmatchedDets.map { highDets[it] }
        val a3 = associate(lost, unassignedHigh, IOU_HIGH)
        for ((ti, di) in a3.matched) applyUpdate(lost[ti], unassignedHigh[di])

        // Remaining lost tracks: age them; remove if too old
        val matchedLostIdx = a3.matched.map { it.first }.toSet()
        for ((i, t) in lost.withIndex()) {
            if (i !in matchedLostIdx) {
                t.missedFrames++
                if (t.missedFrames > MAX_LOST_FRAMES) t.state = TrackState.REMOVED
            }
        }

        // Remaining unmatched high-confidence detections → new tentative tracks
        for (det in a3.unmatchedDets.map { unassignedHigh[it] }) {
            val d = bboxDistanceM(det)
            tracks.add(Track(nextId++, det.classKo, det, d, computeRisk(det, d)))
        }

        tracks.removeAll { it.state == TrackState.REMOVED }

        val output = tracks
            .filter { it.state == TrackState.TRACKED || it.state == TrackState.NEW }
            .map { trackToDetection(it) }
            .sortedWith(compareByDescending<Detection> { it.riskScore }.thenByDescending { it.w * it.h })

        val maxRisk = output.maxOfOrNull { it.riskScore } ?: 0f
        val vp = output.firstOrNull()?.let { patternFor(maxRisk, it.classKo) } ?: VibrationPattern.NONE
        Log.d("VG_BYTETRACK", "output: ${output.size} tracks, maxRisk=%.2f, vp=$vp".format(maxRisk))
        if (output.isNotEmpty()) Log.d("VG_BYTETRACK", "  top: ${output[0].classKo} conf=%.2f risk=%.2f".format(output[0].confidence, output[0].riskScore))
        return MvpFrame(output, maxRisk, vp)
    }

    private fun applyUpdate(track: Track, det: Detection) {
        track.kf.update(det.cx, det.cy, det.w, det.h)
        track.confidence  = det.confidence
        track.distanceM   = bboxDistanceM(det)
        track.risk        = computeRisk(det, track.distanceM)
        track.missedFrames = 0
        track.state        = TrackState.TRACKED
        track.isActivated  = true
    }

    private fun trackToDetection(track: Track): Detection {
        val s = track.kf.state()
        return Detection(
            classKo          = track.cls,
            confidence       = track.confidence,
            cx               = s[0],
            cy               = s[1],
            w                = max(0.001f, s[2]),
            h                = max(0.001f, s[3]),
            trackId          = track.id,
            riskScore        = track.risk.coerceIn(0f, 1f),
            vibrationPattern = patternFor(track.risk, track.cls).name,
            distanceM        = track.distanceM
        )
    }

    // ── IoU association ──────────────────────────────────────────────────────

    private data class Assoc(
        val matched: List<Pair<Int, Int>>,
        val unmatchedTracks: List<Int>,
        val unmatchedDets: List<Int>
    )

    private fun associate(tracks: List<Track>, dets: List<Detection>, iouThr: Float): Assoc {
        if (tracks.isEmpty()) return Assoc(emptyList(), emptyList(), dets.indices.toList())
        if (dets.isEmpty())   return Assoc(emptyList(), tracks.indices.toList(), emptyList())

        val pairs = mutableListOf<Triple<Float, Int, Int>>()
        for (ti in tracks.indices) {
            val box = tracks[ti].predictedBox()
            for (di in dets.indices) {
                val iouVal = iou(box, dets[di])
                if (iouVal >= iouThr) pairs.add(Triple(iouVal, ti, di))
            }
        }
        pairs.sortByDescending { it.first }

        val usedT = mutableSetOf<Int>()
        val usedD = mutableSetOf<Int>()
        val matched = mutableListOf<Pair<Int, Int>>()
        for ((_, ti, di) in pairs) {
            if (ti !in usedT && di !in usedD) {
                matched.add(ti to di); usedT += ti; usedD += di
            }
        }
        return Assoc(
            matched,
            tracks.indices.filter { it !in usedT },
            dets.indices.filter { it !in usedD }
        )
    }

    private fun iou(pred: FloatArray, det: Detection): Float {
        val ax1 = pred[0] - pred[2] / 2f; val ay1 = pred[1] - pred[3] / 2f
        val ax2 = pred[0] + pred[2] / 2f; val ay2 = pred[1] + pred[3] / 2f
        val bx1 = det.cx - det.w / 2f;    val by1 = det.cy - det.h / 2f
        val bx2 = det.cx + det.w / 2f;    val by2 = det.cy + det.h / 2f
        val ix = max(0f, min(ax2, bx2) - max(ax1, bx1))
        val iy = max(0f, min(ay2, by2) - max(ay1, by1))
        val inter = ix * iy
        val union = pred[2] * pred[3] + det.w * det.h - inter
        return if (union > 0f) inter / union else 0f
    }

    // ── Risk / distance / vibration ──────────────────────────────────────────

<<<<<<< HEAD
    private fun bboxDistanceM(det: Detection): Float =
        VoicePolicy.calcDistBboxM(det.classKo, det.w, det.h).toFloat().coerceIn(0.2f, 15f)
=======
    private fun bboxDistanceM(det: Detection): Float {
        return VoicePolicy.calcDistBboxM(det.classKo, det.w, det.h).toFloat().coerceIn(0.2f, 15f)
    }
>>>>>>> main

    private fun computeRisk(det: Detection, distanceM: Float): Float {
        val area = det.w * det.h
        val centerWeight = 1f - min(0.6f, abs(det.cx - 0.5f) * 1.2f)
        val distWeight = when {
            distanceM <= 0.8f -> 1.0f
            distanceM <= 1.5f -> 0.85f
            distanceM <= 2.5f -> 0.65f
            distanceM <= 4.0f -> 0.35f
            else              -> 0.15f
        }
        val classWeight = when {
            det.classKo in VoicePolicy.vehicleKo()  -> 1.0f
            det.classKo in VoicePolicy.animalKo()   -> 0.85f
            det.classKo in VoicePolicy.criticalKo() -> 0.9f
            det.classKo in VoicePolicy.cautionKo()  -> 0.65f
            else                                    -> 0.45f
        }
        return (centerWeight * distWeight * classWeight + min(0.25f, area * 1.8f)).coerceIn(0f, 1f)
    }

    private fun patternFor(risk: Float, classKo: String): VibrationPattern {
        if (classKo in VoicePolicy.vehicleKo() && risk >= 0.55f) return VibrationPattern.URGENT
        if (classKo in VoicePolicy.everydayKo()) return VibrationPattern.NONE
        return when {
            risk >= 0.75f -> VibrationPattern.URGENT
            risk >= 0.55f -> VibrationPattern.DOUBLE
            risk >= 0.35f -> VibrationPattern.SHORT
            else          -> VibrationPattern.NONE
        }
    }

    companion object {
        private const val HIGH_CONF      = 0.20f  // min confidence to start a new track (below detector confThreshold=0.25f)
        private const val LOW_CONF       = 0.20f  // min confidence to update an existing track (no-op; detector filters at 0.30)
        private const val IOU_HIGH       = 0.25f  // IoU threshold for stage-1/3 matching
        private const val IOU_LOW        = 0.15f  // IoU threshold for stage-2 matching
        private const val MAX_LOST_FRAMES = 12    // frames before a lost track is removed
    }
}
