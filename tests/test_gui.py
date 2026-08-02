from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter import font as tkfont
from unittest.mock import Mock

import pytest
from pypdf import PasswordType, PdfReader, PdfWriter

import smashpdf

pytestmark = pytest.mark.skipif(
    os.name != "nt",
    reason="SmashPDF is packaged and supported as a Windows desktop app.",
)


def _descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from _descendants(child)


def _font_size(root, widget) -> int:
    return int(tkfont.Font(root=root, font=widget.cget("font")).actual("size"))


def _font_weight(root, widget) -> str:
    return str(tkfont.Font(root=root, font=widget.cget("font")).actual("weight"))


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
    open_project = Mock(return_value=True)
    default_font_size = None

    def hidden_tk():
        nonlocal default_font_size
        root = real_tk()
        root.withdraw()
        default_font_size = int(
            tkfont.nametofont("TkDefaultFont", root=root).actual("size")
        )
        return root

    def exercise_interface(root, _n=0):
        root.update_idletasks()
        configured_default = tkfont.nametofont("TkDefaultFont", root=root)
        assert configured_default.actual("weight") == "bold"
        expected_default_size = (
            default_font_size + 2 if default_font_size > 0 else default_font_size - 2
        )
        assert int(configured_default.actual("size")) == expected_default_size
        widgets = list(_descendants(root))
        app_heading = next(
            widget
            for widget in widgets
            if isinstance(widget, ttk.Label)
            and widget.cget("text") == smashpdf.APP_NAME
        )
        drop_zone = next(widget for widget in widgets if isinstance(widget, tk.Label))
        log = next(widget for widget in widgets if isinstance(widget, tk.Text))
        assert _font_size(root, app_heading) == 22
        assert _font_size(root, drop_zone) == 14
        assert _font_size(root, log) == 11
        assert _font_weight(root, app_heading) == "bold"
        assert _font_weight(root, drop_zone) == "bold"
        assert _font_weight(root, log) == "bold"

        selector = next(
            widget for widget in widgets if isinstance(widget, ttk.Combobox)
        )
        selector.set("简体中文")
        selector.event_generate("<<ComboboxSelected>>")
        root.update()

        widgets = list(_descendants(root))
        lock_option = next(
            widget
            for widget in widgets
            if isinstance(widget, ttk.Radiobutton)
            and widget.cget("text") == "加密锁定 PDF"
        )
        lock_option.invoke()
        root.update_idletasks()
        compression_toggle = next(
            widget for widget in widgets if isinstance(widget, ttk.Checkbutton)
        )
        assert str(compression_toggle.cget("state")) == "disabled"
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
                project_link = next(
                    widget
                    for widget in _descendants(child)
                    if isinstance(widget, ttk.Label)
                    and widget.cget("text") == smashpdf.PROJECT_URL
                )
                assert str(project_link.cget("cursor")) == "hand2"
                project_link.event_generate("<Button-1>")
                root.update()
                about_sizes = {
                    _font_size(root, widget)
                    for widget in _descendants(child)
                    if isinstance(widget, ttk.Label) and widget.cget("font")
                }
                assert {12, 13, 22}.issubset(about_sizes)
                assert all(
                    _font_weight(root, widget) == "bold"
                    for widget in _descendants(child)
                    if isinstance(widget, ttk.Label) and widget.cget("font")
                )
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
    passwords = iter(("secure-password", "secure-password"))
    monkeypatch.setattr(
        simpledialog,
        "askstring",
        lambda *_args, **_kwargs: next(passwords),
    )
    monkeypatch.setattr(smashpdf.webbrowser, "open_new_tab", open_project)

    assert smashpdf.run_gui() == 0
    assert smashpdf.load_language_preference(settings) == "zh"
    locked = PdfReader(tmp_path / "gui_locked.pdf")
    assert locked.decrypt("secure-password") == PasswordType.USER_PASSWORD
    assert len(locked.pages) == 1
    show_info.assert_called_once()
    show_warning.assert_not_called()
    open_project.assert_called_once_with(smashpdf.PROJECT_URL)
