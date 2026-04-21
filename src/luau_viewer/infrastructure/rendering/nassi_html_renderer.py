"""Render structured control flow as Nassi-Shneiderman HTML."""

from __future__ import annotations

import re
from html import escape
from math import ceil

from luau_viewer.domain.control_flow import (
    ActionFlowStep,
    ClosureFlowStep,
    ControlFlowDiagram,
    ControlFlowStep,
    ForInFlowStep,
    IfFlowStep,
    NumericForFlowStep,
    RepeatUntilFlowStep,
    WhileFlowStep,
)
from luau_viewer.domain.ports import NassiDiagramRenderer

# Luau keywords for syntax highlighting
KEYWORDS = {
    "and",
    "break",
    "do",
    "else",
    "elseif",
    "end",
    "false",
    "for",
    "function",
    "if",
    "in",
    "local",
    "nil",
    "not",
    "or",
    "repeat",
    "return",
    "then",
    "true",
    "until",
    "while",
    "continue",
    "type",
    "export",
    "typeof",
    "declare",
    "const",
    "class",
    "extends",
    "with",
    "extern",
    "read",
    "write",
}

# Luau operators (multi-char first, then single-char)
OPERATORS = [
    "==",
    "~=",
    "<=",
    ">=",
    "...",
    "..=",
    "..",
    "//=",
    "//",
    "->",
    "::",
    "+=",
    "-=",
    "*=",
    "/=",
    "%=",
    "^=",
    "<<",
    ">>",
    "+",
    "-",
    "*",
    "/",
    "%",
    "^",
    "#",
    "&",
    "|",
    "~",
    "<",
    ">",
    "=",
    "(",
    ")",
    "{",
    "}",
    "[",
    "]",
    ";",
    ":",
    ",",
    ".",
]


class HtmlNassiDiagramRenderer(NassiDiagramRenderer):
    def __init__(
        self,
        *,
        enable_syntax_highlight: bool = True,
        use_shared_css: bool = False,
        css_path: str = "nsd.css",
        max_depth_for_css: int = 50,
    ):
        self.enable_syntax_highlight = enable_syntax_highlight
        self.use_shared_css = use_shared_css
        self.css_path = css_path
        self.max_depth_for_css = max_depth_for_css

    def _depth_badge(self, i: int) -> str:
        if i == 0:
            return ""
        if i <= 20:
            return f" {chr(0x2460 + i - 1)}"
        if i <= 35:
            return f" {chr(0x3251 + i - 21)}"
        return f" {chr(0x32B1 + i - 36)}"

    def _depth_css(self) -> str:
        colors = ["blue", "green", "purple", "teal", "amber"]
        rules = []
        for i in range(self.max_depth_for_css):
            c = colors[i % 5]
            rules.append(
                f"      .ns-if-depth-{i}-triangle {{ fill: var(--{c}-dim); stroke: var(--{c}); }}"
            )
            rules.append(f"      .ns-if-depth-{i}-diagonal {{ stroke: var(--{c}); }}")
        return "\n".join(rules)

    def _syntax_token_css(self) -> str:
        return """
      .ns-token {{ }}
      .ns-token.ns-keyword {{ color: var(--blue); }}
      .ns-token.ns-string {{ color: var(--green); }}
      .ns-token.ns-number {{ color: var(--orange); }}
      .ns-token.ns-operator {{ color: var(--purple); }}
      .ns-token.ns-comment {{ color: #6b7280; font-style: italic; }}
"""

    def _toc_css(self) -> str:
        return """
      .toc-sidebar {
        position: fixed;
        top: 0;
        left: 0;
        width: 240px;
        max-height: 100vh;
        overflow-y: auto;
        background: rgba(17, 24, 39, 0.95);
        border-right: 1px solid var(--border);
        padding: 16px 12px;
        font-size: 12px;
        z-index: 10;
      }
      .toc-title {
        font-weight: 600;
        color: var(--text-bright);
        margin-bottom: 8px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
      }
      .toc-list {
        list-style: none;
        margin: 0;
        padding: 0;
      }
      .toc-item {
        margin: 2px 0;
      }
      .toc-link {
        display: block;
        padding: 4px 8px;
        color: var(--muted);
        text-decoration: none;
        border-radius: 4px;
        font-family: var(--mono);
        font-size: 11px;
      }
      .toc-link:hover {
        background: rgba(130,170,255,0.1);
        color: var(--text-bright);
      }
      .toc-link.active {
        background: rgba(130,170,255,0.2);
        color: var(--blue);
        border-left: 2px solid var(--blue);
      }
      .toc-group {
        margin-top: 8px;
        font-weight: 600;
        color: var(--muted);
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
      }

      .viewer-body.with-toc {
        margin-left: 260px;
      }
      @media (max-width: 1100px) {
        .viewer-body.with-toc {
          margin-left: 0;
        }
        .toc-sidebar {
          display: none;
        }
      }
"""

    def _inline_css(self) -> str:
        # Base CSS + depth-specific + syntax highlighting + TOC
        return f"""      :root {{
        /* Palette — editor-first dark */
        --bg:          #0a0f18;
        --bg-accent:   #10182a;
        --surface:     #111827;
        --surface-2:   #172131;
        --surface-3:   #1c2940;
        --surface-4:   #233452;
        --border:      #2b3b59;
        --border-strong: #3f5378;
        --border-soft: #182338;
        --text:        #cfd8f6;
        --text-bright: #f4f7ff;
        --muted:       #8e9bbb;
        --shadow:      0 24px 72px rgba(3, 8, 18, 0.56);

        /* Accent colours */
        --blue:        #82aaff;
        --blue-dim:    #243b69;
        --green:       #a6da95;
        --green-dim:   #163628;
        --red:         #ff93a9;
        --red-dim:     #371925;
        --orange:      #ffb86b;
        --orange-dim:  #37230f;
        --teal:        #56d4dd;
        --teal-dim:    #11343b;
        --purple:      #c4a7ff;
        --purple-dim:  #2a1d41;
        --amber:       #f1ca7a;
        --amber-dim:   #39290f;

        /* Block fills */
        --loop-fill:   #132033;
        --yes-fill:    #102217;
        --no-fill:     #251019;
        --action-fill: var(--surface-2);
        --note-fill:   #101720;

        /* Code font */
        --mono: "JetBrains Mono", "Fira Code", "Cascadia Code", "SF Mono", "Menlo", monospace;
        --ui:   "IBM Plex Sans", -apple-system, "Segoe UI", system-ui, sans-serif;
      }}
      * {{ box-sizing: border-box; margin: 0; padding: 0; }}
      body {{
        font-family: var(--ui);
        font-size: 14px;
        color: var(--text);
        background:
          radial-gradient(circle at top, rgba(130, 170, 255, 0.12), transparent 28%),
          linear-gradient(180deg, var(--bg) 0%, #0c121d 100%);
        padding: 24px;
        min-height: 100vh;
        overflow-x: auto;
        color-scheme: dark;
        -webkit-font-smoothing: antialiased;
        text-rendering: optimizeLegibility;
      }}
      .viewer {{
        width: max-content;
        min-width: min(1200px, calc(100vw - 48px));
        margin: 0 auto;
        border: 1px solid var(--border-strong);
        border-radius: 14px;
        background:
          linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01)),
          var(--surface);
        box-shadow: var(--shadow);
        overflow: hidden;
      }}
      .titlebar {{
        padding: 10px 16px;
        background:
          linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0)),
          var(--surface-3);
        border-bottom: 1px solid var(--border-strong);
        display: flex;
        align-items: center;
        gap: 10px;
      }}
      .titlebar-icon {{
        width: 14px; height: 14px;
        border-radius: 50%;
        background: var(--blue-dim);
        border: 1px solid var(--blue);
        flex-shrink: 0;
      }}
      .titlebar-text {{
        font-size: 13.5px;
        font-weight: 600;
        color: var(--text-bright);
        letter-spacing: 0.01em;
      }}
      .toolbar {{
        padding: 9px 16px;
        border-bottom: 1px solid var(--border-soft);
        background:
          linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0)),
          var(--surface);
        display: flex;
        flex-wrap: wrap;
        gap: 8px 14px;
        align-items: baseline;
      }}
      .toolbar-label {{
        font-size: 10px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--blue);
        background: rgba(130, 170, 255, 0.14);
        border: 1px solid rgba(130, 170, 255, 0.3);
        border-radius: 999px;
        padding: 3px 8px;
        white-space: nowrap;
      }}
      .toolbar-path {{
        font-family: var(--mono);
        font-size: 12px;
        color: var(--muted);
        overflow-wrap: anywhere;
      }}
      .viewer-body {{
        padding: 16px;
        background:
          linear-gradient(180deg, rgba(255,255,255,0.015), rgba(255,255,255,0) 180px),
          var(--bg);
      }}
      .function-panel {{
        margin-bottom: 16px;
        border: 1px solid var(--border);
        border-radius: 10px;
        background: rgba(10, 15, 24, 0.72);
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.02);
        overflow: hidden;
      }}
      .function-panel.collapsed .function-body {{ display: none; }}
      .function-panel:last-child {{ margin-bottom: 0; }}
      .function-head {{
        padding: 12px 16px;
        background:
          linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01)),
          var(--surface-3);
        border-bottom: 1px solid var(--border-strong);
      }}
      .function-title {{
        font-size: 15px;
        font-weight: 600;
        color: var(--text-bright);
        line-height: 1.3;
      }}
      .function-signature {{
        margin-top: 5px;
        font-family: var(--mono);
        font-size: 12px;
        line-height: 1.6;
        color: var(--muted);
        overflow-wrap: anywhere;
        word-break: break-word;
      }}
      .function-body {{
        padding: 12px;
        background:
          linear-gradient(180deg, rgba(255,255,255,0.01), rgba(255,255,255,0)),
          rgba(7, 11, 18, 0.84);
      }}
      .function-body > .ns-sequence {{
        width: max-content;
        min-width: 100%;
      }}
      .ns-sequence {{
        display: flex;
        flex-direction: column;
        width: max-content;
        min-width: 100%;
      }}
      .ns-sequence > .ns-node + .ns-node {{
        margin-top: -1px;
      }}
      .ns-node {{
        border: 1px solid var(--border);
        border-radius: 6px;
        background: var(--action-fill);
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.02);
      }}
      .ns-header,
      .ns-footer {{
        padding: 7px 12px;
        background:
          linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0)),
          var(--blue-dim);
        color: var(--text-bright);
        font-family: var(--mono);
        font-size: 12px;
        font-weight: 500;
        line-height: 1.4;
        border-bottom: 1px solid var(--border-strong);
        overflow-wrap: anywhere;
        word-break: break-word;
      }}
      .ns-footer {{
        border-top: 1px solid var(--border);
        border-bottom: 0;
      }}
      .ns-label,
      .empty,
      .ns-note {{
        padding: 8px 12px;
        background:
          linear-gradient(180deg, rgba(255,255,255,0.015), rgba(255,255,255,0)),
          var(--action-fill);
      }}
      .action-text {{
        display: block;
        font-family: var(--mono);
        font-size: 13px;
        line-height: 1.72;
        color: var(--text-bright);
        letter-spacing: -0.01em;
        font-variant-ligatures: none;
        tab-size: 2;
        white-space: pre-wrap;
        overflow-wrap: anywhere;
      }}
      .ns-loop,
      .ns-repeat  {{ background: var(--loop-fill); }}
      .ns-closure {{ background: var(--purple-dim); border-left: 3px solid var(--purple); }}
      .ns-closure .ns-header {{ background: rgba(196, 167, 255, 0.12); }}
      .ns-closure-signature {{
        padding: 5px 12px;
        font-family: var(--mono);
        font-size: 11px;
        color: var(--purple);
        background: rgba(196, 167, 255, 0.06);
        border-bottom: 1px solid var(--border);
      }}

      /* Left accent stripes */
      .ns-node.ns-loop,
      .ns-node.ns-repeat  {{ border-left: 3px solid var(--blue); }}

      /* Depth tinting */
      .ns-depth-1 > .ns-node {{ background-color: rgba(255,255,255,0.012); }}
      .ns-depth-2 > .ns-node {{ background-color: rgba(255,255,255,0.020); }}
      .ns-depth-3 > .ns-node {{ background-color: rgba(255,255,255,0.028); }}

      .ns-if-cap {{
        border-bottom: 1px solid var(--border);
        line-height: 0;
      }}
      .ns-if-svg {{
        display: block;
        height: auto;
      }}
      .ns-if-triangle {{
        fill: var(--blue-dim);
        stroke: var(--border);
        stroke-width: 1;
      }}
      .ns-if-diagonal {{
        stroke: var(--border);
        stroke-width: 1;
      }}
      .ns-if-condition-fo {{
        overflow: hidden;
      }}
      .ns-if-condition-text {{
        font-family: var(--mono);
        font-size: 13px;
        font-weight: 500;
        color: var(--text-bright);
        text-align: center;
        word-break: break-word;
        overflow-wrap: anywhere;
        line-height: 1.3;
        padding: 4px 8px;
      }}
      .ns-if-label-yes {{
        font-family: var(--mono);
        font-size: 11px;
        font-weight: 700;
        fill: var(--green);
        text-transform: uppercase;
        letter-spacing: 0.06em;
      }}
      .ns-if-label-no {{
        font-family: var(--mono);
        font-size: 11px;
        font-weight: 700;
        fill: var(--red);
        text-transform: uppercase;
        letter-spacing: 0.06em;
      }}
      {self._depth_css()}
      .ns-branches {{
        display: grid;
        grid-template-columns: repeat(2, max-content);
        background: var(--surface-2);
        width: max-content;
        min-width: 100%;
      }}
      .ns-branches-single {{ grid-template-columns: max-content; }}
      .ns-branch {{
        border-left: 2px solid var(--border);
        background: var(--surface-2);
      }}
      .ns-branch-yes {{
        background: rgba(158, 206, 106, 0.08);
      }}
      .ns-branch-no {{
        background: rgba(247, 118, 142, 0.08);
      }}
      .ns-branch-yes > .ns-sequence > .ns-node {{
        background: rgba(158, 206, 106, 0.12);
      }}
      .ns-branch-no > .ns-sequence > .ns-node {{
        background: rgba(247, 118, 142, 0.12);
      }}
      .ns-branch-yes .ns-label,
      .ns-branch-yes .empty,
      .ns-branch-yes .ns-note {{
        background: rgba(158, 206, 106, 0.14);
      }}
      .ns-branch-no .ns-label,
      .ns-branch-no .empty,
      .ns-branch-no .ns-note {{
        background: rgba(247, 118, 142, 0.14);
      }}
      .ns-branch-yes > .ns-branch-title {{
        background: rgba(158, 206, 106, 0.2);
        color: var(--green);
      }}
      .ns-branch-no > .ns-branch-title {{
        background: rgba(247, 118, 142, 0.18);
        color: var(--red);
      }}
      .ns-branch:first-child {{ border-left: 0; }}
      .ns-branch-title {{
        padding: 7px 12px;
        border-bottom: 1px solid var(--border);
        background: rgba(18, 26, 41, 0.92);
        color: var(--muted);
        font-size: 10.5px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.08em;
      }}

      .empty {{
        color: var(--muted);
        font-style: italic;
        font-size: 12px;
        background: rgba(20, 28, 41, 0.92);
      }}
      .ns-note {{
        color: var(--muted);
        font-family: var(--mono);
        font-size: 11px;
        font-style: italic;
        background: var(--note-fill);
        border-top: 1px solid var(--border);
        padding: 8px 12px;
      }}
      .empty-file {{
        padding: 24px;
        color: var(--muted);
      }}

      /* Syntax highlighting tokens */
      {self._syntax_token_css()}

      /* TOC sidebar */
      {self._toc_css()}

      @media (max-width: 800px) {{
        body {{ padding: 12px; }}
        .viewer {{
          width: auto;
          min-width: 0;
        }}
        .viewer-body {{ padding: 8px; }}
        .function-body {{
          padding: 6px;
          overflow-x: auto;
        }}
        .function-body > .ns-sequence,
        .ns-sequence {{
          width: 100%;
          min-width: 0;
        }}
        .ns-branches {{
          width: 100%;
          min-width: 0;
          grid-template-columns: 1fr;
        }}
        .ns-branches-single {{ grid-template-columns: 1fr; }}
        .ns-branch {{
          border-left: 0;
          border-top: 1px solid var(--border);
        }}
        .ns-branch:first-child {{ border-top: 0; }}
       }}
      :root {{
        /* Palette — editor-first dark */
        --bg:          #0a0f18;
        --bg-accent:   #10182a;
        --surface:     #111827;
        --surface-2:   #172131;
        --surface-3:   #1c2940;
        --surface-4:   #233452;
        --border:      #2b3b59;
        --border-strong: #3f5378;
        --border-soft: #182338;
        --text:        #cfd8f6;
        --text-bright: #f4f7ff;
        --muted:       #8e9bbb;
        --shadow:      0 24px 72px rgba(3, 8, 18, 0.56);

        /* Accent colours */
        --blue:        #82aaff;
        --blue-dim:    #243b69;
        --green:       #a6da95;
        --green-dim:   #163628;
        --red:         #ff93a9;
        --red-dim:     #371925;
        --orange:      #ffb86b;
        --orange-dim:  #37230f;
        --teal:        #56d4dd;
        --teal-dim:    #11343b;
        --purple:      #c4a7ff;
        --purple-dim:  #2a1d41;
        --amber:       #f1ca7a;
        --amber-dim:   #39290f;

        /* Block fills */
        --loop-fill:   #132033;
        --yes-fill:    #102217;
        --no-fill:     #251019;
        --action-fill: var(--surface-2);
        --note-fill:   #101720;

        /* Code font */
        --mono: "JetBrains Mono", "Fira Code", "Cascadia Code", "SF Mono", "Menlo", monospace;
        --ui:   "IBM Plex Sans", -apple-system, "Segoe UI", system-ui, sans-serif;
      }}
      * {{ box-sizing: border-box; margin: 0; padding: 0; }}
      body {{
        font-family: var(--ui);
        font-size: 14px;
        color: var(--text);
        background:
          radial-gradient(circle at top, rgba(130, 170, 255, 0.12), transparent 28%),
          linear-gradient(180deg, var(--bg) 0%, #0c121d 100%);
        padding: 24px;
        min-height: 100vh;
        overflow-x: auto;
        color-scheme: dark;
        -webkit-font-smoothing: antialiased;
        text-rendering: optimizeLegibility;
      }}
      .viewer {{
        width: max-content;
        min-width: min(1200px, calc(100vw - 48px));
        margin: 0 auto;
        border: 1px solid var(--border-strong);
        border-radius: 14px;
        background:
          linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01)),
          var(--surface);
        box-shadow: var(--shadow);
        overflow: hidden;
      }}
      .titlebar {{
        padding: 10px 16px;
        background:
          linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0)),
          var(--surface-3);
        border-bottom: 1px solid var(--border-strong);
        display: flex;
        align-items: center;
        gap: 10px;
      }}
      .titlebar-icon {{
        width: 14px; height: 14px;
        border-radius: 50%;
        background: var(--blue-dim);
        border: 1px solid var(--blue);
        flex-shrink: 0;
      }}
      .titlebar-text {{
        font-size: 13.5px;
        font-weight: 600;
        color: var(--text-bright);
        letter-spacing: 0.01em;
      }}
      .toolbar {{
        padding: 9px 16px;
        border-bottom: 1px solid var(--border-soft);
        background:
          linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0)),
          var(--surface);
        display: flex;
        flex-wrap: wrap;
        gap: 8px 14px;
        align-items: baseline;
      }}
      .toolbar-label {{
        font-size: 10px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--blue);
        background: rgba(130, 170, 255, 0.14);
        border: 1px solid rgba(130, 170, 255, 0.3);
        border-radius: 999px;
        padding: 3px 8px;
        white-space: nowrap;
      }}
      .toolbar-path {{
        font-family: var(--mono);
        font-size: 12px;
        color: var(--muted);
        overflow-wrap: anywhere;
      }}
      .viewer-body {{
        padding: 16px;
        background:
          linear-gradient(180deg, rgba(255,255,255,0.015), rgba(255,255,255,0) 180px),
          var(--bg);
      }}
      .function-panel {{
        margin-bottom: 16px;
        border: 1px solid var(--border);
        border-radius: 10px;
        background: rgba(10, 15, 24, 0.72);
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.02);
        overflow: hidden;
      }}
      .function-panel.collapsed .function-body {{ display: none; }}
      .function-panel:last-child {{ margin-bottom: 0; }}
      .function-head {{
        padding: 12px 16px;
        background:
          linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01)),
          var(--surface-3);
        border-bottom: 1px solid var(--border-strong);
      }}
      .function-title {{
        font-size: 15px;
        font-weight: 600;
        color: var(--text-bright);
        line-height: 1.3;
      }}
      .function-signature {{
        margin-top: 5px;
        font-family: var(--mono);
        font-size: 12px;
        line-height: 1.6;
        color: var(--muted);
        overflow-wrap: anywhere;
        word-break: break-word;
      }}
      .function-body {{
        padding: 12px;
        background:
          linear-gradient(180deg, rgba(255,255,255,0.01), rgba(255,255,255,0)),
          rgba(7, 11, 18, 0.84);
      }}
      .function-body > .ns-sequence {{
        width: max-content;
        min-width: 100%;
      }}
      .ns-sequence {{
        display: flex;
        flex-direction: column;
        width: max-content;
        min-width: 100%;
      }}
      .ns-sequence > .ns-node + .ns-node {{
        margin-top: -1px;
      }}
      .ns-node {{
        border: 1px solid var(--border);
        border-radius: 6px;
        background: var(--action-fill);
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.02);
      }}
      .ns-header,
      .ns-footer {{
        padding: 7px 12px;
        background:
          linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0)),
          var(--blue-dim);
        color: var(--text-bright);
        font-family: var(--mono);
        font-size: 12px;
        font-weight: 500;
        line-height: 1.4;
        border-bottom: 1px solid var(--border-strong);
        overflow-wrap: anywhere;
        word-break: break-word;
      }}
      .ns-footer {{
        border-top: 1px solid var(--border);
        border-bottom: 0;
      }}
      .ns-label,
      .empty,
      .ns-note {{
        padding: 8px 12px;
        background:
          linear-gradient(180deg, rgba(255,255,255,0.015), rgba(255,255,255,0)),
          var(--action-fill);
      }}
      .action-text {{
        display: block;
        font-family: var(--mono);
        font-size: 13px;
        line-height: 1.72;
        color: var(--text-bright);
        letter-spacing: -0.01em;
        font-variant-ligatures: none;
        tab-size: 2;
        white-space: pre-wrap;
        overflow-wrap: anywhere;
      }}
      .ns-loop,
      .ns-repeat  {{ background: var(--loop-fill); }}
      .ns-closure {{ background: var(--purple-dim); border-left: 3px solid var(--purple); }}
      .ns-closure .ns-header {{ background: rgba(196, 167, 255, 0.12); }}
      .ns-closure-signature {{
        padding: 5px 12px;
        font-family: var(--mono);
        font-size: 11px;
        color: var(--purple);
        background: rgba(196, 167, 255, 0.06);
        border-bottom: 1px solid var(--border);
      }}

      /* Left accent stripes */
      .ns-node.ns-loop,
      .ns-node.ns-repeat  {{ border-left: 3px solid var(--blue); }}

      /* Depth tinting */
      .ns-depth-1 > .ns-node {{ background-color: rgba(255,255,255,0.012); }}
      .ns-depth-2 > .ns-node {{ background-color: rgba(255,255,255,0.020); }}
      .ns-depth-3 > .ns-node {{ background-color: rgba(255,255,255,0.028); }}

      .ns-if-cap {{
        border-bottom: 1px solid var(--border);
        line-height: 0;
      }}
      .ns-if-svg {{
        display: block;
        height: auto;
      }}
      .ns-if-triangle {{
        fill: var(--blue-dim);
        stroke: var(--border);
        stroke-width: 1;
      }}
      .ns-if-diagonal {{
        stroke: var(--border);
        stroke-width: 1;
      }}
      .ns-if-condition-fo {{
        overflow: hidden;
      }}
      .ns-if-condition-text {{
        font-family: var(--mono);
        font-size: 13px;
        font-weight: 500;
        color: var(--text-bright);
        text-align: center;
        word-break: break-word;
        overflow-wrap: anywhere;
        line-height: 1.3;
        padding: 4px 8px;
      }}
      .ns-if-label-yes {{
        font-family: var(--mono);
        font-size: 11px;
        font-weight: 700;
        fill: var(--green);
        text-transform: uppercase;
        letter-spacing: 0.06em;
      }}
      .ns-if-label-no {{
        font-family: var(--mono);
        font-size: 11px;
        font-weight: 700;
        fill: var(--red);
        text-transform: uppercase;
        letter-spacing: 0.06em;
      }}
      {self._depth_css()}
      .ns-branches {{
        display: grid;
        grid-template-columns: repeat(2, max-content);
        background: var(--surface-2);
        width: max-content;
        min-width: 100%;
      }}
      .ns-branches-single {{ grid-template-columns: max-content; }}
      .ns-branch {{
        border-left: 2px solid var(--border);
        background: var(--surface-2);
      }}
      .ns-branch-yes {{
        background: rgba(158, 206, 106, 0.08);
      }}
      .ns-branch-no {{
        background: rgba(247, 118, 142, 0.08);
      }}
      .ns-branch-yes > .ns-sequence > .ns-node {{
        background: rgba(158, 206, 106, 0.12);
      }}
      .ns-branch-no > .ns-sequence > .ns-node {{
        background: rgba(247, 118, 142, 0.12);
      }}
      .ns-branch-yes .ns-label,
      .ns-branch-yes .empty,
      .ns-branch-yes .ns-note {{
        background: rgba(158, 206, 106, 0.14);
      }}
      .ns-branch-no .ns-label,
      .ns-branch-no .empty,
      .ns-branch-no .ns-note {{
        background: rgba(247, 118, 142, 0.14);
      }}
      .ns-branch-yes > .ns-branch-title {{
        background: rgba(158, 206, 106, 0.2);
        color: var(--green);
      }}
      .ns-branch-no > .ns-branch-title {{
        background: rgba(247, 118, 142, 0.18);
        color: var(--red);
      }}
      .ns-branch:first-child {{ border-left: 0; }}
      .ns-branch-title {{
        padding: 7px 12px;
        border-bottom: 1px solid var(--border);
        background: rgba(18, 26, 41, 0.92);
        color: var(--muted);
        font-size: 10.5px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.08em;
      }}

      .empty {{
        color: var(--muted);
        font-style: italic;
        font-size: 12px;
        background: rgba(20, 28, 41, 0.92);
      }}
      .ns-note {{
        color: var(--muted);
        font-family: var(--mono);
        font-size: 11px;
        font-style: italic;
        background: var(--note-fill);
        border-top: 1px solid var(--border);
        padding: 8px 12px;
      }}
      .empty-file {{
        padding: 24px;
        color: var(--muted);
      }}

      /* Syntax highlighting tokens */
      {self._syntax_token_css()}

      /* TOC sidebar */
      {self._toc_css()}

      @media (max-width: 800px) {{
        body {{ padding: 12px; }}
        .viewer {{
          width: auto;
          min-width: 0;
        }}
        .viewer-body {{ padding: 8px; }}
        .function-body {{
          padding: 6px;
          overflow-x: auto;
        }}
        .function-body > .ns-sequence,
        .ns-sequence {{
          width: 100%;
          min-width: 0;
        }}
        .ns-branches {{
          width: 100%;
          min-width: 0;
          grid-template-columns: 1fr;
        }}
        .ns-branches-single {{ grid-template-columns: 1fr; }}
        .ns-branch {{
          border-left: 0;
          border-top: 1px solid var(--border);
        }}
        .ns-branch:first-child {{ border-top: 0; }}
      }}
"""

    def _highlight_luau(self, text: str) -> str:
        """Apply syntax highlighting to Luau code, returning HTML with span-wrapped tokens."""
        if not self.enable_syntax_highlight:
            return escape(text)

        token_spec = [
            ("STRING", r'"([^"\\]|\\.)*"|\'([^\'\\]|\\.)*\''),
            ("RAWSTRING", r"\[=*\[.*?\]=*\]"),
            ("INTERP", r"`.*?`"),
            ("NUMBER", r"0[xX][0-9a-fA-F_]+|0[bB][01_]+|[\d_]+(\.\d+)?([eE][+-]?\d+)?"),
            ("COMMENT", r"--.*"),
            ("BLOCK_COMMENT", r"--\[=*\[.*?\]=*\]"),
            (
                "OPERATOR",
                r"==|~=|<=|>=|\.{2,3}|\.\.=|//=|//|->|::|\+=|-=|\*=|/=|%=|\^=|<<|>>|[+\-*/%^#&|~<>=:;,.\?@]",
            ),
            (
                "KEYWORD",
                r"\b(?:and|break|do|else|elseif|end|false|for|function|if|in|local|nil|not|or|repeat|return|then|true|until|while|continue|type|export|typeof|declare|const|class|extends|with|extern|read|write)\b",
            ),
            ("NAME", r"[a-zA-Z_]\w*"),
            ("WHITESPACE", r"\s+"),
        ]
        parts = []
        pos = 0
        while pos < len(text):
            matched = False
            for tok_name, pattern in token_spec:
                regex = re.compile(pattern)
                m = regex.match(text, pos)
                if m:
                    value = m.group(0)
                    if tok_name == "WHITESPACE":
                        # Keep whitespace as-is (including spaces)
                        parts.append(escape(value))
                    elif tok_name == "STRING" or tok_name == "RAWSTRING" or tok_name == "INTERP":
                        parts.append(f'<span class="ns-token ns-string">{escape(value)}</span>')
                    elif tok_name == "NUMBER":
                        parts.append(f'<span class="ns-token ns-number">{escape(value)}</span>')
                    elif tok_name == "COMMENT" or tok_name == "BLOCK_COMMENT":
                        parts.append(f'<span class="ns-token ns-comment">{escape(value)}</span>')
                    elif tok_name == "OPERATOR":
                        parts.append(f'<span class="ns-token ns-operator">{escape(value)}</span>')
                    elif tok_name == "KEYWORD":
                        parts.append(f'<span class="ns-token ns-keyword">{escape(value)}</span>')
                    elif tok_name == "NAME":
                        parts.append(f'<span class="ns-token ns-name">{escape(value)}</span>')
                    pos = m.end()
                    matched = True
                    break
            if not matched:
                # No regex matched — emit single char escaped and advance
                parts.append(escape(text[pos]))
                pos += 1
        return "".join(parts)

    def render(self, diagram: ControlFlowDiagram) -> str:
        sections = "".join(self._render_function(function) for function in diagram.functions)
        if not sections:
            sections = '<section class="function-panel"><p class="empty-file">No functions found.</p></section>'

        # Build the TOC sidebar if there are many functions
        toc = self._render_toc(diagram.functions) if len(diagram.functions) >= 10 else ""

        return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Nassi-Shneiderman Control Flow</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
     {'<link rel="stylesheet" href="' + self.css_path + '">' if self.use_shared_css else "<style>"}
     {self._inline_css()}
     {"</style>" if not self.use_shared_css else ""}
     <style>
       /* Collapsible panel overrides (FEAT-6) */
       .function-panel.collapsed .function-body {{ display: block !important; }}
       .function-body {{ overflow: hidden; max-height: 0; opacity: 0; transition: max-height 0.4s ease, opacity 0.3s ease; }}
       .function-panel:not(.collapsed) .function-body {{ max-height: 10000px; opacity: 1; }}
     </style>
  </head>
  <body>
    <div class="viewer">
      <div class="titlebar">
        <div class="titlebar-icon"></div>
        <span class="titlebar-text">Luau Viewer · NSD Viewer</span>
      </div>
      <div class="toolbar">
        <span class="toolbar-label">Nassi-Shneiderman</span>
        <code class="toolbar-path">{escape(diagram.source_location)}</code>
      </div>
      <div class="viewer-body{" " + ("with-toc" if toc else "")}">
        {toc}
        <main class="content">{sections}</main>
      </div>
    </div>
    <script>
      // Collapsible function panels (FEAT-6)
      (function() {{
        const panels = document.querySelectorAll('.function-panel');
        panels.forEach(panel => {{
          const head = panel.querySelector('.function-head');
          const body = panel.querySelector('.function-body');
          if (!head || !body) return;
          head.setAttribute('tabindex', '0');
          head.style.cursor = 'pointer';
          let collapsed = false;
          const toggle = () => {{
            panel.classList.toggle('collapsed');
          }};
          head.addEventListener('click', toggle);
          head.addEventListener('keydown', (e) => {{ if (e.key === 'Enter' || e.key === ' ') {{ e.preventDefault(); toggle(); }} }});
        }});
        // URL hash navigation: auto-expand and scroll to function
        if (window.location.hash) {{
          const id = window.location.hash.slice(1);
          const panel = document.querySelector(`.function-panel[data-function-id="${{id}}"]`);
          if (panel) {{
            panel.classList.remove('collapsed');
            panel.querySelector('.function-body').style.display = '';
            panel.scrollIntoView({{behavior: 'smooth', block: 'center'}});
          }}
        }}
      }})();

      // TOC active highlighting (FEAT-7)
      (function() {{
        const sections = document.querySelectorAll('.function-panel');
        if (sections.length < 10) return;
        const tocLinks = document.querySelectorAll('.toc-link');
        const observer = new IntersectionObserver((entries) => {{
          entries.forEach(entry => {{
            const id = entry.target.getAttribute('data-function-id');
            const link = document.querySelector(`.toc-link[href="#${{id}}"]`);
            if (link && entry.isIntersecting) {{
              link.classList.add('active');
            }} else if (link) {{
              link.classList.remove('active');
            }}
          }});
        }}, {{threshold: 0.5}});
        sections.forEach(s => observer.observe(s));
      }})();
    </script>
  </body>
</html>
"""

    def _render_function(self, function) -> str:
        func_id = re.sub(r"[^a-zA-Z0-9-_]", "_", function.qualified_name)
        return (
            f'<section class="function-panel" data-function-id="{func_id}" id="func-{func_id}">'
            '<div class="function-head">'
            f'<h2 class="function-title">{escape(function.qualified_name)}</h2>'
            f'<div class="function-signature">{escape(function.signature)}</div>'
            "</div>"
            '<div class="function-body">'
            f"{self._render_sequence(function.steps, depth=0)}"
            "</div>"
            "</section>"
        )

    def _render_toc(self, functions) -> str:
        if len(functions) < 10:
            return ""
        items = []
        for function in functions:
            func_id = re.sub(r"[^a-zA-Z0-9-_]", "_", function.qualified_name)
            container = function.container or ""
            if container and container != function.qualified_name.split(".")[0]:
                # Show grouped: container -> name
                display = f"{container} · {function.qualified_name}"
            else:
                display = function.qualified_name
            items.append(
                f'<li class="toc-item"><a class="toc-link" href="#func-{func_id}">{escape(display)}</a></li>'
            )
        return (
            '<nav class="toc-sidebar">'
            '<div class="toc-title">Contents</div>'
            '<ul class="toc-list">' + "".join(items) + "</ul></nav>"
        )

    def _render_sequence(self, steps: tuple[ControlFlowStep, ...], *, depth: int) -> str:
        if not steps:
            return '<div class="empty">No structured steps.</div>'
        rendered = "".join(self._render_step(step, depth=depth) for step in steps)
        return f'<div class="ns-sequence ns-depth-{depth}">{rendered}</div>'

    def _render_step(self, step: ControlFlowStep, *, depth: int) -> str:
        if isinstance(step, ActionFlowStep):
            highlighted = self._highlight_luau(step.label)
            return (
                '<div class="ns-node ns-action">'
                f'<div class="ns-label" aria-label="Action {escape(step.label)}">'
                f'<code class="action-text">{highlighted}</code>'
                "</div>"
                "</div>"
            )
        if isinstance(step, IfFlowStep):
            if step.else_steps:
                else_markup = (
                    '<div class="ns-branch ns-branch-no" aria-label="Else branch">'
                    f"{self._render_sequence(step.else_steps, depth=depth + 1)}"
                    "</div>"
                )
                branches_class = "ns-branches"
                trailing_note = ""
            else:
                else_markup = ""
                branches_class = "ns-branches ns-branches-single"
                trailing_note = '<div class="ns-note">No branch continues after the decision.</div>'

            return (
                '<div class="ns-node ns-if">'
                f"{self._render_if_cap(step.condition, depth=depth)}"
                f'<div class="{branches_class}">'
                '<div class="ns-branch ns-branch-yes" aria-label="Then branch">'
                f"{self._render_sequence(step.then_steps, depth=depth + 1)}"
                "</div>"
                f"{else_markup}"
                "</div>"
                f"{trailing_note}"
                "</div>"
            )
        if isinstance(step, WhileFlowStep):
            return self._render_single_body(
                self._highlight_luau(f"While {step.condition}"), step.body_steps, depth=depth
            )
        if isinstance(step, ForInFlowStep):
            return self._render_single_body(
                self._highlight_luau(f"For {step.header}"), step.body_steps, depth=depth
            )
        if isinstance(step, NumericForFlowStep):
            return self._render_single_body(
                self._highlight_luau(f"For {step.header}"), step.body_steps, depth=depth
            )
        if isinstance(step, RepeatUntilFlowStep):
            return (
                '<div class="ns-node ns-repeat">'
                f"{self._render_header(self._highlight_luau('Repeat'))}"
                f"{self._render_sequence(step.body_steps, depth=depth + 1)}"
                f"{self._render_footer(self._highlight_luau(f'Until {step.condition}'))}"
                "</div>"
            )
        if isinstance(step, ClosureFlowStep):
            return (
                '<div class="ns-node ns-closure">'
                f"{self._render_header(self._highlight_luau(step.call_label))}"
                f'<div class="ns-closure-signature">{escape(step.signature)}</div>'
                f"{self._render_sequence(step.body_steps, depth=depth + 1)}"
                "</div>"
            )
        raise TypeError(f"unsupported step type: {type(step)!r}")

    def _render_single_body(
        self,
        title: str,
        steps: tuple[ControlFlowStep, ...],
        *,
        depth: int,
        css_class: str = "ns-loop",
    ) -> str:
        return (
            f'<div class="ns-node {css_class}">'
            f"{self._render_header(title)}"
            f"{self._render_sequence(steps, depth=depth + 1)}"
            "</div>"
        )

    def _if_cap_geometry(self, condition: str, badge: str) -> tuple[int, int, int, int, int]:
        text = f"{badge} {condition}".strip()
        char_count = max(len(text), 12)
        tokens = [token for token in re.split(r"\s+", text) if token]
        longest_token = max((len(token) for token in tokens), default=char_count)

        content_width = max(
            360,
            min(
                1600,
                max(longest_token * 8 + 48, ceil(char_count / 2) * 7 + 64),
            ),
        )
        svg_width = content_width + 40
        chars_per_line = max(18, int(content_width / 7.4))
        line_count = max(
            1,
            ceil(char_count / chars_per_line),
            ceil(longest_token / chars_per_line),
        )
        text_height = 24 + (line_count - 1) * 17
        split_y = 18 + text_height
        svg_height = split_y + 30
        return svg_width, svg_height, content_width, text_height, split_y

    def _render_if_cap(self, condition: str, *, depth: int = 0) -> str:
        escaped = escape(condition)
        highlighted = self._highlight_luau(condition)
        d = min(depth, 50)
        badge = self._depth_badge(d)
        svg_width, svg_height, content_width, text_height, split_y = self._if_cap_geometry(
            condition,
            badge,
        )
        half_width = svg_width / 2
        yes_x = svg_width / 4
        no_x = svg_width * 0.75
        label_y = svg_height - 8

        return (
            f'<div class="ns-if-cap ns-if-depth-{d}" aria-label="If {escaped}">'
            f'<svg class="ns-if-svg" viewBox="0 0 {svg_width} {svg_height}" '
            f'width="{svg_width}" height="{svg_height}" preserveAspectRatio="xMidYMid meet">'
            f'<polygon points="0,0 {svg_width},0 {half_width},{split_y}" '
            f'class="ns-if-triangle ns-if-depth-{d}-triangle"/>'
            f'<foreignObject x="20" y="6" width="{content_width}" height="{text_height}" '
            'class="ns-if-condition-fo">'
            f'<div xmlns="http://www.w3.org/1999/xhtml" class="ns-if-condition-text">{badge} {highlighted}</div>'
            "</foreignObject>"
            f'<line x1="0" y1="{split_y}" x2="{half_width}" y2="{svg_height}" '
            f'class="ns-if-diagonal ns-if-depth-{d}-diagonal"/>'
            f'<line x1="{svg_width}" y1="{split_y}" x2="{half_width}" y2="{svg_height}" '
            f'class="ns-if-diagonal ns-if-depth-{d}-diagonal"/>'
            f'<text x="{yes_x}" y="{label_y}" text-anchor="middle" class="ns-if-label-yes">Yes</text>'
            f'<text x="{no_x}" y="{label_y}" text-anchor="middle" class="ns-if-label-no">No</text>'
            "</svg>"
            "</div>"
        )

    def _render_header(self, title: str) -> str:
        escaped = escape(title)
        highlighted = self._highlight_luau(title)
        return f'<div class="ns-header" aria-label="{escaped}">{highlighted}</div>'

    def _render_footer(self, title: str) -> str:
        escaped = escape(title)
        highlighted = self._highlight_luau(title)
        return f'<div class="ns-footer" aria-label="{escaped}">{highlighted}</div>'
