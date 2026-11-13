#!/usr/bin/env python3
"""Build a Kobalt X-Ray sidecar from a source file written by chapter.

    python tools/make_sidecar.py BOOK.epub SOURCE.json            # writes BOOK.xray.json beside SOURCE
    python tools/make_sidecar.py BOOK.epub SOURCE.json -o FOLDER  # ... into FOLDER
    python tools/make_sidecar.py BOOK.epub SOURCE.json -n NAME    # ... as NAME.xray.json
    python tools/make_sidecar.py BOOK.epub --chapters             # only list chapters and percentages

The work is done by xraygen/sidecar.py, whose docstring describes the source format.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from xraygen.sidecar import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
