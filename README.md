# ocr-compare-video-trimmer

Cuts the stretches of a screen recording where nothing on screen changes, such as waiting on a long-running command.

It is not a video editor. It finds and removes static stretches, and nothing else. Open the result in any player or editor to scrub through it and fine-tune.

## How it works

1. **Stills.** It grabs a still every *N* seconds (5 by default).
2. **OCR.** It runs EasyOCR on each still and saves the stills and text (see [Output](#output)). Changing settings later doesn't redo the OCR.
3. **Compare.** Each still's text is compared with the next. Two stills count as unchanged when their similarity is at or above the threshold.
4. **Cut.** When 2 or more gaps in a row are unchanged, the stretch is cut. The first interval is kept, along with the interval just before the screen changes.
5. **Render.** The kept parts are saved as one joined file, individual files, or both. Fades at each cut and a speed change are optional.

On screen recordings, a threshold around 0.98 cuts only true waits, where just a timer is ticking. Lower values cut more aggressively.

## Run

The launchers install [uv](https://docs.astral.sh/uv/) if it's missing. uv then installs Python and every dependency, including an ffmpeg build, so nothing else needs to be installed first.

| Platform | Web UI | Command line |
|---|---|---|
| macOS / Linux | `./run.sh` | `./run.sh VIDEO [options]` |
| Windows | `run.cmd` (or double-click it) | `run.cmd VIDEO [options]` |

The first run downloads PyTorch, which EasyOCR needs. That's about 3 GB on Linux and less on macOS and Windows. OCR uses an NVIDIA GPU when there is one; otherwise it runs on the CPU, which is slower.

### Web UI

1. Enter the video's path, or drop the video onto the upload box, then click **Generate OCR text**. A dropped video is copied into an `ocr-compare-video-trimmer` folder in your home folder (`~/` on macOS and Linux, `C:\Users\<you>\` on Windows), and its `ocr/` and `videos/` folders are created next to that copy.
2. Adjust the threshold, the number of unchanged gaps, and the speed. The list of cuts and the final duration update as you go.
3. Choose the fades and the output (joined, individual or both), then click **Render**.

### Command line

```
./run.sh recording.webm --threshold 0.92 --plan-only      # list the cuts and the final duration
./run.sh recording.webm --threshold 0.92 --output both --speed 1.5
```

| Option | Default | |
|---|---|---|
| `--interval` | 5 | seconds between stills |
| `--threshold` | 0.95 | similarity at or above which stills count as unchanged |
| `--min-gaps` | 2 | unchanged gaps in a row before a stretch is cut |
| `--speed` | 1.0 | output playback speed |
| `--fade` | 0.25 | fade length in seconds |
| `--no-fade-out`, `--no-fade-in` | | turn off either fade |
| `--output` | joined | `joined`, `individual` or `both` |
| `--out-dir` | next to the video | where files are written |
| `--plan-only` | | list the cuts without rendering |

## Output

By default everything goes in a folder named after the video, next to it. Setting an output folder (`--out-dir` on the command line) uses that folder instead. The source video is never changed.

```
<video folder>/<video name>/
    ocr/
        s00001.png ...       one still per interval
        <video>-ocr.txt      the OCR text of each still, labeled with its time and file name
        <video>-ocr.json     cache, so changing settings doesn't redo the OCR
    videos/
        <video>-trimmed.webm (or .mp4)   the joined result
        <video>-part01.webm ...          the individual kept segments
```

In the web UI, **Clear cache for loaded video** deletes the `ocr/` folder of the video last loaded with **Generate OCR text**, so the next Generate starts fresh. The OCR is also redone automatically when the video or the still interval changes.

A `.webm` source is saved as `.webm` (VP9/Opus). Any other format is saved as `.mp4` (H.264/AAC).

## Tests

```
uv run --project . pytest
```
