# Host build of the AMPR LZ4 packer for testing against drakmor's
# ampr_pack.py (verify/inspect/list). Run from the repository root:
#   make -f tests/host/Makefile
# No PS5 SDK is needed.

CC ?= cc
PYTHON ?= python3
OUT := build/host
BIN := $(OUT)/ampr_pack_cli

SRCS := tests/host/ampr_pack_cli.c src/ampr_pack.c src/ampr_pack_profile.c \
  src/ampr_pack_toml.c src/ampr_pack_runtime.c src/ampr_index.c \
  third_party/lz4/lz4.c third_party/lz4/lz4hc.c \
  $(addprefix third_party/zlib/,adler32.c crc32.c zutil.c)
GEN := $(OUT)/ampr_runtime_blob.c

CFLAGS ?= -O2 -g
CFLAGS += -Wall -Werror -Isrc -Ithird_party/lz4 -Ithird_party/zlib -pthread

all: $(BIN)

$(GEN): third_party/ampr_emu/libSceAmpr.sprx tools/gen_binary_c.py
	mkdir -p $(OUT)
	$(PYTHON) tools/gen_binary_c.py --symbol lzc_ampr_runtime_blob \
	  --sha256 69e6c4d5e4f5fb83c9e01815db5861c4c75734acbf4595cafa50d4c218116d1a $< > $@

$(BIN): $(SRCS) $(GEN) src/*.h
	$(CC) $(CFLAGS) -o $@ $(SRCS) $(GEN)

clean:
	rm -rf $(OUT)

.PHONY: all clean
