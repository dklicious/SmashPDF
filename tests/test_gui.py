from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
from unittest.mock import Mock

import pytest
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

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


def _text_pdf(path: Path, text: str) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_reference = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_reference})}
    )
    content = DecodedStreamObject()
    content.set_data(f"BT /F1 12 Tf ({text}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(content)
    writer.write(path)


def test_gui_constructs_processes_and_switches_language(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "gui.jpg"
    Image.effect_noise((1600, 1200), 100).convert("RGB").save(
        source,
        "JPEG",
        quality=95,
    )
    search_source = tmp_path / "gui-search.pdf"
    _text_pdf(search_source, "Lease record for Example Tenant in Truganina")
    settings = tmp_path / "settings.json"

    real_tk = tk.Tk
    show_info = Mock()
    show_warning = Mock()
    open_project = Mock(return_value=True)
    select_files = Mock(
        side_effect=((str(source),), (str(search_source),)),
    )
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
        image_option = next(
            widget
            for widget in widgets
            if isinstance(widget, ttk.Radiobutton) and widget.cget("text") == "压缩图片"
        )
        image_option.invoke()
        root.update_idletasks()
        compression_toggle = next(
            widget
            for widget in widgets
            if isinstance(widget, ttk.Checkbutton)
            and widget.cget("text") == "解锁后压缩 PDF"
        )
        assert not compression_toggle.winfo_manager()
        browse = next(
            widget
            for widget in widgets
            if isinstance(widget, ttk.Button) and "图片" in widget.cget("text")
        )
        browse.invoke()

        search_option = next(
            widget
            for widget in widgets
            if isinstance(widget, ttk.Radiobutton) and widget.cget("text") == "搜索 PDF"
        )
        search_option.invoke()
        root.update_idletasks()
        search_entry = next(
            widget
            for widget in _descendants(root)
            if isinstance(widget, ttk.Entry) and not isinstance(widget, ttk.Combobox)
        )
        search_entry.insert(0, "example tenant")
        search_browse = next(
            widget
            for widget in _descendants(root)
            if isinstance(widget, ttk.Button) and widget.cget("text") == "选择 PDF 文件"
        )
        assert str(search_browse.cget("state")) == "normal"
        search_browse.invoke()
        root.update_idletasks()
        assert select_files.call_count == 2
        assert "gui-search.pdf — 第 1 页" in log.get("1.0", "end")
        folder_browse = next(
            widget
            for widget in _descendants(root)
            if isinstance(widget, ttk.Button) and widget.cget("text") == "选择文件夹"
        )
        assert folder_browse.winfo_manager()

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
        select_files,
    )
    monkeypatch.setattr(messagebox, "showinfo", show_info)
    monkeypatch.setattr(messagebox, "showwarning", show_warning)
    monkeypatch.setattr(smashpdf.webbrowser, "open_new_tab", open_project)

    assert smashpdf.run_gui() == 0
    assert smashpdf.load_language_preference(settings) == "zh"
    output = tmp_path / "gui_compressed.jpg"
    assert output.stat().st_size < source.stat().st_size
    with Image.open(output) as compressed:
        assert compressed.format == "JPEG"
    assert show_info.call_count == 2
    show_warning.assert_not_called()
    open_project.assert_called_once_with(smashpdf.PROJECT_URL)
