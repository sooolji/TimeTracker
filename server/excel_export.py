from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from server.db import ROOT

TEMPLATE_NAME = "yyyy-mm-dd nombre.xlsx"
FIRST_DATA_ROW = 6
MAX_BLOCKS = 60
SHEET_PATH = "xl/worksheets/sheet1.xml"
STRINGS_PATH = "xl/sharedStrings.xml"
SHEET_RELS_PATH = "xl/worksheets/_rels/sheet1.xml.rels"

DURATION_FORMULA = (
    "IF(AND(NOT(ISBLANK(C{row})),NOT(ISBLANK(D{row}))),MOD(D{row}-C{row},1),0)"
)


class ExportError(Exception):
    pass


def hhmm_to_serial(value: str) -> float:
    parts = value.strip().split(":")
    if len(parts) < 2:
        raise ExportError(f"Hora inválida: {value}")
    hours = int(parts[0])
    minutes = int(parts[1])
    if not (0 <= hours < 24 and 0 <= minutes < 60):
        raise ExportError(f"Hora fuera de rango: {value}")
    return (hours * 60 + minutes) / (24 * 60)


def serial_xml(value: float) -> str:
    return f"{value:.16g}"


def report_filename(day: str, author: str) -> str:
    datetime.strptime(day, "%Y-%m-%d")
    return f"{day} {author}.xlsx"


def template_path(name: str = TEMPLATE_NAME) -> Path:
    path = ROOT / name
    if not path.exists():
        raise ExportError(f"No se encontró la plantilla: {path}")
    return path


def destination_path(day: str, author: str) -> Path:
    return ROOT / report_filename(day, author)


def _cell_span(xml: str, ref: str) -> tuple[int, int]:
    token = f'<c r="{ref}"'
    start = 0
    while True:
        start = xml.find(token, start)
        if start < 0:
            raise ExportError(f"La plantilla no tiene la celda {ref}.")
        nxt = xml[start + len(token) : start + len(token) + 1]
        if nxt in {"", " ", "/", ">"}:
            break
        start += len(token)
    gt = xml.find(">", start)
    if gt < 0:
        raise ExportError(f"Celda {ref} mal formada.")
    if xml[gt - 1] == "/":
        return start, gt + 1
    end = xml.find("</c>", gt)
    if end < 0:
        raise ExportError(f"Celda {ref} mal formada.")
    return start, end + 4


def _replace_cell(xml: str, ref: str, new_cell: str) -> str:
    start, end = _cell_span(xml, ref)
    return xml[:start] + new_cell + xml[end:]


def _cell_attrs(xml: str, ref: str) -> str:
    start, end = _cell_span(xml, ref)
    opening = xml[start:end]
    gt = opening.find(">")
    attrs = opening[len(f'<c r="{ref}"') : gt]
    attrs = attrs.rstrip("/")
    attrs = re.sub(r'\st="[^"]*"', "", attrs)
    return attrs


def _append_shared_string(sst_xml: str, text: str) -> tuple[str, int]:
    count_match = re.search(r'\buniqueCount="(\d+)"', sst_xml)
    total_match = re.search(r'\bcount="(\d+)"', sst_xml)
    if not count_match or not total_match:
        raise ExportError("sharedStrings.xml no tiene contadores.")
    index = int(count_match.group(1))
    sst_xml = sst_xml.replace(
        f'uniqueCount="{count_match.group(1)}"',
        f'uniqueCount="{index + 1}"',
        1,
    )
    sst_xml = sst_xml.replace(
        f'count="{total_match.group(1)}"',
        f'count="{int(total_match.group(1)) + 1}"',
        1,
    )
    space = ' xml:space="preserve"' if text[:1].isspace() or text[-1:].isspace() else ""
    entry = f"<si><t{space}>{escape(text)}</t></si>\n"
    if "</sst>" not in sst_xml:
        raise ExportError("sharedStrings.xml inválido.")
    sst_xml = sst_xml.replace("</sst>", entry + "</sst>", 1)
    return sst_xml, index


def _strip_stale_hyperlinks(sheet_xml: str) -> str:
    return re.sub(r"\s*<hyperlinks>.*?</hyperlinks>", "", sheet_xml, flags=re.DOTALL)


def _clean_sheet_rels(rels_xml: str | None) -> str | None:
    if not rels_xml:
        return rels_xml
    cleaned = re.sub(
        r"<Relationship[^>]*hyperlink[^>]*/>\s*",
        "",
        rels_xml,
    )
    if "<Relationship " not in cleaned and "<Relationship/" not in cleaned:
        return None
    return cleaned


def _update_cached_value(xml: str, ref: str, value: float) -> str:
    start, end = _cell_span(xml, ref)
    cell = xml[start:end]
    serial = serial_xml(value)
    if re.search(r"<v>[^<]*</v>", cell):
        cell = re.sub(r"<v>[^<]*</v>", f"<v>{serial}</v>", cell, count=1)
    elif cell.endswith("/>"):
        attrs = cell[len(f'<c r="{ref}"') : -2].rstrip()
        cell = f'<c r="{ref}"{attrs}><v>{serial}</v></c>'
    else:
        cell = cell[:-4] + f"<v>{serial}</v></c>"
    return xml[:start] + cell + xml[end:]


def write_report(
    *,
    day: str,
    author: str,
    blocks: list[dict],
    overwrite: bool = False,
    template: str = TEMPLATE_NAME,
) -> Path:
    if not blocks:
        raise ExportError("El informe necesita al menos un bloque de tiempo.")
    if len(blocks) > MAX_BLOCKS:
        raise ExportError(f"Demasiados bloques (máximo {MAX_BLOCKS}).")

    dest = destination_path(day, author)
    if dest.exists() and not overwrite:
        raise FileExistsError(str(dest))

    src = template_path(template)
    with zipfile.ZipFile(src) as zin:
        parts = {info.filename: (info, zin.read(info.filename)) for info in zin.infolist()}

    sheet_xml = parts[SHEET_PATH][1].decode("utf-8")
    sst_xml = parts[STRINGS_PATH][1].decode("utf-8")
    rels_entry = parts.get(SHEET_RELS_PATH)
    rels_xml = rels_entry[1].decode("utf-8") if rels_entry else None

    sheet_xml = _strip_stale_hyperlinks(sheet_xml)
    rels_xml = _clean_sheet_rels(rels_xml)

    total = 0.0
    for index, block in enumerate(blocks):
        row = FIRST_DATA_ROW + index
        title = str(block.get("title") or "").strip()
        description = str(block.get("description") or "").strip()
        if not title:
            raise ExportError(f"El bloque {index + 1} no tiene título.")

        start = hhmm_to_serial(str(block["start"]))
        end = hhmm_to_serial(str(block["end"]))
        duration = (end - start) % 1
        total += duration

        c_attrs = _cell_attrs(sheet_xml, f"C{row}")
        d_attrs = _cell_attrs(sheet_xml, f"D{row}")
        e_attrs = _cell_attrs(sheet_xml, f"E{row}")
        h_attrs = _cell_attrs(sheet_xml, f"H{row}")

        sheet_xml = _replace_cell(
            sheet_xml,
            f"C{row}",
            f'<c r="C{row}"{c_attrs}><v>{serial_xml(start)}</v></c>',
        )
        sheet_xml = _replace_cell(
            sheet_xml,
            f"D{row}",
            f'<c r="D{row}"{d_attrs}><v>{serial_xml(end)}</v></c>',
        )
        sheet_xml = _replace_cell(
            sheet_xml,
            f"E{row}",
            (
                f'<c r="E{row}"{e_attrs}>'
                f"<f>{DURATION_FORMULA.format(row=row)}</f>"
                f"<v>{serial_xml(duration)}</v></c>"
            ),
        )
        sst_xml, title_idx = _append_shared_string(sst_xml, title)
        sheet_xml = _replace_cell(
            sheet_xml,
            f"H{row}",
            f'<c r="H{row}"{h_attrs} t="s"><v>{title_idx}</v></c>',
        )
        if description:
            i_attrs = _cell_attrs(sheet_xml, f"I{row}")
            sst_xml, desc_idx = _append_shared_string(sst_xml, description)
            sheet_xml = _replace_cell(
                sheet_xml,
                f"I{row}",
                f'<c r="I{row}"{i_attrs} t="s"><v>{desc_idx}</v></c>',
            )
        sheet_xml = _update_cached_value(sheet_xml, f"G{row}", duration)

    sheet_xml = _update_cached_value(sheet_xml, "F2", total)

    parts[SHEET_PATH] = (parts[SHEET_PATH][0], sheet_xml.encode("utf-8"))
    parts[STRINGS_PATH] = (parts[STRINGS_PATH][0], sst_xml.encode("utf-8"))
    if rels_xml is None:
        parts.pop(SHEET_RELS_PATH, None)
    elif rels_entry:
        parts[SHEET_RELS_PATH] = (rels_entry[0], rels_xml.encode("utf-8"))

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zout:
        for name, (info, data) in parts.items():
            new_info = zipfile.ZipInfo(filename=name, date_time=info.date_time)
            new_info.compress_type = info.compress_type
            new_info.external_attr = info.external_attr
            zout.writestr(new_info, data)
    dest.write_bytes(buffer.getvalue())
    return dest
