/*
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Host test for src/lzc_boot_files.c. Run from the repository root:
 *   make -f tests/host/Makefile boot-test
 */

#include "lzc_boot_files.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int failures;

#define CHECK(cond) do { \
    if(!(cond)) { fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #cond); failures++; } \
  } while(0)

static void
put(const char *path, const void *data, size_t size) {
  FILE *f = fopen(path, "wb");
  if(!f) { perror(path); exit(1); }
  fwrite(data, 1, size, f);
  fclose(f);
}

static void
make_eboot(const char *path, int plain, int runtime, int playgo) {
  /* Big enough that the strings straddle the 4 MiB read size. */
  size_t size = (4u << 20) + 64;
  char *b = calloc(1, size);
  memcpy(b, plain ? "\177ELF" : "\x54\x14\xf5\xee", 4);
  if(runtime) memcpy(b + (4u << 20) - 8, "RUNTIME_PATH=runtime\0", 21);
  if(playgo) memcpy(b + 4096, "libScePlayGo\0", 13);
  put(path, b, size);
  free(b);
}

static int
exists(const char *path) {
  struct stat st;
  return stat(path, &st) == 0;
}

int
main(void) {
  char base[] = "/tmp/lzc-boot-XXXXXX";
  char p[1024], game[1024], donor[1024], err[256];
  const char *sources[3];
  char games_src[1100];
  lzc_boot_report_t r;

  if(!mkdtemp(base)) { perror("mkdtemp"); return 1; }
  snprintf(game, sizeof(game), "%s/lib/PPSA16387-app0_HITMAN_3", base);
  snprintf(donor, sizeof(donor), "%s/lib/PPSA03671", base);
  snprintf(p, sizeof(p), "%s/lib", base); mkdir(p, 0777);
  mkdir(game, 0777);
  mkdir(donor, 0777);
  snprintf(p, sizeof(p), "%s/Runtime", game); mkdir(p, 0777);
  snprintf(p, sizeof(p), "%s/eboot.bin", game); make_eboot(p, 0, 1, 1);
  snprintf(p, sizeof(p), "%s/fakelib", donor); mkdir(p, 0777);
  snprintf(p, sizeof(p), "%s/fakelib/libScePlayGo.sprx", donor);
  put(p, "\x4f\x15\x3d\x1d....PlayGo PRX stub....", 27);
  snprintf(games_src, sizeof(games_src), "games:%s/lib", base);
  sources[0] = "/nonexistent";
  sources[1] = games_src;
  sources[2] = NULL;

  /* Report only: nothing changes. */
  CHECK(lzc_boot_files_check(game, 0, sources, &r, err, sizeof(err)) == 0);
  CHECK(r.runtime_case_wrong && !r.runtime_renamed);
  CHECK(!strcmp(r.runtime_found, "Runtime") && !strcmp(r.runtime_expected, "runtime"));
  CHECK(r.playgo_missing && !r.playgo_added && strstr(r.playgo_source, "PPSA03671"));
  CHECK(!r.eboot_plain_elf);
  snprintf(p, sizeof(p), "%s/Runtime", game); CHECK(exists(p));

  /* Repair. */
  CHECK(lzc_boot_files_check(game, 1, sources, &r, err, sizeof(err)) == 0);
  CHECK(r.runtime_renamed && r.playgo_added);
  snprintf(p, sizeof(p), "%s/runtime", game); CHECK(exists(p));
  snprintf(p, sizeof(p), "%s/fakelib/libScePlayGo.sprx", game);
  CHECK(lzc_boot_is_playgo_emu(p));

  /* Second pass finds nothing to do. */
  CHECK(lzc_boot_files_check(game, 1, sources, &r, err, sizeof(err)) == 0);
  CHECK(!r.runtime_case_wrong && !r.playgo_missing);

  /* No emulator anywhere: reported as missing with no source. */
  snprintf(p, sizeof(p), "%s/fakelib/libScePlayGo.sprx", game); unlink(p);
  snprintf(p, sizeof(p), "%s/fakelib/libScePlayGo.sprx", donor); unlink(p);
  CHECK(lzc_boot_files_check(game, 1, sources, &r, err, sizeof(err)) == 0);
  CHECK(r.playgo_missing && !r.playgo_added && !r.playgo_source[0]);

  /* Sony's own libScePlayGo in fakelib is left alone; a plain ELF eboot and
   * a game without PlayGo imports. */
  snprintf(p, sizeof(p), "%s/fakelib/libScePlayGo.sprx", game); put(p, "sony", 4);
  CHECK(lzc_boot_files_check(game, 1, sources, &r, err, sizeof(err)) == 0);
  CHECK(!r.playgo_missing);
  unlink(p);
  snprintf(p, sizeof(p), "%s/eboot.bin", game); make_eboot(p, 1, 0, 0);
  CHECK(lzc_boot_files_check(game, 1, sources, &r, err, sizeof(err)) == 0);
  CHECK(r.eboot_plain_elf && !r.playgo_missing && !r.runtime_case_wrong);

  {
    char cmd[1100];
    snprintf(cmd, sizeof(cmd), "rm -rf '%s'", base);
    if(system(cmd) != 0) fprintf(stderr, "cleanup failed: %s\n", base);
  }
  if(failures) {
    fprintf(stderr, "%d check(s) failed\n", failures);
    return 1;
  }
  printf("boot files: all checks passed\n");
  return 0;
}
