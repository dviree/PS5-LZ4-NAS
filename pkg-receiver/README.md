# pkg-receiver with the Glass theme

[pkg-receiver](https://github.com/Loopayeh/pkg-sender) (Loopayeh, MIT, see
`LICENSE-pkg-sender`) is the PS5 payload the NAS page uses to install
packages. This folder only restyles its *pkg remote installer* page:

- `glass.css`: the Glass theme, applied after pkg-sender's own CSS.
- `glass.js`: on the Images tab, one card per game with a choice of its
  images (**exFAT** / **FFPFSC** original or **LZ4**), from the catalog's
  `game` and `variant` fields.
- `glass.py path/to/payload/main.c`: adds both to the page in `main.c`,
  appends `-glass.N` to the build (bump `REV` on every change, so the NAS
  restarts a running receiver), closes the game window on Install so the
  answer shows, and adds a `;` the newer page script is missing.

`.github/workflows/pkg-receiver.yml` builds it from a pinned pkg-sender
commit with the PS5 payload SDK and publishes `pkg-receiver.elf` in the
`pkg-receiver-glass` release. To try a newer pkg-sender, change
`PKG_SENDER_REF` there.
