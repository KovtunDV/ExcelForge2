from __future__ import annotations

_DOC_CSS = """
body { font-family: Segoe UI, sans-serif; font-size: 10pt; margin: 8px; line-height: 1.45; }
h1, h2, h3, h4 { margin-top: 1em; margin-bottom: 0.4em; }
h1 { font-size: 1.5em; }
h2 { font-size: 1.3em; border-bottom: 1px solid #ccc; padding-bottom: 0.2em; }
h3 { font-size: 1.15em; }
p { margin: 0.5em 0; }
ul, ol { margin: 0.4em 0 0.4em 1.5em; }
li { margin: 0.2em 0; }
code { font-family: Consolas, monospace; font-size: 0.92em; background: #f4f4f4; padding: 1px 4px; border-radius: 3px; }
pre { font-family: Consolas, monospace; font-size: 0.9em; background: #f4f4f4; padding: 10px; border-radius: 4px; overflow-x: auto; }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; margin: 0.8em 0; width: 100%; }
th, td { border: 1px solid #bbb; padding: 6px 10px; text-align: left; vertical-align: top; }
th { background: #e8e8e8; font-weight: bold; }
tr:nth-child(even) td { background: #fafafa; }
a { color: #1565c0; }
hr { border: none; border-top: 1px solid #ccc; margin: 1em 0; }
strong { font-weight: bold; }
em { font-style: italic; }
"""


def markdown_to_html(markdown_text: str) -> str:
    """Convert Markdown to HTML wrapped with documentation stylesheet."""
    try:
        import markdown2  # type: ignore

        body = markdown2.markdown(
            markdown_text,
            extras=["fenced-code-blocks", "tables", "code-friendly", "header-ids"],
        )
    except Exception:
        import html

        escaped = html.escape(markdown_text)
        body = f"<pre>{escaped}</pre>"
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{_DOC_CSS}</style></head><body>{body}</body></html>"
