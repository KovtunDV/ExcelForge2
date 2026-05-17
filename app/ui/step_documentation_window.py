from __future__ import annotations

from html.parser import HTMLParser
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

from app.docs.loader import get_section_for_step
from app.ui.app_icon import apply_app_icon_to_window


class _HtmlToTkText(HTMLParser):
    """
    Minimal HTML renderer into Tk Text with basic formatting.

    We generate HTML from Markdown (markdown2) and then render common tags:
    h1-h4, p, br, ul/li, strong/em, code/pre, hr.
    """

    def __init__(self, text: tk.Text):
        super().__init__(convert_charrefs=True)
        self.text = text
        self._list_level = 0
        self._in_pre = False
        self._in_code = False
        self._pending_newline = False
        self._in_table = False
        self._in_tr = False
        self._in_td = False
        self._cur_cell: list[str] = []
        self._cur_row: list[str] = []
        self._table_rows: list[list[str]] = []
        self._table_is_header_row: list[bool] = []
        self._cur_row_is_header = False

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        t = tag.lower()
        if t in ("p", "div"):
            self._newline(1)
        elif t == "br":
            self._newline(1)
        elif t in ("h1", "h2", "h3", "h4"):
            self._newline(1)
            self._push_tag(t)
        elif t == "strong":
            self._push_tag("strong")
        elif t in ("em", "i"):
            self._push_tag("em")
        elif t == "ul":
            self._list_level += 1
            self._newline(1)
        elif t == "li":
            self._newline(1)
            indent = "  " * max(0, self._list_level - 1)
            self._insert(f"{indent}- ")
        elif t == "pre":
            self._newline(1)
            self._in_pre = True
            self._push_tag("pre")
        elif t == "code":
            self._in_code = True
            self._push_tag("code")
        elif t == "hr":
            self._newline(1)
            self._insert("---\n")
        elif t == "table":
            self._newline(1)
            self._in_table = True
            self._table_rows = []
            self._table_is_header_row = []
        elif t == "tr" and self._in_table:
            self._in_tr = True
            self._cur_row = []
            self._cur_row_is_header = False
        elif t in ("th", "td") and self._in_table and self._in_tr:
            self._in_td = True
            self._cur_cell = []
            if t == "th":
                self._cur_row_is_header = True

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        t = tag.lower()
        if t in ("h1", "h2", "h3", "h4"):
            self._pop_tag(t)
            self._newline(2)
        elif t == "strong":
            self._pop_tag("strong")
        elif t in ("em", "i"):
            self._pop_tag("em")
        elif t == "ul":
            self._list_level = max(0, self._list_level - 1)
            self._newline(1)
        elif t == "pre":
            self._pop_tag("pre")
            self._in_pre = False
            self._newline(2)
        elif t == "code":
            self._pop_tag("code")
            self._in_code = False
        elif t in ("p", "div"):
            self._newline(2)
        elif t in ("th", "td") and self._in_table and self._in_td:
            self._in_td = False
            cell = " ".join("".join(self._cur_cell).split())
            self._cur_row.append(cell)
        elif t == "tr" and self._in_table and self._in_tr:
            self._in_tr = False
            if self._cur_row:
                self._table_rows.append(self._cur_row)
                self._table_is_header_row.append(bool(self._cur_row_is_header))
        elif t == "table" and self._in_table:
            self._in_table = False
            self._render_table()
            self._newline(2)

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if not data:
            return
        if self._in_pre:
            self._insert(data)
            return
        if self._in_table and self._in_td:
            self._cur_cell.append(data)
            return
        # Collapse whitespace in normal text.
        s = " ".join(data.split())
        if not s:
            return
        if self._pending_newline:
            self._insert("\n")
            self._pending_newline = False
        self._insert(s + (" " if not s.endswith("\n") else ""))

    def _newline(self, n: int) -> None:
        # Defer newline until we actually have content to insert next.
        self._pending_newline = True
        if n > 1:
            self._insert("\n" * (n - 1))

    def _insert(self, s: str) -> None:
        tags = tuple(self.text.tag_names("insert"))
        self.text.insert("end", s, tags)

    def _push_tag(self, tag: str) -> None:
        self.text.mark_set("insert", "end")
        self.text.tag_add(tag, "insert", "insert")

    def _pop_tag(self, tag: str) -> None:
        try:
            self.text.tag_remove(tag, "1.0", "end")
        except tk.TclError:
            pass

    def _render_table(self) -> None:
        if not self._table_rows:
            return
        n_cols = max(len(r) for r in self._table_rows)
        rows = [r + [""] * (n_cols - len(r)) for r in self._table_rows]
        widths = [0] * n_cols
        for r in rows:
            for j, cell in enumerate(r):
                widths[j] = max(widths[j], len(cell))

        def fmt_row(r: list[str]) -> str:
            parts = [r[j].ljust(widths[j]) for j in range(n_cols)]
            return "| " + " | ".join(parts) + " |\n"

        sep = "| " + " | ".join(["-" * w if w > 0 else "-" for w in widths]) + " |\n"

        # Render with monospaced font for alignment.
        self.text.insert("end", fmt_row(rows[0]), ("pre",))
        if self._table_is_header_row and self._table_is_header_row[0]:
            self.text.insert("end", sep, ("pre",))
            for r in rows[1:]:
                self.text.insert("end", fmt_row(r), ("pre",))
        else:
            self.text.insert("end", sep, ("pre",))
            for r in rows[1:]:
                self.text.insert("end", fmt_row(r), ("pre",))


class StepDocumentationWindow(tk.Toplevel):
    def __init__(self, master: tk.Misc, step_type: str, step_title: str = ""):
        super().__init__(master)
        apply_app_icon_to_window(self)
        title = f"Документация: {step_type}"
        if step_title:
            title = f"{title} ({step_title})"
        self.title(title)
        self.geometry("760x560")
        self.minsize(480, 360)

        frame = ttk.Frame(self, padding=8)
        frame.pack(fill="both", expand=True)

        content = get_section_for_step(step_type)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        yscroll = ttk.Scrollbar(frame, orient="vertical")
        self.text = tk.Text(frame, wrap="word", yscrollcommand=yscroll.set)
        yscroll.config(command=self.text.yview)
        self.text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")

        base_font = tkfont.nametofont("TkDefaultFont")
        mono_font = tkfont.nametofont("TkFixedFont")
        self.text.configure(font=base_font)

        # Basic tags
        self.text.tag_configure("strong", font=(base_font.actual("family"), base_font.actual("size"), "bold"))
        self.text.tag_configure("em", font=(base_font.actual("family"), base_font.actual("size"), "italic"))
        self.text.tag_configure("h1", font=(base_font.actual("family"), base_font.actual("size") + 6, "bold"))
        self.text.tag_configure("h2", font=(base_font.actual("family"), base_font.actual("size") + 4, "bold"))
        self.text.tag_configure("h3", font=(base_font.actual("family"), base_font.actual("size") + 2, "bold"))
        self.text.tag_configure("h4", font=(base_font.actual("family"), base_font.actual("size") + 1, "bold"))
        self.text.tag_configure("code", font=mono_font)
        self.text.tag_configure("pre", font=mono_font)

        # Render markdown via markdown2 -> HTML -> Text tags. Fallback: raw markdown.
        try:
            import markdown2  # type: ignore

            html = markdown2.markdown(content, extras=["fenced-code-blocks", "tables"])
            parser = _HtmlToTkText(self.text)
            parser.feed(html)
        except Exception:
            self.text.insert("1.0", content)

        self.text.configure(state="disabled")

        btn_row = ttk.Frame(self, padding=(8, 0, 8, 8))
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="Закрыть", command=self.destroy).pack(side="right")
