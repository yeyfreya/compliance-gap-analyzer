"""
Report → print-ready HTML, for saving as PDF.

Turns a saved markdown report into a single self-contained HTML file styled for print.
Open it in a browser and use Print → Save as PDF.

Deliberately dependency-free: no PDF library, no system packages. The browser is already the
best PDF renderer on the machine, and this keeps the exporter from breaking on a Windows
install of WeasyPrint the day something needs to go out.

Usage:
    python export_pdf.py reports/report_v0.6_20260101_1200_example-use-case.md
    python export_pdf.py <report.md> --title "Compliance Gap Analysis" --for "Client Name"
    python export_pdf.py --latest
"""

import argparse
import glob
import html
import os
import re
import sys
import webbrowser


# ── Markdown → HTML ───────────────────────────────────────────────────────────
# A small converter covering exactly what ANALYSIS_PROMPT and save_report() emit:
# headings, tables, bullets, numbered lists, blockquotes, bold/italic/code, links,
# horizontal rules. Not a general markdown engine — if the report format grows, this
# grows with it.

def _inline(text: str) -> str:
    """Convert inline markdown inside an already-escaped line."""
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'(?<![*\w])\*([^*]+)\*(?!\w)', r'<em>\1</em>', text)
    return text


def _risk_class(cell: str) -> str:
    """Colour-code the risk column so the matrix is scannable at a glance."""
    level = re.sub(r'<[^>]+>', '', cell).strip().upper()
    return f' class="risk-{level.lower()}"' if level in {
        "CRITICAL", "HIGH", "MEDIUM", "LOW"} else ""


def _table(rows: list) -> str:
    """Render a markdown table. rows[1] is the |---|---| separator, which we drop."""
    def cells(row):
        return [_inline(c.strip()) for c in row.strip().strip('|').split('|')]

    head = cells(rows[0])
    body = [cells(r) for r in rows[2:]]

    out = ['<table>', '<thead><tr>']
    out += [f'<th>{c}</th>' for c in head]
    out.append('</tr></thead><tbody>')
    for row in body:
        out.append('<tr>')
        out += [f'<td{_risk_class(c)}>{c}</td>' for c in row]
        out.append('</tr>')
    out.append('</tbody></table>')
    return "\n".join(out)


def markdown_to_html(md: str) -> str:
    """Convert a report's markdown body to HTML."""
    lines = html.escape(md).split('\n')
    out = []
    i = 0
    list_type = None  # 'ul' | 'ol' | None

    def close_list():
        nonlocal list_type
        if list_type:
            out.append(f'</{list_type}>')
            list_type = None

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Table: a pipe row followed by a |---| separator row
        if (stripped.startswith('|') and i + 1 < len(lines)
                and re.match(r'^\s*\|[\s:|-]+\|\s*$', lines[i + 1])):
            close_list()
            block = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                block.append(lines[i])
                i += 1
            out.append(_table(block))
            continue

        if not stripped:
            close_list()
            i += 1
            continue

        if re.match(r'^-{3,}$', stripped) or re.match(r'^\*{3,}$', stripped):
            close_list()
            out.append('<hr>')
            i += 1
            continue

        heading = re.match(r'^(#{1,6})\s+(.*)$', stripped)
        if heading:
            close_list()
            level = len(heading.group(1))
            out.append(f'<h{level}>{_inline(heading.group(2))}</h{level}>')
            i += 1
            continue

        if stripped.startswith('&gt;'):  # blockquote (escaped '>')
            close_list()
            quote = []
            while i < len(lines) and lines[i].strip().startswith('&gt;'):
                quote.append(re.sub(r'^\s*&gt;\s?', '', lines[i]))
                i += 1
            out.append(f'<blockquote>{_inline(" ".join(quote))}</blockquote>')
            continue

        bullet = re.match(r'^[-*]\s+(.*)$', stripped)
        if bullet:
            if list_type != 'ul':
                close_list()
                out.append('<ul>')
                list_type = 'ul'
            out.append(f'<li>{_inline(bullet.group(1))}</li>')
            i += 1
            continue

        numbered = re.match(r'^\d+\.\s+(.*)$', stripped)
        if numbered:
            if list_type != 'ol':
                close_list()
                out.append('<ol>')
                list_type = 'ol'
            out.append(f'<li>{_inline(numbered.group(1))}</li>')
            i += 1
            continue

        close_list()
        out.append(f'<p>{_inline(stripped)}</p>')
        i += 1

    close_list()
    return "\n".join(out)


# ── Page template ─────────────────────────────────────────────────────────────
# Print-first: A4 margins, no page breaks inside tables or gap entries, and headings
# that don't strand themselves at the bottom of a page.

_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  @page {{ size: A4; margin: 18mm 16mm 20mm 16mm; }}

  :root {{
    --ink: #1a1d23;
    --muted: #5c6470;
    --rule: #e3e6ea;
    --accent: #2d5a8e;
    --bg-soft: #f7f9fb;
  }}

  * {{ box-sizing: border-box; }}

  body {{
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, Helvetica, Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.55;
    color: var(--ink);
    max-width: 830px;
    margin: 0 auto;
    padding: 32px 28px 60px;
    background: #fff;
  }}

  .cover {{ border-bottom: 2px solid var(--accent); padding-bottom: 18px; margin-bottom: 26px; }}
  .cover h1 {{ font-size: 21pt; line-height: 1.25; margin: 0 0 6px; color: var(--accent); border: 0; padding: 0; }}
  .cover .subtitle {{ font-size: 11pt; color: var(--muted); margin: 0; }}
  .cover .prepared {{ font-size: 10pt; color: var(--ink); margin: 12px 0 0; font-weight: 600; }}

  h1, h2, h3, h4 {{ line-height: 1.3; break-after: avoid; page-break-after: avoid; }}
  h1 {{ font-size: 17pt; margin: 26px 0 10px; }}
  h2 {{ font-size: 14pt; margin: 24px 0 10px; padding-bottom: 5px; border-bottom: 1px solid var(--rule); }}
  h3 {{ font-size: 12pt; margin: 20px 0 8px; color: var(--accent); }}
  h4 {{ font-size: 11pt; margin: 14px 0 6px; }}

  p {{ margin: 0 0 9px; }}
  ul, ol {{ margin: 0 0 11px; padding-left: 22px; }}
  li {{ margin-bottom: 5px; break-inside: avoid; }}
  a {{ color: var(--accent); text-decoration: none; word-break: break-word; }}
  code {{ font-family: Consolas, "SF Mono", Menlo, monospace; font-size: 9pt;
          background: var(--bg-soft); padding: 1px 4px; border-radius: 3px; }}
  hr {{ border: 0; border-top: 1px solid var(--rule); margin: 22px 0; }}

  blockquote {{
    margin: 12px 0; padding: 10px 14px;
    background: var(--bg-soft); border-left: 3px solid var(--accent);
    color: var(--muted); break-inside: avoid;
  }}

  table {{
    width: 100%; border-collapse: collapse; margin: 12px 0 18px;
    font-size: 9.5pt; break-inside: avoid; page-break-inside: avoid;
  }}
  th {{ background: var(--bg-soft); text-align: left; font-weight: 600;
        padding: 8px 10px; border-bottom: 2px solid var(--rule); }}
  td {{ padding: 8px 10px; border-bottom: 1px solid var(--rule); vertical-align: top; }}

  td.risk-critical, td.risk-high, td.risk-medium, td.risk-low {{
    font-weight: 600; white-space: nowrap;
  }}
  td.risk-critical {{ color: #a8323b; }}
  td.risk-high    {{ color: #b8621b; }}
  td.risk-medium  {{ color: #8a6d15; }}
  td.risk-low     {{ color: #4a7c59; }}

  .fineprint {{
    margin-top: 34px; padding-top: 14px; border-top: 1px solid var(--rule);
    font-size: 8.5pt; line-height: 1.5; color: var(--muted); break-inside: avoid;
  }}

  @media print {{
    body {{ padding: 0; max-width: none; }}
    a {{ color: var(--ink); }}
  }}
</style>
</head>
<body>
<div class="cover">
  <h1>{title}</h1>
  <p class="subtitle">{subtitle}</p>
  {prepared}
</div>
{content}
</body>
</html>
"""


def _split_report(md: str) -> tuple:
    """Separate the generated header block from the report body.

    save_report() writes a metadata header (version, run id, inputs, timing) that belongs
    on screen but not in a document going to a client. Returns (metadata, body).
    """
    parts = md.split('\n---\n', 1)
    if len(parts) == 2 and parts[0].lstrip().startswith('# '):
        return parts[0], parts[1]
    return "", md


def _parse_metadata(header: str) -> dict:
    """Pull **Key:** value pairs out of the report header."""
    return {
        m.group(1).strip().lower(): m.group(2).strip()
        for m in re.finditer(r'^\*\*(.+?):\*\*\s*(.*?)\s*$', header, re.MULTILINE)
    }


def _drop_section(md: str, heading: str) -> str:
    """Remove a `## Heading` section and everything under it, up to the next `##` or rule."""
    pattern = rf'^##\s+{re.escape(heading)}\s*$.*?(?=^##\s|^---\s*$)'
    return re.sub(pattern, '', md, flags=re.MULTILINE | re.DOTALL)


def build_html(md: str, title: str, prepared_for: str | None = None,
               client_ready: bool = False) -> str:
    """Render a full print-ready HTML page from report markdown.

    client_ready drops the "Search Queries Used" section — useful working detail when
    reviewing a run, internal noise in a document going to someone else. Sources always
    stay: they are how the reader checks the work.
    """
    header, body = _split_report(md)
    meta = _parse_metadata(header)

    if client_ready:
        body = _drop_section(body, "Search Queries Used")

    bits = [b for b in (meta.get('industry'), meta.get('technology')) if b]
    subtitle = " · ".join(bits) if bits else "Regulatory gap analysis"
    if meta.get('generated'):
        subtitle += f" · {meta['generated'].split()[0]}"

    prepared = (f'<p class="prepared">Prepared for {html.escape(prepared_for)}</p>'
                if prepared_for else "")

    return _TEMPLATE.format(
        title=html.escape(title),
        subtitle=html.escape(subtitle),
        prepared=prepared,
        content=markdown_to_html(body.strip()),
    )


def _latest_report(reports_dir: str) -> str:
    """Most recently modified generated report."""
    matches = glob.glob(os.path.join(reports_dir, "report_v*.md"))
    if not matches:
        sys.exit(f"No generated reports found in {reports_dir}")
    return max(matches, key=os.path.getmtime)


def main(argv: list) -> None:
    parser = argparse.ArgumentParser(
        prog="python export_pdf.py",
        description="Turn a saved report into print-ready HTML. Open it, then Print → Save as PDF.",
    )
    parser.add_argument("report", nargs="?", help="path to the report markdown file")
    parser.add_argument("--latest", action="store_true",
                        help="use the most recent report in reports/")
    parser.add_argument("--title", default="Compliance Gap Analysis",
                        help="document title on the cover")
    parser.add_argument("--for", dest="prepared_for",
                        help='name on the "Prepared for" line')
    parser.add_argument("--client-ready", action="store_true",
                        help="drop the internal search-queries section (sources are kept)")
    parser.add_argument("--output", help="where to write the HTML (default: alongside the report)")
    parser.add_argument("--no-open", action="store_true", help="don't open a browser")
    args = parser.parse_args(argv)

    here = os.path.dirname(os.path.abspath(__file__))

    if args.latest:
        report_path = _latest_report(os.path.join(here, "reports"))
    elif args.report:
        report_path = args.report
    else:
        parser.error("give a report path, or --latest")

    if not os.path.isfile(report_path):
        sys.exit(f"Report not found: {report_path}")

    with open(report_path, "r", encoding="utf-8") as f:
        md = f.read()

    out_path = args.output or os.path.splitext(report_path)[0] + ".html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(build_html(md, args.title, args.prepared_for, args.client_ready))

    out_path = os.path.abspath(out_path)
    print(f"\n📄 Print-ready HTML: {out_path}")
    print("   Open it, then Print → Destination: Save as PDF → Margins: Default.")

    if not args.no_open:
        webbrowser.open(f"file:///{out_path.replace(os.sep, '/')}")


if __name__ == "__main__":
    main(sys.argv[1:])
