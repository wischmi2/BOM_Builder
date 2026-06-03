from __future__ import annotations

import io
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

# Typical MPN patterns on distributor labels (Murata, Yageo, etc.)
_MPN_TOKEN = r"[A-Z0-9][A-Z0-9\-\+/\.]{4,}"


@dataclass
class LabelScanResult:
    lib_ref: str = ""
    name: str = ""
    qty_on_hand: int = 0
    notes: str = ""
    raw_text: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "lib_ref": self.lib_ref,
            "name": self.name,
            "qty_on_hand": self.qty_on_hand,
            "notes": self.notes,
            "raw_text": self.raw_text,
            "warnings": self.warnings,
        }


class LabelScanError(Exception):
    pass


def _find_tesseract_executable() -> str | None:
    """Locate tesseract.exe — PATH first, then common Windows install folders."""
    on_path = shutil.which("tesseract")
    if on_path:
        return on_path

    candidates = [
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    ]
    env_path = os.environ.get("TESSERACT_CMD", "").strip()
    if env_path:
        candidates.insert(0, Path(env_path))

    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def _configure_tesseract(pytesseract: object) -> None:
    cmd = _find_tesseract_executable()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd


def _require_ocr() -> tuple[object, object]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise LabelScanError(
            "Pillow is not installed. Run: pip install -r requirements.txt"
        ) from exc
    try:
        import pytesseract
    except ImportError as exc:
        raise LabelScanError(
            "pytesseract is not installed. Run: pip install -r requirements.txt"
        ) from exc
    _configure_tesseract(pytesseract)
    return Image, pytesseract


def ocr_image(image_bytes: bytes) -> str:
    """Run OCR on a label photo. Requires Tesseract installed on the system."""
    Image, pytesseract = _require_ocr()
    try:
        image = Image.open(io.BytesIO(image_bytes))
    except Exception as exc:
        raise LabelScanError("Could not read image file.") from exc

    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    # Upscale small photos; grayscale improves OCR on glossy labels.
    width, height = image.size
    if max(width, height) < 1200:
        scale = 1200 / max(width, height)
        image = image.resize((int(width * scale), int(height * scale)))

    gray = image.convert("L")
    try:
        text = pytesseract.image_to_string(gray, config="--psm 6")
    except pytesseract.TesseractNotFoundError as exc:
        raise LabelScanError(
            "Tesseract OCR was not found. Install it from "
            "https://github.com/UB-Mannheim/tesseract/wiki (default folder is fine). "
            "Or set environment variable TESSERACT_CMD to the full path of tesseract.exe."
        ) from exc
    return text


def parse_label_text(text: str) -> LabelScanResult:
    """Parse distributor label text (DigiKey-style) into inventory fields."""
    result = LabelScanResult(raw_text=text)
    if not text or not text.strip():
        result.warnings.append("No text detected in image.")
        return result

    normalized = text.replace("\r", "\n")
    upper = normalized.upper()

    mfr_pn = _extract_mfr_pn(normalized)
    dk_pn = _extract_digikey_pn(normalized)
    description = _extract_description(normalized)
    qty = _extract_quantity(normalized)
    lot = _extract_field(normalized, r"LOT\s*(?:CODE)?[:\s]*([A-Z0-9\-]+)")
    inv = _extract_field(normalized, r"INV\s*#?[:\s]*([0-9]+)")

    result.lib_ref = mfr_pn or dk_pn or ""
    result.name = description
    result.qty_on_hand = qty

    note_parts: list[str] = []
    if dk_pn and mfr_pn and dk_pn != mfr_pn:
        note_parts.append(f"DigiKey {dk_pn}")
    if lot:
        note_parts.append(f"Lot {lot}")
    if inv:
        note_parts.append(f"INV {inv}")
    result.notes = "; ".join(note_parts)

    if not result.lib_ref:
        result.warnings.append("Could not find MFR PN or DigiKey PN — enter LibRef manually.")
    if not result.name:
        result.warnings.append("Could not find description — enter Name manually.")
    if result.qty_on_hand == 0:
        result.warnings.append("Could not find quantity — enter Qty manually.")

    if "DIGIKEY" in upper or "DIGI-KEY" in upper:
        result.warnings.append("DigiKey label detected — verify MFR PN matches your BOM LibRef.")

    return result


def scan_label_image(image_bytes: bytes) -> LabelScanResult:
    text = ocr_image(image_bytes)
    return parse_label_text(text)


def _extract_field(text: str, pattern: str) -> str:
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _extract_mfr_pn(text: str) -> str:
    patterns = [
        rf"MFR\s*P/?N[:\s]*({_MPN_TOKEN})",
        rf"MANUFACTURER\s*PART\s*(?:NO\.?|NUMBER|#)?[:\s]*({_MPN_TOKEN})",
        rf"MFR\s*PART[:\s]*({_MPN_TOKEN})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _clean_mpn(match.group(1))
    return ""


def _extract_digikey_pn(text: str) -> str:
    patterns = [
        rf"(?:DIGI[-\s]?KEY\s*)?P/?N[:\s]*({_MPN_TOKEN}(?:-ND)?)",
        rf"DK\s*P/?N[:\s]*({_MPN_TOKEN})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _clean_mpn(match.group(1))
    return ""


def _extract_description(text: str) -> str:
    patterns = [
        r"(RES\s+[\d\.]+(?:K|M)?\s*OHM[^\n]{0,80})",
        r"(CAP\s+[^\n]{5,80})",
        r"(IND\s+[^\n]{5,80})",
        r"((?:SMD|SMT)\s+[^\n]{5,60})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            line = " ".join(match.group(1).split())
            if len(line) >= 8:
                return line[:120]
    # Fallback: line after MFR PN block that looks like a spec line
    for line in text.splitlines():
        clean = line.strip()
        if re.search(r"(RES|CAP|IND|OHM|UF|NH|MHZ)", clean, re.IGNORECASE) and len(clean) >= 10:
            return clean[:120]
    return ""


def _extract_quantity(text: str) -> int:
    qty_label = re.search(
        r"Q(?:TY|UANTITY)[:\s]*([\d,]+)",
        text,
        re.IGNORECASE,
    )
    if qty_label:
        return _parse_int(qty_label.group(1))

    candidates: list[int] = []
    for match in re.finditer(r"\b(\d{1,3}(?:,\d{3})+|\d{3,6})\b", text):
        value = _parse_int(match.group(1))
        if value is None or value < 1 or value > 500_000:
            continue
        # Skip common date codes on labels
        if value in (2023, 2024, 2025, 2026, 2124, 2324, 2425):
            continue
        candidates.append(value)

    if not candidates:
        return 0

    standard_reel = {1000, 2500, 3000, 5000, 10000, 15000, 20000, 25000}
    non_standard = [c for c in candidates if c not in standard_reel]
    if non_standard:
        # Handwritten remaining qty (e.g. 9287) vs printed reel size (10000).
        return max(non_standard)
    return max(candidates)


def _parse_int(raw: str) -> int | None:
    try:
        return int(str(raw).replace(",", "").strip())
    except ValueError:
        return None


def _clean_mpn(value: str) -> str:
    return value.strip().strip(".,;:")
