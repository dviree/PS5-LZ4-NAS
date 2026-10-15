/*
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) 2026 Husam Osman.
 *
 * LZ4 Compression - files a game folder needs before it can boot from
 * ShadowMountPlus, whatever format it is in (loose dump or LZ4 packs).
 */

#pragma once

#include <stddef.h>

typedef struct lzc_boot_report {
  /* The engine folder named by RUNTIME_PATH= in eboot.bin (IOI's Glacier:
   * HITMAN 3, 007 First Light) exists only in another case, e.g. Runtime/
   * for runtime/. The PS5 is case-sensitive, so the game can't open
   * packagedefinition.txt and stops with SIGBUS at boot. */
  int runtime_case_wrong;
  int runtime_renamed;
  char runtime_found[64];
  char runtime_expected[64];
  /* The game imports libScePlayGo and fakelib has no PlayGo library.
   * scePlayGoOpen fails for a game run from a folder, and games that check
   * it stop with SIGBUS at boot. */
  int playgo_missing;
  int playgo_added;
  char playgo_source[512];
  /* eboot.bin is a plain ELF instead of a (fake-)signed SELF. */
  int eboot_plain_elf;
} lzc_boot_report_t;

/* Directories searched for a PlayGo emulator, in order. Each entry is either
 * a folder holding libScePlayGo.sprx itself, or, with a "games:" prefix, a
 * folder of game folders whose fakelib/ is checked. NULL-terminated. The
 * emulator isn't shipped with the app; it is taken from the console. */
extern const char *const lzc_boot_playgo_sources[];

/* Checks root (a game folder: eboot.bin, sce_sys/, ...). With repair set it
 * renames the runtime folder and copies a PlayGo emulator into fakelib/;
 * without it only reports. sources may be NULL for the defaults.
 * Returns 0, or -1 with a reason in err when a repair failed. */
int lzc_boot_files_check(const char *root, int repair,
                         const char *const *sources, lzc_boot_report_t *r,
                         char *err, size_t err_size);

/* 1 when the file is a PlayGo emulator (not Sony's libScePlayGo). */
int lzc_boot_is_playgo_emu(const char *path);
