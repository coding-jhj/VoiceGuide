package com.voiceguide

import java.io.File
import java.util.Locale

data class PerfSample(
    val timestampMs: Long,
    val requestId: String,
    val route: String,
    val model: String,
    val provider: String,
    val fps: Float,
    val preprocessMs: Long,
    val inferMs: Long,
    val postprocessMs: Long,
    val totalMs: Long,
    val endToEndMs: Long,
    val rawObjects: Int,
    val votedObjects: Int,
    val mode: String
)

object PerfCsvLogger {
    private const val HEADER =
        "timestamp_ms,request_id,route,model,provider,fps,preprocess_ms,infer_ms,postprocess_ms,total_ms,e2e_ms,raw_objects,voted_objects,mode"

    fun header(): String = HEADER

    fun formatRow(sample: PerfSample): String = listOf(
        sample.timestampMs.toString(),
        escape(sample.requestId),
        escape(sample.route),
        escape(sample.model),
        escape(sample.provider),
        String.format(Locale.US, "%.2f", sample.fps),
        sample.preprocessMs.toString(),
        sample.inferMs.toString(),
        sample.postprocessMs.toString(),
        sample.totalMs.toString(),
        sample.endToEndMs.toString(),
        sample.rawObjects.toString(),
        sample.votedObjects.toString(),
        escape(sample.mode)
    ).joinToString(",")

    @Synchronized
    fun append(file: File, sample: PerfSample) {
        if (!file.exists() || file.length() == 0L) {
            file.parentFile?.mkdirs()
            file.appendText(header() + "\n", Charsets.UTF_8)
        }
        file.appendText(formatRow(sample) + "\n", Charsets.UTF_8)
    }

    private fun escape(value: String): String {
        if (value.none { it == ',' || it == '"' || it == '\n' || it == '\r' }) return value
        return "\"" + value.replace("\"", "\"\"") + "\""
    }
}
