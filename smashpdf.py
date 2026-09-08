#!/usr/bin/env python3
"""Search PDFs or create protected and compressed local file copies.

The source file is never modified. Password encryption is removed after the
document has been successfully opened. Digital-signature fields and document
certification controls are removed; visible signature appearances are retained
as stamp annotations. Optional compression reduces embedded image resolution
while preserving page geometry, images, and selectable text.
Lock mode applies AES-256 encryption and restrictive PDF permission flags.
Picture mode compresses common raster formats while preserving the source file.
Search mode reads selectable PDF text and reports matching pages without writes.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import secrets
import sys
import tempfile
import traceback
import warnings
import webbrowser
import zlib
from collections.abc import Iterable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from pypdf import PasswordType, PdfReader, PdfWriter
from pypdf.constants import UserAccessPermissions
from pypdf.errors import PdfReadError
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    EncodedStreamObject,
    IndirectObject,
    NameObject,
    TextStringObject,
)

from _version import __version__

APP_NAME = "SmashPDF"
APP_VERSION = __version__
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
            "Drop PDF files below to unlock them. Optionally compress them. "
            "Original files are never changed."
        ),
        "warning": (
            "Digital-signature verification will be removed from unlocked "
            "copies. Visible signature appearances are retained."
        ),
        "lock_intro": (
            "Drop PDF files below to protect them with AES-256 encryption. "
            "Original files are never changed."
        ),
        "lock_warning": (
            "Editing, copying and printing are disabled in compliant PDF readers. "
            "These permissions are not irreversible DRM once the opening password "
            "is known. Existing digital signatures may become invalid."
        ),
        "action": "Action",
        "unlock_action": "Unlock PDF",
        "lock_action": "Lock PDF",
        "processing_option": "Processing option",
        "compress_after_unlocking": "Compress PDF after unlocking",
        "standard_compression": "Standard compression - usually 5-30% smaller",
        "maximum_compression": "Maximum compression - usually 10-40% smaller",
        "massive_compression": "Massive compression - targets 60%+ smaller",
        "no_quality_removed": (
            "No quality is removed. The exact saving is shown after processing."
        ),
        "massive_quality_warning": (
            "Massive mode reduces embedded-image resolution and quality. Text and "
            "page structure stay intact. 60%+ is a target, not a guarantee."
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
        "no_pdf": ("No PDF files were found. Drop or select one or more .pdf files."),
        "processing_file": "Processing: {name}",
        "cancelled": "Cancelled.",
        "failed": "Failed: {error}",
        "opening_prompt": "Enter the opening password for:\n{name}",
        "new_credential_prompt": (
            "Create an opening password (at least 8 characters) for the locked PDF(s):"
        ),
        "confirm_credential_prompt": "Enter the new password again to confirm:",
        "credential_mismatch": "The passwords do not match.",
        "credential_too_short": "The password must contain at least 8 characters.",
        "completed_with_failures": (
            "Completed: {successes}\nFailed or cancelled: {failures}\n\n{details}"
        ),
        "finished": "Finished. Created {successes} processed PDF(s).",
        "version": "Version {version}",
        "thank_you": "Thank you for your support",
        "made_by": "Made by dklicious.",
        "size_smaller": "{percent:.1f}% smaller",
        "size_larger": "{percent:.1f}% larger",
        "size_unchanged": "same size",
        "encryption_removed": "encryption removed",
        "signature_fields_removed": ("{count} digital-signature field(s) removed"),
        "unrestricted_copy_created": "an unrestricted copy was created",
        "locked_copy_created": (
            "AES-256 encrypted; editing, copying and printing disabled"
        ),
        "standard_result": (
            "standard lossless compression; {count} stream(s) optimized"
        ),
        "maximum_result": ("maximum lossless compression; {count} stream(s) optimized"),
        "massive_result": ("massive image compression; {count} image(s) recompressed"),
        "result_summary": (
            "Created: {output}\nPages: {pages}; {changes}\n"
            "Size: {source_mb:.2f} MB -> {output_mb:.2f} MB ({size_change})"
        ),
        "lock_result_summary": (
            "Created: {output}\nPages: {pages}; {changes}\n"
            "Size: {source_mb:.2f} MB -> {output_mb:.2f} MB"
        ),
    },
    "zh": {
        "language": "语言",
        "intro": ("将 PDF 文件拖放到下方以解除限制。可选择压缩。原始文件不会被更改。"),
        "warning": ("解锁后的副本将移除数字签名验证。可见的签名外观会保留。"),
        "lock_intro": (
            "将 PDF 文件拖放到下方，使用 AES-256 加密保护。原始文件不会被更改。"
        ),
        "lock_warning": (
            "兼容的 PDF 阅读器将禁止编辑、复制和打印。知道打开密码后，"
            "这些权限并非不可逆的"
            "数字版权保护。现有数字签名可能失效。"
        ),
        "action": "操作",
        "unlock_action": "解锁 PDF",
        "lock_action": "加密锁定 PDF",
        "processing_option": "处理选项",
        "compress_after_unlocking": "解锁后压缩 PDF",
        "standard_compression": "标准压缩 — 通常缩小 5–30%",
        "maximum_compression": "最大压缩 — 通常缩小 10–40%",
        "massive_compression": "超强压缩 — 目标缩小 60% 以上",
        "no_quality_removed": "不会降低质量。处理后会显示实际节省的空间。",
        "massive_quality_warning": (
            "超强模式会降低嵌入图像的分辨率和质量。文本和页面结构保持不变。"
            "缩小 60% 以上是目标，并非保证。"
        ),
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
        "new_credential_prompt": "为锁定的 PDF 创建打开密码（至少 8 个字符）：",
        "confirm_credential_prompt": "再次输入新密码以确认：",
        "credential_mismatch": "两次输入的密码不一致。",
        "credential_too_short": "密码必须至少包含 8 个字符。",
        "completed_with_failures": (
            "已完成：{successes}\n失败或取消：{failures}\n\n{details}"
        ),
        "finished": "处理完成。已创建 {successes} 个 PDF 文件。",
        "version": "版本 {version}",
        "thank_you": "感谢您的支持",
        "made_by": "由 dklicious 制作。",
        "size_smaller": "缩小 {percent:.1f}%",
        "size_larger": "增大 {percent:.1f}%",
        "size_unchanged": "大小不变",
        "encryption_removed": "已移除加密",
        "signature_fields_removed": "已移除 {count} 个数字签名字段",
        "unrestricted_copy_created": "已创建无限制副本",
        "locked_copy_created": "已使用 AES-256 加密；禁止编辑、复制和打印",
        "standard_result": "标准无损压缩；已优化 {count} 个数据流",
        "maximum_result": "最大无损压缩；已优化 {count} 个数据流",
        "massive_result": "超强图像压缩；已重新压缩 {count} 张图像",
        "result_summary": (
            "已创建：{output}\n页数：{pages}；{changes}\n"
            "大小：{source_mb:.2f} MB -> {output_mb:.2f} MB（{size_change}）"
        ),
        "lock_result_summary": (
            "已创建：{output}\n页数：{pages}；{changes}\n"
            "大小：{source_mb:.2f} MB -> {output_mb:.2f} MB"
        ),
    },
    "zh_hant": {
        "language": "語言",
        "intro": ("將 PDF 檔案拖放到下方以解除限制。可選擇壓縮。原始檔案不會被變更。"),
        "warning": ("解鎖後的副本將移除數位簽章驗證。可見的簽章外觀會保留。"),
        "lock_intro": (
            "將 PDF 檔案拖放到下方，使用 AES-256 加密保護。原始檔案不會被變更。"
        ),
        "lock_warning": (
            "相容的 PDF 閱讀器將禁止編輯、複製和列印。知道開啟密碼後，"
            "這些權限並非不可逆的"
            "數位版權保護。現有數位簽章可能失效。"
        ),
        "action": "操作",
        "unlock_action": "解鎖 PDF",
        "lock_action": "加密鎖定 PDF",
        "processing_option": "處理選項",
        "compress_after_unlocking": "解鎖後壓縮 PDF",
        "standard_compression": "標準壓縮 — 通常縮小 5–30%",
        "maximum_compression": "最大壓縮 — 通常縮小 10–40%",
        "massive_compression": "超強壓縮 — 目標縮小 60% 以上",
        "no_quality_removed": "不會降低品質。處理後會顯示實際節省的空間。",
        "massive_quality_warning": (
            "超強模式會降低嵌入影像的解析度和品質。文字和頁面結構保持不變。"
            "縮小 60% 以上是目標，並非保證。"
        ),
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
        "new_credential_prompt": "為鎖定的 PDF 建立開啟密碼（至少 8 個字元）：",
        "confirm_credential_prompt": "再次輸入新密碼以確認：",
        "credential_mismatch": "兩次輸入的密碼不相符。",
        "credential_too_short": "密碼必須至少包含 8 個字元。",
        "completed_with_failures": (
            "已完成：{successes}\n失敗或取消：{failures}\n\n{details}"
        ),
        "finished": "處理完成。已建立 {successes} 個 PDF 檔案。",
        "version": "版本 {version}",
        "thank_you": "感謝您的支持",
        "made_by": "由 dklicious 製作。",
        "size_smaller": "縮小 {percent:.1f}%",
        "size_larger": "增大 {percent:.1f}%",
        "size_unchanged": "大小不變",
        "encryption_removed": "已移除加密",
        "signature_fields_removed": "已移除 {count} 個數位簽章欄位",
        "unrestricted_copy_created": "已建立無限制副本",
        "locked_copy_created": "已使用 AES-256 加密；禁止編輯、複製和列印",
        "standard_result": "標準無損壓縮；已最佳化 {count} 個資料流",
        "maximum_result": "最大無損壓縮；已最佳化 {count} 個資料流",
        "massive_result": "超強影像壓縮；已重新壓縮 {count} 張影像",
        "result_summary": (
            "已建立：{output}\n頁數：{pages}；{changes}\n"
            "大小：{source_mb:.2f} MB -> {output_mb:.2f} MB（{size_change}）"
        ),
        "lock_result_summary": (
            "已建立：{output}\n頁數：{pages}；{changes}\n"
            "大小：{source_mb:.2f} MB -> {output_mb:.2f} MB"
        ),
    },
    "es": {
        "language": "Idioma",
        "intro": (
            "Arrastra archivos PDF abajo para desbloquearlos. También puedes "
            "comprimirlos. Los originales no se modifican."
        ),
        "warning": (
            "La verificación de firmas digitales se eliminará de las copias "
            "desbloqueadas. La apariencia visible de las firmas se conserva."
        ),
        "lock_intro": (
            "Arrastra archivos PDF abajo para protegerlos con cifrado AES-256. "
            "Los originales no se modifican."
        ),
        "lock_warning": (
            "Los lectores PDF compatibles impedirán editar, copiar e imprimir. "
            "Estos permisos no son DRM irreversible si se conoce la contraseña. "
            "Las firmas digitales existentes pueden dejar de ser válidas."
        ),
        "action": "Acción",
        "unlock_action": "Desbloquear PDF",
        "lock_action": "Bloquear PDF",
        "processing_option": "Opción de procesamiento",
        "compress_after_unlocking": "Comprimir el PDF después de desbloquearlo",
        "standard_compression": ("Compresión estándar - normalmente 5-30% más pequeño"),
        "maximum_compression": ("Compresión máxima - normalmente 10-40% más pequeño"),
        "massive_compression": ("Compresión masiva - objetivo: más de 60% más pequeño"),
        "no_quality_removed": (
            "No se reduce la calidad. El ahorro exacto se muestra al terminar."
        ),
        "massive_quality_warning": (
            "El modo masivo reduce la resolución y la calidad de las imágenes "
            "incrustadas. El texto y la estructura de las páginas se conservan. "
            "Más del 60% es un objetivo, no una garantía."
        ),
        "drop_files": (
            "ARRASTRA LOS ARCHIVOS PDF AQUÍ\n\no haz clic en este cuadro para buscarlos"
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
        "new_credential_prompt": (
            "Crea una contraseña de apertura (mínimo 8 caracteres) para los PDF:"
        ),
        "confirm_credential_prompt": "Introduce otra vez la nueva contraseña:",
        "credential_mismatch": "Las contraseñas no coinciden.",
        "credential_too_short": "La contraseña debe tener al menos 8 caracteres.",
        "completed_with_failures": (
            "Completados: {successes}\nFallidos o cancelados: {failures}\n\n{details}"
        ),
        "finished": "Terminado. Se crearon {successes} PDF procesado(s).",
        "version": "Versión {version}",
        "thank_you": "Gracias por tu apoyo",
        "made_by": "Creado por dklicious.",
        "size_smaller": "{percent:.1f}% más pequeño",
        "size_larger": "{percent:.1f}% más grande",
        "size_unchanged": "mismo tamaño",
        "encryption_removed": "cifrado eliminado",
        "signature_fields_removed": ("{count} campo(s) de firma digital eliminado(s)"),
        "unrestricted_copy_created": "se creó una copia sin restricciones",
        "locked_copy_created": (
            "cifrado AES-256; edición, copia e impresión desactivadas"
        ),
        "standard_result": (
            "compresión estándar sin pérdida; {count} flujo(s) optimizado(s)"
        ),
        "maximum_result": (
            "compresión máxima sin pérdida; {count} flujo(s) optimizado(s)"
        ),
        "massive_result": (
            "compresión masiva de imágenes; {count} imagen(es) recomprimida(s)"
        ),
        "result_summary": (
            "Creado: {output}\nPáginas: {pages}; {changes}\n"
            "Tamaño: {source_mb:.2f} MB -> {output_mb:.2f} MB ({size_change})"
        ),
        "lock_result_summary": (
            "Creado: {output}\nPáginas: {pages}; {changes}\n"
            "Tamaño: {source_mb:.2f} MB -> {output_mb:.2f} MB"
        ),
    },
    "ja": {
        "language": "言語",
        "intro": (
            "PDF ファイルを下にドロップして制限を解除します。圧縮することもできます。"
            "元のファイルは変更されません。"
        ),
        "warning": (
            "解除後のコピーではデジタル署名の検証が削除されます。"
            "表示されている署名の外観は保持されます。"
        ),
        "lock_intro": (
            "PDF ファイルを下にドロップして AES-256 暗号化で保護します。"
            "元のファイルは変更されません。"
        ),
        "lock_warning": (
            "対応する PDF リーダーでは編集、コピー、印刷が禁止されます。"
            "開くパスワードを知っている場合、この権限設定は不可逆の DRM "
            "ではありません。"
            "既存のデジタル署名は"
            "無効になることがあります。"
        ),
        "action": "操作",
        "unlock_action": "PDF の制限を解除",
        "lock_action": "PDF をロック",
        "processing_option": "処理オプション",
        "compress_after_unlocking": "解除後に PDF を圧縮",
        "standard_compression": "標準圧縮 — 通常 5～30% 小さくなります",
        "maximum_compression": "最大圧縮 — 通常 10～40% 小さくなります",
        "massive_compression": "超強力圧縮 — 60%以上の縮小を目標",
        "no_quality_removed": "品質は低下しません。処理後に正確な削減量を表示します。",
        "massive_quality_warning": (
            "超強力モードでは埋め込み画像の解像度と品質が低下します。"
            "テキストとページ構造は保持されます。60%以上は目標であり、保証ではありません。"
        ),
        "drop_files": (
            "ここに PDF ファイルをドロップ\n\nまたは、このボックスをクリックして参照"
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
        "new_credential_prompt": "ロックする PDF のパスワードを作成（8文字以上）：",
        "confirm_credential_prompt": "確認のため新しいパスワードを再入力：",
        "credential_mismatch": "パスワードが一致しません。",
        "credential_too_short": "パスワードは8文字以上にしてください。",
        "completed_with_failures": (
            "完了：{successes}\n失敗またはキャンセル：{failures}\n\n{details}"
        ),
        "finished": "完了しました。{successes} 個の PDF を作成しました。",
        "version": "バージョン {version}",
        "thank_you": "ご支援ありがとうございます",
        "made_by": "制作：dklicious",
        "size_smaller": "{percent:.1f}% 縮小",
        "size_larger": "{percent:.1f}% 増加",
        "size_unchanged": "同じサイズ",
        "encryption_removed": "暗号化を解除",
        "signature_fields_removed": "デジタル署名フィールドを {count} 個削除",
        "unrestricted_copy_created": "制限のないコピーを作成",
        "locked_copy_created": "AES-256 暗号化済み；編集、コピー、印刷を禁止",
        "standard_result": "標準ロスレス圧縮；{count} ストリームを最適化",
        "maximum_result": "最大ロスレス圧縮；{count} ストリームを最適化",
        "massive_result": "超強力画像圧縮；{count} 個の画像を再圧縮",
        "result_summary": (
            "作成先：{output}\nページ数：{pages}；{changes}\n"
            "サイズ：{source_mb:.2f} MB -> {output_mb:.2f} MB（{size_change}）"
        ),
        "lock_result_summary": (
            "作成先：{output}\nページ数：{pages}；{changes}\n"
            "サイズ：{source_mb:.2f} MB -> {output_mb:.2f} MB"
        ),
    },
    "ko": {
        "language": "언어",
        "intro": (
            "PDF 파일을 아래에 놓아 제한을 해제하세요. 압축할 수도 있습니다. "
            "원본 파일은 변경되지 않습니다."
        ),
        "warning": (
            "제한이 해제된 사본에서는 디지털 서명 검증이 제거됩니다. "
            "화면에 보이는 서명 모양은 유지됩니다."
        ),
        "lock_intro": (
            "PDF 파일을 아래에 놓아 AES-256 암호화로 보호하세요. "
            "원본 파일은 변경되지 않습니다."
        ),
        "lock_warning": (
            "호환 PDF 리더에서는 편집, 복사 및 인쇄가 금지됩니다. "
            "열기 암호를 알고 있다면 이 권한은 "
            "되돌릴 수 없는 DRM이 아닙니다. 기존 디지털 서명이 무효화될 수 있습니다."
        ),
        "action": "작업",
        "unlock_action": "PDF 제한 해제",
        "lock_action": "PDF 잠금",
        "processing_option": "처리 옵션",
        "compress_after_unlocking": "제한 해제 후 PDF 압축",
        "standard_compression": "표준 압축 — 일반적으로 5~30% 축소",
        "maximum_compression": "최대 압축 — 일반적으로 10~40% 축소",
        "massive_compression": "초강력 압축 — 60% 이상 축소 목표",
        "no_quality_removed": (
            "품질은 저하되지 않습니다. 처리 후 정확한 절감량을 표시합니다."
        ),
        "massive_quality_warning": (
            "초강력 모드는 포함된 이미지의 해상도와 품질을 낮춥니다. 텍스트와 "
            "페이지 구조는 유지됩니다. 60% 이상은 목표이며 보장되지 않습니다."
        ),
        "drop_files": (
            "PDF 파일을 여기에 놓으세요\n\n또는 이 상자를 클릭하여 찾아보기"
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
            "PDF 파일을 찾을 수 없습니다. 하나 이상의 .pdf 파일을 놓거나 선택하세요."
        ),
        "processing_file": "처리 중: {name}",
        "cancelled": "취소되었습니다.",
        "failed": "실패: {error}",
        "opening_prompt": "다음 파일의 열기 암호를 입력하세요:\n{name}",
        "new_credential_prompt": "잠글 PDF의 열기 암호를 만드세요(8자 이상):",
        "confirm_credential_prompt": "새 암호를 다시 입력하여 확인하세요:",
        "credential_mismatch": "암호가 일치하지 않습니다.",
        "credential_too_short": "암호는 8자 이상이어야 합니다.",
        "completed_with_failures": (
            "완료: {successes}\n실패 또는 취소: {failures}\n\n{details}"
        ),
        "finished": "완료되었습니다. 처리된 PDF {successes}개를 만들었습니다.",
        "version": "버전 {version}",
        "thank_you": "지원해 주셔서 감사합니다",
        "made_by": "제작: dklicious",
        "size_smaller": "{percent:.1f}% 감소",
        "size_larger": "{percent:.1f}% 증가",
        "size_unchanged": "동일한 크기",
        "encryption_removed": "암호화 제거됨",
        "signature_fields_removed": "디지털 서명 필드 {count}개 제거됨",
        "unrestricted_copy_created": "제한 없는 사본 생성됨",
        "locked_copy_created": "AES-256 암호화됨; 편집, 복사 및 인쇄 금지",
        "standard_result": "표준 무손실 압축; 스트림 {count}개 최적화됨",
        "maximum_result": "최대 무손실 압축; 스트림 {count}개 최적화됨",
        "massive_result": "초강력 이미지 압축; 이미지 {count}개 재압축됨",
        "result_summary": (
            "생성됨: {output}\n페이지: {pages}; {changes}\n"
            "크기: {source_mb:.2f} MB -> {output_mb:.2f} MB ({size_change})"
        ),
        "lock_result_summary": (
            "생성됨: {output}\n페이지: {pages}; {changes}\n"
            "크기: {source_mb:.2f} MB -> {output_mb:.2f} MB"
        ),
    },
}
IMAGE_TRANSLATIONS = {
    "en": {
        "image_action": "Compress Images",
        "image_intro": (
            "Drop pictures below to make smaller copies. Originals are never changed, "
            "and results are saved in the same folder."
        ),
        "image_warning": (
            "Supports JPEG, PNG, WebP, GIF, BMP and TIFF. Stronger settings may "
            "reduce dimensions or image quality. Animation frames are preserved."
        ),
        "image_standard_compression": "Standard - keeps original dimensions",
        "image_maximum_compression": "Strong - may resize very large pictures",
        "image_massive_compression": "Maximum - smallest picture files",
        "image_standard_quality": (
            "Keeps original dimensions and uses efficient encoding with mild "
            "quality loss."
        ),
        "image_major_quality": (
            "Limits very large pictures to 2560 px and uses stronger compression."
        ),
        "image_massive_quality": (
            "Limits pictures to 1600 px and uses the strongest quality reduction."
        ),
        "image_drop_files": ("DROP PICTURE FILES HERE\n\nor click this box to browse"),
        "image_choose_files": "CLICK HERE TO CHOOSE PICTURE FILES",
        "processing_images": "PROCESSING {count} PICTURE FILE(S)...",
        "image_browse_files": "Browse Picture Files",
        "image_select_title": "Select pictures for SmashPDF",
        "image_files": "Picture files",
        "skipped_not_image": "Skipped (unsupported picture): {name}",
        "no_image": "No supported picture files were found.",
        "finished_images": "Finished. Created {successes} compressed picture(s).",
        "image_result_summary": (
            "Created: {output}\nFrames: {frames}; {profile}\n"
            "Size: {source_mb:.2f} MB -> {output_mb:.2f} MB ({size_change})"
        ),
    },
    "zh": {
        "image_action": "压缩图片",
        "image_intro": "".join(
            (
                "将图片拖放到下方以创建更小的副本。原图不会被更改，",
                "结果保存在同一文件夹。",
            )
        ),
        "image_warning": (
            "支持 JPEG、PNG、WebP、GIF、BMP 和 TIFF。较强的设置可能降低尺寸或画质。"
            "动画帧会被保留。"
        ),
        "image_standard_compression": "标准 - 保持原始尺寸",
        "image_maximum_compression": "强力 - 可能缩小超大图片",
        "image_massive_compression": "最大 - 图片文件尽可能小",
        "image_standard_quality": "保持原始尺寸并使用高效编码，画质仅轻微降低。",
        "image_major_quality": "将超大图片限制为 2560 像素，并使用更强压缩。",
        "image_massive_quality": (
            "将图片限制为 1600 像素，并最大程度降低画质以减小文件。"
        ),
        "image_drop_files": "将图片文件拖放到这里\n\n或单击此框浏览文件",
        "image_choose_files": "单击此处选择图片文件",
        "processing_images": "正在处理 {count} 个图片文件...",
        "image_browse_files": "浏览图片文件",
        "image_select_title": "选择要用 SmashPDF 压缩的图片",
        "image_files": "图片文件",
        "skipped_not_image": "已跳过（不支持的图片）：{name}",
        "no_image": "未找到支持的图片文件。",
        "finished_images": "处理完成。已创建 {successes} 个压缩图片。",
        "image_result_summary": (
            "已创建：{output}\n帧数：{frames}；{profile}\n"
            "大小：{source_mb:.2f} MB -> {output_mb:.2f} MB（{size_change}）"
        ),
    },
    "zh_hant": {
        "image_action": "壓縮圖片",
        "image_intro": "".join(
            (
                "將圖片拖放到下方以建立較小的副本。原圖不會被變更，",
                "結果儲存在同一資料夾。",
            )
        ),
        "image_warning": (
            "支援 JPEG、PNG、WebP、GIF、BMP 和 TIFF。較強的設定可能降低尺寸或畫質。"
            "動畫影格會被保留。"
        ),
        "image_standard_compression": "標準 - 保持原始尺寸",
        "image_maximum_compression": "強力 - 可能縮小超大圖片",
        "image_massive_compression": "最大 - 圖片檔案盡可能小",
        "image_standard_quality": "保持原始尺寸並使用高效編碼，畫質僅輕微降低。",
        "image_major_quality": "將超大圖片限制為 2560 像素，並使用更強壓縮。",
        "image_massive_quality": (
            "將圖片限制為 1600 像素，並最大程度降低畫質以縮小檔案。"
        ),
        "image_drop_files": "將圖片檔案拖放到這裡\n\n或按一下此方塊瀏覽檔案",
        "image_choose_files": "按一下此處選擇圖片檔案",
        "processing_images": "正在處理 {count} 個圖片檔案...",
        "image_browse_files": "瀏覽圖片檔案",
        "image_select_title": "選擇要用 SmashPDF 壓縮的圖片",
        "image_files": "圖片檔案",
        "skipped_not_image": "已略過（不支援的圖片）：{name}",
        "no_image": "找不到支援的圖片檔案。",
        "finished_images": "處理完成。已建立 {successes} 個壓縮圖片。",
        "image_result_summary": (
            "已建立：{output}\n影格數：{frames}；{profile}\n"
            "大小：{source_mb:.2f} MB -> {output_mb:.2f} MB（{size_change}）"
        ),
    },
    "es": {
        "image_action": "Comprimir imágenes",
        "image_intro": (
            "Arrastra imágenes abajo para crear copias más pequeñas. Los originales "
            "no se modifican y los resultados se guardan en la misma carpeta."
        ),
        "image_warning": (
            "Admite JPEG, PNG, WebP, GIF, BMP y TIFF. Los ajustes más fuertes pueden "
            "reducir las dimensiones o la calidad. Se conservan los fotogramas."
        ),
        "image_standard_compression": "Estándar - conserva las dimensiones",
        "image_maximum_compression": "Fuerte - puede reducir imágenes muy grandes",
        "image_massive_compression": "Máxima - archivos de imagen más pequeños",
        "image_standard_quality": (
            "Conserva las dimensiones y usa codificación eficiente con pérdida leve."
        ),
        "image_major_quality": (
            "Limita las imágenes muy grandes a 2560 px y aplica más compresión."
        ),
        "image_massive_quality": (
            "Limita las imágenes a 1600 px y aplica la mayor reducción de calidad."
        ),
        "image_drop_files": "ARRASTRA LAS IMÁGENES AQUÍ\n\no haz clic para buscarlas",
        "image_choose_files": "HAZ CLIC AQUÍ PARA ELEGIR IMÁGENES",
        "processing_images": "PROCESANDO {count} IMAGEN(ES)...",
        "image_browse_files": "Buscar imágenes",
        "image_select_title": "Seleccionar imágenes para SmashPDF",
        "image_files": "Archivos de imagen",
        "skipped_not_image": "Omitido (imagen no compatible): {name}",
        "no_image": "No se encontraron archivos de imagen compatibles.",
        "finished_images": (
            "Terminado. Se crearon {successes} imagen(es) comprimida(s)."
        ),
        "image_result_summary": (
            "Creado: {output}\nFotogramas: {frames}; {profile}\n"
            "Tamaño: {source_mb:.2f} MB -> {output_mb:.2f} MB ({size_change})"
        ),
    },
    "ja": {
        "image_action": "画像を圧縮",
        "image_intro": (
            "画像を下にドロップして小さいコピーを作成します。元の画像は変更されず、"
            "結果は同じフォルダーに保存されます。"
        ),
        "image_warning": (
            "JPEG、PNG、WebP、GIF、BMP、TIFF に対応します。強い設定ではサイズや画質が"
            "低下する場合があります。アニメーションのフレームは保持されます。"
        ),
        "image_standard_compression": "標準 - 元の寸法を維持",
        "image_maximum_compression": "強力 - 非常に大きい画像を縮小",
        "image_massive_compression": "最大 - 画像ファイルを最小化",
        "image_standard_quality": "元の寸法を保ち、軽い画質低下で効率よく圧縮します。",
        "image_major_quality": "非常に大きい画像を 2560 px に制限し、強く圧縮します。",
        "image_massive_quality": "画像を 1600 px に制限し、最も強く画質を下げます。",
        "image_drop_files": "ここに画像ファイルをドロップ\n\nまたはクリックして参照",
        "image_choose_files": "ここをクリックして画像ファイルを選択",
        "processing_images": "{count} 個の画像ファイルを処理中...",
        "image_browse_files": "画像ファイルを参照",
        "image_select_title": "SmashPDF で圧縮する画像を選択",
        "image_files": "画像ファイル",
        "skipped_not_image": "スキップ（未対応の画像）：{name}",
        "no_image": "対応する画像ファイルが見つかりません。",
        "finished_images": "完了しました。{successes} 個の圧縮画像を作成しました。",
        "image_result_summary": (
            "作成先：{output}\nフレーム数：{frames}；{profile}\n"
            "サイズ：{source_mb:.2f} MB -> {output_mb:.2f} MB（{size_change}）"
        ),
    },
    "ko": {
        "image_action": "이미지 압축",
        "image_intro": (
            "이미지를 아래에 놓아 더 작은 사본을 만드세요. "
            "원본은 변경되지 않으며 결과는 "
            "같은 폴더에 저장됩니다."
        ),
        "image_warning": (
            "JPEG, PNG, WebP, GIF, BMP 및 TIFF를 지원합니다. 강한 설정은 크기나 화질을 "
            "낮출 수 있습니다. 애니메이션 프레임은 유지됩니다."
        ),
        "image_standard_compression": "표준 - 원본 크기 유지",
        "image_maximum_compression": "강력 - 매우 큰 이미지 축소 가능",
        "image_massive_compression": "최대 - 가장 작은 이미지 파일",
        "image_standard_quality": (
            "원본 크기를 유지하고 약간의 화질 저하로 효율적으로 압축합니다."
        ),
        "image_major_quality": (
            "매우 큰 이미지를 2560 px로 제한하고 더 강하게 압축합니다."
        ),
        "image_massive_quality": (
            "이미지를 1600 px로 제한하고 화질을 가장 많이 낮춥니다."
        ),
        "image_drop_files": "이미지 파일을 여기에 놓으세요\n\n또는 클릭하여 찾아보기",
        "image_choose_files": "여기를 클릭하여 이미지 파일 선택",
        "processing_images": "이미지 파일 {count}개 처리 중...",
        "image_browse_files": "이미지 파일 찾아보기",
        "image_select_title": "SmashPDF로 압축할 이미지 선택",
        "image_files": "이미지 파일",
        "skipped_not_image": "건너뜀(지원하지 않는 이미지): {name}",
        "no_image": "지원되는 이미지 파일을 찾을 수 없습니다.",
        "finished_images": "완료되었습니다. 압축 이미지 {successes}개를 만들었습니다.",
        "image_result_summary": (
            "생성됨: {output}\n프레임: {frames}; {profile}\n"
            "크기: {source_mb:.2f} MB -> {output_mb:.2f} MB ({size_change})"
        ),
    },
}
for _language, _image_translations in IMAGE_TRANSLATIONS.items():
    TRANSLATIONS[_language].update(_image_translations)

SEARCH_TRANSLATIONS = {
    "en": {
        "search_action": "Search PDFs",
        "search_intro": (
            "Search many PDFs at once without opening them. Drop PDF files or a "
            "folder below to see every matching page and nearby text."
        ),
        "search_warning": (
            "Search reads selectable text only. Scanned or photographed pages need "
            "OCR before their words can be found. No files are changed."
        ),
        "search_for": "Text to find",
        "case_sensitive": "Match uppercase and lowercase exactly",
        "search_drop_files": (
            "DROP PDF FILES OR A FOLDER HERE\n\nor click this box to browse files"
        ),
        "search_choose_files": "CLICK HERE TO CHOOSE PDF FILES",
        "search_browse_files": "Choose PDF Files",
        "search_browse_folder": "Choose Folder",
        "search_folder_title": "Choose a folder to search recursively",
        "search_query_required": "Enter the text you want to find first.",
        "searching_files": "SEARCHING {count} PDF FILE(S)...",
        "searching_file": "Searching: {name}",
        "search_match": "{name} — page {page}\n{snippet}",
        "search_file_summary": "{name}: {matches} match(es) on {pages} page(s).",
        "search_no_match": "{name}: no matches.",
        "search_no_text": (
            "{name}: no selectable text found; it may be a scanned PDF."
        ),
        "search_truncated": (
            "{name}: showing the first {limit} matches to keep results responsive."
        ),
        "search_finished": (
            "Search finished. Found {matches} match(es) in {files} PDF file(s)."
        ),
    },
    "zh": {
        "search_action": "搜索 PDF",
        "search_intro": (
            "无需逐个打开即可搜索多个 PDF。将 PDF 文件或文件夹拖到下方，"
            "查看匹配页码和附近文字。"
        ),
        "search_warning": "".join(
            (
                "只能搜索可选择的文字。扫描或拍照页面需要先进行 OCR。",
                "不会更改任何文件。",
            )
        ),
        "search_for": "要查找的文字",
        "case_sensitive": "严格区分大小写",
        "search_drop_files": "将 PDF 文件或文件夹拖放到这里\n\n或单击此框浏览文件",
        "search_choose_files": "单击此处选择 PDF 文件",
        "search_browse_files": "选择 PDF 文件",
        "search_browse_folder": "选择文件夹",
        "search_folder_title": "选择要递归搜索的文件夹",
        "search_query_required": "请先输入要查找的文字。",
        "searching_files": "正在搜索 {count} 个 PDF 文件...",
        "searching_file": "正在搜索：{name}",
        "search_match": "{name} — 第 {page} 页\n{snippet}",
        "search_file_summary": "{name}：在 {pages} 页中找到 {matches} 个匹配项。",
        "search_no_match": "{name}：未找到匹配项。",
        "search_no_text": "{name}：未找到可选择的文字；这可能是扫描版 PDF。",
        "search_truncated": "{name}：为保持响应速度，仅显示前 {limit} 个匹配项。",
        "search_finished": (
            "搜索完成。在 {files} 个 PDF 文件中找到 {matches} 个匹配项。"
        ),
    },
    "zh_hant": {
        "search_action": "搜尋 PDF",
        "search_intro": (
            "無需逐一開啟即可搜尋多個 PDF。將 PDF 檔案或資料夾拖到下方，"
            "查看相符頁碼和附近文字。"
        ),
        "search_warning": "".join(
            (
                "只能搜尋可選取的文字。掃描或拍照頁面需要先進行 OCR。",
                "不會變更任何檔案。",
            )
        ),
        "search_for": "要尋找的文字",
        "case_sensitive": "嚴格區分大小寫",
        "search_drop_files": "將 PDF 檔案或資料夾拖放到這裡\n\n或按一下此方塊瀏覽檔案",
        "search_choose_files": "按一下此處選擇 PDF 檔案",
        "search_browse_files": "選擇 PDF 檔案",
        "search_browse_folder": "選擇資料夾",
        "search_folder_title": "選擇要遞迴搜尋的資料夾",
        "search_query_required": "請先輸入要尋找的文字。",
        "searching_files": "正在搜尋 {count} 個 PDF 檔案...",
        "searching_file": "正在搜尋：{name}",
        "search_match": "{name} — 第 {page} 頁\n{snippet}",
        "search_file_summary": "{name}：在 {pages} 頁中找到 {matches} 個相符項目。",
        "search_no_match": "{name}：找不到相符項目。",
        "search_no_text": "{name}：找不到可選取的文字；這可能是掃描版 PDF。",
        "search_truncated": "{name}：為保持回應速度，僅顯示前 {limit} 個相符項目。",
        "search_finished": (
            "搜尋完成。在 {files} 個 PDF 檔案中找到 {matches} 個相符項目。"
        ),
    },
    "es": {
        "search_action": "Buscar en PDF",
        "search_intro": (
            "Busca en muchos PDF sin abrirlos uno por uno. Arrastra archivos o "
            "una carpeta para ver la página y el texto cercano."
        ),
        "search_warning": (
            "Solo se busca texto seleccionable. Las páginas escaneadas necesitan "
            "OCR. No se modifica ningún archivo."
        ),
        "search_for": "Texto que buscar",
        "case_sensitive": "Distinguir exactamente mayúsculas y minúsculas",
        "search_drop_files": "\n\n".join(
            ("ARRASTRA PDF O UNA CARPETA AQUÍ", "o haz clic para elegir archivos")
        ),
        "search_choose_files": "HAZ CLIC AQUÍ PARA ELEGIR PDF",
        "search_browse_files": "Elegir archivos PDF",
        "search_browse_folder": "Elegir carpeta",
        "search_folder_title": "Elige una carpeta para buscar recursivamente",
        "search_query_required": "Escribe primero el texto que quieres buscar.",
        "searching_files": "BUSCANDO EN {count} ARCHIVO(S) PDF...",
        "searching_file": "Buscando: {name}",
        "search_match": "{name} — página {page}\n{snippet}",
        "search_file_summary": (
            "{name}: {matches} coincidencia(s) en {pages} página(s)."
        ),
        "search_no_match": "{name}: sin coincidencias.",
        "search_no_text": (
            "{name}: no hay texto seleccionable; puede ser un PDF escaneado."
        ),
        "search_truncated": "{name}: se muestran las primeras {limit} coincidencias.",
        "search_finished": (
            "Búsqueda terminada. {matches} coincidencia(s) en {files} PDF."
        ),
    },
    "ja": {
        "search_action": "PDF を検索",
        "search_intro": (
            "PDF を個別に開かず、まとめて検索できます。PDF またはフォルダーを"
            "下にドロップすると、該当ページと周辺の文章を表示します。"
        ),
        "search_warning": (
            "選択可能なテキストのみ検索します。スキャン画像には事前に OCR が"
            "必要です。ファイルは変更しません。"
        ),
        "search_for": "検索するテキスト",
        "case_sensitive": "大文字と小文字を区別",
        "search_drop_files": "\n\n".join(
            (
                "PDF またはフォルダーをここにドロップ",
                "またはクリックしてファイルを選択",
            )
        ),
        "search_choose_files": "ここをクリックして PDF を選択",
        "search_browse_files": "PDF ファイルを選択",
        "search_browse_folder": "フォルダーを選択",
        "search_folder_title": "再帰検索するフォルダーを選択",
        "search_query_required": "最初に検索するテキストを入力してください。",
        "searching_files": "{count} 個の PDF を検索中...",
        "searching_file": "検索中：{name}",
        "search_match": "{name} — {page} ページ\n{snippet}",
        "search_file_summary": "{name}：{pages} ページに {matches} 件の一致。",
        "search_no_match": "{name}：一致なし。",
        "search_no_text": "{name}：選択可能なテキストなし（スキャン PDF の可能性）。",
        "search_truncated": "{name}：最初の {limit} 件のみ表示しています。",
        "search_finished": "検索完了。{files} 個の PDF で {matches} 件見つかりました。",
    },
    "ko": {
        "search_action": "PDF 검색",
        "search_intro": (
            "PDF를 하나씩 열지 않고 한꺼번에 검색하세요. PDF 파일이나 폴더를 "
            "놓으면 일치하는 페이지와 주변 텍스트를 표시합니다."
        ),
        "search_warning": (
            "선택 가능한 텍스트만 검색합니다. 스캔한 페이지는 먼저 OCR이 "
            "필요합니다. 파일은 변경되지 않습니다."
        ),
        "search_for": "찾을 텍스트",
        "case_sensitive": "대문자와 소문자를 정확히 구분",
        "search_drop_files": (
            "PDF 파일 또는 폴더를 여기에 놓으세요\n\n또는 클릭하여 파일 선택"
        ),
        "search_choose_files": "여기를 클릭하여 PDF 파일 선택",
        "search_browse_files": "PDF 파일 선택",
        "search_browse_folder": "폴더 선택",
        "search_folder_title": "하위 폴더까지 검색할 폴더 선택",
        "search_query_required": "먼저 찾을 텍스트를 입력하세요.",
        "searching_files": "PDF 파일 {count}개 검색 중...",
        "searching_file": "검색 중: {name}",
        "search_match": "{name} — {page}페이지\n{snippet}",
        "search_file_summary": "{name}: {pages}개 페이지에서 {matches}개 일치.",
        "search_no_match": "{name}: 일치 항목 없음.",
        "search_no_text": "{name}: 선택 가능한 텍스트 없음(스캔 PDF일 수 있음).",
        "search_truncated": "{name}: 처음 {limit}개 일치 항목만 표시합니다.",
        "search_finished": "검색 완료. PDF {files}개에서 {matches}개를 찾았습니다.",
    },
}
for _language, _search_translations in SEARCH_TRANSLATIONS.items():
    TRANSLATIONS[_language].update(_search_translations)

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
    "massive": {
        "label": "Massive image compression",
        "suffix": "_unlocked_massive_compressed",
    },
}
IMAGE_COMPRESSION_PROFILES = {
    "standard": {
        "label": "Standard image compression",
        "max_dimension": None,
        "quality": 85,
        "png_colors": None,
        "gif_colors": 256,
    },
    "major": {
        "label": "Strong image compression",
        "max_dimension": 2560,
        "quality": 68,
        "png_colors": 256,
        "gif_colors": 192,
    },
    "massive": {
        "label": "Maximum image compression",
        "max_dimension": 1600,
        "quality": 45,
        "png_colors": 128,
        "gif_colors": 96,
    },
}
SUPPORTED_IMAGE_EXTENSIONS = frozenset(
    {".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
)
MAX_TOTAL_IMAGE_PIXELS = 250_000_000


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
        return (1 - self.output_size / self.source_size) * 100


@dataclass(frozen=True)
class LockResult:
    source: Path
    output: Path
    page_count: int
    was_encrypted: bool
    source_size: int
    output_size: int


@dataclass(frozen=True)
class ImageCompressionResult:
    source: Path
    output: Path
    frame_count: int
    compression_mode: str
    source_size: int
    output_size: int

    @property
    def reduction_percent(self) -> float:
        if not self.source_size:
            return 0.0
        return (1 - self.output_size / self.source_size) * 100


@dataclass(frozen=True)
class PdfSearchMatch:
    page_number: int
    snippet: str


@dataclass(frozen=True)
class PdfSearchResult:
    source: Path
    page_count: int
    searchable_pages: int
    matches: tuple[PdfSearchMatch, ...]
    truncated: bool


LOCKED_PERMISSIONS = (
    UserAccessPermissions.R7
    | UserAccessPermissions.R8
    | UserAccessPermissions.R13
    | UserAccessPermissions.R14
    | UserAccessPermissions.R15
    | UserAccessPermissions.R16
    | UserAccessPermissions.R17
    | UserAccessPermissions.R18
    | UserAccessPermissions.R19
    | UserAccessPermissions.R20
    | UserAccessPermissions.R21
    | UserAccessPermissions.R22
    | UserAccessPermissions.R23
    | UserAccessPermissions.R24
    | UserAccessPermissions.R25
    | UserAccessPermissions.R26
    | UserAccessPermissions.R27
    | UserAccessPermissions.R28
    | UserAccessPermissions.R29
    | UserAccessPermissions.R30
    | UserAccessPermissions.R31
    | UserAccessPermissions.R32
)
USER_ACTION_PERMISSIONS = (
    UserAccessPermissions.PRINT
    | UserAccessPermissions.MODIFY
    | UserAccessPermissions.EXTRACT
    | UserAccessPermissions.ADD_OR_MODIFY
    | UserAccessPermissions.FILL_FORM_FIELDS
    | UserAccessPermissions.EXTRACT_TEXT_AND_GRAPHICS
    | UserAccessPermissions.ASSEMBLE_DOC
    | UserAccessPermissions.PRINT_TO_REPRESENTATION
)


def _format_size_change(
    result: UnlockResult | ImageCompressionResult,
    language: str = "en",
) -> str:
    translations = TRANSLATIONS[language]
    if result.reduction_percent > 0:
        return translations["size_smaller"].format(percent=result.reduction_percent)
    if result.reduction_percent < 0:
        return translations["size_larger"].format(percent=abs(result.reduction_percent))
    return translations["size_unchanged"]


def resource_path(relative_path: str) -> Path:
    """Resolve a bundled resource in source and PyInstaller builds."""

    application_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return application_root / relative_path


def settings_path() -> Path:
    """Return the per-user settings path without using the working directory."""

    local_app_data = os.environ.get("LOCALAPPDATA")
    settings_root = Path(local_app_data) if local_app_data else Path.home() / ".config"
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


def collect_pdf_files(inputs: Iterable[str | Path]) -> list[Path]:
    """Return unique PDF files, recursively expanding selected folders."""

    collected: list[Path] = []
    seen: set[str] = set()
    for value in inputs:
        path = Path(value)
        candidates = (
            sorted(
                (
                    candidate
                    for candidate in path.rglob("*")
                    if candidate.is_file() and candidate.suffix.lower() == ".pdf"
                ),
                key=lambda candidate: str(candidate).casefold(),
            )
            if path.is_dir()
            else [path]
        )
        for candidate in candidates:
            if not candidate.is_file() or candidate.suffix.lower() != ".pdf":
                continue
            resolved = candidate.resolve()
            identity = os.path.normcase(str(resolved))
            if identity not in seen:
                seen.add(identity)
                collected.append(resolved)
    return collected


def _normalise_search_text(text: str) -> str:
    return " ".join(text.split())


def _search_snippet(text: str, start: int, end: int, context_chars: int) -> str:
    left = max(0, start - context_chars)
    right = min(len(text), end + context_chars)
    snippet = text[left:right]
    if left:
        snippet = f"…{snippet}"
    if right < len(text):
        snippet = f"{snippet}…"
    return snippet


def search_pdf(
    source: str | Path,
    query: str,
    *,
    password: str | None = None,
    case_sensitive: bool = False,
    context_chars: int = 100,
    max_matches: int = 200,
) -> PdfSearchResult:
    """Search selectable PDF text and return page-numbered context snippets."""

    source_path = Path(source).resolve()
    if not source_path.is_file() or source_path.suffix.lower() != ".pdf":
        raise ValueError(f"Not a PDF file: {source_path}")
    normalised_query = _normalise_search_text(query)
    if not normalised_query:
        raise ValueError("Search text cannot be empty.")
    if context_chars < 0:
        raise ValueError("context_chars cannot be negative.")
    if max_matches < 1:
        raise ValueError("max_matches must be at least 1.")

    reader, _ = _open_reader(source_path, password)
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(re.escape(normalised_query), flags)
    matches: list[PdfSearchMatch] = []
    searchable_pages = 0
    truncated = False

    for page_number, page in enumerate(reader.pages, start=1):
        try:
            page_text = page.extract_text() or ""
        except (PdfReadError, TypeError, ValueError, KeyError):
            page_text = ""
        normalised_text = _normalise_search_text(page_text)
        if not normalised_text:
            continue
        searchable_pages += 1
        for occurrence in pattern.finditer(normalised_text):
            if len(matches) >= max_matches:
                truncated = True
                break
            matches.append(
                PdfSearchMatch(
                    page_number=page_number,
                    snippet=_search_snippet(
                        normalised_text,
                        occurrence.start(),
                        occurrence.end(),
                        context_chars,
                    ),
                )
            )
        if truncated:
            break

    return PdfSearchResult(
        source=source_path,
        page_count=len(reader.pages),
        searchable_pages=searchable_pages,
        matches=tuple(matches),
        truncated=truncated,
    )


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


def default_lock_output_path(source: Path) -> Path:
    base = source.with_name(f"{source.stem}_locked{source.suffix}")
    if not base.exists():
        return base

    number = 2
    while True:
        candidate = source.with_name(f"{source.stem}_locked ({number}){source.suffix}")
        if not candidate.exists():
            return candidate
        number += 1


def default_image_output_path(source: Path) -> Path:
    suffix = "_compressed"
    base = source.with_name(f"{source.stem}{suffix}{source.suffix}")
    if not base.exists():
        return base

    number = 2
    while True:
        candidate = source.with_name(f"{source.stem}{suffix} ({number}){source.suffix}")
        if not candidate.exists():
            return candidate
        number += 1


def _preserved_image_metadata(image, image_format: str) -> dict:
    metadata = {}
    for key in ("exif", "icc_profile", "dpi"):
        value = image.info.get(key)
        if value:
            metadata[key] = value

    if image_format == "PNG" and getattr(image, "text", None):
        from PIL.PngImagePlugin import PngInfo

        png_info = PngInfo()
        for key, value in image.text.items():
            if isinstance(value, str):
                png_info.add_text(str(key), value)
        metadata["pnginfo"] = png_info
    return metadata


def _resize_image_frame(frame, max_dimension: int | None):
    candidate = frame.copy()
    candidate.load()
    if max_dimension and max(candidate.size) > max_dimension:
        from PIL import Image

        candidate.thumbnail(
            (max_dimension, max_dimension),
            Image.Resampling.LANCZOS,
        )
    return candidate


def _prepare_image_frame(frame, image_format: str, profile: dict):
    from PIL import Image

    candidate = _resize_image_frame(frame, profile["max_dimension"])
    has_alpha = candidate.mode in {"RGBA", "LA"} or (
        candidate.mode == "P" and "transparency" in candidate.info
    )
    if image_format == "JPEG":
        if has_alpha:
            rgba = candidate.convert("RGBA")
            background = Image.new("RGB", rgba.size, "white")
            background.paste(rgba, mask=rgba.getchannel("A"))
            candidate = background
        elif candidate.mode not in {"RGB", "L", "CMYK"}:
            candidate = candidate.convert("RGB")
    elif image_format == "PNG" and profile["png_colors"]:
        if candidate.mode not in {"RGB", "RGBA"}:
            candidate = candidate.convert("RGBA" if has_alpha else "RGB")
        method = (
            Image.Quantize.FASTOCTREE
            if candidate.mode == "RGBA"
            else Image.Quantize.MEDIANCUT
        )
        candidate = candidate.quantize(
            colors=profile["png_colors"],
            method=method,
        )
    elif image_format in {"GIF", "BMP"}:
        colors = profile["gif_colors"]
        if candidate.mode not in {"RGB", "RGBA"}:
            candidate = candidate.convert("RGBA" if has_alpha else "RGB")
        method = (
            Image.Quantize.FASTOCTREE
            if candidate.mode == "RGBA"
            else Image.Quantize.MEDIANCUT
        )
        candidate = candidate.quantize(colors=colors, method=method)
    elif image_format == "WEBP" and candidate.mode not in {"RGB", "RGBA"}:
        candidate = candidate.convert("RGBA" if "A" in candidate.mode else "RGB")
    return candidate


def _image_save_options(image, image_format: str, profile: dict) -> dict:
    options = _preserved_image_metadata(image, image_format)
    quality = profile["quality"]
    if image_format == "JPEG":
        options.update(
            quality=quality,
            optimize=True,
            progressive=True,
            subsampling=0 if quality >= 80 else 2,
        )
    elif image_format == "PNG":
        options.update(optimize=True, compress_level=9)
    elif image_format == "WEBP":
        options.update(quality=quality, method=6)
    elif image_format == "GIF":
        options.update(optimize=True)
    elif image_format == "TIFF":
        options.update(compression="tiff_adobe_deflate")
    return options


def _write_compressed_image(source_image, temp_path: Path, mode: str) -> int:
    from PIL import Image, ImageSequence

    image_format = str(source_image.format or "").upper()
    if image_format == "JPG":
        image_format = "JPEG"
    if image_format not in {"JPEG", "PNG", "WEBP", "GIF", "BMP", "TIFF"}:
        raise ValueError(f"Unsupported image format: {image_format or 'unknown'}")

    profile = IMAGE_COMPRESSION_PROFILES[mode]
    frame_count = int(getattr(source_image, "n_frames", 1))
    total_pixels = source_image.width * source_image.height * frame_count
    if total_pixels > MAX_TOTAL_IMAGE_PIXELS:
        raise Image.DecompressionBombError(
            "The picture or animation is too large to process safely."
        )
    frames = [
        _prepare_image_frame(frame, image_format, profile)
        for frame in ImageSequence.Iterator(source_image)
    ]
    if not frames:
        raise ValueError("The image contains no readable frames.")

    options = _image_save_options(source_image, image_format, profile)
    if len(frames) > 1:
        options["save_all"] = True
        options["append_images"] = frames[1:]
        durations = [
            int(frame.info.get("duration", source_image.info.get("duration", 0)))
            for frame in ImageSequence.Iterator(source_image)
        ]
        if any(durations):
            options["duration"] = durations
        if "loop" in source_image.info:
            options["loop"] = source_image.info["loop"]

    frames[0].save(temp_path, format=image_format, **options)
    return frame_count


def _validate_compressed_image(
    output: Path,
    *,
    expected_format: str,
    expected_frames: int,
    source_size: int,
) -> None:
    from PIL import Image

    output_size = output.stat().st_size
    if output_size >= source_size:
        raise RuntimeError(
            "The image is already optimised; this setting could not make it smaller."
        )
    with Image.open(output) as check:
        check.verify()
    with Image.open(output) as check:
        actual_format = str(check.format or "").upper()
        if actual_format != expected_format:
            raise RuntimeError(
                f"Image format changed from {expected_format} to {actual_format}."
            )
        actual_frames = int(getattr(check, "n_frames", 1))
        if actual_frames != expected_frames:
            raise RuntimeError(
                f"Frame count changed from {expected_frames} to {actual_frames}."
            )
        if check.width <= 0 or check.height <= 0:
            raise RuntimeError("The compressed image has invalid dimensions.")


def compress_image(
    source: str | Path,
    *,
    output: str | Path | None = None,
    overwrite: bool = False,
    compression: str = "standard",
) -> ImageCompressionResult:
    """Create a smaller image copy beside the source while preserving its format."""

    from PIL import Image

    if compression not in IMAGE_COMPRESSION_PROFILES:
        raise ValueError(f"Unknown image compression mode: {compression}")

    source_path = Path(source).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"Image not found: {source_path}")
    if source_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ValueError(f"Unsupported image file: {source_path}")

    automatic_output = output is None
    output_path = (
        Path(output).expanduser().resolve()
        if output is not None
        else default_image_output_path(source_path)
    )
    if output_path == source_path:
        raise ValueError("The output must be different from the source image.")
    if output_path.suffix.lower() != source_path.suffix.lower():
        raise ValueError("The output must use the same image file extension.")
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output_path}")

    source_size = source_path.stat().st_size
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_fd, temp_name = tempfile.mkstemp(
        prefix=f".{output_path.stem}-",
        suffix=output_path.suffix,
        dir=str(output_path.parent),
    )
    os.close(temp_fd)
    temp_path = Path(temp_name)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(source_path) as source_image:
                expected_format = str(source_image.format or "").upper()
                if expected_format == "JPG":
                    expected_format = "JPEG"
                frame_count = _write_compressed_image(
                    source_image,
                    temp_path,
                    compression,
                )
        _validate_compressed_image(
            temp_path,
            expected_format=expected_format,
            expected_frames=frame_count,
            source_size=source_size,
        )
        if overwrite:
            os.replace(temp_path, output_path)
        else:
            while True:
                try:
                    _publish_without_overwrite(temp_path, output_path)
                    break
                except FileExistsError:
                    if not automatic_output:
                        raise
                    output_path = default_image_output_path(source_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    return ImageCompressionResult(
        source=source_path,
        output=output_path,
        frame_count=frame_count,
        compression_mode=compression,
        source_size=source_size,
        output_size=output_path.stat().st_size,
    )


def _publish_without_overwrite(temp_path: Path, output_path: Path) -> None:
    """Atomically publish a file while refusing to replace an existing path."""

    try:
        if os.name == "nt":
            os.rename(temp_path, output_path)
        else:
            os.link(temp_path, output_path)
            temp_path.unlink()
    except OSError as error:
        if output_path.exists():
            raise FileExistsError(f"Output already exists: {output_path}") from error
        raise


def _losslessly_recompress_streams(writer: PdfWriter, mode: str) -> int:
    if mode == "none":
        return 0

    optimized = 0
    for page in writer.pages:
        if _compress_page_content(page):
            optimized += 1

    if mode not in {"major", "massive"}:
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


def _massively_recompress_images(writer: PdfWriter) -> int:
    """Downsample and recompress large embedded images for maximum size savings."""
    from PIL import Image, UnidentifiedImageError

    max_dimension = 1440
    jpeg_quality = 28
    recompressed = 0
    processed_references: set[tuple[int, int]] = set()

    for page in writer.pages:
        try:
            page_images = list(page.images)
        except (ImportError, PdfReadError, TypeError, ValueError):
            continue

        for image_file in page_images:
            reference = image_file.indirect_reference
            if reference is None:
                # pypdf cannot safely replace inline images.
                continue

            reference_key = (reference.idnum, reference.generation)
            if reference_key in processed_references:
                continue
            processed_references.add(reference_key)

            try:
                original_image = image_file.image
                if (
                    original_image is None
                    or original_image.width * original_image.height < 65_536
                ):
                    continue

                candidate = original_image.copy()
                candidate.load()
                if max(candidate.size) > max_dimension:
                    candidate.thumbnail(
                        (max_dimension, max_dimension),
                        Image.Resampling.LANCZOS,
                    )

                if candidate.mode in {"RGBA", "LA"} or (
                    candidate.mode == "P" and "transparency" in candidate.info
                ):
                    rgba = candidate.convert("RGBA")
                    background = Image.new("RGB", rgba.size, "white")
                    background.paste(rgba, mask=rgba.getchannel("A"))
                    candidate = background
                elif candidate.mode != "RGB":
                    candidate = candidate.convert("RGB")

                preview = BytesIO()
                candidate.save(
                    preview,
                    "JPEG",
                    quality=jpeg_quality,
                    optimize=True,
                    progressive=True,
                )
                original_size = len(image_file.data)
                if original_size and preview.tell() >= original_size:
                    continue

                image_file.replace(
                    candidate,
                    quality=jpeg_quality,
                    optimize=True,
                    progressive=True,
                )
                recompressed += 1
            except (
                Image.DecompressionBombError,
                OSError,
                PdfReadError,
                TypeError,
                UnidentifiedImageError,
                ValueError,
            ):
                continue

    return recompressed


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


def _validate_locked_output(
    output: Path,
    expected_pages: int,
    user_password: str,
) -> None:
    check = PdfReader(str(output))
    if not check.is_encrypted:
        raise RuntimeError("The output is unexpectedly not encrypted.")
    if check.decrypt(user_password) != PasswordType.USER_PASSWORD:
        raise RuntimeError("The output cannot be opened with the chosen password.")
    if not check.are_permissions_valid:
        raise RuntimeError("The encrypted permission data failed its integrity check.")
    if len(check.pages) != expected_pages:
        raise RuntimeError(
            f"Page count changed from {expected_pages} to {len(check.pages)}."
        )
    permissions = check.user_access_permissions
    if permissions is None or permissions & USER_ACTION_PERMISSIONS:
        raise RuntimeError("Editing restrictions were not applied correctly.")


def lock_pdf(
    source: str | Path,
    user_password: str,
    *,
    source_password: str | None = None,
    output: str | Path | None = None,
    overwrite: bool = False,
) -> LockResult:
    """Create an AES-256 encrypted, permission-restricted copy of a PDF."""

    if len(user_password) < 8:
        raise ValueError("The new password must contain at least 8 characters.")

    source_path = Path(source).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"PDF not found: {source_path}")
    if source_path.suffix.lower() != ".pdf":
        raise ValueError(f"Not a PDF file: {source_path}")

    automatic_output = output is None
    output_path = (
        Path(output).expanduser().resolve()
        if output is not None
        else default_lock_output_path(source_path)
    )
    if output_path == source_path:
        raise ValueError("The output must be different from the source PDF.")
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    reader, was_encrypted = _open_reader(source_path, source_password)
    expected_pages = len(reader.pages)
    writer = PdfWriter(clone_from=reader)
    writer.encrypt(
        user_password=user_password,
        owner_password=secrets.token_urlsafe(48),
        permissions_flag=LOCKED_PERMISSIONS,
        algorithm="AES-256",
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
        _validate_locked_output(temp_path, expected_pages, user_password)
        if overwrite:
            os.replace(temp_path, output_path)
        else:
            while True:
                try:
                    _publish_without_overwrite(temp_path, output_path)
                    break
                except FileExistsError:
                    if not automatic_output:
                        raise
                    output_path = default_lock_output_path(source_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    return LockResult(
        source=source_path,
        output=output_path,
        page_count=expected_pages,
        was_encrypted=was_encrypted,
        source_size=source_path.stat().st_size,
        output_size=output_path.stat().st_size,
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

    automatic_output = output is None
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
    if compression == "massive":
        streams_optimized = _massively_recompress_images(writer)

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
        if overwrite:
            os.replace(temp_path, output_path)
        else:
            while True:
                try:
                    _publish_without_overwrite(temp_path, output_path)
                    break
                except FileExistsError:
                    if not automatic_output:
                        raise
                    output_path = default_output_path(source_path, compression)
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
        f"({_format_size_change(result)})"
    )


def _format_lock_result(result: LockResult) -> str:
    return (
        f"Created: {result.output}\n"
        f"Pages: {result.page_count}; AES-256 encrypted; editing, copying and "
        "printing disabled\n"
        f"Size: {result.source_size / 1_048_576:.2f} MB -> "
        f"{result.output_size / 1_048_576:.2f} MB"
    )


def _format_image_result(result: ImageCompressionResult) -> str:
    return (
        f"Created: {result.output}\n"
        f"Frames: {result.frame_count}; "
        f"{IMAGE_COMPRESSION_PROFILES[result.compression_mode]['label'].lower()}\n"
        f"Size: {result.source_size / 1_048_576:.2f} MB -> "
        f"{result.output_size / 1_048_576:.2f} MB "
        f"({_format_size_change(result)})"
    )


def _increase_named_font_sizes(root, increase: int = 2) -> None:
    """Increase every Tk named font and apply a bold, high-visibility weight."""
    from tkinter import font as tkfont

    for font_name in tkfont.names(root=root):
        named_font = tkfont.nametofont(font_name, root=root)
        named_font.configure(weight="bold")
        current_size = int(named_font.cget("size"))
        if current_size > 0:
            named_font.configure(size=current_size + increase)
        elif current_size < 0:
            # Negative Tk font sizes are pixels, so a larger magnitude is larger.
            named_font.configure(size=current_size - increase)


def _open_project_url(_event=None) -> bool:
    """Open the public project page in the user's default browser."""
    return webbrowser.open_new_tab(PROJECT_URL)


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
    root.geometry("840x820")
    root.minsize(780, 740)

    app_logo = None
    try:
        app_logo = tk.PhotoImage(file=str(resource_path("assets/smashpdf_logo_64.png")))
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
    _increase_named_font_sizes(root)

    preferred_language = load_language_preference()
    language_code = tk.StringVar(value=preferred_language)
    language_name = tk.StringVar(value=LANGUAGE_NAMES[preferred_language])

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
        font=("Segoe UI", 22, "bold"),
    ).pack(side="left")

    intro_label = ttk.Label(
        outer,
        text=tr("intro"),
        wraplength=760,
    )
    intro_label.pack(anchor="w", pady=(4, 14))

    warning_label = ttk.Label(
        outer,
        text=tr("warning"),
        foreground="#9A4D00",
        wraplength=760,
    )
    warning_label.pack(anchor="w", pady=(0, 14))

    action_mode = tk.StringVar(value="unlock")
    compression_enabled = tk.BooleanVar(value=False)
    compression_level = tk.StringVar(value="standard")
    search_query = tk.StringVar()
    search_case_sensitive = tk.BooleanVar(value=False)
    options = ttk.LabelFrame(outer, text=tr("processing_option"), padding=10)
    options.pack(fill="x", pady=(0, 14))

    action_label = ttk.Label(options, text=tr("action"))
    action_label.pack(anchor="w")
    unlock_radio = ttk.Radiobutton(
        options,
        text=tr("unlock_action"),
        variable=action_mode,
        value="unlock",
        command=lambda: update_compression_controls(),
    )
    unlock_radio.pack(anchor="w", padx=(22, 0), pady=2)
    lock_radio = ttk.Radiobutton(
        options,
        text=tr("lock_action"),
        variable=action_mode,
        value="lock",
        command=lambda: update_compression_controls(),
    )
    lock_radio.pack(anchor="w", padx=(22, 0), pady=2)
    image_radio = ttk.Radiobutton(
        options,
        text=tr("image_action"),
        variable=action_mode,
        value="image",
        command=lambda: update_compression_controls(),
    )
    image_radio.pack(anchor="w", padx=(22, 0), pady=2)
    search_radio = ttk.Radiobutton(
        options,
        text=tr("search_action"),
        variable=action_mode,
        value="search",
        command=lambda: update_compression_controls(),
    )
    search_radio.pack(anchor="w", padx=(22, 0), pady=(2, 8))

    search_frame = ttk.Frame(options)
    search_label = ttk.Label(search_frame, text=tr("search_for"))
    search_label.pack(anchor="w")
    search_entry = ttk.Entry(
        search_frame,
        textvariable=search_query,
    )
    search_entry.pack(fill="x", pady=(4, 5))
    search_case_check = ttk.Checkbutton(
        search_frame,
        text=tr("case_sensitive"),
        variable=search_case_sensitive,
    )
    search_case_check.pack(anchor="w")

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
        command=lambda: update_compression_controls(),
    )
    standard_radio.pack(anchor="w", padx=(22, 0), pady=2)
    major_radio = ttk.Radiobutton(
        options,
        text=tr("maximum_compression"),
        variable=compression_level,
        value="major",
        command=lambda: update_compression_controls(),
    )
    major_radio.pack(anchor="w", padx=(22, 0), pady=2)
    massive_radio = ttk.Radiobutton(
        options,
        text=tr("massive_compression"),
        variable=compression_level,
        value="massive",
        command=lambda: update_compression_controls(),
    )
    massive_radio.pack(anchor="w", padx=(22, 0), pady=2)

    quality_label = ttk.Label(
        options,
        text=tr("no_quality_removed"),
        foreground="#555555",
        wraplength=730,
    )
    quality_label.pack(anchor="w", pady=(5, 0))

    dynamic_widgets = {}

    def update_compression_controls() -> None:
        selected_action = action_mode.get()
        unlocking = selected_action == "unlock"
        compressing_images = selected_action == "image"
        searching = selected_action == "search"
        compression_widgets = (
            compression_check,
            standard_radio,
            major_radio,
            massive_radio,
            quality_label,
        )
        if searching:
            for widget in compression_widgets:
                widget.pack_forget()
            if not search_frame.winfo_manager():
                search_frame.pack(fill="x", pady=(2, 0), after=search_radio)
            search_entry.focus_set()
        else:
            search_frame.pack_forget()
            if not standard_radio.winfo_manager():
                standard_radio.pack(anchor="w", padx=(22, 0), pady=2)
                major_radio.pack(anchor="w", padx=(22, 0), pady=2)
                massive_radio.pack(anchor="w", padx=(22, 0), pady=2)
                quality_label.pack(anchor="w", pady=(5, 0))
        if compressing_images:
            compression_check.pack_forget()
        elif not searching:
            if not compression_check.winfo_manager():
                compression_check.pack(
                    anchor="w",
                    pady=(2, 5),
                    before=standard_radio,
                )
            compression_check.configure(state="normal" if unlocking else "disabled")

        state = (
            "normal"
            if compressing_images or (unlocking and compression_enabled.get())
            else "disabled"
        )
        if not searching:
            standard_radio.configure(state=state)
            major_radio.configure(state=state)
            massive_radio.configure(state=state)
        if compressing_images:
            standard_radio.configure(text=tr("image_standard_compression"))
            major_radio.configure(text=tr("image_maximum_compression"))
            massive_radio.configure(text=tr("image_massive_compression"))
            warning_key = {
                "standard": "image_standard_quality",
                "major": "image_major_quality",
                "massive": "image_massive_quality",
            }[compression_level.get()]
        elif not searching:
            standard_radio.configure(text=tr("standard_compression"))
            major_radio.configure(text=tr("maximum_compression"))
            massive_radio.configure(text=tr("massive_compression"))
            warning_key = (
                "massive_quality_warning"
                if compression_enabled.get() and compression_level.get() == "massive"
                else "no_quality_removed"
            )
        if not searching:
            quality_label.configure(text=tr(warning_key))
        intro_key = {
            "unlock": "intro",
            "lock": "lock_intro",
            "image": "image_intro",
            "search": "search_intro",
        }[selected_action]
        warning_text_key = {
            "unlock": "warning",
            "lock": "lock_warning",
            "image": "image_warning",
            "search": "search_warning",
        }[selected_action]
        intro_label.configure(text=tr(intro_key))
        warning_label.configure(text=tr(warning_text_key))
        if "drop_zone" in dynamic_widgets:
            dynamic_widgets["drop_zone"].configure(text=current_drop_text())
            dynamic_widgets["choose_button"].configure(text=current_browse_text())
            folder_button = dynamic_widgets["folder_button"]
            if searching:
                if not folder_button.winfo_manager():
                    folder_button.pack(side="left", padx=(8, 0))
            else:
                folder_button.pack_forget()

    update_compression_controls()

    def current_drop_text() -> str:
        if action_mode.get() == "search":
            return tr(
                "search_drop_files"
                if drag_and_drop_available
                else "search_choose_files"
            )
        if action_mode.get() == "image":
            return tr(
                "image_drop_files" if drag_and_drop_available else "image_choose_files"
            )
        return tr("drop_files") if drag_and_drop_available else tr("choose_files")

    def current_browse_text() -> str:
        if action_mode.get() == "image":
            return tr("image_browse_files")
        if action_mode.get() == "search":
            return tr("search_browse_files")
        return tr("browse_files")

    drop_zone = tk.Label(
        outer,
        text=current_drop_text(),
        font=("Segoe UI", 14, "bold"),
        foreground="#1F4E79",
        background="#F2F7FC",
        relief="groove",
        borderwidth=2,
        height=6,
        cursor="hand2",
    )
    drop_zone.pack(fill="x", pady=(0, 14))
    dynamic_widgets["drop_zone"] = drop_zone

    log = tk.Text(
        outer,
        height=9,
        wrap="word",
        font=("Consolas", 11, "bold"),
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
            changes.append(tr("standard_result", count=result.streams_optimized))
        elif result.compression_mode == "major":
            changes.append(tr("maximum_result", count=result.streams_optimized))
        elif result.compression_mode == "massive":
            changes.append(tr("massive_result", count=result.streams_optimized))

        return tr(
            "result_summary",
            output=result.output,
            pages=result.page_count,
            changes="; ".join(changes),
            source_mb=result.source_size / 1_048_576,
            output_mb=result.output_size / 1_048_576,
            size_change=_format_size_change(result, language_code.get()),
        )

    def format_gui_lock_result(result: LockResult) -> str:
        return tr(
            "lock_result_summary",
            output=result.output,
            pages=result.page_count,
            changes=tr("locked_copy_created"),
            source_mb=result.source_size / 1_048_576,
            output_mb=result.output_size / 1_048_576,
        )

    def format_gui_image_result(result: ImageCompressionResult) -> str:
        profile_key = {
            "standard": "image_standard_compression",
            "major": "image_maximum_compression",
            "massive": "image_massive_compression",
        }[result.compression_mode]
        return tr(
            "image_result_summary",
            output=result.output,
            frames=result.frame_count,
            profile=tr(profile_key),
            source_mb=result.source_size / 1_048_576,
            output_mb=result.output_size / 1_048_576,
            size_change=_format_size_change(result, language_code.get()),
        )

    def process_files(filenames) -> None:
        selected_action = action_mode.get()
        if selected_action == "search" and not search_query.get().strip():
            messagebox.showwarning(
                APP_NAME,
                tr("search_query_required"),
                parent=root,
            )
            search_entry.focus_set()
            return

        input_files = (
            collect_pdf_files(filenames) if selected_action == "search" else []
        )
        if selected_action != "search":
            for filename in filenames:
                path = Path(filename)
                valid_file = path.is_file() and (
                    path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
                    if selected_action == "image"
                    else path.suffix.lower() == ".pdf"
                )
                if valid_file:
                    input_files.append(path)
                else:
                    skipped_key = (
                        "skipped_not_image"
                        if selected_action == "image"
                        else "skipped_not_pdf"
                    )
                    append_log(tr(skipped_key, name=path.name or path))

        if not input_files:
            messagebox.showwarning(
                APP_NAME,
                tr("no_image" if selected_action == "image" else "no_pdf"),
                parent=root,
            )
            return

        selected_mode = (
            compression_level.get()
            if selected_action == "image"
            or (selected_action == "unlock" and compression_enabled.get())
            else "none"
        )
        new_password = None
        if selected_action == "lock":
            new_password = simpledialog.askstring(
                APP_NAME,
                tr("new_credential_prompt"),
                parent=root,
                show="*",
            )
            if new_password is None:
                return
            if len(new_password) < 8:
                messagebox.showwarning(
                    APP_NAME,
                    tr("credential_too_short"),
                    parent=root,
                )
                return
            confirmation = simpledialog.askstring(
                APP_NAME,
                tr("confirm_credential_prompt"),
                parent=root,
                show="*",
            )
            if confirmation is None:
                return
            if confirmation != new_password:
                messagebox.showwarning(
                    APP_NAME,
                    tr("credential_mismatch"),
                    parent=root,
                )
                return
        choose_button.configure(state="disabled")
        folder_button.configure(state="disabled")
        drop_zone.configure(
            text=tr(
                "processing_images"
                if selected_action == "image"
                else (
                    "searching_files"
                    if selected_action == "search"
                    else "processing_files"
                ),
                count=len(input_files),
            ),
            cursor="watch",
            background="#FFF7E6",
        )
        successes = 0
        failures = []
        total_matches = 0

        try:
            for source in input_files:
                append_log(
                    tr(
                        "searching_file"
                        if selected_action == "search"
                        else "processing_file",
                        name=source.name,
                    )
                )
                try:
                    if selected_action == "image":
                        result = compress_image(source, compression=selected_mode)
                    elif selected_action == "lock":
                        result = lock_pdf(source, new_password or "")
                    elif selected_action == "search":
                        result = search_pdf(
                            source,
                            search_query.get(),
                            case_sensitive=search_case_sensitive.get(),
                        )
                    else:
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
                        if selected_action == "lock":
                            result = lock_pdf(
                                source,
                                new_password or "",
                                source_password=password,
                            )
                        elif selected_action == "search":
                            result = search_pdf(
                                source,
                                search_query.get(),
                                password=password,
                                case_sensitive=search_case_sensitive.get(),
                            )
                        else:
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
                if isinstance(result, PdfSearchResult):
                    display_source = str(result.source)
                    total_matches += len(result.matches)
                    if result.searchable_pages == 0:
                        append_log(tr("search_no_text", name=display_source))
                    elif not result.matches:
                        append_log(tr("search_no_match", name=display_source))
                    else:
                        for match in result.matches:
                            append_log(
                                tr(
                                    "search_match",
                                    name=display_source,
                                    page=match.page_number,
                                    snippet=match.snippet,
                                )
                            )
                        matched_pages = len(
                            {match.page_number for match in result.matches}
                        )
                        append_log(
                            tr(
                                "search_file_summary",
                                name=display_source,
                                matches=len(result.matches),
                                pages=matched_pages,
                            )
                        )
                    if result.truncated:
                        append_log(
                            tr(
                                "search_truncated",
                                name=display_source,
                                limit=len(result.matches),
                            )
                        )
                elif isinstance(result, ImageCompressionResult):
                    append_log(format_gui_image_result(result))
                elif isinstance(result, LockResult):
                    append_log(format_gui_lock_result(result))
                else:
                    append_log(format_gui_result(result))
        finally:
            choose_button.configure(state="normal")
            folder_button.configure(state="normal")
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
                (
                    tr(
                        "search_finished",
                        matches=total_matches,
                        files=successes,
                    )
                    if selected_action == "search"
                    else tr(
                        "finished_images" if selected_action == "image" else "finished",
                        successes=successes,
                    )
                ),
                parent=root,
            )

    def select_and_unlock() -> None:
        selecting_images = action_mode.get() == "image"
        filenames = filedialog.askopenfilenames(
            parent=root,
            title=tr("image_select_title" if selecting_images else "select_title"),
            filetypes=[
                (
                    tr("image_files" if selecting_images else "pdf_files"),
                    (
                        "*.jpg *.jpeg *.jpe *.jfif *.png *.webp *.gif *.bmp "
                        "*.tif *.tiff"
                        if selecting_images
                        else "*.pdf"
                    ),
                ),
                (tr("all_files"), "*.*"),
            ],
        )
        if filenames:
            process_files(filenames)

    def select_search_folder() -> None:
        folder = filedialog.askdirectory(
            parent=root,
            title=tr("search_folder_title"),
            mustexist=True,
        )
        if folder:
            process_files((folder,))

    def handle_drop(event) -> None:
        filenames = root.tk.splitlist(event.data)
        process_files(filenames)

    def show_about() -> None:
        about = tk.Toplevel(root)
        about.title(f"{tr('about')} {APP_NAME}")
        about.geometry("440x340")
        about.resizable(False, False)
        about.transient(root)
        about.grab_set()

        if app_logo is not None:
            ttk.Label(about, image=app_logo).pack(pady=(20, 2))
        ttk.Label(
            about,
            text=APP_NAME,
            font=("Segoe UI", 22, "bold"),
        ).pack(pady=((24 if app_logo is None else 2), 2))
        ttk.Label(
            about,
            text=tr("version", version=APP_VERSION),
            foreground="#555555",
        ).pack()
        ttk.Label(
            about,
            text=tr("thank_you"),
            font=("Segoe UI", 13, "bold"),
        ).pack(pady=(20, 4))
        ttk.Label(
            about,
            text=tr("made_by"),
            font=("Segoe UI", 12, "bold"),
        ).pack()
        project_link = ttk.Label(
            about,
            text=PROJECT_URL,
            foreground="#1F4E79",
            cursor="hand2",
            font=("Segoe UI", 12, "bold underline"),
            takefocus=True,
        )
        project_link.pack(pady=(8, 14))
        project_link.bind("<Button-1>", _open_project_url)
        project_link.bind("<Return>", _open_project_url)
        ttk.Button(about, text=tr("close"), command=about.destroy).pack()

        about.update_idletasks()
        x = root.winfo_x() + (root.winfo_width() - about.winfo_width()) // 2
        y = root.winfo_y() + (root.winfo_height() - about.winfo_height()) // 2
        about.geometry(f"+{max(0, x)}+{max(0, y)}")
        about.focus_set()

    choose_button = ttk.Button(
        button_row,
        text=current_browse_text(),
        command=select_and_unlock,
    )
    choose_button.pack(side="left")
    dynamic_widgets["choose_button"] = choose_button
    folder_button = ttk.Button(
        button_row,
        text=tr("search_browse_folder"),
        command=select_search_folder,
    )
    dynamic_widgets["folder_button"] = folder_button
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
            code for code, name in LANGUAGE_NAMES.items() if name == selected_name
        )
        language_code.set(selected_code)

        language_label.configure(text=tr("language"))
        intro_label.configure(text=tr("intro"))
        warning_label.configure(text=tr("warning"))
        options.configure(text=tr("processing_option"))
        action_label.configure(text=tr("action"))
        unlock_radio.configure(text=tr("unlock_action"))
        lock_radio.configure(text=tr("lock_action"))
        image_radio.configure(text=tr("image_action"))
        search_radio.configure(text=tr("search_action"))
        search_label.configure(text=tr("search_for"))
        search_case_check.configure(text=tr("case_sensitive"))
        compression_check.configure(text=tr("compress_after_unlocking"))
        update_compression_controls()
        drop_zone.configure(text=current_drop_text())
        choose_button.configure(text=current_browse_text())
        folder_button.configure(text=tr("search_browse_folder"))
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
            "Unlock, protect, compress, or search local files without "
            "modifying sources."
        )
    )
    parser.add_argument("files", nargs="*", help="PDF or picture files to process")
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
        "--lock",
        action="store_true",
        help="Create an AES-256 encrypted copy with editing disabled",
    )
    parser.add_argument(
        "--lock-password",
        help=(
            "New opening password for --lock; omit to enter it securely at the prompt"
        ),
    )
    parser.add_argument(
        "--compress-images",
        action="store_true",
        help="Compress JPEG, PNG, WebP, GIF, BMP, or TIFF picture files",
    )
    parser.add_argument(
        "--search",
        metavar="TEXT",
        help="Search selectable text in PDF files or folders without changing them",
    )
    parser.add_argument(
        "--case-sensitive",
        action="store_true",
        help="Make --search distinguish uppercase and lowercase",
    )
    parser.add_argument(
        "--compression",
        choices=("none", "standard", "major", "massive"),
        default="none",
        help=(
            "Compression mode. For PDFs: none, standard or major (lossless), "
            "or massive (lossy). For pictures: standard, major, or massive."
        ),
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Open the graphical interface",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    search_requested = args.search is not None
    if args.gui:
        return run_gui()
    if not args.files:
        if search_requested:
            raise SystemExit("--search requires at least one PDF file or folder.")
        return run_gui()
    if args.output and len(args.files) != 1:
        raise SystemExit("--output can only be used with one input file.")
    if args.lock_password and not args.lock:
        raise SystemExit("--lock-password requires --lock.")
    if args.lock and args.compress_images:
        raise SystemExit("--lock cannot be used with --compress-images.")
    if search_requested and (args.lock or args.compress_images):
        raise SystemExit("--search cannot be used with --lock or --compress-images.")
    if args.case_sensitive and not search_requested:
        raise SystemExit("--case-sensitive requires --search.")
    if search_requested and (args.output or args.overwrite):
        raise SystemExit("--output and --overwrite cannot be used with --search.")
    if search_requested and args.compression != "none":
        raise SystemExit("--compression cannot be used with --search.")
    if args.lock and args.compression != "none":
        raise SystemExit("--compression cannot be used with --lock.")
    if args.password and args.compress_images:
        raise SystemExit("--password cannot be used with --compress-images.")

    lock_password = args.lock_password
    if args.lock and lock_password is None:
        lock_password = getpass.getpass("New PDF opening password: ")
        confirmation = getpass.getpass("Confirm new PDF opening password: ")
        if lock_password != confirmation:
            raise SystemExit("The new passwords do not match.")
    if args.lock and len(lock_password or "") < 8:
        raise SystemExit("The new password must contain at least 8 characters.")

    exit_code = 0
    filenames = collect_pdf_files(args.files) if search_requested else args.files
    if search_requested and not filenames:
        print("No PDF files were found.", file=sys.stderr)
        return 1
    for filename in filenames:
        try:
            if search_requested:
                search_result = search_pdf(
                    filename,
                    args.search or "",
                    password=args.password,
                    case_sensitive=args.case_sensitive,
                )
                for match in search_result.matches:
                    print(
                        f"{search_result.source} — page {match.page_number}\n"
                        f"{match.snippet}\n"
                    )
                matched_pages = len(
                    {match.page_number for match in search_result.matches}
                )
                print(
                    f"{search_result.source}: {len(search_result.matches)} match(es) "
                    f"on {matched_pages} page(s)."
                )
                if search_result.searchable_pages == 0:
                    print("No selectable text found; this may be a scanned PDF.")
                if search_result.truncated:
                    print("Showing the first 200 matches.")
            elif args.compress_images:
                image_compression = (
                    "standard" if args.compression == "none" else args.compression
                )
                result = compress_image(
                    filename,
                    output=args.output,
                    overwrite=args.overwrite,
                    compression=image_compression,
                )
                print(_format_image_result(result))
            elif args.lock:
                result = lock_pdf(
                    filename,
                    lock_password or "",
                    source_password=args.password,
                    output=args.output,
                    overwrite=args.overwrite,
                )
                print(_format_lock_result(result))
            else:
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
