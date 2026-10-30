LZ4 Compression engine (`lz4-compression.elf`) from **PS5-LZ4-NAS**, with the original's
1.6 to 1.6.4 engine changes (theghostonline.dev, reviewed):

- **Title ID from the image:** an `.exfat`/`.ffpfsc` whose file name has no Title ID
  gets it from the image's own `sce_sys/param.json`.
- **Payload Manager 0.6:** payloads load from `payloads/local/<name>/` through
  `loadpayload` as a POST with `X-PLDMGR-Request` (GET for older Payload Managers).
- **IOI Glacier games** (`.rpkg` in `runtime/`) are never LZ4 packed: they read their
  packages straight from disk.
- **.ffpfsc found whatever it is called:** the engine matches an image through
  ShadowMountPlus's mount hash, not only by its file name.
- **CONTROL Resonant:** Remedy Northlight's `*.rmdtoc` pack tables stay loose ("the pack
  files seem to be missing" when packed).
- Community reports are read more leniently (free text, or the status at the end of the
  title).

Install: the NAS page's **Update available** / **Install ELF on PS5** button (or its
automatic update) puts it in Payload Manager at
`/data/pldmgr/payloads/local/lz4-compression/lz4-compression.elf` (0.6 and later) or
`/data/pldmgr/payloads/lz4-compression/lz4-compression.elf` (older).

Everything else is the original LZ4 Compression:
https://theghostonline.dev/theghostonline/PS5-LZ4-Compression/releases
