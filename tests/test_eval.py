"""Tests for the accuracy measurement (eval/run_eval.py).

No API key and no internet needed. A fake client stands in for Gemini, and a
fake clock stands in for real waiting, so the 4 requests a minute limit is
checked without the tests taking minutes.
"""

import json
from types import SimpleNamespace

import pytest

from eval import run_eval
from eval.run_eval import EvalError

EXAMPLE = run_eval.KEYS_DIR / "EXAMPLE.json"


class FakeClock:
    """Pretend time. sleep moves the clock forward instead of waiting."""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class FakeClient:
    """Stands in for Gemini. Answers each PDF with its own canned answer.

    Each request takes `seconds` of pretend time, and its start time is noted.
    """

    def __init__(self, answers, clock, seconds=5):
        self.answers = answers
        self.clock = clock
        self.seconds = seconds
        self.starts = []
        self.models = self

    def generate_content(self, *, model, contents, config):
        self.starts.append(self.clock.now)
        self.clock.now += self.seconds
        return SimpleNamespace(text=json.dumps(self.answers[contents[0].inline_data.data]))


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    """Every test here uses pretend time, so nothing ever really waits."""
    fake = FakeClock()
    monkeypatch.setattr(run_eval, "monotonic", fake.monotonic)
    monkeypatch.setattr(run_eval, "sleep", fake.sleep)
    return fake


def item(name, weight=None, when="unknown", **timing) -> dict:
    """An item with every timing field, the way the scoring code sees both key and extracted items."""
    return {"name": name, "weight_percent": weight} | {field: None for field in run_eval.TIMING_FIELDS} | {"when": when} | timing


def pdf(code: str) -> bytes:
    return b"%PDF-1.7 " + code.encode()


def gemini_answer(code: str, *items) -> dict:
    """What Gemini sends back for one outline."""
    return {"subject_code": code, "subject_name": "Some Subject", "items": list(items)}


def write_key(folder, code, items, checked=True):
    """Save an answer key file the way the owner writes one."""
    folder.mkdir(exist_ok=True)
    key = {"subject": f"{code} Some Subject", "checked": checked, "items": items}
    (folder / f"{code}.json").write_text(json.dumps(key))


# ---------- pairing names ----------


def test_names_are_compared_in_lower_case_without_punctuation():
    assert run_eval.normalise("  Skills-Test #1 (Online)") == "skills test 1 online"


def test_the_same_name_after_normalising_is_a_perfect_match():
    assert run_eval.name_similarity("Skills test 1", "SKILLS TEST 1.") == 1.0


def test_similarity_is_difflib_ratio_on_the_normalised_names():
    # "skills test 6" (13 letters) is inside "skills test 6 weeks 11 12" (25 letters),
    # so the ratio is 2 x 13 matching letters / (13 + 25) letters = 26 / 38
    assert run_eval.name_similarity("Skills Test 6", "Skills Test 6 (weeks 11-12)") == pytest.approx(26 / 38)


def test_a_different_number_is_never_a_match():
    assert run_eval.name_similarity("Skills Test 2", "Skills Test 7") == 0.0
    assert run_eval.name_similarity("Skills Test 2", "Skills Test 12") == 0.0


def test_items_are_paired_by_name_whatever_the_order():
    key = [item("Assignment 1"), item("Quiz"), item("Final exam")]
    found = [item("Final Exam"), item("Assignment 1"), item("quiz")]
    assert run_eval.match_items(key, found) == [(0, 1), (1, 2), (2, 0)]


def test_split_items_only_pair_with_the_same_number():
    key = [item("Skills Test 1"), item("Skills Test 2")]
    found = [item("Skills Test 1"), item("Skills Test 7")]
    assert run_eval.match_items(key, found) == [(0, 0)]


def test_the_most_alike_pair_wins_even_if_it_comes_later():
    key = [item("Quiz 1")]
    found = [item("Quiz 1 online"), item("Quiz 1")]
    # Both are alike enough to pair (12 / 19 is about 0.63), but the exact name is better
    assert run_eval.name_similarity("Quiz 1", "Quiz 1 online") >= run_eval.MATCH_THRESHOLD
    assert run_eval.match_items(key, found) == [(0, 1)]


def test_each_item_is_used_at_most_once_and_ties_go_to_the_first():
    assert run_eval.match_items([item("Quiz"), item("Quiz")], [item("Quiz")]) == [(0, 0)]
    assert run_eval.match_items([item("Quiz")], [item("Quiz"), item("Quiz")]) == [(0, 0)]


def test_names_that_are_not_alike_enough_are_not_paired():
    assert run_eval.name_similarity("Final exam", "Group report") < run_eval.MATCH_THRESHOLD
    assert run_eval.match_items([item("Final exam")], [item("Group report")]) == []


# ---------- small scoring rules ----------


@pytest.mark.parametrize(
    "key_weight, found_weight, same",
    [
        (10, 10.0, True),
        (3.33, 3.333, True),
        (10, 10.04, True),
        (10, 10.1, False),
        (3.3, 3.4, False),
        (None, None, True),
        (None, 10, False),
        (10, None, False),
    ],
)
def test_weights_match_within_a_small_tolerance(key_weight, found_weight, same):
    assert run_eval.same_weight(key_weight, found_weight) is same


@pytest.mark.parametrize(
    "timing, dated",
    [
        ({"when": "date", "date": "2026-09-04"}, True),
        ({"when": "week", "week": 2}, True),
        ({"when": "tutorial", "week": 12}, True),
        ({"when": "tutorial"}, False),
        ({"when": "recurring", "first_week": 4}, True),
        ({"when": "exam_period"}, False),
        ({"when": "unknown"}, False),
    ],
)
def test_which_timings_give_a_date(timing, dated):
    assert run_eval.gives_a_date(item("X", **timing)) is dated


@pytest.mark.parametrize(
    "part, whole, text",
    [(9, 10, "9 of 10 (90%)"), (2, 3, "2 of 3 (67%)"), (4, 4, "4 of 4 (100%)"), (0, 0, "0 of 0")],
)
def test_fractions_are_written_with_a_percentage(part, whole, text):
    assert run_eval.fraction(part, whole) == text


# ---------- scoring one outline ----------


def hand_made_score() -> dict:
    """A small outline worked out by hand.

    Skills Test 1: right weight, right week.
    Skills Test 2: wrong weight. Key says tutorial (no date) but week 5 was found, a silently wrong date.
    Assignment 1: right weight. Key gives a date but week 6 was found, a silently wrong date.
    Final exam: right weight. Key says exam period but unknown was found. Wrong, but it shows no date.
    Group report: missed. Bonus quiz: invented.
    """
    key = [
        item("Skills Test 1", 10, "week", week=2),
        item("Skills Test 2", 10, "tutorial"),
        item("Assignment 1", 30, "date", date="2026-09-04"),
        item("Final exam", 40, "exam_period"),
        item("Group report", 10),
    ]
    found = [
        item("Skills Test 1", 10, "week", week=2),
        item("Skills Test 2", 15, "week", week=5),
        item("Assignment 1", 30, "week", week=6),
        item("Final exam", 40, "unknown"),
        item("Bonus quiz", 5, "week", week=3),
    ]
    return run_eval.score_outline(key, found)


def test_the_counts_for_a_hand_made_outline():
    score = hand_made_score()
    counts = {name: score[name] for name in run_eval.COUNTS}
    assert counts == {
        "key_items": 5,
        "found_items": 5,
        "matched": 4,  # recall 4 of 5, precision 4 of 5
        "weights_right": 3,  # 3 of 4 matched
        "dated": 2,  # Skills Test 1 and Assignment 1 have a date in the key
        "dates_right": 1,  # only Skills Test 1
        "silently_wrong": 2,  # Skills Test 2 and Assignment 1
    }


def test_the_mistakes_for_a_hand_made_outline_are_listed():
    score = hand_made_score()
    assert score["missed"] == ["Group report"]
    assert score["invented"] == ["Bonus quiz"]
    assert score["wrong_weights"] == ['"Skills Test 2": key 10, found 15']
    assert score["wrong_timings"] == [
        '"Skills Test 2": key when=tutorial, found when=week, week=5 (silently wrong)',
        '"Assignment 1": key when=date, date=2026-09-04, found when=week, week=6 (silently wrong)',
        '"Final exam": key when=exam_period, found when=unknown',
    ]


def test_a_timing_detail_the_outline_does_not_give_counts_as_wrong():
    # The key copies the outline exactly, so an added weekday was made up
    score = run_eval.score_outline(
        [item("Quiz", 10, "week", week=2)], [item("Quiz", 10, "week", week=2, weekday="friday")]
    )
    assert (score["dates_right"], score["silently_wrong"]) == (0, 1)


def test_nothing_found_scores_zero_without_dividing_by_zero():
    score = run_eval.score_outline([item("Quiz", 10)], [])
    assert run_eval.table_row("12345", score) == "| 12345 | 0 of 1 (0%) | 0 of 0 | 0 of 0 | 0 of 0 | 0 |"


def test_results_add_up_every_outline_in_the_all_row():
    scores = {"11111": hand_made_score(), "22222": hand_made_score()}
    results = run_eval.render(scores, unchecked=["33333"])

    assert "| 11111 | 4 of 5 (80%) | 4 of 5 (80%) | 3 of 4 (75%) | 1 of 2 (50%) | 2 |" in results
    assert "| All | 8 of 10 (80%) | 8 of 10 (80%) | 6 of 8 (75%) | 2 of 4 (50%) | 4 |" in results
    assert "## 22222" in results
    assert "- Missed:\n  - Group report\n- Invented:\n  - Bonus quiz\n" in results
    assert "- Wrong timing:\n  - \"Skills Test 2\"" in results
    assert "Not counted, because the answer key is not checked yet: 33333." in results


# ---------- answer keys ----------


def test_the_example_key_follows_the_format():
    key = run_eval.load_key(EXAMPLE)
    assert {i["when"] for i in key["items"]} == set(run_eval.outline.WHEN_VALUES)
    assert sum(i["weight_percent"] for i in key["items"]) == 100


def test_timing_fields_left_out_of_a_key_count_as_null(tmp_path):
    write_key(tmp_path, "12345", [{"name": "Quiz", "weight_percent": 10, "when": "week", "week": 3, "note": "p4"}])
    [quiz] = run_eval.load_key(tmp_path / "12345.json")["items"]
    assert quiz == item("Quiz", 10, "week", week=3)


@pytest.mark.parametrize(
    "items, problem",
    [
        ([{"weight_percent": 10, "when": "week", "week": 2}], "missing name"),
        ([{"name": "Quiz", "weight_percent": 10, "when": "week", "weeks": 2}], "unknown fields: weeks"),
        ([{"name": "Quiz", "weight_percent": 10, "when": "week", "week": 2, "weekday": "Friday"}], "weekday 'Friday'"),
        ([{"name": "Quiz", "weight_percent": 10, "when": "week"}], "when 'week'"),
        ([{"name": "Quiz", "weight_percent": "10%", "when": "unknown"}], "weight_percent '10%'"),
        ([{"name": "Quiz", "weight_percent": 10, "when": "date", "date": "4 Sep"}], "date '4 Sep'"),
        ([{"name": "Quiz", "weight_percent": 10, "when": "soon"}], "when 'soon'"),
        ([{"name": "", "weight_percent": 10, "when": "unknown"}], "needs a name"),
        (["Quiz"], "not an object"),
    ],
)
def test_a_typo_in_a_key_stops_the_run(tmp_path, items, problem):
    write_key(tmp_path, "12345", items)
    with pytest.raises(EvalError, match=problem):
        run_eval.load_key(tmp_path / "12345.json")


@pytest.mark.parametrize(
    "text, problem",
    [
        ("{not json", "not valid JSON"),
        ('{"checked": true, "items": []}', "exactly these fields"),
        ('{"subject": "x", "checked": "yes", "items": []}', "true or false"),
        ('{"subject": "x", "checked": true, "items": {}}', "must be a list"),
    ],
)
def test_a_broken_key_file_stops_the_run(tmp_path, text, problem):
    path = tmp_path / "12345.json"
    path.write_text(text)
    with pytest.raises(EvalError, match=problem):
        run_eval.load_key(path)


def test_keys_are_split_into_checked_and_not_checked_and_the_example_is_skipped(tmp_path):
    (tmp_path / "EXAMPLE.json").write_text(EXAMPLE.read_text())
    write_key(tmp_path, "22222", [], checked=False)
    write_key(tmp_path, "11111", [{"name": "Quiz", "weight_percent": 10, "when": "unknown"}])

    checked, unchecked = run_eval.load_keys(tmp_path)

    assert list(checked) == ["11111"]
    assert unchecked == ["22222"]


def test_a_key_must_be_named_after_its_subject_code(tmp_path):
    write_key(tmp_path, "maths", [])
    with pytest.raises(EvalError, match="five digit subject code"):
        run_eval.load_keys(tmp_path)


# ---------- reading the outlines ----------


def test_a_missing_outline_stops_the_run_before_any_request(tmp_path, clock):
    (tmp_path / "11111.pdf").write_bytes(pdf("11111"))
    client = FakeClient({}, clock)
    with pytest.raises(EvalError, match="no outline for 22222"):
        run_eval.read_outlines(["11111", "22222"], tmp_path, client)
    assert client.starts == []


def test_an_outline_can_be_any_kind_of_file_groot_reads(tmp_path, monkeypatch):
    (tmp_path / "11111.docx").write_bytes(b"a Word outline")
    (tmp_path / "22222.PDF").write_bytes(pdf("22222"))  # capital letters in the ending are fine
    calls = []

    def fake_extract_items(data, filename=None, client=None):
        calls.append((data, filename, client))
        return []

    monkeypatch.setattr(run_eval.outline, "extract_items", fake_extract_items)
    run_eval.read_outlines(["11111", "22222"], tmp_path, client="the client")

    # The file name goes along as the hint for documents.py
    assert calls == [(b"a Word outline", "11111.docx", "the client"), (pdf("22222"), "22222.PDF", "the client")]


def test_files_that_are_not_an_outline_for_the_code_are_ignored(tmp_path):
    (tmp_path / "11111.json").write_text("{}")  # not a kind Groot reads
    (tmp_path / "11111.old.pdf").write_bytes(pdf("11111"))  # named after something else
    (tmp_path / "11111.txt").mkdir()  # a folder, not a file
    with pytest.raises(EvalError, match="no outline for 11111"):
        run_eval.find_outline("11111", tmp_path)


def test_two_outlines_for_one_code_stop_the_run(tmp_path):
    (tmp_path / "11111.pdf").write_bytes(pdf("11111"))
    (tmp_path / "11111.docx").write_bytes(b"a Word outline")
    with pytest.raises(EvalError, match=r"more than one outline for 11111 \(11111.docx, 11111.pdf\)"):
        run_eval.find_outline("11111", tmp_path)


def test_requests_are_spaced_out_to_stay_under_4_a_minute(tmp_path, clock):
    codes = [str(code) for code in range(11111, 11117)]  # six outlines
    for code in codes:
        (tmp_path / f"{code}.pdf").write_bytes(pdf(code))
    client = FakeClient({pdf(code): gemini_answer(code) for code in codes}, clock, seconds=5)

    run_eval.read_outlines(codes, tmp_path, client)

    # Each request takes 5 seconds, so it waits 11 more to make 16 seconds between starts
    assert client.starts == [0, 16, 32, 48, 64, 80]
    assert clock.sleeps == [11] * 5
    for start in client.starts:
        in_the_next_minute = [s for s in client.starts if start <= s < start + 60]
        assert len(in_the_next_minute) <= 4


def test_no_waiting_after_a_slow_request(tmp_path, clock):
    for code in ["11111", "22222"]:
        (tmp_path / f"{code}.pdf").write_bytes(pdf(code))
    answers = {pdf(code): gemini_answer(code) for code in ["11111", "22222"]}
    client = FakeClient(answers, clock, seconds=30)

    run_eval.read_outlines(["11111", "22222"], tmp_path, client)

    assert clock.sleeps == []
    assert client.starts == [0, 30]


# ---------- the whole run ----------


def setup_two_outlines(tmp_path):
    """Two checked keys and their PDFs. Gemini gets 11111 fully right and misses one item in 22222."""
    keys, outlines = tmp_path / "answer_key", tmp_path / "outlines"
    outlines.mkdir()
    quiz = {"name": "Quiz 1", "weight_percent": 20, "when": "week", "week": 3}
    exam = {"name": "Final exam", "weight_percent": 80, "when": "exam_period"}
    write_key(keys, "11111", [quiz, exam])
    write_key(keys, "22222", [quiz, exam])
    for code in ["11111", "22222"]:
        (outlines / f"{code}.pdf").write_bytes(pdf(code))
    answers = {
        pdf("11111"): gemini_answer("11111", quiz, exam),
        pdf("22222"): gemini_answer("22222", quiz),
    }
    return keys, outlines, answers


def test_a_whole_run_with_a_fake_gemini(tmp_path, clock):
    keys, outlines, answers = setup_two_outlines(tmp_path)

    results = run_eval.evaluate(outlines, keys, FakeClient(answers, clock))

    assert "| 11111 | 2 of 2 (100%) | 2 of 2 (100%) | 2 of 2 (100%) | 1 of 1 (100%) | 0 |" in results
    assert "| 22222 | 1 of 2 (50%) | 1 of 1 (100%) | 1 of 1 (100%) | 1 of 1 (100%) | 0 |" in results
    assert "| All | 3 of 4 (75%) | 3 of 3 (100%) | 3 of 3 (100%) | 2 of 2 (100%) | 0 |" in results
    assert "## 11111\n\n- Missed: none\n" in results
    assert "## 22222\n\n- Missed:\n  - Final exam\n" in results


def test_a_failed_outline_stops_the_run_instead_of_giving_part_of_the_results(tmp_path, clock):
    keys, outlines, answers = setup_two_outlines(tmp_path)
    answers[pdf("22222")] = "not json"  # Gemini's answer for the second outline cannot be read

    with pytest.raises(run_eval.outline.OutlineError):
        run_eval.evaluate(outlines, keys, FakeClient(answers, clock))


def test_no_checked_keys_is_a_clear_error(tmp_path):
    write_key(tmp_path, "11111", [], checked=False)
    with pytest.raises(EvalError, match="no checked answer keys"):
        run_eval.evaluate(tmp_path, tmp_path)


def test_main_stops_without_touching_results_when_something_is_wrong(tmp_path, monkeypatch):
    results_file = tmp_path / "results.md"
    monkeypatch.setattr(run_eval, "KEYS_DIR", tmp_path)  # no keys at all
    monkeypatch.setattr(run_eval, "RESULTS_FILE", results_file)

    with pytest.raises(SystemExit, match="results.md was not changed"):
        run_eval.main()
    assert not results_file.exists()


def test_main_saves_the_results_with_unix_line_endings(tmp_path, monkeypatch):
    results_file = tmp_path / "results.md"
    monkeypatch.setattr(run_eval, "RESULTS_FILE", results_file)
    monkeypatch.setattr(run_eval, "evaluate", lambda outlines_dir, keys_dir: "# Results\nline two\n")

    run_eval.main()

    assert results_file.read_bytes() == b"# Results\nline two\n"
