package com.voiceguide

object YoloOutputFormat {
    fun isRaw(rows: Int, cols: Int): Boolean {
        return rows >= 5 && cols > 6
    }
}
