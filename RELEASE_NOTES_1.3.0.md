# LZ4 Compression 1.3.0

The first release of LZ4 Compression: LZ4 compression for APR-EMU games, done
entirely on the PS5.

## LZ4 asset packs

- `Compress with LZ4` packs game data into seekable LZ4 blocks that APR-EMU
  reads while the game runs. Executables, system files and already-compressed
  media stay loose.
- Choose `Fast`, `Balanced` (LZ4 HC 9) or `Maximum` (LZ4 HC 12).
- Use the automatic profile or upload an `ampr_pack` TOML profile, including
  trace-generated ones and their include lists, from a PC or phone browser.
- Write the packed game next to the original, to the internal SSD or to
  external storage, or pack the folder in place to use the least free space.
- Every packed file is compared byte for byte with the original before
  anything is removed, and the pack-capable APR-EMU runtime is installed into
  `fakelib`.
- `Verify LZ4 Packs` checks every block against its CRC, and
  `Uncompress LZ4` gives you back the normal loose game.

## The app

- Black UI built for the PS5 screen. Your games run left to right like the
  home screen, and the highlighted game shows its status, size and progress
  underneath, with your recent jobs below.
- Every game opens its own page. The main action is up top and every other
  option sits below it as a card, grouped into Compress, Check, Restore,
  APR-EMU, Copy and move, and Delete.
- Compress, LZ4, uncompress, copy or move, delete, history and about each open
  as a full page. Browser back or Escape closes them.
- A launch splash while games are scanned, a done screen when a job finishes,
  and a closing screen when you shut the app down.
- Its own black `LZ4` tile and home-screen art.

It also does `.ffpfsc` compression and uncompression, exFAT/PFS images,
validate and repair, APR-EMU versions, and copy and move.

## Install

Load `lz4-compression.elf` from Payload Manager (or send it to port 9021),
then open the `LZ4 Compression` tile or `http://<PS5 IP>:5920`. Tested on
firmware 13.60 with kstuff and ShadowMountPlus 1.7.

It has its own tile (`PSLZ40001`), port (`5920`) and settings folder
(`/data/LZ4Compression`), so it can be installed next to Game Compressor.

Keep your original game until you've launched the packed version.
