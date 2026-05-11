"""Small braille-character spinner shown while a worker is running.

Plain ``QLabel`` driven by a 100 ms ``QTimer`` that cycles through the
classic ``⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏`` glyphs. Zero image-asset overhead, scales
with the user's font, and renders identically across macOS / Linux /
Windows. Pair it with a status message via :meth:`set_message`.

Usage::

    spinner = BusySpinner()
    spinner.set_busy(True, message="Scanning…")
    # … later
    spinner.set_busy(False)
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget


# Classic braille spinner frames. Each frame fits in one monospace cell
# so the label width doesn't flicker as frames cycle.
_FRAMES: tuple[str, ...] = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
_FRAME_MS = 100


class BusySpinner(QWidget):
    """A small ``[spinner glyph] message`` indicator.

    Invisible by default; call :meth:`set_busy(True, "…")` to show it
    and ``set_busy(False)`` to hide. Multiple sequential operations can
    safely call ``set_busy`` repeatedly — the timer is owned by the
    widget and resets on each transition.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("busy-spinner")
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)

        self._glyph = QLabel(_FRAMES[0])
        self._glyph.setObjectName("busy-spinner-glyph")
        # Reserve a fixed-width cell so frame swaps don't shift layout.
        self._glyph.setMinimumWidth(14)
        self._glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.addWidget(self._glyph)

        self._message = QLabel("")
        self._message.setObjectName("busy-spinner-message")
        h.addWidget(self._message)

        self._idx = 0
        self._timer = QTimer(self)
        self._timer.setInterval(_FRAME_MS)
        self._timer.timeout.connect(self._advance)

        # Start hidden — the layout reserves no space when not busy.
        self.setVisible(False)

    # ------------------------------------------------------------------
    def set_busy(self, busy: bool, *, message: str = "") -> None:
        """Show / hide the spinner and update its message."""
        if busy:
            self._message.setText(message)
            self._idx = 0
            self._glyph.setText(_FRAMES[0])
            self.setVisible(True)
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
            self.setVisible(False)
            self._message.setText("")

    def set_message(self, message: str) -> None:
        """Update only the trailing message without restarting the timer."""
        self._message.setText(message)

    def is_busy(self) -> bool:
        return self._timer.isActive()

    # ------------------------------------------------------------------
    def _advance(self) -> None:
        self._idx = (self._idx + 1) % len(_FRAMES)
        self._glyph.setText(_FRAMES[self._idx])


__all__ = ["BusySpinner"]
