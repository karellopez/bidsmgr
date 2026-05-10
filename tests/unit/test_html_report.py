"""Unit tests for ``bidsmgr.editor.html_report``.

The renderer is pure: it takes a ``ValidationReport`` and returns a
self-contained HTML string. Tests assert on the structural shape and
on key escaping / colour-coding choices, not on exact byte sequences.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bidsmgr.editor import (
    FieldLevel,
    FileVerdict,
    Issue,
    Severity,
    SidecarField,
    ValidationReport,
    render_html,
)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _issue(sev: Severity, rule_id: str, message: str, **kwargs) -> Issue:
    return Issue(severity=sev, rule_id=rule_id, message=message, **kwargs)


def _empty_report(*, severity: Severity = Severity.OK) -> ValidationReport:
    return ValidationReport(
        bids_root=Path("/tmp/study"),
        bidsmgr_version="0.0.1",
        bids_version="1.10.0",
        generated_at="2026-05-09T00:00:00Z",
        severity=severity,
        counts={"ok": 0, "warn": 0, "err": 0},
    )


# ---------------------------------------------------------------------------
# Structural assertions
# ---------------------------------------------------------------------------


class TestSelfContained:
    def test_full_html5_document(self) -> None:
        out = render_html(_empty_report())
        assert out.startswith("<!DOCTYPE html>")
        assert "<html" in out and "</html>" in out
        assert "<head>" in out and "</head>" in out
        assert "<body>" in out and "</body>" in out

    def test_no_external_resources(self) -> None:
        """No <link>/<script>/<img> tags — file must be portable offline."""
        out = render_html(_empty_report())
        assert "<link" not in out.lower()
        assert "<script" not in out.lower()
        # External images would require src; we don't render any.
        assert "<img" not in out.lower()

    def test_inline_style_block_present(self) -> None:
        out = render_html(_empty_report())
        assert "<style>" in out and "</style>" in out
        assert ":root {" in out  # CSS palette block

    def test_uses_meta_charset_utf8(self) -> None:
        out = render_html(_empty_report())
        assert 'meta charset="utf-8"' in out


# ---------------------------------------------------------------------------
# Header / status banner
# ---------------------------------------------------------------------------


class TestHeader:
    def test_renders_dataset_name(self) -> None:
        out = render_html(_empty_report())
        assert "study" in out  # bids_root.name
        assert "BIDS validation" in out

    def test_status_banner_uses_severity_class(self) -> None:
        for sev in [Severity.OK, Severity.WARN, Severity.ERR]:
            out = render_html(_empty_report(severity=sev))
            assert f'class="status {sev.value}"' in out
            assert f'class="label">{sev.value}<' in out

    def test_count_pills_render(self) -> None:
        report = _empty_report()
        report.counts = {"ok": 12, "warn": 3, "err": 1}
        out = render_html(report)
        assert ">12 ok<" in out
        assert ">3 warnings<" in out
        assert ">1 errors<" in out


# ---------------------------------------------------------------------------
# Issue list rendering & color coding
# ---------------------------------------------------------------------------


class TestIssueRendering:
    def test_dataset_issues_render_with_severity_class(self) -> None:
        report = _empty_report()
        report.dataset_issues = [
            _issue(Severity.ERR, "bids.missing_dataset_description",
                   "dataset_description.json is missing"),
        ]
        out = render_html(report)
        # Issue badge picks up the severity class.
        assert '<span class="badge err">err</span>' in out
        assert "missing_dataset_description" in out

    def test_folder_issues_grouped_by_folder(self) -> None:
        report = _empty_report()
        report.folder_issues = {
            "sub-001": [
                _issue(Severity.WARN, "bids.unknown_datatype_dir",
                       "unrecognised directory: 'raw_dicoms'"),
            ],
        }
        out = render_html(report)
        assert "sub-001" in out
        assert "unknown_datatype_dir" in out
        # The folder block carries the worst-severity class.
        assert 'class="folder warn"' in out

    def test_file_issues_render_path_and_typed(self) -> None:
        report = _empty_report()
        report.files = [
            FileVerdict(
                path=Path("sub-001/func/sub-001_task-rest_bold.json"),
                severity=Severity.WARN,
                datatype="func", suffix="bold",
                issues=[
                    _issue(Severity.WARN, "bidsmgr.todo_placeholder",
                           "field 'TaskDescription' contains TODO placeholder",
                           field="TaskDescription"),
                ],
            ),
        ]
        out = render_html(report)
        assert "sub-001/func/sub-001_task-rest_bold.json" in out
        assert "func/bold" in out  # the typed annotation
        assert "TaskDescription" in out

    def test_file_with_no_issues_is_omitted(self) -> None:
        """We only show flagged files in the report."""
        report = _empty_report()
        report.files = [
            FileVerdict(path=Path("sub-001/anat/sub-001_T1w.json"),
                        severity=Severity.OK, datatype="anat", suffix="T1w"),
        ]
        out = render_html(report)
        assert "sub-001_T1w.json" not in out
        assert "No per-file issues" in out

    def test_color_classes_for_each_severity(self) -> None:
        """Each severity uses the agreed CSS class for color coding."""
        report = _empty_report()
        report.files = [
            FileVerdict(
                path=Path("a.json"),
                severity=Severity.ERR,
                issues=[_issue(Severity.ERR, "rule.x", "boom")],
            ),
            FileVerdict(
                path=Path("b.json"),
                severity=Severity.WARN,
                issues=[_issue(Severity.WARN, "rule.y", "tepid")],
            ),
        ]
        out = render_html(report)
        assert 'class="file err"' in out
        assert 'class="file warn"' in out
        assert '<span class="badge err">err</span>' in out
        assert '<span class="badge warn">warn</span>' in out


# ---------------------------------------------------------------------------
# Empty states
# ---------------------------------------------------------------------------


class TestEmptyStates:
    def test_no_dataset_issues_shows_empty_message(self) -> None:
        out = render_html(_empty_report())
        assert "No dataset-level issues" in out

    def test_no_folder_issues_shows_empty_message(self) -> None:
        out = render_html(_empty_report())
        assert "No folder-level issues" in out

    def test_no_file_issues_shows_empty_message(self) -> None:
        out = render_html(_empty_report())
        assert "No per-file issues" in out


# ---------------------------------------------------------------------------
# Escaping
# ---------------------------------------------------------------------------


class TestEscaping:
    def test_escapes_html_in_messages(self) -> None:
        report = _empty_report()
        report.dataset_issues = [
            _issue(Severity.WARN, "rule.x",
                   "<script>alert('xss')</script> & friends"),
        ]
        out = render_html(report)
        # The HTML must NOT contain a real script tag.
        assert "<script>alert" not in out
        # The escaped form is present.
        assert "&lt;script&gt;" in out
        assert "&amp; friends" in out

    def test_escapes_paths_with_special_chars(self) -> None:
        report = _empty_report()
        report.files = [
            FileVerdict(
                path=Path("sub-001/odd<dir>/file.json"),
                severity=Severity.WARN,
                issues=[_issue(Severity.WARN, "rule", "msg")],
            ),
        ]
        out = render_html(report)
        # The dangerous brackets are escaped.
        assert "<dir>" not in out
        assert "&lt;dir&gt;" in out


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


class TestRenderingSize:
    def test_renders_without_crashing_for_realistic_size(self) -> None:
        """100 files × 5 issues each. Just confirm it doesn't blow up."""
        report = _empty_report(severity=Severity.WARN)
        report.counts = {"ok": 100, "warn": 500, "err": 0}
        report.files = [
            FileVerdict(
                path=Path(f"sub-{i:03d}/func/sub-{i:03d}_bold.json"),
                severity=Severity.WARN,
                datatype="func", suffix="bold",
                issues=[
                    _issue(Severity.WARN, f"rule.{j}", f"message {j}",
                           field=f"Field{j}")
                    for j in range(5)
                ],
            )
            for i in range(100)
        ]
        out = render_html(report)
        # Rough size check — should be under a reasonable upper bound.
        assert len(out) < 5_000_000  # 5 MB ceiling for 500 issues
        assert out.count('<div class="file') == 100
