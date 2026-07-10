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
        "net amount", "round off", "sub total", "subtotal",
    ],
    RegionType.GST_SECTION: ["hsn summary", "tax summary", "gst summary"],
    RegionType.FOOTER: [
        "terms & conditions", "terms and conditions", "declaration",
        "authorised signatory", "authorized signatory", "e. & o.e", "subject to",
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

        table_start, table_end = self._find_product_table_bounds(document)
        products: List[InvoiceProduct] = []
        if table_start is not None:
            products = self._extract_products(document, table_start, table_end, consumed)
            regions.extend(p.region for p in products if p.region)

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
    # ----------------------------------------------------------------

    def _find_product_table_bounds(self, document: OCRDocument):
        """Returns ((start_page, start_line), (end_page, end_line)) — the
        header row's position and the first terminator line's position
        after it (end is exclusive; None means "to the end of the
        document")."""
        start = None
        for page in document.pages:
            for line in page.lines:
                if _looks_like_table_header(line.text):
                    start = (page.page_no, line.line_no)
                    break
            if start:
                break
        if start is None:
            return None, None

        end = _find_first_terminator(document, start)
        return start, end

    def _extract_products(self, document, start, end, consumed) -> List[InvoiceProduct]:
        table_lines = _collect_lines_between(document, start, end)
        by_page: Dict[int, List[OCRLine]] = {}
        for page_no, line in table_lines:
            by_page.setdefault(page_no, []).append(line)

        products: List[InvoiceProduct] = []
        line_number = 0
        for page_no in sorted(by_page):
            for row in _group_into_rows(by_page[page_no]):
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
                    consumed.add((page_no, l.line_no))
                products.append(InvoiceProduct(
                    line_number=line_number,
                    ocr_row_text=text_joined,
                    tokens=tokens,
                    product_name_guess=_guess_product_name(tokens),
                    confidence=confidence,
                    region=PageRegion(
                        region_type=RegionType.PRODUCT_TABLE, page_no=page_no,
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
        candidate_name = block_lines[0].text

        address_lines = []
        for l in block_lines[1:]:
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


def _looks_like_table_header(text: str) -> bool:
    tokens = set(re.findall(r"[a-zA-Z]+", text.lower()))
    return len(tokens & _PRODUCT_HEADER_KEYWORDS) >= 3


def _looks_like_gst_header(text: str) -> bool:
    tokens = set(re.findall(r"[a-zA-Z]+", text.lower()))
    return len(tokens & _GST_HEADER_KEYWORDS) >= 2


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


def _group_into_rows(lines: List[OCRLine]) -> List[List[OCRLine]]:
    """Groups OCRLines into visual table rows by y-overlap — the same
    technique ocr/paddle_engine.py uses to merge split words, applied here
    to reconstruct rows instead. A candidate joins the current row if it
    y-overlaps any existing member by >=50% of the shorter line's height;
    members are then sorted left-to-right by x1."""
    if not lines:
        return []
    sorted_lines = sorted(lines, key=lambda l: (l.bbox.y1, l.bbox.x1))
    rows: List[List[OCRLine]] = [[sorted_lines[0]]]
    for line in sorted_lines[1:]:
        current_row = rows[-1]
        if any(_y_overlaps(member.bbox, line.bbox) for member in current_row):
            current_row.append(line)
        else:
            rows.append([line])
    for row in rows:
        row.sort(key=lambda l: l.bbox.x1)
    return rows


def _y_overlaps(a: BoundingBox, b: BoundingBox) -> bool:
    shared_height = max(min(a.y2 - a.y1, b.y2 - b.y1), 1)
    overlap = min(a.y2, b.y2) - max(a.y1, b.y1)
    return overlap > shared_height * 0.5


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
