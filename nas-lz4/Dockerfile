# ps5-lz4: LZ4 HC packing of PS5 games for APR-EMU, run entirely on the NAS.
# Build from the repository root:
#   docker build -t ps5-lz4:local -f nas-lz4/Dockerfile .

# James branches combined: low descriptors, read-only directories, kernel AIO.
FROM rust:1.99.0-slim-trixie@sha256:24e632c09342c20abf8312cf4f61430a911c01ed3a5e4c02b87292b1c39c5273 AS ng-runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates clang-19 lld-19 llvm-19 make curl unzip python3 patch \
    && rm -rf /var/lib/apt/lists/*
ENV PS5_PAYLOAD_SDK=/opt/ps5-payload-sdk LLVM_CONFIG=/usr/bin/llvm-config-19
ENV PATH=/usr/lib/llvm-19/bin:$PATH
ENV RUSTUP_TOOLCHAIN=1.99.0 RUSTUP_AUTO_INSTALL=0
RUN curl -fsSL --retry 3 https://github.com/ps5-payload-dev/sdk/releases/download/v0.43/ps5-payload-sdk.zip -o /tmp/sdk.zip \
    && echo 'a9cc9929f21b2b2c5d5b309f3bab4997067c45281c0622cf4838b1aecba66fcb  /tmp/sdk.zip' | sha256sum -c - \
    && unzip -q /tmp/sdk.zip -d /opt && rm /tmp/sdk.zip
RUN rustup component add rust-src
WORKDIR /runtime
RUN curl -fsSL --retry 3 https://codeload.github.com/jamesst20/ampr-emu-ng/tar.gz/83464d46972f913054831917abfa2851c85cb2f6 -o source.tar.gz \
    && echo '511a720c6587562ed53751832e68e7a5122dc8008fe2f322a803507daa5d6c79  source.tar.gz' | sha256sum -c - \
    && mkdir source && tar -xzf source.tar.gz --strip-components=1 -C source
COPY nas-lz4/patches/ampr-emu-ng-kernel-aio.patch /runtime/kernel-aio.patch
WORKDIR /runtime/source
RUN echo 'a60e1e38a64cafc7d416f54dc5b1aa73423a521e040caddcbc4da15e68ab4068  /runtime/kernel-aio.patch' | sha256sum -c - \
    && patch --fuzz=0 -p1 < /runtime/kernel-aio.patch \
    && cargo test --workspace --locked \
    && make verify AMPR_GIT_REV=83464d4-aio-fe97dce \
    && cp out/release/libSceAmpr.sprx /runtime/libSceAmpr-ng.sprx \
    && python3 -c 'import hashlib,json;from pathlib import Path;p=Path("/runtime/libSceAmpr-ng.sprx");Path("/runtime/ng-runtime.json").write_text(json.dumps({"name":"ampr-emu-ng 83464d4 + AIO fe97dce","commit":"83464d46972f913054831917abfa2851c85cb2f6","aio_commit":"fe97dce63ce1790081c4f539b0f9b4efc4b91a1b","patch_sha256":"a60e1e38a64cafc7d416f54dc5b1aa73423a521e040caddcbc4da15e68ab4068","sha256":hashlib.sha256(p.read_bytes()).hexdigest()}))'

FROM python:3.12-slim-bookworm AS build
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc libc6-dev make \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY src ./src
COPY third_party ./third_party
COPY tools/gen_binary_c.py ./tools/
COPY tests/host ./tests/host
# The upstream host Makefile uses -Werror; GCC (unlike clang) warns about an
# intentionally truncated 16-byte keyword buffer in ampr_pack_profile.c.
RUN CFLAGS="-O2 -Wno-error=format-truncation" make -f tests/host/Makefile PYTHON=python3 \
 && strip build/host/ampr_pack_cli \
 && build/host/ampr_pack_cli 2>&1 | grep -q 'verify <packed>'

FROM python:3.12-slim-bookworm AS forge
COPY nas-lz4/install-forge.py /tmp/install-forge.py
RUN python3 /tmp/install-forge.py

FROM python:3.12-slim-bookworm
ARG MKPFS_VERSION=1.1.0
# unrar (RARLAB's freeware, from Debian non-free): extracts multi-part RAR5
# archives in the library, checking every file's CRC.
RUN sed -i 's/^Components: main$/Components: main non-free/' /etc/apt/sources.list.d/debian.sources \
 && apt-get update \
 && apt-get install -y --no-install-recommends unrar libstdc++6 \
 && rm -rf /var/lib/apt/lists/* \
 && unrar | head -1
RUN pip install --no-cache-dir "mkpfs==${MKPFS_VERSION}" \
 && mkpfs -V | grep -q "${MKPFS_VERSION}" \
 && python3 -c "from mkpfs.exfat import ExfatReader; import cryptography"
COPY --from=build /src/build/host/ampr_pack_cli /usr/local/bin/ampr_pack_cli
COPY --from=forge /usr/local/bin/ps5-dump-forge /usr/local/bin/ps5-dump-forge
COPY --from=forge /opt/ps5lz4/ /opt/ps5lz4/
COPY --from=ng-runtime /runtime/libSceAmpr-ng.sprx /opt/ps5lz4/libSceAmpr-ng.sprx
COPY --from=ng-runtime /runtime/ng-runtime.json /opt/ps5lz4/ng-runtime.json
COPY --from=ng-runtime /runtime/source.tar.gz /opt/ps5lz4/licenses/ampr-emu-ng-83464d4/source.tar.gz
COPY --from=ng-runtime /runtime/source/LICENSE /opt/ps5lz4/licenses/ampr-emu-ng-83464d4/LICENSE
COPY --from=ng-runtime /runtime/kernel-aio.patch /opt/ps5lz4/licenses/ampr-emu-ng-83464d4/kernel-aio.patch
COPY profiles /opt/ps5lz4/profiles
COPY compat/compat.json /opt/ps5lz4/compat.json
COPY nas-lz4/ps5lz4.py /opt/ps5lz4/ps5lz4.py
COPY nas-lz4/ui.html /opt/ps5lz4/ui.html
COPY nas-lz4/store.html /opt/ps5lz4/store.html
COPY nas-lz4/ps5regist.py /opt/ps5lz4/ps5regist.py
COPY app/lz4-compression/version.js /opt/ps5lz4/lz4c-version.js
COPY third_party/ampr_emu/libSceAmpr.sprx /opt/ps5lz4/libSceAmpr.sprx
COPY nas-lz4/entrypoint.sh /usr/local/bin/ps5lz4-entrypoint
COPY nas-lz4/busy.sh /usr/local/bin/ps5lz4-busy
RUN printf '#!/bin/sh\nexec python3 /opt/ps5lz4/ps5lz4.py "$@"\n' > /usr/local/bin/ps5lz4 \
 && chmod 755 /usr/local/bin/ps5lz4 /opt/ps5lz4/ps5lz4.py \
 && chmod -R a+rX /opt/ps5lz4
ENV PS5LZ4_LIBRARY=/library \
    PS5LZ4_OUTPUT=/output \
    PS5LZ4_STATE=/state \
    PS5LZ4_PACKER=/usr/local/bin/ampr_pack_cli \
    PS5LZ4_PROFILES=/opt/ps5lz4/profiles \
    PYTHONUNBUFFERED=1
LABEL org.opencontainers.image.title="ps5-lz4" \
      org.opencontainers.image.description="LZ4 HC packing of PS5 games for APR-EMU on a NAS"
LABEL org.opencontainers.image.source="https://github.com/dviree/PS5-LZ4-NAS"
# Resume an unfinished queue, then idle until `docker exec ps5-lz4 ps5lz4 ...`.
CMD ["/usr/local/bin/ps5lz4-entrypoint"]
