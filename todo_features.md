# Luau Viewer — Roadmap & Engineering Tasks

Prioritized backlog for the NSD parser, extractor, and renderer. Each task is scoped for a senior engineer — includes the "why", acceptance criteria, and key files to touch.

---

## P0 — Bugs

### BUG-1: Return type annotations leak as spurious ActionFlowSteps

Functions with return type annotations like `function lerp(a, b, t): any` produce `: any` as the first action step in the NSD diagram. The fast-path token scanner extracts the body text starting after `)`, but the Luau syntax allows a type annotation between `)` and the first statement. The body text then includes `: any\n...`, and the statement splitter treats the colon-prefixed type as a standalone action.

**Why:** Every typed function in real Luau codebases (Roblox, Moonlite) renders a garbage first step. This is the #1 visual bug.

**Acceptance:**
- Functions with return type annotations render without spurious first steps
- Covers `: Type`, `: Type?`, `: (Type, Type) -> Type`, `: {Type}` annotation forms
- Existing tests still pass

**Key files:** `control_flow_extractor.py` (`_try_scan_function_slice` body text extraction), `_split_top_level_statement_spans`

**Approach:** After extracting the body text from after `)` to before `end`, detect whether the first non-whitespace token is a colon (`:`) followed by a type expression. If so, skip past the type annotation before splitting statements. Alternatively, adjust `_find_matching_end` to start after the type annotation.

---

### BUG-2: Elseif chains lose intermediate branches

`_extract_if_stat` iterates over `elseifClause` entries in a loop but only the last elseif's data survives into `else_steps`. Intermediate `chained` IfFlowStep objects are created but never stored — the loop body either overwrites `else_steps` or hits the `pass` branch (line 872).

**Why:** Multi-way `if/elseif/elseif/else/end` chains silently collapse to `if/else`, losing all intermediate conditions. This is incorrect NSD rendering.

**Acceptance:**
- `if a then ... elseif b then ... elseif c then ... else ... end` produces a properly nested chain of IfFlowStep objects
- Each elseif condition and body is preserved
- Summarization path also handles elseif chains correctly

**Key files:** `control_flow_extractor.py` (visitor `_extract_if_stat`), `_build_summarized_if_step`

**Approach:** Build the elseif chain as nested IfFlowStep objects: each `elseif` becomes an `IfFlowStep` in the `else_steps` of the previous one. The final `else` (if any) becomes the innermost else_steps.

---

### BUG-3: do...end blocks with multiple statements are silently dropped

`_extract_block_as_steps` returns `None` when a block contains more than 1 step. The caller `_extract_stat` then falls through to `ActionFlowStep(context.compact(stat_ctx))`, rendering the entire do-block as one monolithic label.

**Why:** Any `do ... multiple statements ... end` in Luau code disappears from the diagram.

**Acceptance:**
- `do` blocks with any number of statements render as a proper sequence
- `do` blocks are visually distinguishable (optional — a simple sequence is fine)

**Key files:** `control_flow_extractor.py` (`_extract_block_as_steps`, `_extract_stat`)

**Approach:** Remove the `len(steps) == 1` short-circuit. Return a wrapper step (or just inline the steps into the parent sequence). If a dedicated DoFlowStep domain type is undesirable, extract the block's steps and splice them into the parent sequence.

---

### BUG-4: Compact whitespace stripping destroys label readability

`_compact_source_text()` and `_compact_label_text()` use `re.sub(r"\s+", " ", text)` which collapses all whitespace. This removes spaces around binary operators and after keywords, producing unreadable labels like `localpart1=desc.Part1`, `returna+((b-a)*t)`, `self._markerSignals[marker]=Instance.new(...)`.

**Why:** Every NSD diagram with non-trivial code is harder to read than it should be. This is a papercut that affects every user.

**Acceptance:**
- Spaces preserved around `=`, `+`, `-`, `*`, `/`, `..`, `==`, `~=`, `<=`, `>=`, `<`, `>`, `and`, `or`, `not`
- Spaces preserved after keywords: `local`, `return`, `function`, `if`, `while`, `for`, `repeat`, `until`, `else`, `elseif`, `then`, `do`
- Spaces preserved after commas
- Labels remain single-line (newlines still collapsed)

**Key files:** `control_flow_extractor.py` (`_compact_source_text`, `_compact_label_text`, `compact` method on `_ExtractorContext`)

**Approach:** Instead of regex-collapsing all whitespace, use the ANTLR token stream to reconstruct the label from individual tokens with single-space separators. Tokens already have proper boundaries. The token-stream-based `text()` method on `_ExtractorContext` already does this — extend the approach to the compact helpers, or use `token_stream.getText()` with the token range and then collapse only newlines.

---

## P1 — Correctness & Completeness

### FEAT-1: Method call colon syntax extraction

Luau supports `obj:method(args)` which is syntactic sugar for `obj.method(obj, args)`. The current `_extract_container_from_name` handles colon in function declarations (`function Obj:method()`), but the extractor should also recognize method definitions with implicit `self` and annotate the steps accordingly.

**Acceptance:**
- `function Class:method()` extracts container=`Class`, name=`Class:method`
- Steps inside colon-methods that reference `self` render correctly

**Key files:** `control_flow_extractor.py`, `control_flow.py`

---

### FEAT-2: Local variable assignment as action step with proper formatting

Multi-assignment statements like `local a, b, c = 1, 2, 3` and destructuring like `local {x, y} = table` are currently rendered as compacted single-line actions. The formatting should preserve the structure.

**Acceptance:**
- Multi-assignment and destructuring render as readable single-line labels
- Tuple returns like `local ok, err = pcall(fn)` preserve the comma separation

**Key files:** `control_flow_extractor.py` (visitor `visitLocalStat`)

---

### FEAT-3: Anonymous functions / closures decomposition

Closures like `pcall(function() ... end)` or `table.sort(items, function(a, b) ... end)` are rendered as single monolithic action steps. Anonymous functions should be extracted as nested function diagrams or at least decomposed into their constituent steps.

**Why:** Real Luau code heavily uses anonymous functions (event handlers, callbacks, `pcall`, `spawn`). Without decomposition, large chunks of logic are invisible in the NSD.

**Acceptance:**
- Anonymous function bodies are extracted as separate FunctionControlFlow entries (tagged as anonymous)
- OR anonymous function bodies are inlined as action sequences at the call site
- Does not break fast-path optimization for simple functions

**Key files:** `control_flow_extractor.py` (visitor, `_extract_stat`), `control_flow.py` (possible `AnonymousFunctionFlowStep`), `nassi_html_renderer.py`

---

### FEAT-4: Compound assignment operators

Luau supports `+=`, `-=`, `*=`, `/=`, `//=`, `%=`, `^=`, `..=`. These should render as distinct action steps with proper formatting.

**Acceptance:**
- `total += 1` renders as `total += 1` (not mangled)
- All compound operators handled

**Key files:** `control_flow_extractor.py` (visitor `visitCompoundAssignStat`)

---

## P2 — Rendering Improvements

### FEAT-5: Syntax highlighting in action labels

Add optional token-level syntax coloring to action labels and if-conditions. Keywords in blue, strings in green, numbers in orange, operators in purple, comments in muted gray.

**Why:** Monochrome monospace in a dark theme makes it hard to visually scan large NSD diagrams. Syntax highlighting is the single biggest readability win.

**Acceptance:**
- Keywords, strings, numbers, operators, and comments are colorized
- Highlighting is applied to action labels, if-conditions, loop headers, and repeat-until conditions
- Highlighting is optional (flag on the renderer, default on)
- No external JS dependencies — use inline `<span>` elements with CSS classes

**Key files:** `nassi_html_renderer.py` (add `_highlight_luau` method), CSS additions for token colors

**Approach:** Use a lightweight tokenizer (reuse the existing ANTLR lexer or write a simple regex-based one) to split labels into tokens and wrap each in a color-classed span. Alternatively, use Pygments (already a transitive dependency via pytest) with the Lua lexer.

---

### FEAT-6: Collapsible function panels (JavaScript)

Files with many functions (e.g., `init.lua` with 30 functions) produce very long pages. Add collapsible function panels with smooth transitions.

**Acceptance:**
- Each function panel has a clickable header that toggles body visibility
- Smooth CSS transition for expand/collapse
- URL hash navigation: `#function-name` auto-expands and scrolls to the function
- No external JS libraries — vanilla JavaScript, <50 lines

**Key files:** `nassi_html_renderer.py` (add JS to the template, modify header HTML)

---

### FEAT-7: Table of contents / sidebar navigation

For files with 10+ functions, add a sidebar or top-bar navigation listing all functions with click-to-scroll.

**Acceptance:**
- Navigation shows function names with container grouping
- Click scrolls to the function panel
- Active function is highlighted based on scroll position
- Collapses on mobile

**Key files:** `nassi_html_renderer.py`

---

### FEAT-8: Shared CSS for directory bundles

The directory bundle (`nassi-dir`) currently embeds the full ~350-line CSS block (including all 51 depth levels) in every HTML file. Extract CSS to a shared `nsd.css` and reference it via `<link>`.

**Why:** The Moonlite bundle is 250KB across 4 files; deduplicating CSS would cut that by ~40%.

**Acceptance:**
- `nassi-dir` outputs a single `nsd.css` alongside the index
- All per-file HTML files reference it via `<link rel="stylesheet" href="../nsd.css">`
- Only depth levels actually used are included (e.g., if max depth is 3, only emit depth 0-3 CSS)
- Single-file `nassi-file` still embeds CSS inline (for portability)

**Key files:** `nassi_html_renderer.py`, `control_flow.py` (application layer)

---

## P3 — Architecture & DX

### FEAT-9: Source position tracking on steps

Add line/column information to `ControlFlowStep` so that clicking a diagram element can navigate to the source. Render as `data-line` and `data-col` attributes for tooling integration.

**Acceptance:**
- Each step carries `line: int` and `col: int` (optional, for backward compat)
- Rendered as `data-line="42"` attributes on `.ns-node` elements
- Hover tooltip shows source location

**Key files:** `control_flow.py` (add fields to base `ControlFlowStep`), `control_flow_extractor.py` (extract position from ANTLR contexts), `nassi_html_renderer.py` (render data attributes)

---

### FEAT-10: Export to SVG and PNG

Add CLI commands `nassi-svg` and `nassi-png` that render diagrams as standalone SVG or PNG images instead of HTML.

**Acceptance:**
- `nassi-svg` produces valid SVG files viewable in any browser
- `nassi-png` produces PNG screenshots via headless Chrome or CairoSVG
- Both support single-file and directory modes

**Key files:** New renderer in `infrastructure/rendering/`, CLI additions in `presentation/cli/main.py`

---

### FEAT-11: Mermaid flowchart export

Add `nassi-mermaid` command that outputs a Mermaid flowchart representation of the control flow. Useful for embedding in Markdown/GitHub.

**Acceptance:**
- Outputs valid Mermaid syntax
- Handles if/else, loops, repeat-until, for-in, numeric-for
- Single-file and directory modes

**Key files:** New renderer in `infrastructure/rendering/mermaid_renderer.py`

---

### FEAT-12: Incremental parsing and caching

For large codebases, re-parsing unchanged files is wasteful. Add a content-hash-based cache so that only modified files are re-parsed.

**Acceptance:**
- Cache keyed on file path + content hash + grammar version
- `nassi-dir` skips files with valid cache entries
- Cache invalidation when grammar version changes
- Configurable cache directory (default `.luau-viewer-cache/`)

**Key files:** New cache adapter in `infrastructure/`, `control_flow.py` (application layer)

---

## P4 — Nice-to-have

### FEAT-13: Lua 5.1/5.2/5.3/5.4 compatibility mode

The Luau grammar handles Luau-specific constructs (type annotations, compound assignments, string interpolation). Add a mode that gracefully degrades for standard Lua files that may use constructs not in Luau (e.g., `goto`).

### FEAT-14: Dark/light theme toggle

Add a theme switcher button. Light theme with matching color palette.

### FEAT-15: Print-friendly stylesheet

Add `@media print` rules that remove shadows, adjust colors for paper, and paginate at function boundaries.

### FEAT-16: Interactive step highlighting on hover

When hovering over an action step, highlight the corresponding region in a split-pane source code view.
