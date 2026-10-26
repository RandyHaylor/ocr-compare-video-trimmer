"""Command line entry point. With no arguments it opens the web UI."""

from __future__ import annotations

import argparse
import sys

from . import core


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ocr-compare-video-trimmer",
        description="Cut the static stretches out of a screen recording. Run with no arguments for the web UI.",
    )
    parser.add_argument("video")
    parser.add_argument("--interval", type=float, default=5, help="seconds between stills (default 5)")
    parser.add_argument("--threshold", type=float, default=0.95,
                        help="OCR text similarity at or above which two stills count as unchanged (default 0.95)")
    parser.add_argument("--min-gaps", type=int, default=2,
                        help="unchanged gaps in a row before a stretch is cut (default 2, minimum 2)")
    parser.add_argument("--speed", type=float, default=1.0, help="playback speed of the output (default 1.0)")
    parser.add_argument("--fade", type=float, default=0.25, help="fade length in seconds (default 0.25)")
    parser.add_argument("--no-fade-out", action="store_true", help="don't fade out before each cut")
    parser.add_argument("--no-fade-in", action="store_true", help="don't fade in after each cut")
    parser.add_argument("--output", choices=["joined", "individual", "both"], default="joined")
    parser.add_argument("--out-dir", help="folder for the ocr/ and videos/ subfolders "
                                          "(default: a folder named after the video, next to it)")
    parser.add_argument("--plan-only", action="store_true", help="list the cuts without rendering")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        from .ui import launch
        launch()
        return 0

    args = parse_args(argv)
    analysis = core.analyze(args.video, args.interval, args.out_dir,
                            progress=lambda done, total: print(f"\rOCR {done}/{total}", end="", flush=True))
    print()
    cuts = core.plan(analysis, args.threshold, args.min_gaps)
    for start, end in cuts:
        print(f"cut {core.format_time(start)} - {core.format_time(end)} ({core.format_time(end - start)})")
    print(core.summary(analysis, cuts, args.speed))
    if args.plan_only:
        return 0
    for path in core.render(analysis, core.keeps(cuts, analysis.duration), args.out_dir, args.output,
                            args.speed, args.fade, not args.no_fade_in, not args.no_fade_out):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
