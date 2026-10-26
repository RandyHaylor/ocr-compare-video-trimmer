"""Find and cut the static stretches of a screen recording.

1. analyze(): grab a still every `interval` seconds, OCR each one, and save the stills and text
   in an ocr/ folder (<stem>-ocr.txt to read, <stem>-ocr.json as a cache so re-planning skips
   the OCR).
2. plan(): two consecutive stills whose OCR text is at least `threshold` similar are unchanged.
   A run of `min_gaps` or more unchanged gaps in a row is static: its first and last interval
   are kept and the middle is cut.
3. render(): write the kept segments to a videos/ folder as one joined file, individual files,
   or both, with optional fades at each cut and an optional speed change.
"""

from __future__ import annotations

import difflib
import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
FPS = 30


@dataclass
class Analysis:
    video: str
    video_size: int
    video_mtime: float
    duration: float
    interval: float
    has_audio: bool
    texts: list[str]
    similarities: list[float]  # similarities[i] compares still i with still i + 1


def format_time(seconds: float) -> str:
    seconds = round(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr[-2000:]}")
    return result


def probe(video: Path) -> tuple[float, bool]:
    """Duration in seconds and whether the video has an audio stream."""
    stderr = subprocess.run([FFMPEG, "-hide_banner", "-i", str(video)],
                            capture_output=True, text=True).stderr
    match = re.search(r"Duration: (\d+):(\d+):([\d.]+)", stderr)
    if match:
        duration = int(match[1]) * 3600 + int(match[2]) * 60 + float(match[3])
    else:  # some recorders don't write a duration; decode to measure it
        _, duration = imageio_ffmpeg.count_frames_and_secs(str(video))
    return duration, re.search(r"Stream #.*: Audio:", stderr) is not None


@dataclass
class OutputPaths:
    ocr_dir: Path     # stills + OCR text (the cache)
    videos_dir: Path  # rendered videos
    txt: Path
    json: Path


def output_paths(video: str | Path, out_dir: str | Path | None = None) -> OutputPaths:
    """Default layout: <video folder>/<video name>/ocr and .../videos. `out_dir` replaces
    <video folder>/<video name>."""
    video = Path(video).resolve()
    base = Path(out_dir) if out_dir else video.parent / video.stem
    ocr_dir = base / "ocr"
    return OutputPaths(ocr_dir, base / "videos", ocr_dir / f"{video.stem}-ocr.txt",
                       ocr_dir / f"{video.stem}-ocr.json")


def clear_cache(video: str | Path, out_dir: str | Path | None = None) -> Path:
    """Delete the stills and OCR text so the next analyze() redoes the OCR."""
    ocr_dir = output_paths(video, out_dir).ocr_dir
    shutil.rmtree(ocr_dir, ignore_errors=True)
    return ocr_dir


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def analyze(video: str | Path, interval: float = 5, out_dir: str | Path | None = None,
            progress=None) -> Analysis:
    """OCR a still every `interval` seconds. Reuses the saved result if the video and interval
    are unchanged. `progress(done, total)` is called after each still."""
    video = Path(video).resolve()
    if not video.is_file():
        raise FileNotFoundError(f"No video at {video}")
    paths = output_paths(video, out_dir)
    stat = video.stat()

    if paths.json.is_file():
        cached = Analysis(**json.loads(paths.json.read_text(encoding="utf-8")))
        if (cached.interval, cached.video_size, cached.video_mtime) == (interval, stat.st_size, stat.st_mtime):
            return cached

    import easyocr  # slow import; only needed when OCR actually runs
    import torch

    duration, has_audio = probe(video)
    reader = easyocr.Reader(["en"], gpu=torch.cuda.is_available(), verbose=False)
    clear_cache(video, out_dir)  # drop stills from an earlier interval
    paths.ocr_dir.mkdir(parents=True)
    _run([FFMPEG, "-hide_banner", "-i", str(video), "-vf", f"fps=1/{interval}",
          str(paths.ocr_dir / "s%05d.png")])
    stills = sorted(paths.ocr_dir.glob("s*.png"))
    texts = []
    for done, still in enumerate(stills, start=1):
        texts.append("\n".join(text for _box, text, _conf in reader.readtext(str(still))))
        if progress:
            progress(done, len(stills))

    analysis = Analysis(
        video=str(video), video_size=stat.st_size, video_mtime=stat.st_mtime,
        duration=duration, interval=interval, has_audio=has_audio, texts=texts,
        similarities=[similarity(a, b) for a, b in zip(texts, texts[1:])],
    )
    with paths.txt.open("w", encoding="utf-8") as out:
        for index, (still, text) in enumerate(zip(stills, texts)):
            out.write(f"=== [{format_time(index * interval)}] {still.name} ===\n{text}\n\n")
    paths.json.write_text(json.dumps(asdict(analysis)), encoding="utf-8")
    return analysis


def plan(analysis: Analysis, threshold: float, min_gaps: int = 2) -> list[tuple[float, float]]:
    """Return the (start, end) seconds to cut."""
    step = analysis.interval
    min_gaps = max(2, min_gaps)  # with fewer than 2 gaps there is nothing between the kept ends
    cuts, run_start, run_length = [], 0, 0
    for index, ratio in enumerate(analysis.similarities + [-1.0]):  # sentinel closes the last run
        if ratio >= threshold:
            if run_length == 0:
                run_start = index
            run_length += 1
            continue
        if run_length >= min_gaps:
            end = min((run_start + run_length) * step, analysis.duration)
            cuts.append(((run_start + 1) * step, end))
        run_length = 0
    return cuts


def keeps(cuts: list[tuple[float, float]], duration: float) -> list[tuple[float, float]]:
    """The segments left after removing `cuts`."""
    segments, start = [], 0.0
    for cut_start, cut_end in cuts:
        if cut_start > start:
            segments.append((start, cut_start))
        start = cut_end
    if duration > start:
        segments.append((start, duration))
    return segments


def _atempo(speed: float) -> str:
    """atempo only takes 0.5-2.0 on older ffmpeg builds, so chain it."""
    factors = []
    while speed > 2.0:
        factors.append(2.0)
        speed /= 2.0
    while speed < 0.5:
        factors.append(0.5)
        speed /= 0.5
    factors.append(speed)
    return ",".join(f"atempo={factor}" for factor in factors)


def _segment_filters(index: int, length: float, has_audio: bool, speed: float,
                     fade: float, fade_in: bool, fade_out: bool) -> str:
    """Filter chains for input `index` -> [v{index}] and [a{index}]."""
    length /= speed
    # Screen recorders only write frames when the screen changes; a constant frame rate gives the
    # fades frames to darken. H.264 needs even dimensions and yuv420p.
    video = [f"setpts=(PTS-STARTPTS)/{speed}", f"fps={FPS}",
             "scale=trunc(iw/2)*2:trunc(ih/2)*2", "format=yuv420p"]
    audio = ["asetpts=PTS-STARTPTS", _atempo(speed)] if speed != 1 else ["asetpts=PTS-STARTPTS"]
    if fade_in:
        video.append(f"fade=t=in:st=0:d={fade}")
        audio.append(f"afade=t=in:st=0:d={fade}")
    if fade_out:
        video.append(f"fade=t=out:st={max(0.0, length - fade)}:d={fade}")
        audio.append(f"afade=t=out:st={max(0.0, length - fade)}:d={fade}")
    chains = f"[{index}:v]{','.join(video)}[v{index}]"
    if has_audio:
        chains += f";[{index}:a]{','.join(audio)}[a{index}]"
    return chains


def _encode_args(video: Path) -> tuple[list[str], list[str], str]:
    if video.suffix.lower() == ".webm":
        return (["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-row-mt", "1", "-cpu-used", "4"],
                ["-c:a", "libopus"], ".webm")
    return ["-c:v", "libx264", "-crf", "20", "-preset", "veryfast"], ["-c:a", "aac"], ".mp4"


def render(analysis: Analysis, segments: list[tuple[float, float]], out_dir: str | Path | None = None,
           mode: str = "joined", speed: float = 1.0, fade: float = 0.25,
           fade_in: bool = True, fade_out: bool = True) -> list[Path]:
    """Write the kept `segments` as "joined", "individual" or "both". Fades are applied only at
    cuts, never at the very start or end of the video. Returns the written files."""
    video = Path(analysis.video)
    out_dir = output_paths(video, out_dir).videos_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    video_args, audio_args, ext = _encode_args(video)
    audio_args = audio_args if analysis.has_audio else ["-an"]
    last = len(segments) - 1
    written = []

    def filters(input_index: int, segment_index: int) -> str:
        start, end = segments[segment_index]
        return _segment_filters(input_index, end - start, analysis.has_audio, speed, fade,
                                fade_in and segment_index > 0, fade_out and segment_index < last)

    def inputs(indexes) -> list[str]:
        args = []
        for i in indexes:
            start, end = segments[i]
            args += ["-ss", str(start), "-t", str(end - start), "-i", str(video)]
        return args

    if mode in ("individual", "both"):
        for i in range(len(segments)):
            path = out_dir / f"{video.stem}-part{i + 1:02d}{ext}"
            maps = ["-map", "[v0]"] + (["-map", "[a0]"] if analysis.has_audio else [])
            _run([FFMPEG, "-hide_banner", "-y", *inputs([i]), "-filter_complex", filters(0, i),
                  *maps, *video_args, *audio_args, str(path)])
            written.append(path)

    if mode in ("joined", "both"):
        path = out_dir / f"{video.stem}-trimmed{ext}"
        count = len(segments)
        labels = "".join(f"[v{i}][a{i}]" if analysis.has_audio else f"[v{i}]" for i in range(count))
        concat = f"{labels}concat=n={count}:v=1:a={int(analysis.has_audio)}[v]" + ("[a]" if analysis.has_audio else "")
        graph = ";".join(filters(i, i) for i in range(count)) + ";" + concat
        maps = ["-map", "[v]"] + (["-map", "[a]"] if analysis.has_audio else [])
        _run([FFMPEG, "-hide_banner", "-y", *inputs(range(count)), "-filter_complex", graph,
              *maps, *video_args, *audio_args, str(path)])
        written.append(path)

    return written


def summary(analysis: Analysis, cuts: list[tuple[float, float]], speed: float = 1.0) -> str:
    kept = sum(end - start for start, end in keeps(cuts, analysis.duration))
    final = kept / speed
    return (f"{len(cuts)} cuts removing {format_time(analysis.duration - kept)} · "
            f"original {format_time(analysis.duration)} → final {format_time(final)} "
            f"({final / analysis.duration:.0%})")
