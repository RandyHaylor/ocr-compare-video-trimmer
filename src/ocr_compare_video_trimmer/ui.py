"""Small Gradio page: generate the OCR text, tune the cut settings, render. No video player."""

from __future__ import annotations

import shutil
from pathlib import Path

import gradio as gr

from . import core

UPLOAD_DIR = Path.home() / "ocr-compare-video-trimmer"


def _save_upload(uploaded):
    """Copy a dropped video into UPLOAD_DIR and put its path in the path box. Re-dropping the same
    file reuses the existing copy so its OCR cache stays valid."""
    if not uploaded:
        return gr.update()
    source = Path(uploaded)
    target = UPLOAD_DIR / source.name
    if not (target.is_file() and target.stat().st_size == source.stat().st_size):
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return str(target)


def _plan(analysis, threshold, min_gaps, speed):
    if analysis is None:
        return "", []
    cuts = core.plan(analysis, threshold, int(min_gaps))
    rows = [[core.format_time(s), core.format_time(e), core.format_time(e - s)] for s, e in cuts]
    return core.summary(analysis, cuts, speed), rows


def _analyze(video, out_dir, interval, progress=gr.Progress()):
    if not video.strip():
        raise gr.Error("Enter the path to a video file.")
    try:
        analysis = core.analyze(video.strip().strip('"'), interval, out_dir.strip() or None,
                                progress=lambda done, total: progress(done / total, desc=f"OCR {done}/{total}"))
    except FileNotFoundError as error:
        raise gr.Error(str(error))
    out_dir = out_dir.strip() or None
    return analysis, out_dir, f"Done. Stills and OCR text: {core.output_paths(analysis.video, out_dir).ocr_dir}"


def _clear_cache(analysis, loaded_out_dir):
    if analysis is None:
        raise gr.Error("No video loaded. Generate the OCR text first.")
    cleared = core.clear_cache(analysis.video, loaded_out_dir)
    return None, f"Cleared {cleared}", "", []


def _render(analysis, loaded_out_dir, threshold, min_gaps, speed, fade, fade_in, fade_out, mode):
    if analysis is None:
        raise gr.Error("Generate the OCR text first.")
    cuts = core.plan(analysis, threshold, int(min_gaps))
    written = core.render(analysis, core.keeps(cuts, analysis.duration), loaded_out_dir,
                          mode.lower(), speed, fade, fade_in, fade_out)
    return "Wrote:\n" + "\n".join(f"- `{path}`" for path in written)


def build() -> gr.Blocks:
    with gr.Blocks(title="OCR Compare Video Trimmer") as app:
        analysis = gr.State()
        loaded_out_dir = gr.State()  # output folder the loaded video was analyzed with
        gr.Markdown("# OCR Compare Video Trimmer\n"
                    "Cuts the stretches of a screen recording where the on-screen text barely changes.")
        with gr.Column(variant="panel"):
            gr.Markdown("## Step 1 · Generate OCR text")
            with gr.Row():
                video = gr.Textbox(label="Video file path", scale=3)
                out_dir = gr.Textbox(label="Output folder (blank: a folder named after the video, next to it)",
                                     scale=2)
                interval = gr.Number(5, label="Still every (seconds)", minimum=1)
            upload = gr.File(label=f"…or drop a video here (saved to {UPLOAD_DIR})", file_types=["video"],
                             type="filepath", height=120)
            with gr.Row():
                analyze_button = gr.Button("Generate OCR text", variant="primary", scale=4)
                clear_button = gr.Button("Clear cache for loaded video", variant="secondary")
            status = gr.Textbox("Not run yet.", label="Status", interactive=False)

        with gr.Column(variant="panel"):
            gr.Markdown("## Step 2 · Choose cuts and render")
            with gr.Row():
                threshold = gr.Slider(0.5, 1.0, value=0.95, step=0.01,
                                      label="Similarity threshold (at or above = unchanged)")
                min_gaps = gr.Number(2, precision=0, minimum=2, label="Unchanged gaps in a row before cutting")
                speed = gr.Number(1.0, minimum=0.25, label="Speed (x)")
            summary = gr.Markdown()
            cuts = gr.Dataframe(headers=["Cut from", "Cut to", "Length"], interactive=False)

            with gr.Row():
                fade_out = gr.Checkbox(True, label="Fade out before each cut")
                fade_in = gr.Checkbox(True, label="Fade in after each cut")
                fade = gr.Number(0.25, minimum=0.05, label="Fade length (seconds)")
                mode = gr.Radio(["Joined", "Individual", "Both"], value="Joined", label="Save as")
            render_button = gr.Button("Render", variant="primary")
            written = gr.Markdown()

        upload.upload(_save_upload, upload, video)
        plan_inputs = [analysis, threshold, min_gaps, speed]
        # Only the status box shows the OCR progress; the plan fills in afterwards.
        analyze_button.click(_analyze, [video, out_dir, interval], [analysis, loaded_out_dir, status]).then(
            _plan, plan_inputs, [summary, cuts], show_progress="hidden")
        clear_button.click(_clear_cache, [analysis, loaded_out_dir], [analysis, status, summary, cuts])
        for control in (threshold, min_gaps, speed):
            control.change(_plan, plan_inputs, [summary, cuts])
        render_button.click(_render, [analysis, loaded_out_dir, threshold, min_gaps, speed, fade, fade_in,
                                      fade_out, mode], written)
    return app


def launch() -> None:
    build().launch(inbrowser=True)
