from ocr_compare_video_trimmer.core import Analysis, keeps, plan


def make(similarities, interval=5.0):
    stills = len(similarities) + 1
    return Analysis(video="v.webm", video_size=0, video_mtime=0, duration=(stills - 1) * interval + 2,
                    interval=interval, has_audio=False, texts=[""] * stills, similarities=similarities)


def test_run_of_two_or_more_unchanged_gaps_is_cut_keeping_both_ends():
    # stills at 0,5,...,40; gaps 1-3 (5s-20s) unchanged
    analysis = make([0.5, 0.99, 0.99, 0.99, 0.5, 0.5, 0.5, 0.5])
    assert plan(analysis, 0.95) == [(10.0, 20.0)]


def test_single_unchanged_gap_is_not_cut():
    assert plan(make([0.5, 0.99, 0.5, 0.5]), 0.95) == []


def test_min_gaps_raises_the_bar():
    analysis = make([0.99, 0.99, 0.5, 0.99, 0.99, 0.99])
    assert plan(analysis, 0.95, min_gaps=3) == [(20.0, 30.0)]


def test_run_reaching_the_last_still_is_cut():
    assert plan(make([0.5, 0.99, 0.99]), 0.95) == [(10.0, 15.0)]


def test_lower_threshold_cuts_more():
    analysis = make([0.93, 0.93, 0.5])
    assert plan(analysis, 0.95) == []
    assert plan(analysis, 0.92) == [(5.0, 10.0)]


def test_keeps_is_the_complement_of_cuts():
    assert keeps([(10, 20), (30, 40)], 50) == [(0.0, 10), (20, 30), (40, 50)]
