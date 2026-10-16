#!/usr/bin/env python3
"""Give pkg-receiver's page (Loopayeh/pkg-sender, payload/main.c) the Glass
theme of the PS5-LZ4 NAS page.

    python3 glass.py path/to/payload/main.c

Edits main.c in place: glass.css goes in as C string lines right before the
page's </style>, so pkg-sender's own CSS stays and these rules win; the build
gets a "-glass" suffix; and a missing ";" in the page script (which stops the
whole script in newer sources) is added. Nothing else changes.
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def c_lines(css: str) -> str:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out = []
    for line in css.splitlines():
        line = line.strip()
        if line:
            out.append('"' + line.replace("\\", "\\\\").replace('"', '\\"') + '"\n')
    return "".join(out)


def main() -> None:
    src = Path(sys.argv[1])
    text = src.read_text()
    if "glass.css" in text:
        sys.exit("main.c already has the Glass theme")

    end = '</style></head><body><div class=wrap>"'
    if text.count(end) != 1:
        sys.exit("can't find the end of the page CSS in main.c")
    text = text.replace(end, '"\n/* glass.css (PS5-LZ4 NAS) */\n' + c_lines((HERE / "glass.css").read_text())
                        + '"' + end, 1)

    build = re.search(r'(#define RECEIVER_BUILD ")([^"]+)(")', text)
    if not build:
        sys.exit("can't find RECEIVER_BUILD in main.c")
    text = text[:build.start()] + build.group(1) + build.group(2) + "-glass" + build.group(3) + text[build.end():]

    text = text.replace("replaceChild(s,t);}},true)\"\n\"function card(", "replaceChild(s,t);}},true);\"\n\"function card(")
    src.write_text(text)
    print(f"Glass theme added to {src} (build {build.group(2)}-glass)")


if __name__ == "__main__":
    main()
