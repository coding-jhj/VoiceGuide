package com.voiceguide

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class YoloOutputFormatTest {
    @Test
    fun treatsCocoRawYoloOutputAsRaw() {
        assertTrue(YoloOutputFormat.isRaw(rows = 84, cols = 2100))
    }

    @Test
    fun treatsFineTunedRawYoloOutputWithExtraClassesAsRaw() {
        assertTrue(YoloOutputFormat.isRaw(rows = 86, cols = 2100))
    }

    @Test
    fun treatsEndToEndNmsOutputAsNotRaw() {
        assertFalse(YoloOutputFormat.isRaw(rows = 300, cols = 6))
    }
}
