package com.voiceguide

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class VoiceGuideLabelsTest {
    @Test
    fun keepsDoorAndStairsAfterCoco80() {
        assertEquals("계단", voiceGuideClassKo(80))
        assertEquals("문", voiceGuideClassKo(81))
    }

    @Test
    fun keepsUnknownClassIdsFilteredOut() {
        assertNull(voiceGuideClassKo(82))
    }
}
