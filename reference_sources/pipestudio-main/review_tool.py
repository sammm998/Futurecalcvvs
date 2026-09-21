#!/usr/bin/env python3

import argparse
import os
import sys


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    os.chdir(here)
    sys.path.insert(0, here)

    ap = argparse.ArgumentParser(
        description="Pipe Review Studio - review the CV pipeline's output")
    ap.add_argument("pdf", help="input drawing, e.g. clean/W-50-1-A-0134.pdf")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true",
                    help="do not open a browser window")
    args = ap.parse_args()

    if not os.path.exists(args.pdf):
        ap.error(f"no such file: {args.pdf}")

    from reviewapp import serve
    serve(args.pdf, port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
