# -*- coding: utf-8 -*-
"""Minimal XLSX reading and writing, on the standard library alone.

The plugin needs exactly two things from an XLSX file:

1. Read one column of strings from one sheet (TRACT's country list).
2. Copy a template and write a handful of string cells into one of its sheets
   (the Master Data writer).

That is a small enough surface to do directly, which lets the plugin ship with
no third-party code at all — previously this was a 5.3 MB vendored copy of
openpyxl + et_xmlfile.

Two deliberate implementation choices:

* **No ``xml.etree``.** The sheet XML is manipulated as text. Pulling in a real
  XML parser would defeat one of the reasons this module exists, and rewriting
  the file through a parser would also normalize namespaces and drop parts of
  the workbook that Excel put there on purpose.
* **Only the targeted cells are touched.** Every other zip entry is copied
  through byte-for-byte, so nothing else in the workbook can be lost. openpyxl
  silently dropped the country drop-down (an ``extLst`` data validation it does
  not model) from every file it wrote; this module preserves it.

Written cells use inline strings (``t="inlineStr"``), so the shared-string
table never has to be rewritten.
"""

import re
import shutil
import zipfile


# ---------------------------------------------------------------------------
# Small XML / spreadsheet primitives
# ---------------------------------------------------------------------------

_ENTITIES = (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'"))


def _start_tags(xml, element):
    """Find every start tag for `element`, tolerating '>' inside attributes.

    XML only requires '<' and '&' to be escaped in an attribute value, so a bare
    '>' is legal there — the bundled farms template really does have a sheet
    named '>>>'. Matching with a plain [^>]* would truncate that tag and lose
    the sheet entirely.
    """
    return re.findall(r'<%s\b(?:[^>"]|"[^"]*")*>' % element, xml)


def _attr(tag, name):
    """Return the value of one attribute of an XML start tag, or None."""
    match = re.search(r'[\s]%s="([^"]*)"' % re.escape(name), tag)
    return match.group(1) if match else None


def _unescape(text):
    """Resolve the XML entities that can appear in spreadsheet text."""
    for entity, char in _ENTITIES:
        text = text.replace(entity, char)
    text = re.sub(r"&#x([0-9A-Fa-f]+);", lambda m: chr(int(m.group(1), 16)), text)
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    # Ampersand last, so "&amp;lt;" does not become "<".
    return text.replace("&amp;", "&")


def _escape(text):
    """Escape text for use inside an XML element."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _col_index(letters):
    """'A' -> 1, 'Z' -> 26, 'AA' -> 27."""
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index


def _col_letters(index):
    """1 -> 'A', 27 -> 'AA'."""
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def _split_ref(ref):
    """'B12' -> ('B', 12)."""
    match = re.match(r"([A-Z]+)(\d+)$", ref)
    if not match:
        raise ValueError("not a cell reference: %r" % (ref,))
    return match.group(1), int(match.group(2))


# ---------------------------------------------------------------------------
# Workbook navigation
# ---------------------------------------------------------------------------

def _sheet_part(archive, sheet_name):
    """Resolve a sheet's display name to its part name inside the archive.

    Raises KeyError if the workbook has no sheet with that name.
    """
    workbook = archive.read("xl/workbook.xml").decode("utf-8")
    rels = archive.read("xl/_rels/workbook.xml.rels").decode("utf-8")

    rel_id = None
    for tag in _start_tags(workbook, "sheet"):
        if _unescape(_attr(tag, "name") or "") == sheet_name:
            rel_id = _attr(tag, "r:id")
            break
    if rel_id is None:
        raise KeyError("no sheet named %r in %s" % (sheet_name, archive.filename))

    for tag in _start_tags(rels, "Relationship"):
        if _attr(tag, "Id") == rel_id:
            target = _attr(tag, "Target") or ""
            # Targets are usually relative to xl/, occasionally absolute.
            return target.lstrip("/") if target.startswith("/") else "xl/" + target

    raise KeyError("sheet %r has no resolvable target" % (sheet_name,))


def _shared_strings(archive):
    """Return the shared-string table as a list of plain strings."""
    try:
        raw = archive.read("xl/sharedStrings.xml").decode("utf-8")
    except KeyError:
        return []

    strings = []
    for item in re.findall(r"<si\b[^>]*>(.*?)</si>|<si\b[^>]*/>", raw, re.S):
        if not item:
            strings.append("")
            continue
        # Drop phonetic runs, which carry their own <t> and are not content.
        body = re.sub(r"<rPh\b.*?</rPh>", "", item, flags=re.S)
        parts = re.findall(r"<t\b[^>]*>(.*?)</t>|<t\b[^>]*/>", body, re.S)
        strings.append(_unescape("".join(parts)))
    return strings


def _iter_rows(sheet_xml):
    """Yield (row_number, row_xml) for every <row> in document order."""
    for match in re.finditer(r'<row\b[^>]*?r="(\d+)"[^>]*?(?:/>|>.*?</row>)', sheet_xml, re.S):
        yield int(match.group(1)), match.group(0)


def _iter_cells(row_xml):
    """Yield (column_letters, cell_xml) for every <c> in a row."""
    for match in re.finditer(r'<c\b[^>]*?r="([A-Z]+)\d+"[^>]*?(?:/>|>.*?</c>)', row_xml, re.S):
        yield match.group(1), match.group(0)


def _cell_text(cell_xml, strings):
    """Resolve a cell's displayed text, or "" when it holds nothing."""
    cell_type = _attr(cell_xml, "t")

    if cell_type == "inlineStr":
        parts = re.findall(r"<t\b[^>]*>(.*?)</t>", cell_xml, re.S)
        return _unescape("".join(parts))

    value = re.search(r"<v\b[^>]*>(.*?)</v>", cell_xml, re.S)
    if value is None:
        return ""
    raw = value.group(1)

    if cell_type == "s":
        try:
            return strings[int(raw)]
        except (ValueError, IndexError):
            return ""
    return _unescape(raw)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def read_column(path, sheet_name, column, first_row=1):
    """Read one column of a sheet, returning its non-empty values in order.

    Args:
        path: filesystem path to the .xlsx file.
        sheet_name: sheet display name, exactly as shown in Excel.
        column: column letters, e.g. ``"B"``.
        first_row: 1-based row to start at (use 2 to skip a header).

    Returns:
        List of strings — blank cells are skipped, not preserved as "".

    Raises:
        KeyError: if the sheet does not exist.
    """
    with zipfile.ZipFile(path) as archive:
        strings = _shared_strings(archive)
        sheet_xml = archive.read(_sheet_part(archive, sheet_name)).decode("utf-8")

    values = []
    for row_number, row_xml in _iter_rows(sheet_xml):
        if row_number < first_row:
            continue
        for letters, cell_xml in _iter_cells(row_xml):
            if letters != column:
                continue
            text = _cell_text(cell_xml, strings)
            if text != "":
                values.append(text)
            break
    return values


def read_cells(path, sheet_name, refs):
    """Read specific cells, returning ``{ref: text}`` with "" for blanks.

    Args:
        path: filesystem path to the .xlsx file.
        sheet_name: sheet display name.
        refs: iterable of A1-style references, e.g. ``("B3", "E3")``.

    Raises:
        KeyError: if the sheet does not exist.
    """
    wanted = {}
    for ref in refs:
        letters, row_number = _split_ref(ref.upper())
        wanted.setdefault(row_number, {})[letters] = ref

    with zipfile.ZipFile(path) as archive:
        strings = _shared_strings(archive)
        sheet_xml = archive.read(_sheet_part(archive, sheet_name)).decode("utf-8")

    found = {ref: "" for ref in refs}
    for row_number, row_xml in _iter_rows(sheet_xml):
        columns = wanted.get(row_number)
        if not columns:
            continue
        for letters, cell_xml in _iter_cells(row_xml):
            ref = columns.get(letters)
            if ref is not None:
                found[ref] = _cell_text(cell_xml, strings)
    return found


def sheet_names(path):
    """Return the workbook's sheet display names, in tab order."""
    with zipfile.ZipFile(path) as archive:
        workbook = archive.read("xl/workbook.xml").decode("utf-8")
    return [_unescape(_attr(tag, "name") or "") for tag in _start_tags(workbook, "sheet")]


def write_cells(template_path, output_path, sheet_name, values, style_row=None):
    """Copy `template_path` to `output_path`, writing string cells on the way.

    Only the named sheet's XML is rewritten; every other part of the workbook is
    copied through unchanged, so sheets, styling, images and data validations
    all survive.

    Args:
        template_path: .xlsx to use as the source. Never modified.
        output_path: where to write the populated copy.
        sheet_name: sheet display name to write into.
        values: mapping of ``(row_number, column_letters) -> text``. Values are
            written as inline strings; None and "" are skipped.
        style_row: row to copy cell formatting from when a target cell or row
            does not already exist. Defaults to the first row being written.

    Raises:
        KeyError: if the sheet does not exist in the template.
    """
    if not values:
        shutil.copyfile(template_path, output_path)
        return

    targets = {}
    for (row_number, letters), text in values.items():
        if text is None or text == "":
            continue
        targets.setdefault(int(row_number), {})[letters.upper()] = str(text)
    if not targets:
        shutil.copyfile(template_path, output_path)
        return

    if style_row is None:
        style_row = min(targets)

    with zipfile.ZipFile(template_path) as archive:
        part = _sheet_part(archive, sheet_name)
        sheet_xml = archive.read(part).decode("utf-8")
        entries = [(info, archive.read(info.filename)) for info in archive.infolist()]

    updated = _write_sheet_cells(sheet_xml, targets, style_row)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as out:
        for info, data in entries:
            if info.filename == part:
                data = updated.encode("utf-8")
            new_info = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            new_info.compress_type = info.compress_type
            new_info.external_attr = info.external_attr
            new_info.internal_attr = info.internal_attr
            new_info.create_system = info.create_system
            out.writestr(new_info, data)


# ---------------------------------------------------------------------------
# Sheet rewriting
# ---------------------------------------------------------------------------

def _make_cell(letters, row_number, text, style):
    """Build an inline-string cell, carrying `style` when there is one."""
    style_attr = ' s="%s"' % style if style is not None else ""
    space = ' xml:space="preserve"' if text != text.strip() else ""
    return '<c r="%s%d"%s t="inlineStr"><is><t%s>%s</t></is></c>' % (
        letters, row_number, style_attr, space, _escape(text),
    )


def _row_styles(row_xml):
    """Map column letters -> style id for the cells present in a row."""
    return {
        letters: _attr(cell_xml, "s")
        for letters, cell_xml in _iter_cells(row_xml)
    }


def _rewrite_row(row_xml, row_number, cell_values, style_source):
    """Return `row_xml` with `cell_values` written into it.

    Existing cells keep their own formatting; new cells inherit it from the
    matching column of `style_source`, so appended rows still look like the
    template's own rows.
    """
    existing = {letters: cell_xml for letters, cell_xml in _iter_cells(row_xml)}

    open_match = re.match(r"<row\b[^>]*?>", row_xml)
    open_tag = open_match.group(0) if open_match else '<row r="%d">' % row_number
    if open_tag.endswith("/>"):  # self-closing, i.e. an empty row
        open_tag = open_tag[:-2] + ">"

    rebuilt = dict(existing)
    for letters, text in cell_values.items():
        if letters in existing:
            style = _attr(existing[letters], "s")
        else:
            style = style_source.get(letters)
        rebuilt[letters] = _make_cell(letters, row_number, text, style)

    ordered = sorted(rebuilt, key=_col_index)
    body = "".join(rebuilt[letters] for letters in ordered)

    if ordered:
        spans = "%d:%d" % (_col_index(ordered[0]), _col_index(ordered[-1]))
        if _attr(open_tag, "spans") is None:
            open_tag = open_tag[:-1] + ' spans="%s">' % spans
        else:
            open_tag = re.sub(r'(\sspans=")[^"]*"', r'\g<1>%s"' % spans, open_tag)

    return open_tag + body + "</row>"


def _blank_row(row_number, template_open_tag):
    """An empty <row> for `row_number`, based on the template row's attributes."""
    open_tag = template_open_tag
    if open_tag.endswith("/>"):
        open_tag = open_tag[:-2] + ">"
    open_tag = re.sub(r'(\sr=")\d+"', r'\g<1>%d"' % row_number, open_tag)
    return open_tag + "</row>"


def _write_sheet_cells(sheet_xml, targets, style_row):
    """Write `targets` ({row: {col: text}}) into a sheet's XML."""
    data_match = re.search(r"<sheetData\b[^>]*>(.*?)</sheetData>|<sheetData\b[^>]*/>",
                           sheet_xml, re.S)
    if data_match is None:
        raise ValueError("sheet has no <sheetData>")

    rows = dict(_iter_rows(sheet_xml))

    # Formatting to fall back on for cells and rows the template lacks.
    style_source = _row_styles(rows.get(style_row, ""))
    model_open = re.match(r"<row\b[^>]*?>", rows.get(style_row, "") or "")
    model_open_tag = model_open.group(0) if model_open else '<row r="1">'

    for row_number, cell_values in targets.items():
        base = rows.get(row_number) or _blank_row(row_number, model_open_tag)
        rows[row_number] = _rewrite_row(base, row_number, cell_values, style_source)

    body = "".join(rows[number] for number in sorted(rows))
    sheet_xml = sheet_xml[:data_match.start()] + "<sheetData>" + body + "</sheetData>" \
        + sheet_xml[data_match.end():]

    return _widen_dimension(sheet_xml, targets)


def _widen_dimension(sheet_xml, targets):
    """Grow <dimension> so it covers everything that was written."""
    match = re.search(r'<dimension\b[^>]*?ref="([A-Z]+\d+)(?::([A-Z]+\d+))?"[^>]*/?>',
                      sheet_xml)
    if match is None:
        return sheet_xml

    start_col, start_row = _split_ref(match.group(1))
    if match.group(2):
        end_col, end_row = _split_ref(match.group(2))
    else:
        end_col, end_row = start_col, start_row

    max_col = _col_index(end_col)
    max_row = end_row
    for row_number, cell_values in targets.items():
        max_row = max(max_row, row_number)
        for letters in cell_values:
            max_col = max(max_col, _col_index(letters))

    new_ref = "%s%d:%s%d" % (start_col, start_row, _col_letters(max_col), max_row)
    return sheet_xml[:match.start()] + '<dimension ref="%s"/>' % new_ref \
        + sheet_xml[match.end():]
