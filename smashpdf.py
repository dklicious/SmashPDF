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
import json
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
APP_VERSION = "1.2.2"
PROJECT_URL = "https://github.com/dklicious/SmashPDF"
LANGUAGE_NAMES = {
    "zh": "简体中文",
    "zh_hant": "繁體中文",
    "en": "English",
    "es": "Español",
    "ja": "日本語",
    "ko": "한국어",
}
TRANSLATIONS = {
    "en": {
        "language": "Language",
        "intro": (
            "Drop PDF files below to unlock them. Optionally compress them "
            "without reducing quality. Original files are never changed."
        ),
        "warning": (
            "Digital-signature verification will be removed from unlocked "
            "copies. Visible signature appearances are retained."
        ),
        "processing_option": "Processing option",
        "compress_after_unlocking": (
            "Compress PDF after unlocking (keeps original quality)"
        ),
        "standard_compression": "Standard compression - usually 5-30% smaller",
        "maximum_compression": "Maximum compression - usually 10-40% smaller",
        "no_quality_removed": (
            "No quality is removed. The exact saving is shown after processing."
        ),
        "drop_files": "DROP PDF FILES HERE\n\nor click this box to browse",
        "choose_files": "CLICK HERE TO CHOOSE PDF FILES",
        "processing_files": "PROCESSING {count} PDF FILE(S)...",
        "browse_files": "Browse PDF Files",
        "close": "Close",
        "about": "About",
        "select_title": "Select PDF files for SmashPDF",
        "pdf_files": "PDF files",
        "all_files": "All files",
        "skipped_not_pdf": "Skipped (not a PDF): {name}",
        "no_pdf": (
            "No PDF files were found. Drop or select one or more .pdf files."
        ),
        "processing_file": "Processing: {name}",
        "cancelled": "Cancelled.",
        "failed": "Failed: {error}",
        "opening_prompt": "Enter the opening password for:\n{name}",
        "completed_with_failures": (
            "Completed: {successes}\nFailed or cancelled: {failures}\n\n{details}"
        ),
        "finished": "Finished. Created {successes} processed PDF(s).",
        "version": "Version {version}",
        "thank_you": "Thank you for your support",
        "made_by": "Made by dklicious.",
        "encryption_removed": "encryption removed",
        "signature_fields_removed": (
            "{count} digital-signature field(s) removed"
        ),
        "unrestricted_copy_created": "an unrestricted copy was created",
        "standard_result": (
            "standard lossless compression; {count} stream(s) optimized"
        ),
        "maximum_result": (
            "maximum lossless compression; {count} stream(s) optimized"
        ),
        "result_summary": (
            "Created: {output}\nPages: {pages}; {changes}\n"
            "Size: {source_mb:.2f} MB -> {output_mb:.2f} MB "
            "({reduction:.1f}% smaller)"
        ),
    },
    "zh": {
        "language": "语言",
        "intro": (
            "将 PDF 文件拖放到下方以解除限制。可选择在不降低质量的情况下压缩。"
            "原始文件不会被更改。"
        ),
        "warning": (
            "解锁后的副本将移除数字签名验证。可见的签名外观会保留。"
        ),
        "processing_option": "处理选项",
        "compress_after_unlocking": "解锁后压缩 PDF（保持原始质量）",
        "standard_compression": "标准压缩 — 通常缩小 5–30%",
        "maximum_compression": "最大压缩 — 通常缩小 10–40%",
        "no_quality_removed": "不会降低质量。处理后会显示实际节省的空间。",
        "drop_files": "将 PDF 文件拖放到这里\n\n或单击此框浏览文件",
        "choose_files": "单击此处选择 PDF 文件",
        "processing_files": "正在处理 {count} 个 PDF 文件...",
        "browse_files": "浏览 PDF 文件",
        "close": "关闭",
        "about": "关于",
        "select_title": "选择要用 SmashPDF 处理的 PDF 文件",
        "pdf_files": "PDF 文件",
        "all_files": "所有文件",
        "skipped_not_pdf": "已跳过（不是 PDF）：{name}",
        "no_pdf": "未找到 PDF 文件。请拖放或选择一个或多个 .pdf 文件。",
        "processing_file": "正在处理：{name}",
        "cancelled": "已取消。",
        "failed": "失败：{error}",
        "opening_prompt": "请输入以下文件的打开密码：\n{name}",
        "completed_with_failures": (
            "已完成：{successes}\n失败或取消：{failures}\n\n{details}"
        ),
        "finished": "处理完成。已创建 {successes} 个 PDF 文件。",
        "version": "版本 {version}",
        "thank_you": "感谢您的支持",
        "made_by": "由 dklicious 制作。",
        "encryption_removed": "已移除加密",
        "signature_fields_removed": "已移除 {count} 个数字签名字段",
        "unrestricted_copy_created": "已创建无限制副本",
        "standard_result": "标准无损压缩；已优化 {count} 个数据流",
        "maximum_result": "最大无损压缩；已优化 {count} 个数据流",
        "result_summary": (
            "已创建：{output}\n页数：{pages}；{changes}\n"
            "大小：{source_mb:.2f} MB -> {output_mb:.2f} MB "
            "（缩小 {reduction:.1f}%）"
        ),
    },
    "zh_hant": {
        "language": "語言",
        "intro": (
            "將 PDF 檔案拖放到下方以解除限制。可選擇在不降低品質的情況下壓縮。"
            "原始檔案不會被變更。"
        ),
        "warning": (
            "解鎖後的副本將移除數位簽章驗證。可見的簽章外觀會保留。"
        ),
        "processing_option": "處理選項",
        "compress_after_unlocking": "解鎖後壓縮 PDF（保持原始品質）",
        "standard_compression": "標準壓縮 — 通常縮小 5–30%",
        "maximum_compression": "最大壓縮 — 通常縮小 10–40%",
        "no_quality_removed": "不會降低品質。處理後會顯示實際節省的空間。",
        "drop_files": "將 PDF 檔案拖放到這裡\n\n或按一下此方塊瀏覽檔案",
        "choose_files": "按一下此處選擇 PDF 檔案",
        "processing_files": "正在處理 {count} 個 PDF 檔案...",
        "browse_files": "瀏覽 PDF 檔案",
        "close": "關閉",
        "about": "關於",
        "select_title": "選擇要用 SmashPDF 處理的 PDF 檔案",
        "pdf_files": "PDF 檔案",
        "all_files": "所有檔案",
        "skipped_not_pdf": "已略過（不是 PDF）：{name}",
        "no_pdf": "找不到 PDF 檔案。請拖放或選擇一個或多個 .pdf 檔案。",
        "processing_file": "正在處理：{name}",
        "cancelled": "已取消。",
        "failed": "失敗：{error}",
        "opening_prompt": "請輸入以下檔案的開啟密碼：\n{name}",
        "completed_with_failures": (
            "已完成：{successes}\n失敗或取消：{failures}\n\n{details}"
        ),
        "finished": "處理完成。已建立 {successes} 個 PDF 檔案。",
        "version": "版本 {version}",
        "thank_you": "感謝您的支持",
        "made_by": "由 dklicious 製作。",
        "encryption_removed": "已移除加密",
        "signature_fields_removed": "已移除 {count} 個數位簽章欄位",
        "unrestricted_copy_created": "已建立無限制副本",
        "standard_result": "標準無損壓縮；已最佳化 {count} 個資料流",
        "maximum_result": "最大無損壓縮；已最佳化 {count} 個資料流",
        "result_summary": (
            "已建立：{output}\n頁數：{pages}；{changes}\n"
            "大小：{source_mb:.2f} MB -> {output_mb:.2f} MB "
            "（縮小 {reduction:.1f}%）"
        ),
    },
    "es": {
        "language": "Idioma",
        "intro": (
            "Arrastra archivos PDF abajo para desbloquearlos. También puedes "
            "comprimirlos sin reducir la calidad. Los originales no se modifican."
        ),
        "warning": (
            "La verificación de firmas digitales se eliminará de las copias "
            "desbloqueadas. La apariencia visible de las firmas se conserva."
        ),
        "processing_option": "Opción de procesamiento",
        "compress_after_unlocking": (
            "Comprimir el PDF después de desbloquearlo (mantiene la calidad)"
        ),
        "standard_compression": (
            "Compresión estándar - normalmente 5-30% más pequeño"
        ),
        "maximum_compression": (
            "Compresión máxima - normalmente 10-40% más pequeño"
        ),
        "no_quality_removed": (
            "No se reduce la calidad. El ahorro exacto se muestra al terminar."
        ),
        "drop_files": (
            "ARRASTRA LOS ARCHIVOS PDF AQUÍ\n\n"
            "o haz clic en este cuadro para buscarlos"
        ),
        "choose_files": "HAZ CLIC AQUÍ PARA ELEGIR ARCHIVOS PDF",
        "processing_files": "PROCESANDO {count} ARCHIVO(S) PDF...",
        "browse_files": "Buscar archivos PDF",
        "close": "Cerrar",
        "about": "Acerca de",
        "select_title": "Seleccionar archivos PDF para SmashPDF",
        "pdf_files": "Archivos PDF",
        "all_files": "Todos los archivos",
        "skipped_not_pdf": "Omitido (no es un PDF): {name}",
        "no_pdf": (
            "No se encontraron archivos PDF. Arrastra o selecciona uno o más "
            "archivos .pdf."
        ),
        "processing_file": "Procesando: {name}",
        "cancelled": "Cancelado.",
        "failed": "Error: {error}",
        "opening_prompt": "Introduce la contraseña de apertura para:\n{name}",
        "completed_with_failures": (
            "Completados: {successes}\nFallidos o cancelados: {failures}\n\n"
            "{details}"
        ),
        "finished": "Terminado. Se crearon {successes} PDF procesado(s).",
        "version": "Versión {version}",
        "thank_you": "Gracias por tu apoyo",
        "made_by": "Creado por dklicious.",
        "encryption_removed": "cifrado eliminado",
        "signature_fields_removed": (
            "{count} campo(s) de firma digital eliminado(s)"
        ),
        "unrestricted_copy_created": "se creó una copia sin restricciones",
        "standard_result": (
            "compresión estándar sin pérdida; {count} flujo(s) optimizado(s)"
        ),
        "maximum_result": (
            "compresión máxima sin pérdida; {count} flujo(s) optimizado(s)"
        ),
        "result_summary": (
            "Creado: {output}\nPáginas: {pages}; {changes}\n"
            "Tamaño: {source_mb:.2f} MB -> {output_mb:.2f} MB "
            "({reduction:.1f}% más pequeño)"
        ),
    },
    "ja": {
        "language": "言語",
        "intro": (
            "PDF ファイルを下にドロップして制限を解除します。品質を落とさずに"
            "圧縮することもできます。元のファイルは変更されません。"
        ),
        "warning": (
            "解除後のコピーではデジタル署名の検証が削除されます。"
            "表示されている署名の外観は保持されます。"
        ),
        "processing_option": "処理オプション",
        "compress_after_unlocking": "解除後に PDF を圧縮（元の品質を保持）",
        "standard_compression": "標準圧縮 — 通常 5～30% 小さくなります",
        "maximum_compression": "最大圧縮 — 通常 10～40% 小さくなります",
        "no_quality_removed": "品質は低下しません。処理後に正確な削減量を表示します。",
        "drop_files": (
            "ここに PDF ファイルをドロップ\n\n"
            "または、このボックスをクリックして参照"
        ),
        "choose_files": "ここをクリックして PDF ファイルを選択",
        "processing_files": "{count} 個の PDF ファイルを処理中...",
        "browse_files": "PDF ファイルを参照",
        "close": "閉じる",
        "about": "このアプリについて",
        "select_title": "SmashPDF で処理する PDF ファイルを選択",
        "pdf_files": "PDF ファイル",
        "all_files": "すべてのファイル",
        "skipped_not_pdf": "スキップ（PDF ではありません）：{name}",
        "no_pdf": (
            "PDF ファイルが見つかりません。1 つ以上の .pdf ファイルを"
            "ドロップまたは選択してください。"
        ),
        "processing_file": "処理中：{name}",
        "cancelled": "キャンセルしました。",
        "failed": "失敗：{error}",
        "opening_prompt": "次のファイルを開くパスワードを入力してください：\n{name}",
        "completed_with_failures": (
            "完了：{successes}\n失敗またはキャンセル：{failures}\n\n{details}"
        ),
        "finished": "完了しました。{successes} 個の PDF を作成しました。",
        "version": "バージョン {version}",
        "thank_you": "ご支援ありがとうございます",
        "made_by": "制作：dklicious",
        "encryption_removed": "暗号化を解除",
        "signature_fields_removed": "デジタル署名フィールドを {count} 個削除",
        "unrestricted_copy_created": "制限のないコピーを作成",
        "standard_result": "標準ロスレス圧縮；{count} ストリームを最適化",
        "maximum_result": "最大ロスレス圧縮；{count} ストリームを最適化",
        "result_summary": (
            "作成先：{output}\nページ数：{pages}；{changes}\n"
            "サイズ：{source_mb:.2f} MB -> {output_mb:.2f} MB "
            "（{reduction:.1f}% 縮小）"
        ),
    },
    "ko": {
        "language": "언어",
        "intro": (
            "PDF 파일을 아래에 놓아 제한을 해제하세요. 품질 저하 없이 압축할 수도 "
            "있습니다. 원본 파일은 변경되지 않습니다."
        ),
        "warning": (
            "제한이 해제된 사본에서는 디지털 서명 검증이 제거됩니다. "
            "화면에 보이는 서명 모양은 유지됩니다."
        ),
        "processing_option": "처리 옵션",
        "compress_after_unlocking": "제한 해제 후 PDF 압축(원본 품질 유지)",
        "standard_compression": "표준 압축 — 일반적으로 5~30% 축소",
        "maximum_compression": "최대 압축 — 일반적으로 10~40% 축소",
        "no_quality_removed": (
            "품질은 저하되지 않습니다. 처리 후 정확한 절감량을 표시합니다."
        ),
        "drop_files": (
            "PDF 파일을 여기에 놓으세요\n\n"
            "또는 이 상자를 클릭하여 찾아보기"
        ),
        "choose_files": "여기를 클릭하여 PDF 파일 선택",
        "processing_files": "PDF 파일 {count}개 처리 중...",
        "browse_files": "PDF 파일 찾아보기",
        "close": "닫기",
        "about": "정보",
        "select_title": "SmashPDF로 처리할 PDF 파일 선택",
        "pdf_files": "PDF 파일",
        "all_files": "모든 파일",
        "skipped_not_pdf": "건너뜀(PDF 아님): {name}",
        "no_pdf": (
            "PDF 파일을 찾을 수 없습니다. 하나 이상의 .pdf 파일을 놓거나 "
            "선택하세요."
        ),
        "processing_file": "처리 중: {name}",
        "cancelled": "취소되었습니다.",
        "failed": "실패: {error}",
        "opening_prompt": "다음 파일의 열기 암호를 입력하세요:\n{name}",
        "completed_with_failures": (
            "완료: {successes}\n실패 또는 취소: {failures}\n\n{details}"
        ),
        "finished": "완료되었습니다. 처리된 PDF {successes}개를 만들었습니다.",
        "version": "버전 {version}",
        "thank_you": "지원해 주셔서 감사합니다",
        "made_by": "제작: dklicious",
        "encryption_removed": "암호화 제거됨",
        "signature_fields_removed": "디지털 서명 필드 {count}개 제거됨",
        "unrestricted_copy_created": "제한 없는 사본 생성됨",
        "standard_result": "표준 무손실 압축; 스트림 {count}개 최적화됨",
        "maximum_result": "최대 무손실 압축; 스트림 {count}개 최적화됨",
        "result_summary": (
            "생성됨: {output}\n페이지: {pages}; {changes}\n"
            "크기: {source_mb:.2f} MB -> {output_mb:.2f} MB "
            "({reduction:.1f}% 축소)"
        ),
    },
}
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


def resource_path(relative_path: str) -> Path:
    """Resolve a bundled resource in source and PyInstaller builds."""

    application_root = Path(
        getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)
    )
    return application_root / relative_path


def settings_path() -> Path:
    """Return the per-user settings path without using the working directory."""

    local_app_data = os.environ.get("LOCALAPPDATA")
    settings_root = (
        Path(local_app_data)
        if local_app_data
        else Path.home() / ".config"
    )
    return settings_root / APP_NAME / "settings.json"


def load_language_preference(path: str | Path | None = None) -> str:
    """Load a valid saved language, defaulting to English on first launch."""

    preference_path = Path(path) if path is not None else settings_path()
    try:
        payload = json.loads(preference_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "en"

    if not isinstance(payload, dict):
        return "en"
    language = payload.get("language")
    return language if language in LANGUAGE_NAMES else "en"


def save_language_preference(
    language: str,
    path: str | Path | None = None,
) -> None:
    """Atomically save the selected language without storing document data."""

    if language not in LANGUAGE_NAMES:
        raise ValueError(f"Unsupported language: {language}")

    preference_path = Path(path) if path is not None else settings_path()
    preference_path.parent.mkdir(parents=True, exist_ok=True)
    temp_fd, temp_name = tempfile.mkstemp(
        prefix=".settings-",
        suffix=".tmp",
        dir=str(preference_path.parent),
    )
    temp_path = Path(temp_name)

    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(
                {"language": language},
                stream,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            stream.write("\n")
        os.replace(temp_path, preference_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


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
    root.geometry("780x720")
    root.minsize(720, 640)

    app_logo = None
    try:
        app_logo = tk.PhotoImage(
            file=str(resource_path("assets/smashpdf_logo_64.png"))
        )
        root.iconphoto(True, app_logo)
    except tk.TclError as error:
        print(f"Could not load the application logo: {error}", file=sys.stderr)
        app_logo = None

    if os.name == "nt":
        try:
            root.iconbitmap(default=str(resource_path("assets/smashpdf.ico")))
        except tk.TclError as error:
            print(f"Could not load the Windows icon: {error}", file=sys.stderr)

    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")

    preferred_language = load_language_preference()
    language_code = tk.StringVar(value=preferred_language)
    language_name = tk.StringVar(
        value=LANGUAGE_NAMES[preferred_language]
    )

    def tr(key: str, **values) -> str:
        return TRANSLATIONS[language_code.get()][key].format(**values)

    outer = ttk.Frame(root, padding=20)
    outer.pack(fill="both", expand=True)

    header = ttk.Frame(outer)
    header.pack(fill="x", anchor="w")

    language_frame = ttk.Frame(header)
    language_frame.pack(side="right", anchor="ne")
    language_label = ttk.Label(language_frame, text=tr("language"))
    language_label.pack(side="left", padx=(0, 6))
    language_selector = ttk.Combobox(
        language_frame,
        textvariable=language_name,
        values=tuple(LANGUAGE_NAMES.values()),
        state="readonly",
        width=11,
    )
    language_selector.pack(side="left")

    if app_logo is not None:
        ttk.Label(header, image=app_logo).pack(side="left", padx=(0, 12))
    ttk.Label(
        header,
        text=APP_NAME,
        font=("Segoe UI", 20, "bold"),
    ).pack(side="left")

    intro_label = ttk.Label(
        outer,
        text=tr("intro"),
        wraplength=700,
    )
    intro_label.pack(anchor="w", pady=(4, 14))

    warning_label = ttk.Label(
        outer,
        text=tr("warning"),
        foreground="#9A4D00",
        wraplength=700,
    )
    warning_label.pack(anchor="w", pady=(0, 14))

    compression_enabled = tk.BooleanVar(value=False)
    compression_level = tk.StringVar(value="standard")
    options = ttk.LabelFrame(outer, text=tr("processing_option"), padding=10)
    options.pack(fill="x", pady=(0, 14))

    compression_check = ttk.Checkbutton(
        options,
        text=tr("compress_after_unlocking"),
        variable=compression_enabled,
        command=lambda: update_compression_controls(),
    )
    compression_check.pack(anchor="w", pady=(2, 5))

    standard_radio = ttk.Radiobutton(
        options,
        text=tr("standard_compression"),
        variable=compression_level,
        value="standard",
    )
    standard_radio.pack(anchor="w", padx=(22, 0), pady=2)
    major_radio = ttk.Radiobutton(
        options,
        text=tr("maximum_compression"),
        variable=compression_level,
        value="major",
    )
    major_radio.pack(anchor="w", padx=(22, 0), pady=2)

    def update_compression_controls() -> None:
        state = "normal" if compression_enabled.get() else "disabled"
        standard_radio.configure(state=state)
        major_radio.configure(state=state)

    update_compression_controls()

    quality_label = ttk.Label(
        options,
        text=tr("no_quality_removed"),
        foreground="#555555",
        wraplength=670,
    )
    quality_label.pack(anchor="w", pady=(5, 0))

    def current_drop_text() -> str:
        return tr("drop_files") if drag_and_drop_available else tr("choose_files")

    drop_zone = tk.Label(
        outer,
        text=current_drop_text(),
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

    def format_gui_result(result: UnlockResult) -> str:
        changes = []
        if result.was_encrypted:
            changes.append(tr("encryption_removed"))
        if result.removed_signature_fields:
            changes.append(
                tr(
                    "signature_fields_removed",
                    count=result.removed_signature_fields,
                )
            )
        if not changes:
            changes.append(tr("unrestricted_copy_created"))
        if result.compression_mode == "standard":
            changes.append(
                tr("standard_result", count=result.streams_optimized)
            )
        elif result.compression_mode == "major":
            changes.append(
                tr("maximum_result", count=result.streams_optimized)
            )

        return tr(
            "result_summary",
            output=result.output,
            pages=result.page_count,
            changes="; ".join(changes),
            source_mb=result.source_size / 1_048_576,
            output_mb=result.output_size / 1_048_576,
            reduction=result.reduction_percent,
        )

    def process_files(filenames) -> None:
        pdf_files = []
        for filename in filenames:
            path = Path(filename)
            if path.is_file() and path.suffix.lower() == ".pdf":
                pdf_files.append(path)
            else:
                append_log(tr("skipped_not_pdf", name=path.name or path))

        if not pdf_files:
            messagebox.showwarning(
                APP_NAME,
                tr("no_pdf"),
                parent=root,
            )
            return

        selected_mode = compression_level.get() if compression_enabled.get() else "none"
        choose_button.configure(state="disabled")
        drop_zone.configure(
            text=tr("processing_files", count=len(pdf_files)),
            cursor="watch",
            background="#FFF7E6",
        )
        successes = 0
        failures = []

        try:
            for source in pdf_files:
                append_log(tr("processing_file", name=source.name))
                try:
                    result = unlock_pdf(source, compression=selected_mode)
                except PasswordRequiredError:
                    password = simpledialog.askstring(
                        APP_NAME,
                        tr("opening_prompt", name=source.name),
                        parent=root,
                        show="*",
                    )
                    if password is None:
                        failures.append(f"{source.name}: cancelled")
                        append_log(tr("cancelled"))
                        continue
                    try:
                        result = unlock_pdf(
                            source,
                            password=password,
                            compression=selected_mode,
                        )
                    except Exception as exc:
                        failures.append(f"{source.name}: {exc}")
                        append_log(tr("failed", error=exc))
                        continue
                except Exception as exc:
                    failures.append(f"{source.name}: {exc}")
                    append_log(tr("failed", error=exc))
                    continue

                successes += 1
                append_log(format_gui_result(result))
        finally:
            choose_button.configure(state="normal")
            drop_zone.configure(
                text=current_drop_text(),
                cursor="hand2",
                background="#F2F7FC",
            )

        if failures:
            messagebox.showwarning(
                APP_NAME,
                tr(
                    "completed_with_failures",
                    successes=successes,
                    failures=len(failures),
                    details="\n".join(failures[:8]),
                ),
                parent=root,
            )
        else:
            messagebox.showinfo(
                APP_NAME,
                tr("finished", successes=successes),
                parent=root,
            )

    def select_and_unlock() -> None:
        filenames = filedialog.askopenfilenames(
            parent=root,
            title=tr("select_title"),
            filetypes=[
                (tr("pdf_files"), "*.pdf"),
                (tr("all_files"), "*.*"),
            ],
        )
        if filenames:
            process_files(filenames)

    def handle_drop(event) -> None:
        filenames = root.tk.splitlist(event.data)
        process_files(filenames)

    def show_about() -> None:
        about = tk.Toplevel(root)
        about.title(f"{tr('about')} {APP_NAME}")
        about.geometry("410x310")
        about.resizable(False, False)
        about.transient(root)
        about.grab_set()

        if app_logo is not None:
            ttk.Label(about, image=app_logo).pack(pady=(20, 2))
        ttk.Label(
            about,
            text=APP_NAME,
            font=("Segoe UI", 20, "bold"),
        ).pack(pady=((24 if app_logo is None else 2), 2))
        ttk.Label(
            about,
            text=tr("version", version=APP_VERSION),
            foreground="#555555",
        ).pack()
        ttk.Label(
            about,
            text=tr("thank_you"),
            font=("Segoe UI", 11),
        ).pack(pady=(20, 4))
        ttk.Label(
            about,
            text=tr("made_by"),
            font=("Segoe UI", 10, "bold"),
        ).pack()
        ttk.Label(
            about,
            text=PROJECT_URL,
            foreground="#1F4E79",
        ).pack(pady=(8, 14))
        ttk.Button(about, text=tr("close"), command=about.destroy).pack()

        about.update_idletasks()
        x = root.winfo_x() + (root.winfo_width() - about.winfo_width()) // 2
        y = root.winfo_y() + (root.winfo_height() - about.winfo_height()) // 2
        about.geometry(f"+{max(0, x)}+{max(0, y)}")
        about.focus_set()

    choose_button = ttk.Button(
        button_row,
        text=tr("browse_files"),
        command=select_and_unlock,
    )
    choose_button.pack(side="left")
    close_button = ttk.Button(
        button_row,
        text=tr("close"),
        command=root.destroy,
    )
    close_button.pack(side="right")
    about_button = ttk.Button(
        button_row,
        text=tr("about"),
        command=show_about,
    )
    about_button.pack(
        side="right",
        padx=(0, 8),
    )

    def update_language(_event=None) -> None:
        selected_name = language_name.get()
        selected_code = next(
            code
            for code, name in LANGUAGE_NAMES.items()
            if name == selected_name
        )
        language_code.set(selected_code)

        language_label.configure(text=tr("language"))
        intro_label.configure(text=tr("intro"))
        warning_label.configure(text=tr("warning"))
        options.configure(text=tr("processing_option"))
        compression_check.configure(text=tr("compress_after_unlocking"))
        standard_radio.configure(text=tr("standard_compression"))
        major_radio.configure(text=tr("maximum_compression"))
        quality_label.configure(text=tr("no_quality_removed"))
        drop_zone.configure(text=current_drop_text())
        choose_button.configure(text=tr("browse_files"))
        about_button.configure(text=tr("about"))
        close_button.configure(text=tr("close"))
        try:
            save_language_preference(selected_code)
        except OSError as error:
            print(
                f"Could not save the language preference: {error}",
                file=sys.stderr,
            )

    language_selector.bind("<<ComboboxSelected>>", update_language)
    drop_zone.bind("<Button-1>", lambda _event: select_and_unlock())
    if drag_and_drop_available and DND_FILES is not None:
        drop_zone.drop_target_register(DND_FILES)
        drop_zone.dnd_bind("<<Drop>>", handle_drop)

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
