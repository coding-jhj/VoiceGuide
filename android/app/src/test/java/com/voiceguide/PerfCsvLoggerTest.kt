package com.voiceguide

import org.junit.Assert.assertEquals
import org.junit.Test

class PerfCsvLoggerTest {
    @Test
    fun formatsHeaderAndCsvRowsWithStableColumns() {
        val sample = PerfSample(
            timestampMs = 123456789L,
            requestId = "vg-42",
            route = "on_device",
            model = "yolo11n_320.tflite",
            provider = "XNNPACK",
            fps = 12.345f,
            preprocessMs = 4L,
            inferMs = 71L,
            postprocessMs = 6L,
            totalMs = 81L,
            endToEndMs = 93L,
            rawObjects = 5,
            votedObjects = 3,
            mode = "일반"
        )

        assertEquals(
            "timestamp_ms,request_id,route,model,provider,fps,preprocess_ms,infer_ms,postprocess_ms,total_ms,e2e_ms,raw_objects,voted_objects,mode",
            PerfCsvLogger.header()
        )
        assertEquals(
            "123456789,vg-42,on_device,yolo11n_320.tflite,XNNPACK,12.35,4,71,6,81,93,5,3,일반",
            PerfCsvLogger.formatRow(sample)
        )
    }

    @Test
    fun escapesCsvTextFields() {
        val sample = PerfSample(
            timestampMs = 1L,
            requestId = "id,\"quoted\"",
            route = "on_device",
            model = "model,with,comma",
            provider = "GPU",
            fps = 8f,
            preprocessMs = 1L,
            inferMs = 2L,
            postprocessMs = 3L,
            totalMs = 6L,
            endToEndMs = 7L,
            rawObjects = 1,
            votedObjects = 1,
            mode = "질문"
        )

        assertEquals(
            "1,\"id,\"\"quoted\"\"\",on_device,\"model,with,comma\",GPU,8.00,1,2,3,6,7,1,1,질문",
            PerfCsvLogger.formatRow(sample)
        )
    }
}
