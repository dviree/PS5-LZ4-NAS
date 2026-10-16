# pkg-receiver with the Glass theme

[pkg-receiver](https://github.com/Loopayeh/pkg-sender) (Loopayeh, MIT, see
`LICENSE-pkg-sender`) is the PS5 payload the NAS page uses to install
packages. This folder only restyles its *pkg remote installer* page:

- `glass.css`: the Glass theme, applied after pkg-sender's own CSS.
- `glass.py path/to/payload/main.c`: adds `glass.css` to the page in
  `main.c`, appends `-glass` to the build and adds a `;` the newer page
  script is missing.

`.github/workflows/pkg-receiver.yml` builds it from a pinned pkg-sender
commit with the PS5 payload SDK and publishes `pkg-receiver.elf` in the
`pkg-receiver-glass` release. To try a newer pkg-sender, change
`PKG_SENDER_REF` there.
