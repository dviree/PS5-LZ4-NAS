/*
 * LZ4 Compression - keep PS5 idle/display timers reset during operations.
 */

#pragma once

void lzc_power_guard_start(void);

/* Keep the PS5 out of rest mode for the next `seconds` (at most an hour),
 * e.g. while a NAS sends a game over FTP; 0 lets it rest again. Returns the
 * seconds left. */
long lzc_power_guard_hold(long seconds);
