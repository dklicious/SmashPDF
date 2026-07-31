from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from unittest.mock import Mock

import pytest
from pypdf import PdfReader, PdfWriter

import smashpdf

pytestmark = pytest.mark.skipif(
    os.name != "nt",
    reason="SmashPDF is packaged and supported as a Windows desktop app.",
)


def _descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from _descendants(child)


def test_gui_constructs_processes_and_switches_language(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "gui.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(source)
    settings = tmp_path / "settings.json"

    real_tk = tk.Tk
    show_info = Mock()
    show_warning = Mock()

    def hidden_tk():
        root = real_tk()
        root.withdraw()
        return root

    def exercise_interface(root, _n=0):
        root.update_idletasks()
        widgets = list(_descendants(root))
        selector = next(
            widget for widget in widgets if isinstance(widget, ttk.Combobox)
        )
        selector.set("简体中文")
        selector.event_generate("<<ComboboxSelected>>")
        root.update()

        widgets = list(_descendants(root))
        browse = next(
            widget
            for widget in widgets
            if isinstance(widget, ttk.Button) and "PDF" in widget.cget("text")
        )
        browse.invoke()

        about = next(
            widget
            for widget in widgets
            if isinstance(widget, ttk.Button) and widget.cget("text") == "关于"
        )
        about.invoke()
        root.update_idletasks()
        for child in root.winfo_children():
            if isinstance(child, tk.Toplevel):
                child.destroy()
        root.destroy()

    monkeypatch.setitem(sys.modules, "tkinterdnd2", None)
    monkeypatch.setattr(tk, "Tk", hidden_tk)
    monkeypatch.setattr(tk.Misc, "mainloop", exercise_interface)
    monkeypatch.setattr(smashpdf, "settings_path", lambda: settings)
    monkeypatch.setattr(
        filedialog,
        "askopenfilenames",
        lambda **_kwargs: (str(source),),
    )
    monkeypatch.setattr(messagebox, "showinfo", show_info)
    monkeypatch.setattr(messagebox, "showwarning", show_warning)

    assert smashpdf.run_gui() == 0
    assert smashpdf.load_language_preference(settings) == "zh"
    assert len(PdfReader(tmp_path / "gui_unlocked.pdf").pages) == 1
    show_info.assert_called_once()
    show_warning.assert_not_called()
