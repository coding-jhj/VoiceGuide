package com.voiceguide

import kotlin.math.abs
import kotlin.math.max

/**
 * 8-state linear Kalman filter for bounding box tracking.
 * State vector: [cx, cy, w, h, vcx, vcy, vw, vh] (normalized image coordinates, dt=1 frame).
 *
 * Observation matrix H = [I₄ | 0₄] — we only observe position/size, not velocity.
 * Transition  matrix F: pos += vel each frame (constant-velocity model).
 *
 * Noise weights follow the ByteTrack paper, scaled by bbox height so larger objects
 * allow more absolute pixel movement.
 */
internal class ByteTrackKalmanFilter {

    private val x = FloatArray(8)   // state
    private val P = FloatArray(64)  // 8×8 covariance, row-major

    private fun p(i: Int, j: Int) = P[i * 8 + j]
    private fun pSet(i: Int, j: Int, v: Float) { P[i * 8 + j] = v }

    fun initiate(cx: Float, cy: Float, w: Float, h: Float) {
        x[0] = cx; x[1] = cy; x[2] = w; x[3] = h
        x[4] = 0f; x[5] = 0f; x[6] = 0f; x[7] = 0f
        P.fill(0f)
        val pv = (2f * STD_POS * h) * (2f * STD_POS * h)
        val vv = (10f * STD_VEL * h) * (10f * STD_VEL * h)
        for (i in 0..3) pSet(i, i, pv)
        for (i in 4..7) pSet(i, i, vv)
    }

    /** Advance one frame. Modifies internal state in-place. */
    fun predict() {
        for (i in 0..3) x[i] += x[i + 4]   // pos += vel

        val h = max(x[3], 0.01f)
        val qPos = (STD_POS * h) * (STD_POS * h)
        val qVel = (STD_VEL * h) * (STD_VEL * h)

        // P_new = F·P·Fᵀ + Q  — exploit constant-velocity F structure
        val nP = FloatArray(64)
        for (i in 0..3) {
            for (j in 0..3) nP[i*8+j] = p(i,j) + p(i+4,j) + p(i,j+4) + p(i+4,j+4)
            for (j in 4..7) nP[i*8+j] = p(i,j) + p(i+4,j)
        }
        for (i in 4..7) {
            for (j in 0..3) nP[i*8+j] = p(i,j) + p(i,j+4)
            for (j in 4..7) nP[i*8+j] = p(i,j)
        }
        for (i in 0..3) nP[i*8+i] += qPos
        for (i in 4..7) nP[i*8+i] += qVel
        nP.copyInto(P)
    }

    /** Correct with a new bounding box observation. */
    fun update(mCx: Float, mCy: Float, mW: Float, mH: Float) {
        val rVar = (STD_POS * max(x[3], 0.01f)).toDouble().let { it * it }

        // S = H·P·Hᵀ + R  →  top-left 4×4 of P + R (diagonal)
        val S = Array(4) { i -> DoubleArray(4) { j -> p(i, j).toDouble() } }
        for (i in 0..3) S[i][i] += rVar
        val si = inv4(S) ?: return   // numerically singular — skip update

        // K = P·Hᵀ·S⁻¹  (8×4)
        val K = Array(8) { row ->
            DoubleArray(4) { col -> (0..3).sumOf { k -> p(row, k).toDouble() * si[k][col] } }
        }

        val inn = doubleArrayOf(
            mCx.toDouble() - x[0], mCy.toDouble() - x[1],
            mW.toDouble()  - x[2], mH.toDouble()  - x[3]
        )
        for (i in 0..7) x[i] += (0..3).sumOf { j -> K[i][j] * inn[j] }.toFloat()

        // P -= K·H·P  (H·P = first 4 rows of P)
        for (i in 0..7) for (j in 0..7) {
            P[i*8+j] -= (0..3).sumOf { m -> K[i][m] * p(m, j).toDouble() }.toFloat()
        }
    }

    fun state(): FloatArray = x.copyOf()

    // 4×4 Gauss-Jordan inverse with partial pivoting
    private fun inv4(m: Array<DoubleArray>): Array<DoubleArray>? {
        val a = Array(4) { i ->
            DoubleArray(8) { j -> if (j < 4) m[i][j] else if (i == j - 4) 1.0 else 0.0 }
        }
        for (col in 0..3) {
            val pivotRow = (col..3).maxByOrNull { abs(a[it][col]) } ?: return null
            if (abs(a[pivotRow][col]) < 1e-12) return null
            val tmp = a[col]; a[col] = a[pivotRow]; a[pivotRow] = tmp
            val scale = a[col][col]
            for (j in 0..7) a[col][j] /= scale
            for (row in 0..3) {
                if (row == col) continue
                val f = a[row][col]
                for (j in 0..7) a[row][j] -= f * a[col][j]
            }
        }
        return Array(4) { i -> DoubleArray(4) { j -> a[i][j + 4] } }
    }

    companion object {
        private const val STD_POS = 1f / 20f    // position noise weight (ByteTrack default)
        private const val STD_VEL = 1f / 160f   // velocity noise weight
    }
}
