#!/usr/bin/env python3
"""Create editable, restriction-free and compressed copies of PDF files.

The source file is never modified. Password encryption is removed after the
document has been successfully opened. Digital-signature fields and document
certification controls are removed; visible signature appearances are retained
as stamp annotations. Optional compression reduces embedded image resolution
while preserving page geometry, images, and selectable text.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import traceback
import zlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    EncodedStreamObject,
    IndirectObject,
    NameObject,
    TextStringObject,
)

APP_NAME = "SmashPDF"
APP_VERSION = "1.0.0"
PROJECT_URL = "https://github.com/dklicious/SmashPDF"
COMPRESSION_PROFILES = {
    "none": {
        "label": "Unlock only",
        "suffix": "_unlocked",
    },
    "standard": {
        "label": "Standard lossless compression",
        "suffix": "_unlocked_compressed",
    },
    "major": {
        "label": "Maximum lossless compression",
        "suffix": "_unlocked_major_compressed",
    },
}


class PasswordRequiredError(Exception):
    """Raised when a PDF requires a valid opening password."""


@dataclass(frozen=True)
class UnlockResult:
    source: Path
    output: Path
    page_count: int
    was_encrypted: bool
    removed_signature_fields: int
    preserved_signature_appearances: int
    compression_mode: str
    streams_optimized: int
    source_size: int
    output_size: int

    @property
    def reduction_percent(self) -> float:
        if not self.source_size:
            return 0.0
        return max(0.0, (1 - self.output_size / self.source_size) * 100)


def _resolved(value):
    return value.get_object() if isinstance(value, IndirectObject) else value


def _field_type(obj: DictionaryObject) -> str | None:
    field_type = obj.get("/FT")
    if field_type:
        return str(field_type)
    parent = _resolved(obj.get("/Parent"))
    return str(parent.get("/FT")) if parent and parent.get("/FT") else None


def _rect_has_area(rect) -> bool:
    if not rect or len(rect) != 4:
        return False
    try:
        return (
            abs(float(rect[2]) - float(rect[0])) > 0.01
            and abs(float(rect[3]) - float(rect[1])) > 0.01
        )
    except (TypeError, ValueError):
        return False


def _signature_has_visible_appearance(widget: DictionaryObject) -> bool:
    appearance = _resolved(widget.get("/AP"))
    return bool(
        _rect_has_area(widget.get("/Rect"))
        and appearance
        and appearance.get("/N")
        and not (int(widget.get("/F", 0)) & 0b11)
    )


def _convert_signature_widget_to_stamp(widget: DictionaryObject) -> None:
    """Keep the widget appearance while detaching cryptographic field data."""

    widget[NameObject("/Subtype")] = NameObject("/Stamp")
    widget[NameObject("/Contents")] = TextStringObject(
        "Visible appearance retained from a removed digital-signature field."
    )
    widget[NameObject("/NM")] = TextStringObject("Retained signature appearance")

    for key in (
        "/FT",
        "/V",
        "/T",
        "/TU",
        "/TM",
        "/Ff",
        "/Parent",
        "/Kids",
        "/Lock",
        "/SV",
        "/AA",
        "/A",
    ):
        widget.pop(NameObject(key), None)


def _detach_signature_widgets(writer: PdfWriter) -> tuple[int, int]:
    removed = 0
    preserved = 0

    for page in writer.pages:
        annotations = page.get("/Annots")
        if not annotations:
            continue

        annotation_array = _resolved(annotations)
        kept = ArrayObject()

        for reference in annotation_array:
            annotation = reference.get_object()
            is_signature = (
                annotation.get("/Subtype") == "/Widget"
                and _field_type(annotation) == "/Sig"
            )
            if not is_signature:
                kept.append(reference)
                continue

            removed += 1
            if _signature_has_visible_appearance(annotation):
                _convert_signature_widget_to_stamp(annotation)
                kept.append(reference)
                preserved += 1

        if kept:
            page[NameObject("/Annots")] = kept
        else:
            page.pop(NameObject("/Annots"), None)

    return removed, preserved


def _prune_signature_fields(field_refs: Iterable) -> tuple[ArrayObject, int]:
    kept = ArrayObject()
    removed = 0

    for reference in field_refs:
        field = reference.get_object()
        inherited_type = _field_type(field)

        if inherited_type == "/Sig":
            removed += 1
            continue

        kids = field.get("/Kids")
        if kids:
            retained_kids, child_removed = _prune_signature_fields(_resolved(kids))
            removed += child_removed
            if retained_kids:
                field[NameObject("/Kids")] = retained_kids
            else:
                field.pop(NameObject("/Kids"), None)

        kept.append(reference)

    return kept, removed


def _remove_signature_controls(writer: PdfWriter) -> tuple[int, int]:
    widget_count, preserved_count = _detach_signature_widgets(writer)
    root = writer.root_object

    root.pop(NameObject("/Perms"), None)

    acroform_ref = root.get("/AcroForm")
    if not acroform_ref:
        return widget_count, preserved_count

    acroform = _resolved(acroform_ref)
    fields = _resolved(acroform.get("/Fields")) if acroform.get("/Fields") else []
    kept_fields, removed_fields = _prune_signature_fields(fields)

    if kept_fields:
        acroform[NameObject("/Fields")] = kept_fields
        acroform.pop(NameObject("/SigFlags"), None)
    else:
        root.pop(NameObject("/AcroForm"), None)

    return max(widget_count, removed_fields), preserved_count


def _open_reader(source: Path, password: str | None) -> tuple[PdfReader, bool]:
    reader = PdfReader(str(source))
    was_encrypted = reader.is_encrypted

    if not was_encrypted:
        return reader, False

    candidate_passwords = []
    if password is not None:
        candidate_passwords.append(password)
    if "" not in candidate_passwords:
        candidate_passwords.append("")

    for candidate in candidate_passwords:
        if _password_unlocks(reader, candidate):
            return reader, True

    raise PasswordRequiredError(
        "This PDF requires its opening password. Editing-permission passwords "
        "are removed automatically when the PDF can already be opened."
    )


def _password_unlocks(reader: PdfReader, password: str) -> bool:
    try:
        return bool(reader.decrypt(password))
    except (PdfReadError, TypeError, ValueError):
        return False


def _compress_page_content(page) -> bool:
    try:
        page.compress_content_streams()
    except (PdfReadError, TypeError, ValueError):
        return False
    return True


def _decoded_stream_data(stream) -> bytes | None:
    try:
        decoded_data = stream.get_data()
    except (PdfReadError, TypeError, ValueError, zlib.error):
        return None
    return decoded_data if isinstance(decoded_data, bytes) else None


def default_output_path(source: Path, compression: str = "none") -> Path:
    profile = COMPRESSION_PROFILES[compression]
    suffix = profile["suffix"]
    base = source.with_name(f"{source.stem}{suffix}{source.suffix}")
    if not base.exists():
        return base

    number = 2
    while True:
        candidate = source.with_name(f"{source.stem}{suffix} ({number}){source.suffix}")
        if not candidate.exists():
            return candidate
        number += 1


def _losslessly_recompress_streams(writer: PdfWriter, mode: str) -> int:
    if mode == "none":
        return 0

    optimized = 0
    for page in writer.pages:
        if _compress_page_content(page):
            optimized += 1

    if mode != "major":
        return optimized

    # Maximum mode performs a second lossless pass over eligible streams.
    # JPEG, JPEG2000, CCITT and JBIG2 image bytes are deliberately untouched.
    for index, stream in enumerate(list(writer._objects)):
        if stream is None or not hasattr(stream, "get_data"):
            continue

        stream_filter = stream.get("/Filter")
        if stream_filter not in (None, "/FlateDecode"):
            continue

        stored_data = getattr(stream, "_data", None)
        if not isinstance(stored_data, bytes) or len(stored_data) < 256:
            continue

        decoded_data = _decoded_stream_data(stream)
        if decoded_data is None:
            continue

        compressed_data = zlib.compress(decoded_data, 9)
        if len(compressed_data) + 12 >= len(stored_data):
            continue

        replacement = EncodedStreamObject()
        replacement._data = compressed_data
        replacement.indirect_reference = getattr(
            stream,
            "indirect_reference",
            None,
        )
        for key, value in stream.items():
            if key not in ("/Length", "/Filter", "/DecodeParms"):
                replacement[key] = value
        replacement[NameObject("/Filter")] = NameObject("/FlateDecode")
        writer._objects[index] = replacement
        optimized += 1

    return optimized


def _validate_output(output: Path, expected_pages: int) -> None:
    check = PdfReader(str(output))
    if check.is_encrypted:
        raise RuntimeError("The output is unexpectedly still encrypted.")
    if len(check.pages) != expected_pages:
        raise RuntimeError(
            f"Page count changed from {expected_pages} to {len(check.pages)}."
        )
    if check.root_object.get("/Perms"):
        raise RuntimeError("Certification permissions remain in the output.")

    fields = check.get_fields() or {}
    remaining_signatures = [
        name for name, field in fields.items() if str(field.get("/FT")) == "/Sig"
    ]
    if remaining_signatures:
        raise RuntimeError(
            "Signature fields remain in the output: " + ", ".join(remaining_signatures)
        )


def unlock_pdf(
    source: str | Path,
    *,
    password: str | None = None,
    output: str | Path | None = None,
    overwrite: bool = False,
    compression: str = "none",
) -> UnlockResult:
    if compression not in COMPRESSION_PROFILES:
        raise ValueError(f"Unknown compression mode: {compression}")

    source_path = Path(source).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"PDF not found: {source_path}")
    if source_path.suffix.lower() != ".pdf":
        raise ValueError(f"Not a PDF file: {source_path}")

    output_path = (
        Path(output).expanduser().resolve()
        if output is not None
        else default_output_path(source_path, compression)
    )
    if output_path == source_path:
        raise ValueError("The output must be different from the source PDF.")
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    reader, was_encrypted = _open_reader(source_path, password)
    expected_pages = len(reader.pages)

    writer = PdfWriter(clone_from=reader)
    signature_fields, preserved_appearances = _remove_signature_controls(writer)
    streams_optimized = _losslessly_recompress_streams(writer, compression)

    # Remove detached cryptographic objects and duplicate resources.
    writer.compress_identical_objects(
        remove_duplicates=True,
        remove_unreferenced=True,
    )

    temp_fd, temp_name = tempfile.mkstemp(
        prefix=f".{output_path.stem}-",
        suffix=".tmp.pdf",
        dir=str(output_path.parent),
    )
    os.close(temp_fd)
    temp_path = Path(temp_name)

    try:
        writer.write(str(temp_path))
        _validate_output(temp_path, expected_pages)
        if output_path.exists() and overwrite:
            os.replace(temp_path, output_path)
        else:
            temp_path.replace(output_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    return UnlockResult(
        source=source_path,
        output=output_path,
        page_count=expected_pages,
        was_encrypted=was_encrypted,
        removed_signature_fields=signature_fields,
        preserved_signature_appearances=preserved_appearances,
        compression_mode=compression,
        streams_optimized=streams_optimized,
        source_size=source_path.stat().st_size,
        output_size=output_path.stat().st_size,
    )


def _format_result(result: UnlockResult) -> str:
    changes = []
    if result.was_encrypted:
        changes.append("encryption removed")
    if result.removed_signature_fields:
        changes.append(
            f"{result.removed_signature_fields} digital-signature field(s) removed"
        )
    if not changes:
        changes.append("an unrestricted copy was created")
    if result.compression_mode != "none":
        changes.append(
            f"{COMPRESSION_PROFILES[result.compression_mode]['label'].lower()}; "
            f"{result.streams_optimized} stream(s) optimized"
        )

    return (
        f"Created: {result.output}\n"
        f"Pages: {result.page_count}; "
        + "; ".join(changes)
        + f"\nSize: {result.source_size / 1_048_576:.2f} MB -> "
        f"{result.output_size / 1_048_576:.2f} MB "
        f"({result.reduction_percent:.1f}% smaller)"
    )


def run_gui() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk

    try:
        from tkinterdnd2 import DND_FILES, TkinterDnD

        root = TkinterDnD.Tk()
        drag_and_drop_available = True
    except ImportError:
        DND_FILES = None
        root = tk.Tk()
        drag_and_drop_available = False

    root.title(APP_NAME)
    root.geometry("740x690")
    root.minsize(680, 610)

    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")

    outer = ttk.Frame(root, padding=20)
    outer.pack(fill="both", expand=True)

    ttk.Label(
        outer,
        text="SmashPDF",
        font=("Segoe UI", 20, "bold"),
    ).pack(anchor="w")
    ttk.Label(
        outer,
        text=(
            "Drop PDF files below to unlock them. Optionally compress them "
            "without reducing quality. Original files are never changed."
        ),
        wraplength=660,
    ).pack(anchor="w", pady=(4, 14))

    warning = (
        "Digital-signature verification will be removed from unlocked copies. "
        "Visible signature appearances are retained."
    )
    ttk.Label(
        outer,
        text=warning,
        foreground="#9A4D00",
        wraplength=660,
    ).pack(anchor="w", pady=(0, 14))

    compression_enabled = tk.BooleanVar(value=False)
    compression_level = tk.StringVar(value="standard")
    options = ttk.LabelFrame(outer, text="Processing option", padding=10)
    options.pack(fill="x", pady=(0, 14))

    ttk.Checkbutton(
        options,
        text="Compress PDF after unlocking (keeps original quality)",
        variable=compression_enabled,
        command=lambda: update_compression_controls(),
    ).pack(anchor="w", pady=(2, 5))

    standard_radio = ttk.Radiobutton(
        options,
        text="Standard compression - usually 5-30% smaller",
        variable=compression_level,
        value="standard",
    )
    standard_radio.pack(anchor="w", padx=(22, 0), pady=2)
    major_radio = ttk.Radiobutton(
        options,
        text="Maximum compression - usually 10-40% smaller",
        variable=compression_level,
        value="major",
    )
    major_radio.pack(anchor="w", padx=(22, 0), pady=2)

    def update_compression_controls() -> None:
        state = "normal" if compression_enabled.get() else "disabled"
        standard_radio.configure(state=state)
        major_radio.configure(state=state)

    update_compression_controls()

    ttk.Label(
        options,
        text=("No quality is removed. The exact saving is shown after processing."),
        foreground="#555555",
        wraplength=630,
    ).pack(anchor="w", pady=(5, 0))

    drop_text = (
        "DROP PDF FILES HERE\n\nor click this box to browse"
        if drag_and_drop_available
        else "CLICK HERE TO CHOOSE PDF FILES"
    )
    drop_zone = tk.Label(
        outer,
        text=drop_text,
        font=("Segoe UI", 12, "bold"),
        foreground="#1F4E79",
        background="#F2F7FC",
        relief="groove",
        borderwidth=2,
        height=6,
        cursor="hand2",
    )
    drop_zone.pack(fill="x", pady=(0, 14))

    log = tk.Text(
        outer,
        height=9,
        wrap="word",
        font=("Consolas", 9),
        state="disabled",
    )
    log.pack(fill="both", expand=True)

    button_row = ttk.Frame(outer)
    button_row.pack(fill="x", pady=(14, 0))

    def append_log(text: str) -> None:
        log.configure(state="normal")
        log.insert("end", text.rstrip() + "\n\n")
        log.see("end")
        log.configure(state="disabled")
        root.update_idletasks()

    def process_files(filenames) -> None:
        pdf_files = []
        for filename in filenames:
            path = Path(filename)
            if path.is_file() and path.suffix.lower() == ".pdf":
                pdf_files.append(path)
            else:
                append_log(f"Skipped (not a PDF): {path.name or path}")

        if not pdf_files:
            messagebox.showwarning(
                APP_NAME,
                "No PDF files were found. Drop or select one or more .pdf files.",
                parent=root,
            )
            return

        selected_mode = compression_level.get() if compression_enabled.get() else "none"
        choose_button.configure(state="disabled")
        drop_zone.configure(
            text=f"PROCESSING {len(pdf_files)} PDF FILE(S)...",
            cursor="watch",
            background="#FFF7E6",
        )
        successes = 0
        failures = []

        try:
            for source in pdf_files:
                append_log(f"Processing: {source.name}")
                try:
                    result = unlock_pdf(source, compression=selected_mode)
                except PasswordRequiredError:
                    password = simpledialog.askstring(
                        APP_NAME,
                        f"Enter the opening password for:\n{source.name}",
                        parent=root,
                        show="*",
                    )
                    if password is None:
                        failures.append(f"{source.name}: cancelled")
                        append_log("Cancelled.")
                        continue
                    try:
                        result = unlock_pdf(
                            source,
                            password=password,
                            compression=selected_mode,
                        )
                    except Exception as exc:
                        failures.append(f"{source.name}: {exc}")
                        append_log(f"Failed: {exc}")
                        continue
                except Exception as exc:
                    failures.append(f"{source.name}: {exc}")
                    append_log(f"Failed: {exc}")
                    continue

                successes += 1
                append_log(_format_result(result))
        finally:
            choose_button.configure(state="normal")
            drop_zone.configure(
                text=drop_text,
                cursor="hand2",
                background="#F2F7FC",
            )

        if failures:
            messagebox.showwarning(
                APP_NAME,
                f"Completed: {successes}\nFailed or cancelled: {len(failures)}\n\n"
                + "\n".join(failures[:8]),
                parent=root,
            )
        else:
            messagebox.showinfo(
                APP_NAME,
                f"Finished. Created {successes} processed PDF(s).",
                parent=root,
            )

    def select_and_unlock() -> None:
        filenames = filedialog.askopenfilenames(
            parent=root,
            title="Select PDF files for SmashPDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if filenames:
            process_files(filenames)

    def handle_drop(event) -> None:
        filenames = root.tk.splitlist(event.data)
        process_files(filenames)

    def show_about() -> None:
        about = tk.Toplevel(root)
        about.title(f"About {APP_NAME}")
        about.geometry("390x240")
        about.resizable(False, False)
        about.transient(root)
        about.grab_set()

        ttk.Label(
            about,
            text=APP_NAME,
            font=("Segoe UI", 20, "bold"),
        ).pack(pady=(24, 2))
        ttk.Label(
            about,
            text=f"Version {APP_VERSION}",
            foreground="#555555",
        ).pack()
        ttk.Label(
            about,
            text="Thank you for your support",
            font=("Segoe UI", 11),
        ).pack(pady=(20, 4))
        ttk.Label(
            about,
            text="Made by dklicious.",
            font=("Segoe UI", 10, "bold"),
        ).pack()
        ttk.Label(
            about,
            text=PROJECT_URL,
            foreground="#1F4E79",
        ).pack(pady=(8, 14))
        ttk.Button(about, text="Close", command=about.destroy).pack()

        about.update_idletasks()
        x = root.winfo_x() + (root.winfo_width() - about.winfo_width()) // 2
        y = root.winfo_y() + (root.winfo_height() - about.winfo_height()) // 2
        about.geometry(f"+{max(0, x)}+{max(0, y)}")
        about.focus_set()

    drop_zone.bind("<Button-1>", lambda _event: select_and_unlock())
    if drag_and_drop_available and DND_FILES is not None:
        drop_zone.drop_target_register(DND_FILES)
        drop_zone.dnd_bind("<<Drop>>", handle_drop)

    choose_button = ttk.Button(
        button_row,
        text="Browse PDF Files",
        command=select_and_unlock,
    )
    choose_button.pack(side="left")
    ttk.Button(button_row, text="Close", command=root.destroy).pack(side="right")
    ttk.Button(button_row, text="About", command=show_about).pack(
        side="right",
        padx=(0, 8),
    )

    root.mainloop()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create unrestricted PDF copies without modifying the source files."
        )
    )
    parser.add_argument("files", nargs="*", help="PDF files to unlock")
    parser.add_argument(
        "-p",
        "--password",
        help="Opening password, if the PDF requires one",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output path (valid only when processing one PDF)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacement of an explicitly selected output file",
    )
    parser.add_argument(
        "--compression",
        choices=("none", "standard", "major"),
        default="none",
        help=("Lossless compression: none, standard, or major"),
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Open the graphical interface",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.gui or not args.files:
        return run_gui()
    if args.output and len(args.files) != 1:
        raise SystemExit("--output can only be used with one input PDF.")

    exit_code = 0
    for filename in args.files:
        try:
            result = unlock_pdf(
                filename,
                password=args.password,
                output=args.output,
                overwrite=args.overwrite,
                compression=args.compression,
            )
            print(_format_result(result))
        except Exception as exc:
            exit_code = 1
            print(f"Failed: {filename}\n{exc}", file=sys.stderr)
            if os.environ.get("PDF_UNLOCKER_DEBUG"):
                traceback.print_exc()

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
