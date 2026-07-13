"""Invoice Parser abstraction (pre-Chunk-7). GenericInvoiceParser.

Consumes OCRDocument, returns InvoiceDocument. Contains NO supplier-specific
logic — no supplier layout config, no per-supplier column mapping, no
database access. Everything here is keyword + relative-position + bounding-
box heuristics that work the same way regardless of which supplier printed
the invoice. Supplier-specific refinement (doc_supplier_layout-driven
column mapping, real header field validation) is Chunk 8/9's job, applied
on top of this parser's output, not inside it.

Region/field detection strategy (never a hardcoded coordinate):
  * Keywords — a small vocabulary of label phrases ("invoice no", "cgst",
    "batch", ...) that are common across invoice layouts in general, not
    tied to any one supplier's template.
  * Relative position — e.g. the supplier block is "everything on page 1
    before the first recognized header/table keyword", not "the top 200
    pixels".
  * Bounding boxes — table rows are grouped by real OCRLine y-overlap
    (same technique ocr/paddle_engine.py uses to merge split words), so
    column layout differences between suppliers don't matter; only which
    lines share a visual row does.

Product table cells: PaddleOCR (see ocr/paddle_engine.py) detects each
table cell as its own OCRLine when cells are spaced apart — so a "row" is
reconstructed here by grouping OCRLines with overlapping y-ranges, then
ordering left-to-right by x1. This is more reliable than trying to split a
single line's text on whitespace, since it operates on real detection
boxes rather than an approximated word split.
"""

import re
from datetime import datetime, timezone
from statistics import median
from typing import Dict, List, Optional, Set, Tuple

from modules.document_extraction.ocr.models import BoundingBox, Confidence, OCRDocument, OCRLine
from modules.document_extraction.parser.base import InvoiceParser
from modules.document_extraction.parser.models import (
    DocumentMetadata,
    GSTSummary,
    InvoiceDocument,
    InvoiceHeader,
    InvoiceProduct,
    InvoiceTotals,
    PageRegion,
    RegionType,
    RowCell,
    SupplierBlock,
)

_FlatLine = Tuple[int, OCRLine]  # (page_no, line)

# --------------------------------------------------------------------------
# Keyword vocabularies (generic — no supplier-specific phrasing)
# --------------------------------------------------------------------------

_HEADER_FIELD_KEYWORDS: Dict[str, List[str]] = {
    "invoice_number": ["invoice no", "invoice number", "inv no", "bill no", "invoice #"],
    "invoice_date": ["invoice date", "inv date", "bill date", "dated"],
    "order_number": ["order no", "po no", "purchase order"],
    "transport": ["transport", "carrier", "lr no", "vehicle no"],
    "salesman": ["salesman", "sales person", "sales rep"],
    "credit_days": ["credit days", "credit period"],
    "irn_number": ["irn"],
    "ack_number": ["ack no", "acknowledgement no", "acknowledgment no"],
    "ack_date": ["ack date", "acknowledgement date", "acknowledgment date"],
}

_FIELD_REGION_TYPE = {
    "invoice_number": RegionType.INVOICE_NUMBER,
    "invoice_date": RegionType.INVOICE_DATE,
}

_INVOICE_TYPE_VOCABULARY = [
    "tax invoice", "credit note", "debit note", "delivery challan",
    "proforma invoice", "retail invoice", "bill of supply",
]

_TOTALS_FIELD_KEYWORDS: Dict[str, List[str]] = {
    "gross_amount": ["gross amount", "gross value"],
    "discount_amount": ["discount amount", "less discount", "trade discount"],
    "scheme_discount": ["scheme discount"],
    "cash_discount": ["cash discount"],
    "taxable_amount": ["taxable amount", "taxable value"],
    "cgst_amount": ["cgst"],
    "sgst_amount": ["sgst"],
    "igst_amount": ["igst"],
    "cess_amount": ["cess"],
    "round_off": ["round off", "round-off", "rounding"],
    "net_amount": ["net amount", "grand total", "invoice total", "total amount"],
    "total_quantity": ["total qty", "total quantity"],
}

_PRODUCT_HEADER_KEYWORDS = {
    "product", "description", "particular", "particulars", "item", "qty",
    "quantity", "batch", "exp", "expiry", "mrp", "rate", "hsn", "pack",
    "amount", "free", "disc",
}

_GST_HEADER_KEYWORDS = {"gst", "taxable", "cgst", "sgst", "igst"}

_TERMINATOR_KEYWORDS = {
    RegionType.TOTALS: [
        "gross amount", "taxable amount", "total amount", "grand total",
        "net amount", "net amt", "disc amt", "tot.o/s", "round off",
        "sub total", "subtotal",
    ],
    RegionType.GST_SECTION: ["hsn summary", "tax summary", "gst summary"],
    RegionType.FOOTER: [
        "terms & conditions", "terms and conditions", "declaration",
        "authorised signatory", "authorized signatory", "e. & o.e", "subject to",
        "bank details", "customer seal", "do not return",
    ],
}

_DL_KEYWORDS = ["dl no", "d.l.no", "dl.no", "dl number", "drug licence", "drug license"]

_GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]\b")
_PHONE_RE = re.compile(r"(?:\+?91[-\s]?)?\b\d{10}\b")
_NUMBER_RE = re.compile(r"[-+]?\d[\d,]*\.?\d*")
_NUMERIC_TOKEN_RE = re.compile(r"^[\d.,/%-]+$")
_MULTISPACE_RE = re.compile(r"\s{2,}")


class GenericInvoiceParser(InvoiceParser):
    _NAME = "GenericInvoiceParser"
    _VERSION = "1.0"

    def parser_name(self) -> str:
        return self._NAME

    def parser_version(self) -> str:
        return self._VERSION

    def parse(self, document: OCRDocument) -> InvoiceDocument:
        flat = _flatten(document)
        consumed: Set[Tuple[int, int]] = set()
        regions: List[PageRegion] = []

        header, header_regions, first_field_pos = self._extract_header(flat, consumed)
        header.invoice_type = self._detect_invoice_type(flat, consumed)
        regions.extend(header_regions)

        totals, totals_regions = self._extract_totals(flat, consumed)
        regions.extend(totals_regions)

        table_start = _find_table_header_end(document)
        products: List[InvoiceProduct] = []
        table_header_cells: List[RowCell] = []
        if table_start is not None:
            products = self._extract_products(document, table_start, consumed)
            regions.extend(p.region for p in products if p.region)
            table_header_cells = _table_header_cells(document, table_start)

        gst_summary, gst_regions = self._extract_gst_summary(document, consumed)
        regions.extend(gst_regions)

        supplier_block = self._extract_supplier_block(
            document, table_start, first_field_pos, consumed,
        )
        if supplier_block and supplier_block.region:
            regions.append(supplier_block.region)

        footer_text, footer_regions = self._extract_footer(flat, consumed)
        regions.extend(footer_regions)

        unassigned_lines = [
            line.text for (page_no, line) in flat
            if (page_no, line.line_no) not in consumed
        ]

        metadata = DocumentMetadata(
            ocr_engine_name=document.engine_name,
            ocr_engine_version=document.engine_version,
            ocr_average_confidence=(
                document.average_confidence.score if document.average_confidence else None
            ),
            page_count=len(document.pages),
            parser_name=self.parser_name(),
            parser_version=self.parser_version(),
            parsed_at=datetime.now(timezone.utc).isoformat(),
        )

        return InvoiceDocument(
            metadata=metadata,
            regions=regions,
            supplier_block=supplier_block,
            header=header,
            totals=totals,
            gst_summary=gst_summary,
            products=products,
            table_header_cells=table_header_cells,
            footer_text=footer_text,
            unassigned_lines=unassigned_lines,
        )

    # ----------------------------------------------------------------
    # Header fields (label keyword -> same-line or next-line value)
    # ----------------------------------------------------------------

    def _extract_header(self, flat, consumed):
        header = InvoiceHeader()
        regions: List[PageRegion] = []
        first_field_pos: Optional[Tuple[int, int]] = None

        for field_name, keywords in _HEADER_FIELD_KEYWORDS.items():
            hit = _find_first_keyword(flat, keywords)
            if hit is None:
                continue
            idx, page_no, line, keyword = hit
            value, value_line = _extract_labeled_value(flat, idx, keyword)
            if not value:
                continue
            setattr(header, field_name, value)
            consumed.add((page_no, line.line_no))
            region_lines = [line.line_no]
            if value_line is not None:
                consumed.add((value_line[0], value_line[1].line_no))
                region_lines.append(value_line[1].line_no)
            regions.append(PageRegion(
                region_type=_FIELD_REGION_TYPE.get(field_name, RegionType.HEADER),
                page_no=page_no, bbox=line.bbox, line_numbers=region_lines,
                matched_keyword=keyword, confidence=Confidence(score=0.6),
            ))
            if first_field_pos is None or (page_no, line.line_no) < first_field_pos:
                first_field_pos = (page_no, line.line_no)

        return header, regions, first_field_pos

    def _detect_invoice_type(self, flat, consumed) -> Optional[str]:
        for page_no, line in flat:
            lowered = line.text.lower()
            for phrase in _INVOICE_TYPE_VOCABULARY:
                if phrase in lowered:
                    consumed.add((page_no, line.line_no))
                    return phrase.title()
        return None

    # ----------------------------------------------------------------
    # Totals
    # ----------------------------------------------------------------

    def _extract_totals(self, flat, consumed):
        totals = InvoiceTotals()
        regions: List[PageRegion] = []

        for field_name, keywords in _TOTALS_FIELD_KEYWORDS.items():
            for page_no, line in flat:
                lowered = line.text.lower()
                matched_keyword = next((kw for kw in keywords if kw in lowered), None)
                if not matched_keyword:
                    continue
                value = _extract_number_after_keyword(line.text, matched_keyword)
                if value is None:
                    continue
                if field_name == "total_quantity":
                    setattr(totals, field_name, value)
                else:
                    setattr(totals, field_name, value)
                consumed.add((page_no, line.line_no))
                regions.append(PageRegion(
                    region_type=RegionType.TOTALS, page_no=page_no, bbox=line.bbox,
                    line_numbers=[line.line_no], matched_keyword=matched_keyword,
                    confidence=Confidence(score=0.6),
                ))
                break  # first matching line wins for this field

        return totals, regions

    # ----------------------------------------------------------------
    # Product table
    #
    # Multi-page invoices from dot-matrix/POS-style printers (the common
    # case here) reprint their full header AND a running-subtotal footer
    # on EVERY page around that page's slice of product rows — there is no
    # single global (start, end) range spanning the whole document. So
    # product rows are collected per page: page `table_start` belongs to
    # uses `table_start`'s line as its local header-end; every later page
    # is checked for its OWN reprinted header cluster (skipped if found,
    # else the whole page is candidate rows — a genuine continuation page
    # with no reprinted boilerplate), and any page's local terminator line
    # (see _TERMINATOR_KEYWORDS) caps that page's rows before its footer.
    # ----------------------------------------------------------------

    def _extract_products(self, document, table_start, consumed) -> List[InvoiceProduct]:
        start_page_no, start_line_no = table_start
        products: List[InvoiceProduct] = []
        line_number = 0

        for page in document.pages:
            if page.page_no < start_page_no:
                continue
            if page.page_no == start_page_no:
                candidate_lines = [l for l in page.lines if l.line_no > start_line_no]
            else:
                local_header = _cluster_end(page.lines, _PRODUCT_HEADER_KEYWORDS)
                candidate_lines = [
                    l for l in page.lines
                    if local_header is None or l.line_no > local_header.line_no
                ]

            footer_line_no = _find_terminator_on_lines(candidate_lines)
            if footer_line_no is not None:
                candidate_lines = [l for l in candidate_lines if l.line_no < footer_line_no]

            for row in _group_into_rows(candidate_lines):
                tokens = _row_tokens(row)
                text_joined = "  ".join(tokens)
                if len(text_joined.strip()) < 3:
                    continue
                line_number += 1
                confidence = Confidence(
                    score=round(sum(l.confidence.score for l in row) / len(row), 4)
                )
                bbox = _union_bbox([l.bbox for l in row])
                for l in row:
                    consumed.add((page.page_no, l.line_no))
                products.append(InvoiceProduct(
                    line_number=line_number,
                    ocr_row_text=text_joined,
                    tokens=tokens,
                    cells=_row_cells(row),
                    product_name_guess=_guess_product_name(tokens),
                    confidence=confidence,
                    region=PageRegion(
                        region_type=RegionType.PRODUCT_TABLE, page_no=page.page_no,
                        bbox=bbox, line_numbers=[l.line_no for l in row],
                        confidence=confidence,
                    ),
                ))
        return products

    # ----------------------------------------------------------------
    # GST slab breakup
    # ----------------------------------------------------------------

    def _extract_gst_summary(self, document, consumed):
        header_pos = None
        for page in document.pages:
            for line in page.lines:
                if _looks_like_gst_header(line.text):
                    header_pos = (page.page_no, line.line_no)
                    break
            if header_pos:
                break
        if header_pos is None:
            return [], []

        end = _find_first_terminator(document, header_pos, region_types=(RegionType.TOTALS, RegionType.FOOTER))
        table_lines = _collect_lines_between(document, header_pos, end)
        by_page: Dict[int, List[OCRLine]] = {}
        for page_no, line in table_lines:
            by_page.setdefault(page_no, []).append(line)

        summaries: List[GSTSummary] = []
        regions: List[PageRegion] = []
        for page_no in sorted(by_page):
            for row in _group_into_rows(by_page[page_no]):
                tokens = _row_tokens(row)
                gst_percent = _first_token_as_percent(tokens[0]) if tokens else None
                if gst_percent is None:
                    continue  # not a slab row — stop treating this page's remaining rows as GST rows
                numbers = [n for n in (_extract_trailing_number(t) for t in tokens[1:]) if n is not None]
                summaries.append(GSTSummary(
                    gst_percent=gst_percent,
                    taxable_amount=numbers[0] if len(numbers) > 0 else None,
                    cgst_amount=numbers[1] if len(numbers) > 1 else None,
                    sgst_amount=numbers[2] if len(numbers) > 2 else None,
                    igst_amount=numbers[3] if len(numbers) > 3 else None,
                    cess_amount=numbers[4] if len(numbers) > 4 else None,
                    total_amount=numbers[-1] if numbers else None,
                ))
                bbox = _union_bbox([l.bbox for l in row])
                for l in row:
                    consumed.add((page_no, l.line_no))
                regions.append(PageRegion(
                    region_type=RegionType.GST_SECTION, page_no=page_no, bbox=bbox,
                    line_numbers=[l.line_no for l in row],
                    confidence=Confidence(score=0.5),
                ))
        return summaries, regions

    # ----------------------------------------------------------------
    # Supplier block — relative position: everything on page 1 before the
    # first recognized header field or product-table header.
    # ----------------------------------------------------------------

    def _extract_supplier_block(self, document, table_start, first_field_pos, consumed):
        if not document.pages:
            return None
        first_page = document.pages[0]

        cutoff_line_no = None
        for pos in (table_start, first_field_pos):
            if pos is not None and pos[0] == first_page.page_no:
                cutoff_line_no = pos[1] if cutoff_line_no is None else min(cutoff_line_no, pos[1])

        block_lines = [
            l for l in first_page.lines
            if cutoff_line_no is None or l.line_no < cutoff_line_no
        ]
        if not block_lines:
            return None

        raw_text = "\n".join(l.text for l in block_lines)
        candidate_gst = _find_gstin(raw_text)
        candidate_dl = _find_dl_number(block_lines)
        candidate_phone = _find_phone(raw_text)
        name_line = _pick_supplier_name_line(block_lines, candidate_gst, candidate_dl, candidate_phone)
        candidate_name = name_line.text

        address_lines = []
        for l in block_lines:
            if l is name_line:
                continue
            lowered = l.text.lower()
            if candidate_gst and candidate_gst in l.text.upper():
                continue
            if candidate_dl and any(kw in lowered for kw in _DL_KEYWORDS):
                continue
            if candidate_phone and candidate_phone in l.text:
                continue
            address_lines.append(l.text)
        candidate_address = "\n".join(address_lines) if address_lines else None

        for l in block_lines:
            consumed.add((first_page.page_no, l.line_no))

        bbox = _union_bbox([l.bbox for l in block_lines])
        return SupplierBlock(
            raw_text=raw_text, candidate_name=candidate_name,
            candidate_gst_number=candidate_gst, candidate_dl_number=candidate_dl,
            candidate_phone=candidate_phone, candidate_address=candidate_address,
            region=PageRegion(
                region_type=RegionType.SUPPLIER_BLOCK, page_no=first_page.page_no,
                bbox=bbox, line_numbers=[l.line_no for l in block_lines],
                confidence=Confidence(score=0.5),
            ),
        )

    # ----------------------------------------------------------------
    # Footer
    # ----------------------------------------------------------------

    def _extract_footer(self, flat, consumed):
        for idx, (page_no, line) in enumerate(flat):
            lowered = line.text.lower()
            if any(kw in lowered for kw in _TERMINATOR_KEYWORDS[RegionType.FOOTER]):
                footer_lines = flat[idx:]
                for p, l in footer_lines:
                    consumed.add((p, l.line_no))
                regions = [PageRegion(
                    region_type=RegionType.FOOTER, page_no=page_no, bbox=line.bbox,
                    line_numbers=[l.line_no for _, l in footer_lines],
                    confidence=Confidence(score=0.5),
                )]
                return "\n".join(l.text for _, l in footer_lines), regions
        return None, []


# --------------------------------------------------------------------------
# Module-level helpers (pure functions, no state)
# --------------------------------------------------------------------------

def _flatten(document: OCRDocument) -> List[_FlatLine]:
    flat: List[_FlatLine] = []
    for page in document.pages:
        for line in page.lines:
            flat.append((page.page_no, line))
    return flat


def _find_first_keyword(flat: List[_FlatLine], keywords: List[str]):
    for idx, (page_no, line) in enumerate(flat):
        lowered = line.text.lower()
        for keyword in keywords:
            if keyword in lowered:
                return idx, page_no, line, keyword
    return None


def _extract_labeled_value(flat: List[_FlatLine], idx: int, keyword: str):
    """"Keyword: value" or "Keyword value" on the same line; falls back to
    the next line's text when the label appears alone (common when OCR
    splits a label and its value onto separate detected lines)."""
    page_no, line = flat[idx]
    lowered = line.text.lower()
    pos = lowered.find(keyword)
    remainder = line.text[pos + len(keyword):].strip(" :.-\t")
    if remainder:
        return remainder, None
    if idx + 1 < len(flat):
        next_page_no, next_line = flat[idx + 1]
        candidate = next_line.text.strip()
        if candidate and not any(candidate.lower().startswith(k) for kws in _HEADER_FIELD_KEYWORDS.values() for k in kws):
            return candidate, (next_page_no, next_line)
    return None, None


def _extract_number_after_keyword(text: str, keyword: str) -> Optional[float]:
    lowered = text.lower()
    pos = lowered.find(keyword)
    if pos == -1:
        return None
    match = _NUMBER_RE.search(text[pos + len(keyword):])
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _extract_trailing_number(text: str) -> Optional[float]:
    matches = _NUMBER_RE.findall(text)
    if not matches:
        return None
    try:
        return float(matches[-1].replace(",", ""))
    except ValueError:
        return None


def _tokenize(text: str) -> Set[str]:
    return set(re.findall(r"[a-zA-Z]+", text.lower()))


# A tightly-typeset invoice's column-header row (e.g. "Loc Code Batch Date
# Exp M.R.P PRODUCT NAME Pack QTY FR Price ...") is frequently detected by
# OCR as many short separate lines rather than one wide line -- stacked
# two-row labels ("Batch" over "Date"), and per-column values spaced far
# enough apart that PaddleOCR's row-merge (see ocr/paddle_engine.py) doesn't
# join them. A single line almost never carries 3+ header keywords on its
# own in that case, so the header block is found as a contiguous *cluster*
# of keyword-bearing lines (small gaps between hits tolerated) that
# together clear a distinct-keyword threshold, rather than requiring any
# one line to clear it alone.
_TABLE_HEADER_MAX_GAP = 6  # lines between consecutive keyword hits still considered the same header cluster
_TABLE_HEADER_MIN_KEYWORDS = 5  # distinct keyword hits required across the cluster to call it a real header


def _cluster_end(lines: List[OCRLine], keyword_vocabulary: Set[str]) -> Optional[OCRLine]:
    """Contiguous cluster of keyword-bearing lines (gaps of up to
    _TABLE_HEADER_MAX_GAP lines tolerated between hits) that together clear
    _TABLE_HEADER_MIN_KEYWORDS distinct hits against keyword_vocabulary.
    Returns the cluster's LAST keyword-bearing line, or None if no cluster
    in `lines` ever reaches the threshold."""
    cluster_last: Optional[OCRLine] = None
    cluster_keywords: Set[str] = set()
    for line in lines:
        hits = _tokenize(line.text) & keyword_vocabulary
        if not hits:
            continue
        if cluster_last is not None and line.line_no - cluster_last.line_no > _TABLE_HEADER_MAX_GAP:
            if len(cluster_keywords) >= _TABLE_HEADER_MIN_KEYWORDS:
                return cluster_last
            cluster_keywords = set()
        cluster_keywords |= hits
        cluster_last = line
    if cluster_last is not None and len(cluster_keywords) >= _TABLE_HEADER_MIN_KEYWORDS:
        return cluster_last
    return None


def _find_table_header_end(document: OCRDocument):
    """First page/line position of a qualifying column-header cluster's
    LAST keyword-bearing line, across all pages in document order. None if
    no page has one."""
    for page in document.pages:
        line = _cluster_end(page.lines, _PRODUCT_HEADER_KEYWORDS)
        if line is not None:
            return page.page_no, line.line_no
    return None


def _find_terminator_on_lines(lines: List[OCRLine]) -> Optional[int]:
    """First line_no among `lines` whose text matches any
    _TERMINATOR_KEYWORDS phrase — a page-scoped counterpart to
    _find_first_terminator, used to cap one page's product rows at that
    page's own reprinted footer/subtotal block (see _extract_products)."""
    for line in lines:
        lowered = line.text.lower()
        for keywords in _TERMINATOR_KEYWORDS.values():
            if any(kw in lowered for kw in keywords):
                return line.line_no
    return None


def _looks_like_gst_header(text: str) -> bool:
    return len(_tokenize(text) & _GST_HEADER_KEYWORDS) >= 2


def _first_token_as_percent(token: str) -> Optional[float]:
    cleaned = token.strip().rstrip("%")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if 0 <= value <= 100 else None


def _find_first_terminator(document: OCRDocument, after_pos, region_types=None):
    """First line strictly after after_pos=(page_no, line_no) matching any
    terminator vocabulary (default: TOTALS, GST_SECTION, FOOTER)."""
    region_types = region_types or (RegionType.TOTALS, RegionType.GST_SECTION, RegionType.FOOTER)
    started = False
    for page in document.pages:
        for line in page.lines:
            if not started:
                if page.page_no == after_pos[0] and line.line_no == after_pos[1]:
                    started = True
                continue
            lowered = line.text.lower()
            for region_type in region_types:
                if any(kw in lowered for kw in _TERMINATOR_KEYWORDS[region_type]):
                    return page.page_no, line.line_no
    return None


def _collect_lines_between(document: OCRDocument, start, end) -> List[_FlatLine]:
    collected: List[_FlatLine] = []
    started = False
    for page in document.pages:
        for line in page.lines:
            if not started:
                if page.page_no == start[0] and line.line_no == start[1]:
                    started = True
                continue
            if end is not None and page.page_no == end[0] and line.line_no == end[1]:
                return collected
            collected.append((page.page_no, line))
    return collected


def _row_tokens(row: List[OCRLine]) -> List[str]:
    """Cell text for one grouped table row. When PaddleOCR detected the
    whole row as a single wide box (common for tightly-typeset tables,
    as opposed to tables with real cell borders producing one box per
    cell), fall back to splitting that one line's text on runs of 2+
    whitespace characters — a generic column-gap proxy, not a supplier-
    specific delimiter."""
    if len(row) == 1:
        parts = [p for p in _MULTISPACE_RE.split(row[0].text.strip()) if p]
        if len(parts) > 1:
            return parts
    return [l.text for l in row]


def _row_cells(row: List[OCRLine]) -> List[RowCell]:
    """One RowCell per WORD of the row, left to right.

    Not one cell per OCR box: a box routinely spans several printed columns
    ("BPB26038301/28 145.26 ELVAS AM 40/5 TAB" arrives from PaddleOCR as a
    single box holding Batch, MRP and Product Name), and a box is the
    smallest thing that can be split back apart. Words are, and the table
    engine regroups them by the column they physically sit under
    (table_engine/geometry_columns.py), so a fused box costs nothing.

    Word boxes are approximations — PaddleOCR has no word segmentation, so
    ocr/paddle_engine.py distributes the box width across its words by
    character count. That's accurate enough to place a word in the right
    column band; it is not accurate enough to trust as a pixel measurement,
    and nothing here does."""
    cells = [
        RowCell(text=word.text, bbox=word.bbox)
        for line in row for word in line.words
    ]
    if not cells:  # an OCR provider that emits no per-word boxes at all
        cells = [RowCell(text=line.text, bbox=line.bbox) for line in row]
    cells.sort(key=lambda c: c.bbox.x1)
    return cells


def _table_header_cells(document: OCRDocument, table_start) -> List[RowCell]:
    """The product table's header words, with geometry — the x anchors every
    data row is then aligned against (table_engine/geometry_columns.py).

    Words, not cells: OCR fuses the header exactly as it fuses the rows ("Pack
    QTY FR Trade Price" comes back as one box), so there is no gap left to
    split those four columns on. Grouping words back into header cells is the
    table engine's job, and it has the one signal that survives fusion — the
    header vocabulary itself.

    A pharma header is also often printed on two stacked lines ("Exp." over
    "Date"), so the whole header band is taken, not a single line."""
    page_no, header_end_line_no = table_start
    page = next((p for p in document.pages if p.page_no == page_no), None)
    if page is None:
        return []

    band_lines = [
        line for line in page.lines
        if 0 <= header_end_line_no - line.line_no <= _TABLE_HEADER_MAX_GAP
        and _tokenize(line.text) & _PRODUCT_HEADER_KEYWORDS
    ]
    if not band_lines:
        return []

    # Padded by half a line: a header cell that carries no keyword of its own
    # ("Loc", "Free", "Value") sits a few pixels above or below the keyword
    # lines that anchored the band, and dropping it would leave its column
    # with no anchor — so the data printed under it would drift into the
    # neighbouring real column.
    padding = 0.5 * median(max(l.bbox.y2 - l.bbox.y1, 1.0) for l in band_lines)
    y_top = min(l.bbox.y1 for l in band_lines) - padding
    y_bottom = max(l.bbox.y2 for l in band_lines) + padding
    in_band = [
        line for line in page.lines
        if y_top <= _y_center(line.bbox) <= y_bottom
    ]

    words = sorted(
        (word for line in in_band for word in line.words),
        key=lambda w: w.bbox.x1,
    )
    return [RowCell(text=word.text, bbox=word.bbox) for word in words]


# A line joins a row if its vertical centre sits within this fraction of a
# median line-height of the row's centre. Big enough to hold a row together
# across the tilt of a hand-held photo (the leftmost and rightmost cells of
# one printed row can sit half a line apart), small enough that the NEXT
# printed row — a full row-pitch away — never qualifies.
_ROW_BAND_TOLERANCE = 0.6


def _group_into_rows(lines: List[OCRLine]) -> List[List[OCRLine]]:
    """Groups OCRLines into visual table rows by vertical centre.

    Each line is one table CELL (PaddleOCR boxes each cell of a printed grid
    separately), so a printed row has to be rebuilt from the cells that share
    its band. Membership is decided against the row's own centre — the median
    of its members' centres — and never against "does this overlap ANY member
    already in the row". That any-member rule chains: one tall cell (a
    two-line product name) overlaps the row below it, which pulls that row's
    cells in, which reach further down again, and a dense invoice table
    collapses into a single 48-cell "row" that no column aligner can make
    sense of. A median centre cannot be dragged that way — it stays on the
    printed row it started on.

    Members are then sorted left-to-right by x1, which is the order the
    column aligner (table_engine) expects."""
    if not lines:
        return []

    median_height = median(max(line.bbox.y2 - line.bbox.y1, 1.0) for line in lines)
    tolerance = _ROW_BAND_TOLERANCE * median_height

    ordered = sorted(lines, key=lambda l: (_y_center(l.bbox), l.bbox.x1))
    rows: List[List[OCRLine]] = [[ordered[0]]]
    centers: List[float] = [_y_center(ordered[0].bbox)]

    for line in ordered[1:]:
        center = _y_center(line.bbox)
        if abs(center - median(centers)) <= tolerance:
            rows[-1].append(line)
            centers.append(center)
        else:
            rows.append([line])
            centers = [center]

    for row in rows:
        row.sort(key=lambda l: l.bbox.x1)
    return rows


def _y_center(box: BoundingBox) -> float:
    return (box.y1 + box.y2) / 2.0


def _union_bbox(boxes: List[BoundingBox]) -> BoundingBox:
    return BoundingBox(
        x1=min(b.x1 for b in boxes), y1=min(b.y1 for b in boxes),
        x2=max(b.x2 for b in boxes), y2=max(b.y2 for b in boxes),
    )


def _guess_product_name(tokens: List[str]) -> Optional[str]:
    candidates = [t for t in tokens if not _NUMERIC_TOKEN_RE.match(t.strip())]
    if not candidates:
        return None
    return max(candidates, key=lambda t: sum(c.isalpha() for c in t))


def _find_gstin(text: str) -> Optional[str]:
    match = _GSTIN_RE.search(text.upper())
    return match.group(0) if match else None


def _find_dl_number(lines: List[OCRLine]) -> Optional[str]:
    for idx, line in enumerate(lines):
        lowered = line.text.lower()
        for keyword in _DL_KEYWORDS:
            pos = lowered.find(keyword)
            if pos == -1:
                continue
            remainder = line.text[pos + len(keyword):].strip(" :.-\t")
            if remainder:
                return remainder
            if idx + 1 < len(lines):
                return lines[idx + 1].text.strip()
    return None


def _find_phone(text: str) -> Optional[str]:
    match = _PHONE_RE.search(text)
    return match.group(0) if match else None


# Some letterheads print a floor/street line ABOVE the business name (seen
# on a real sample invoice: a "<no.>, Ground Floor, ... Road" address line
# printed directly before the company name) -- so the supplier block's
# literal first line isn't a safe assumption for the name. Lines that look
# like an address, or that were already claimed as the GSTIN/DL/phone
# candidate, are skipped in favor of the first remaining line.
_ADDRESS_KEYWORDS = {
    "road", "floor", "street", "nagar", "colony", "layout", "cross",
    "near", "opp", "behind", "state", "district", "taluk", "village",
    "post", "pincode", "pin code", "lane", "extension",
}
_ADDRESS_LEADING_NUMBER_RE = re.compile(r"^\s*\d+\s*[.,]")


def _looks_like_address(text: str) -> bool:
    if _ADDRESS_LEADING_NUMBER_RE.match(text):
        return True
    lowered = text.lower()
    return any(keyword in lowered for keyword in _ADDRESS_KEYWORDS)


def _looks_like_name(text: str) -> bool:
    """Rules out invoice-number-shaped OCR fragments (a duplicate stamp
    of the invoice number, digit-dominant, seen printed near the
    letterhead on a real sample) and short column-header leftovers
    ("ode", from a fragmented "Code") -- a real business name is
    letter-dominant and more than a couple characters."""
    letters = sum(c.isalpha() for c in text)
    digits = sum(c.isdigit() for c in text)
    return letters >= 4 and letters >= digits


def _pick_supplier_name_line(block_lines: List[OCRLine], candidate_gst, candidate_dl, candidate_phone) -> OCRLine:
    for line in block_lines:
        text = line.text
        lowered = text.lower()
        if _looks_like_address(text) or not _looks_like_name(text):
            continue
        if any(phrase in lowered for phrase in _INVOICE_TYPE_VOCABULARY):
            continue
        if candidate_gst and candidate_gst in text.upper():
            continue
        if candidate_dl and any(kw in lowered for kw in _DL_KEYWORDS):
            continue
        if candidate_phone and candidate_phone in text:
            continue
        return line
    return block_lines[0]
