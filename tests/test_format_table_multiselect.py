"""FormatTable onay-kutulu çoklu seçim: QT_QPA_PLATFORM=offscreen ile gerçek widget testleri."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.downloaders.base_downloader import MediaFormat
from app.ui.format_table import FormatTable


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _fmt(format_id, kind="video", container="mp4", resolution="1080p"):
    return MediaFormat(format_id=format_id, kind=kind, container=container, resolution=resolution)


def test_starts_fully_unchecked(qapp):
    table = FormatTable()
    table.set_formats([_fmt("v1"), _fmt("v2"), _fmt("a1", kind="audio", container="mp3", resolution="")])
    assert table.checked_formats() == []


def test_multiple_rows_checkable_together(qapp):
    table = FormatTable()
    video = _fmt("v1")
    audio = _fmt("a1", kind="audio", container="mp3", resolution="")
    table.set_formats([video, audio])
    table.item(0, 0).setCheckState(Qt.Checked)
    table.item(1, 0).setCheckState(Qt.Checked)
    checked = table.checked_formats()
    assert len(checked) == 2
    assert video in checked and audio in checked


def test_preselect_exclusive_unchecks_others(qapp):
    table = FormatTable()
    v1, v2 = _fmt("v1"), _fmt("v2")
    table.set_formats([v1, v2])
    table.item(1, 0).setCheckState(Qt.Checked)
    table.preselect(v1, exclusive=True)
    checked = table.checked_formats()
    assert len(checked) == 1
    assert checked[0].format_id == "v1"


def test_preselect_overrides_container_and_cell_text(qapp):
    table = FormatTable()
    v1 = _fmt("v1", container="mp4")
    table.set_formats([v1])
    forced = _fmt("v1", container="mkv")
    table.preselect(forced, exclusive=True)
    checked = table.checked_formats()
    assert checked[0].container == "mkv"
    assert table.item(0, 6).text() == "MKV"


def test_set_all_true_then_false(qapp):
    table = FormatTable()
    table.set_formats([_fmt("v1"), _fmt("v2"), _fmt("v3")])
    table.set_all(True)
    assert len(table.checked_formats()) == 3
    table.set_all(False)
    assert table.checked_formats() == []


def test_selection_changed_fires_once_per_action(qapp):
    table = FormatTable()
    table.set_formats([_fmt("v1"), _fmt("v2")])
    count = {"n": 0}
    table.selection_changed.connect(lambda: count.__setitem__("n", count["n"] + 1))

    table.item(0, 0).setCheckState(Qt.Checked)
    assert count["n"] == 1

    table.set_all(True)
    assert count["n"] == 2


def test_preselect_non_exclusive_preserves_other_checked_row(qapp):
    table = FormatTable()
    video, audio = _fmt("v1"), _fmt("a1", kind="audio", container="mp3", resolution="")
    table.set_formats([video, audio])
    table.item(1, 0).setCheckState(Qt.Checked)  # ses önceden işaretli
    table.preselect(video, exclusive=False)
    checked_ids = {f.format_id for f in table.checked_formats()}
    assert checked_ids == {"v1", "a1"}
