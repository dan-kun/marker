#!/usr/bin/env python3
"""Generate flatpak/vendor-sources.json from the pinned preview libraries.

Flatpak builds have no network access, so every vendor file is declared as
a source with its URL and SHA-256. Run this after changing
scripts/vendor-files.txt or scripts/vendor.sha256; pass --check to verify
that the generated file is up to date (used by the tests).
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT = os.path.join(ROOT, "flatpak", "vendor-sources.json")
WEB_DIR = "marker/data/web"


def build() -> str:
    with open(os.path.join(ROOT, "scripts", "vendor.sha256"), encoding="utf-8") as f:
        sums = {name: digest for digest, name in (line.split() for line in f if line.strip())}

    sources = []
    with open(os.path.join(ROOT, "scripts", "vendor-files.txt"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            dest, package, path = line.split("|")
            sources.append({
                "type": "file",
                "url": f"https://cdn.jsdelivr.net/npm/{package}/{path}",
                "sha256": sums[dest],
                "dest": os.path.join(WEB_DIR, os.path.dirname(dest)),
                "dest-filename": os.path.basename(dest),
            })
    return json.dumps(sources, indent=2) + "\n"


def main() -> int:
    content = build()
    if "--check" in sys.argv[1:]:
        try:
            with open(OUTPUT, encoding="utf-8") as f:
                current = f.read()
        except OSError:
            current = None
        if current != content:
            print(f"{OUTPUT} is out of date: run scripts/flatpak-sources.py", file=sys.stderr)
            return 1
        return 0
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
