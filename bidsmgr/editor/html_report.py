"""Self-contained HTML rendering of a :class:`ValidationReport`.

Produces a single HTML document with inline CSS — no external assets —
so the file is shareable, archivable, and openable offline. The visual
language matches the Inspector prototype's editor view
(``../inspector_proto/proto.py``):

* Severity colour tokens follow the prototype's light palette
  (``DARK`` / ``LIGHT`` dicts in ``proto.py`` line 38–104).
* Severity badges are pill-shaped chips next to each issue.
* Issues are grouped by scope (dataset → folders → files) — the same
  three sections the GUI's right pane shows.

The renderer is Qt-free (architectural rule 2) and pure: it takes a
``ValidationReport`` and returns a string.
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Iterable

from .types import FileVerdict, Issue, Severity, ValidationReport


# Palette from the Inspector prototype's LIGHT theme (proto.py L67–104).
# Comfortable in any browser with the OS in either light or dark mode
# because we paint our own background; we don't inherit from ``html``.
_CSS = """
:root {
  --bg: #ffffff;
  --fg: #1f2328;
  --muted: #6e7781;
  --panel: #f6f8fa;
  --panel-border: #d0d7de;
  --accent: #0969da;
  --code-bg: #eef1f4;

  --ok-fg: #1a7f37;
  --ok-bg: #dafbe1;
  --ok-border: #1a7f3733;

  --warn-fg: #9a6700;
  --warn-bg: #fff8c5;
  --warn-border: #9a670033;

  --err-fg: #cf222e;
  --err-bg: #ffebe9;
  --err-border: #cf222e33;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial,
               sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
  font-size: 14px;
  line-height: 1.5;
  color: var(--fg);
  background: var(--bg);
}

.container { max-width: 1100px; margin: 0 auto; padding: 32px 24px; }

header {
  border-bottom: 1px solid var(--panel-border);
  padding-bottom: 24px;
  margin-bottom: 24px;
}

header h1 {
  margin: 0 0 8px 0;
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

header h1 code {
  background: var(--code-bg);
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.85em;
}

.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  color: var(--muted);
  font-size: 13px;
  margin-bottom: 16px;
}

.meta span code {
  background: var(--code-bg);
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 12px;
}

.status {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  border-radius: 8px;
  border: 1px solid var(--panel-border);
}

.status.ok    { background: var(--ok-bg);   border-color: var(--ok-border); }
.status.warn  { background: var(--warn-bg); border-color: var(--warn-border); }
.status.err   { background: var(--err-bg);  border-color: var(--err-border); }

.status .label {
  font-weight: 700;
  font-size: 16px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.status.ok   .label { color: var(--ok-fg); }
.status.warn .label { color: var(--warn-fg); }
.status.err  .label { color: var(--err-fg); }

.counts { display: flex; gap: 8px; margin-left: auto; }

.pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
}
.pill.ok   { background: var(--ok-bg);   color: var(--ok-fg);   border: 1px solid var(--ok-border); }
.pill.warn { background: var(--warn-bg); color: var(--warn-fg); border: 1px solid var(--warn-border); }
.pill.err  { background: var(--err-bg);  color: var(--err-fg);  border: 1px solid var(--err-border); }

.pill .dot {
  width: 8px; height: 8px; border-radius: 50%;
  display: inline-block;
}
.pill.ok   .dot { background: var(--ok-fg); }
.pill.warn .dot { background: var(--warn-fg); }
.pill.err  .dot { background: var(--err-fg); }

section {
  margin: 32px 0;
}

section h2 {
  margin: 0 0 12px 0;
  font-size: 18px;
  font-weight: 600;
  border-bottom: 1px solid var(--panel-border);
  padding-bottom: 8px;
}

section .empty {
  color: var(--muted);
  font-style: italic;
  padding: 8px 0;
}

.folder, .file {
  background: var(--panel);
  border: 1px solid var(--panel-border);
  border-radius: 8px;
  padding: 12px 16px;
  margin: 12px 0;
  border-left-width: 4px;
}
.folder.warn, .file.warn { border-left-color: var(--warn-fg); }
.folder.err,  .file.err  { border-left-color: var(--err-fg); }
.folder.ok,   .file.ok   { border-left-color: var(--ok-fg); }

.folder h3, .file h3 {
  margin: 0 0 8px 0;
  font-size: 14px;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 10px;
}

.file h3 .badge { /* override below */ }

.file h3 code {
  background: var(--code-bg);
  padding: 2px 8px;
  border-radius: 4px;
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Monaco,
               Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 13px;
}

.file h3 .typed {
  margin-left: auto;
  color: var(--muted);
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.badge.ok   { background: var(--ok-bg);   color: var(--ok-fg);   border: 1px solid var(--ok-border); }
.badge.warn { background: var(--warn-bg); color: var(--warn-fg); border: 1px solid var(--warn-border); }
.badge.err  { background: var(--err-bg);  color: var(--err-fg);  border: 1px solid var(--err-border); }

ul.issues { list-style: none; padding: 0; margin: 8px 0 0 0; }

ul.issues li {
  display: grid;
  grid-template-columns: auto auto 1fr auto;
  gap: 10px;
  align-items: baseline;
  padding: 6px 0;
  border-top: 1px solid var(--panel-border);
}
ul.issues li:first-child { border-top: 0; }

ul.issues .rule {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  color: var(--muted);
}

ul.issues .msg { color: var(--fg); }

ul.issues .field {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  color: var(--accent);
}

ul.issues .fix {
  display: inline-block;
  font-size: 11px;
  color: var(--accent);
  border: 1px dashed var(--accent);
  padding: 1px 6px;
  border-radius: 3px;
}

footer {
  margin-top: 48px;
  padding-top: 16px;
  border-top: 1px solid var(--panel-border);
  color: var(--muted);
  font-size: 12px;
  text-align: center;
}
"""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def render_html(report: ValidationReport) -> str:
    """Render ``report`` as a self-contained HTML document.

    Returns the full HTML as a string; the caller writes it to disk.
    """
    bids_root = report.bids_root.name if report.bids_root else "BIDS dataset"
    sev = report.severity.value
    parts: list[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append('<meta charset="utf-8">')
    parts.append(
        f"<title>{html.escape(bids_root)} — bidsmgr validation report</title>"
    )
    parts.append(f"<style>{_CSS}</style>")
    parts.append("</head>")
    parts.append("<body>")
    parts.append('<div class="container">')

    # Header
    parts.append("<header>")
    parts.append(
        f"<h1>BIDS validation — <code>{html.escape(bids_root)}</code></h1>"
    )
    parts.append('<div class="meta">')
    parts.append(
        f"<span>Generated {html.escape(report.generated_at or '')}</span>"
    )
    if report.bids_version:
        parts.append(
            f"<span>BIDS <code>{html.escape(report.bids_version)}</code></span>"
        )
    parts.append(
        f"<span>bidsmgr <code>{html.escape(report.bidsmgr_version)}</code></span>"
    )
    if report.bids_root:
        parts.append(
            f"<span title='Absolute path'><code>"
            f"{html.escape(str(report.bids_root))}</code></span>"
        )
    parts.append("</div>")  # .meta
    parts.append(f'<div class="status {sev}">')
    parts.append(f'<span class="label">{sev}</span>')
    parts.append('<span class="counts">')
    counts = report.counts or {}
    parts.append(_pill("ok", f"{counts.get('ok', 0)} ok"))
    parts.append(_pill("warn", f"{counts.get('warn', 0)} warnings"))
    parts.append(_pill("err", f"{counts.get('err', 0)} errors"))
    parts.append("</span>")
    parts.append("</div>")  # .status
    parts.append("</header>")

    # Dataset-level issues
    parts.append('<section id="dataset">')
    parts.append("<h2>Dataset</h2>")
    if report.dataset_issues:
        parts.append('<div class="folder ' + _max_severity_class(report.dataset_issues) + '">')
        parts.append(_render_issue_list(report.dataset_issues))
        parts.append("</div>")
    else:
        parts.append('<p class="empty">No dataset-level issues.</p>')
    parts.append("</section>")

    # Folder-level issues
    parts.append('<section id="folders">')
    parts.append("<h2>Folders</h2>")
    if report.folder_issues:
        for folder, issues in sorted(report.folder_issues.items()):
            sev_class = _max_severity_class(issues)
            parts.append(f'<div class="folder {sev_class}">')
            parts.append(
                f"<h3><span class='badge {sev_class}'>{sev_class}</span>"
                f"<code>{html.escape(folder)}</code></h3>"
            )
            parts.append(_render_issue_list(issues))
            parts.append("</div>")
    else:
        parts.append('<p class="empty">No folder-level issues.</p>')
    parts.append("</section>")

    # Per-file issues — only show files with at least one issue.
    parts.append('<section id="files">')
    parts.append("<h2>Files with issues</h2>")
    flagged = [f for f in report.files if f.issues]
    if flagged:
        # Group by parent directory for readability.
        flagged.sort(key=lambda f: (str(f.path.parent), f.path.name))
        for f in flagged:
            parts.append(_render_file(f))
    else:
        parts.append('<p class="empty">No per-file issues.</p>')
    parts.append("</section>")

    # Footer
    parts.append("<footer>")
    parts.append(
        f"Generated by <code>bidsmgr {html.escape(report.bidsmgr_version)}</code>"
        f" at {html.escape(_format_now())}."
    )
    parts.append("</footer>")

    parts.append("</div>")  # .container
    parts.append("</body></html>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pill(kind: str, label: str) -> str:
    return (
        f'<span class="pill {kind}"><span class="dot"></span>'
        f"{html.escape(label)}</span>"
    )


def _render_issue_list(issues: Iterable[Issue]) -> str:
    parts: list[str] = ['<ul class="issues">']
    for issue in issues:
        sev = issue.severity.value
        parts.append(
            f'<li class="{sev}">'
            f'<span class="badge {sev}">{sev}</span>'
            f'<span class="rule">{html.escape(issue.rule_id)}</span>'
            f'<span class="msg">{html.escape(issue.message)}</span>'
        )
        if issue.fix_label:
            parts.append(
                f'<span class="fix">{html.escape(issue.fix_label)}</span>'
            )
        elif issue.field:
            parts.append(
                f'<span class="field">{html.escape(issue.field)}</span>'
            )
        else:
            parts.append("<span></span>")
        parts.append("</li>")
    parts.append("</ul>")
    return "".join(parts)


def _render_file(f: FileVerdict) -> str:
    sev = f.severity.value
    parts: list[str] = [f'<div class="file {sev}">']
    parts.append(
        f"<h3>"
        f"<span class='badge {sev}'>{sev}</span>"
        f"<code>{html.escape(str(f.path))}</code>"
    )
    if f.datatype or f.suffix:
        typed = "/".join(filter(None, [f.datatype, f.suffix]))
        parts.append(f"<span class='typed'>{html.escape(typed)}</span>")
    parts.append("</h3>")
    parts.append(_render_issue_list(f.issues))
    parts.append("</div>")
    return "".join(parts)


def _max_severity_class(issues: Iterable[Issue]) -> str:
    """Return the worst severity in the list, as a CSS class string."""
    seen = {i.severity for i in issues}
    if Severity.ERR in seen:
        return "err"
    if Severity.WARN in seen:
        return "warn"
    return "ok"


def _format_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


__all__ = ["render_html"]
