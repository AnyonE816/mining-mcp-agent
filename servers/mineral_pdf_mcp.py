"""MCP Server 3: mineral-pdf — NI 43-101 矿产资源储量抽取

Tools:
  - extract_resources(pdf_url) → 从 PDF 抽取 Indicated / Inferred 资源量

技术:
  - pdfplumber 表格抽取 (find_tables + extract_table fallback)
  - 关键词定位: 'mineral resource', 'indicated', 'inferred', 'tonnes', 'grade'
  - 结构化输出: category, tonnes(Mt), grade, contained_metal

Transport: stdio
"""

import tempfile
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mineral-pdf")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Safari/605.1.15"
)

# Keywords that signal a page likely contains resource/reserve tables
RESOURCE_KEYWORDS = [
    "mineral resource",
    "mineral reserve",
    "indicated",
    "inferred",
    "measured",
    "proven",
    "probable",
    "tonnes",
    "grade",
    "cut-off",
    "resource estimate",
]


# ---------------------------------------------------------------------------
# Core extraction logic
# ---------------------------------------------------------------------------

async def _download_pdf(url: str) -> bytes:
    """Download PDF from URL into memory."""
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


def _find_resource_pages(pdf) -> list[int]:
    """Return page numbers (0-indexed) likely to contain resource tables."""
    pages = []
    for i, page in enumerate(pdf.pages):
        text = (page.extract_text() or "").lower()
        hits = sum(1 for kw in RESOURCE_KEYWORDS if kw in text)
        if hits >= 2:
            pages.append(i)
    return pages


def _extract_tables_from_pages(pdf, page_nums: list[int]) -> list[dict[str, Any]]:
    """Extract tables from resource-relevant pages using pdfplumber."""
    results = []

    for pn in page_nums:
        page = pdf.pages[pn]

        # Strategy 1: find_tables() — works for bordered tables
        tables = page.find_tables()
        for tbl in tables:
            try:
                df = tbl.to_pandas()
            except Exception:
                continue

            # Clean: strip whitespace, merge multi-line cells
            df = df.map(lambda x: " ".join(str(x).split()) if x is not None else "")

            # Drop fully empty rows
            df = df.dropna(how="all")

            # Convert to list-of-lists for JSON serialization
            rows = [df.columns.tolist()] + df.values.tolist()
            results.append({
                "page": pn + 1,
                "method": "bordered_table",
                "rows": rows,
            })

        # Strategy 2: extract_table() — text-based, catches borderless tables
        if not tables:
            raw = page.extract_table({
                "vertical_strategy": "text",
                "horizontal_strategy": "text",
                "snap_tolerance": 6,
                "join_tolerance": 4,
            })
            if raw and len(raw) > 2:  # need header + at least 2 data rows
                clean = [[(" ".join(str(c).split()) if c else "") for c in row] for row in raw]
                results.append({
                    "page": pn + 1,
                    "method": "text_table",
                    "rows": clean,
                })

    return results


def _parse_resource_rows(tables: list[dict]) -> list[dict[str, Any]]:
    """Try to parse extracted tables into structured resource entries.

    Looks for rows containing category keywords (measured/indicated/inferred)
    and numeric values for tonnes, grade, and contained metal.
    """
    structured = []
    category_kw = {
        "measured": "Measured",
        "indicated": "Indicated",
        "inferred": "Inferred",
        "proven": "Proven",
        "probable": "Probable",
        "m+i": "Measured + Indicated",
        "p+p": "Proven + Probable",
    }

    for tbl in tables:
        for row in tbl["rows"]:
            row_text = " ".join(str(c) for c in row).lower() if row else ""

            # Find which category this row belongs to
            matched_cat = None
            for kw, label in category_kw.items():
                if kw in row_text:
                    matched_cat = label
                    break

            if not matched_cat:
                continue

            # Try to extract numeric values from the row
            # Look for number patterns that could be tonnes (Mt), grade (g/t or %), metal content
            import re

            numbers = re.findall(r"[\d,]+\.?\d*", row_text)
            entry = {
                "category": matched_cat,
                "page": tbl["page"],
                "raw_row": row,
            }

            # Heuristic: first large number is often tonnes, second is grade
            if len(numbers) >= 2:
                try:
                    entry["tonnes_mt"] = float(numbers[0].replace(",", ""))
                except ValueError:
                    pass
                try:
                    entry["grade"] = float(numbers[1].replace(",", ""))
                except ValueError:
                    pass
            if len(numbers) >= 3:
                try:
                    entry["contained_metal"] = float(numbers[2].replace(",", ""))
                except ValueError:
                    pass

            structured.append(entry)

    return structured


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


@mcp.tool()
async def extract_resources(pdf_url: str) -> dict[str, Any]:
    """Extract NI 43-101 mineral resource estimates from a PDF report.

    Downloads the PDF from the given URL, locates pages with resource
    tables, and extracts structured data about Indicated and Inferred
    mineral resources (tonnes, grade, contained metal).

    Args:
        pdf_url: URL to a NI 43-101 technical report PDF
    """
    # --- Download ---
    try:
        pdf_bytes = await _download_pdf(pdf_url)
    except Exception as e:
        return {
            "error": f"Failed to download PDF: {e}",
            "url": pdf_url,
            "tip": "Verify the URL is accessible and points to a PDF file.",
        }

    # --- Parse ---
    import pdfplumber

    try:
        with pdfplumber.open(pdf_bytes) as pdf:
            # Find relevant pages
            resource_pages = _find_resource_pages(pdf)
            if not resource_pages:
                return {
                    "status": "no_resource_pages_found",
                    "url": pdf_url,
                    "total_pages": len(pdf.pages),
                    "message": (
                        "No pages with mineral resource/reserve keywords found. "
                        "The PDF may not be a NI 43-101 report, or the text layer "
                        "may be missing (scanned PDF)."
                    ),
                }

            # Extract tables
            raw_tables = _extract_tables_from_pages(pdf, resource_pages)

            # Parse structured entries
            structured = _parse_resource_rows(raw_tables)

            return {
                "url": pdf_url,
                "total_pages": len(pdf.pages),
                "resource_pages": [p + 1 for p in resource_pages],
                "tables_found": len(raw_tables),
                "resource_entries": structured if structured else [],
                "raw_tables": raw_tables if not structured else [],
                "note": (
                    "Extraction is heuristic-based. Verify values against the original PDF. "
                    "For scanned/image-based PDFs, extraction will fail — use OCR preprocessing."
                ),
            }

    except Exception as e:
        return {
            "error": f"PDF parsing failed: {e}",
            "url": pdf_url,
            "tip": "The file may be corrupted, encrypted, or not a valid PDF.",
        }


if __name__ == "__main__":
    mcp.run(transport="stdio")
