"""Derive print geometry from the user-owned FastReport .fr3 template.

The original template is READ ONLY. No bank numbers, phone numbers, addresses,
names of private buyer records, or fonts are exported into the app bundle.
Only the explicitly allowed static labels, dimensions and template logo are
retained. Do not run against an untrusted .fr3 file.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r"C:\Program Files (x86)\Parsian\Report\000- Karma Sale Factor.fr3")
MANIFEST = ROOT / "src" / "parsian_karma_layout.json"
LOGO = ROOT / "src" / "assets" / "parsian_karma_template_logo.jpg"

SOURCE_SHA256 = "75a67d25e2da7e40d2589df4cc2d007505b546f62baa5db849f850d93f39dc6a"
TEXT_ALLOWLIST = {
    "Memo25", "Memo13", "Memo15", "Memo28", "Memo29", "Memo36", "Memo52",
    "Memo62", "Memo65", "Memo66", "Memo67", "Memo69", "Memo71", "Memo72",
    "Memo73", "Memo77", "Memo2", "Memo4", "Memo6", "Memo7", "Memo8",
    "Memo11", "Memo3", "Memo9", "Memo12", "Memo30", "Memo42", "Memo43",
    "Memo53", "Memo46", "Memo47", "Memo49", "Memo50",
}
GEOMETRY_TAGS = {"TfrxShapeView": "rect", "TfrxLineView": "line",
                 "TfrxMemoView": "text"}
KNOWN_BANDS = ("TfrxReportTitle", "TfrxHeader",
               "TfrxMasterData", "TfrxReportSummary", "TfrxPageHeader")


def number(attrs, key, default=0):
    return round(float(attrs.get(key, default)), 5)


def objects(parent):
    result = []
    for obj in parent:
        kind = GEOMETRY_TAGS.get(obj.tag)
        if not kind:
            continue
        a = obj.attrib
        entry = {"type": kind, "name": a.get("Name", ""),
                 "x": number(a, "Left"), "y": number(a, "Top"),
                 "w": number(a, "Width"), "h": number(a, "Height")}
        if kind == "text":
            # Dynamic fields and mutable data are resolved from R5 at print
            # time. Only safe static heading labels are retained.
            entry["text"] = a.get("Text", "") if entry["name"] in TEXT_ALLOWLIST else ""
            entry["font"] = a.get("Font.Name", "DanaFaNum")
            entry["fontHeight"] = abs(number(a, "Font.Height", 13))
            entry["hAlign"] = a.get("HAlign", "haLeft")
            entry["vAlign"] = a.get("VAlign", "vaTop")
            entry["visible"] = a.get("Visible") != "False"
        elif kind == "rect":
            entry["round"] = a.get("Shape") == "skRoundRectangle"
            entry["strokeWidth"] = number(a, "Frame.Width", 1)
            entry["background"] = a.get("Color", "")
        else:
            entry["strokeWidth"] = number(a, "Frame.Width", 1)
        result.append(entry)
    return result


def main():
    data = SOURCE.read_bytes()
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise RuntimeError("FastReport template changed; audit before re-extraction")
    # The installed file declares UTF-8 but its PrintOptions.Printer field
    # contains non-UTF8 Windows bytes. Replacement is confined to invalid
    # metadata; the Persian labels are genuine UTF-8.
    report = ET.fromstring(data.decode("utf-8", errors="replace"))
    page = report.find("TfrxReportPage")
    if page is None or page.get("PaperWidth") != "210" or page.get("PaperHeight") != "297":
        raise RuntimeError("Unexpected FastReport page size or structure")
    bands = {}
    for tag in KNOWN_BANDS:
        band = page.find(tag)
        if band is None:
            raise RuntimeError("Missing expected FastReport band: " + tag)
        bands[tag.replace("Tfrx", "")] = {
            "height": number(band.attrib, "Height"),
            "objects": objects(band),
        }
    picture = page.find("TfrxPictureView[@Name='Picture1']")
    if picture is None:
        raise RuntimeError("Expected FastReport logo not found")
    hex_data = picture.get("Picture.PropData", "")
    binary = bytes.fromhex(hex_data)
    offset = binary.index(b"\xff\xd8")
    jpeg = binary[offset:]
    if jpeg[-2:] != b"\xff\xd9" or len(jpeg) < 1000:
        raise RuntimeError("Unexpected embedded JPEG data")
    if LOGO.exists() or MANIFEST.exists():
        raise FileExistsError("Refusing to overwrite derived print assets")
    LOGO.parent.mkdir(parents=True, exist_ok=True)
    # No raw FR3 copied into the public frontend.
    extracted = {
        "template": "Parsian / 000- Karma Sale Factor.fr3",
        "sourceSha256": SOURCE_SHA256,
        "paperMm": [210, 297],
        "marginMm": [10, 10, 10, 10],
        "bandWidth": 718.1107,
        "bands": bands,
        "logoRect": {k: number(picture.attrib, k2) for k, k2 in
                     (("x", "Left"), ("y", "Top"), ("w", "Width"), ("h", "Height"))},
        "titleFrame": objects(page)[:1],
    }
    LOGO.write_bytes(jpeg)
    MANIFEST.write_text(json.dumps(extracted, ensure_ascii=False,
                                   separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"geometry": str(MANIFEST), "logo": str(LOGO),
                      "objects": {k: len(b["objects"]) for k, b in bands.items()},
                      "sourceHashMatch": True}, ensure_ascii=True))


if __name__ == "__main__":
    main()
