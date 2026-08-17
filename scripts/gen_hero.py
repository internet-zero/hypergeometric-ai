"""Generate assets/hero.svg — animated terminal for the hypergeometric-ai README.

Same technique as the profile README terminal: SMIL clip-path typing reveal,
staged <set> reveals, GitHub-dark palette, plays once and freezes.
"""

CW = 9  # char width @ font-size 15 monospace
FG = "#e6edf3"
DIM = "#8b949e"
GREEN = "#3fb950"
BLUE = "#58a6ff"
ORANGE = "#d29922"
CYAN = "#79c0ff"
PURPLE = "#d2a8ff"
BG = "#0d1117"
PANEL = "#161b22"
BORDER = "#30363d"


def type_cmd(cid: str, x: int, y: int, text: str, begin: float, dur: float) -> tuple[str, str]:
    """Return (clipPath def, text element) for a typewriter reveal."""
    n = len(text)
    widths = ";".join(str(i * CW) for i in range(n + 1))
    clip = (
        f'<clipPath id="{cid}"><rect x="{x}" y="{y - 15}" width="0" height="22">'
        f'<animate attributeName="width" values="{widths}" calcMode="discrete" '
        f'begin="{begin}s" dur="{dur}s" fill="freeze"/></rect></clipPath>'
    )
    esc = text.replace("&", "&amp;").replace("<", "&lt;")
    body = (
        f'<g clip-path="url(#{cid})"><text x="{x}" y="{y}" fill="{FG}" '
        f'textLength="{n * CW}" lengthAdjust="spacing">{esc}</text></g>'
    )
    return clip, body


def reveal(y: int, begin: float, spans: list[tuple[str, str]], x: int = 28) -> str:
    """A line of colored tspans that appears at `begin`."""
    parts = "".join(
        f'<tspan fill="{color}">{t.replace("&", "&amp;").replace("<", "&lt;")}</tspan>'
        for color, t in spans
    )
    return (
        f'<text x="{x}" y="{y}" opacity="0">{parts}'
        f'<set attributeName="opacity" to="1" begin="{begin}s" fill="freeze"/></text>'
    )


CMD = "hypergeometric --prompt agent.txt --rules rules.yaml"

clip, cmd_body = type_cmd("t0", 46, 82, CMD, 0.4, 1.6)

rows = [
    # (rule, a, b, verdict, color, note, begin)
    ("R1-json-contract", "98 / 41", "99 / 96", "DELETE", BLUE, "dead weight", 3.4),
    ("R2-export-filter", "97 / 22", "71 / 19", "REWRITE", ORANGE, "regression", 3.9),
    ("R3-missing-data", "93 / 55", "95 / 61", "KEEP", GREEN, "load-bearing", 4.4),
    ("planted-redundant", "control", "control", "DELETE ✓", GREEN, "", 4.9),
    ("planted-load-bearing", "control", "control", "KEEP ✓", GREEN, "", 5.2),
]

# SVG collapses whitespace runs, so columns get explicit x positions.
COL_RULE, COL_A, COL_B, COL_V, COL_NOTE = 28, 262, 392, 522, 646


def row_line(y: int, begin: float, cells: list[tuple[int, str, str]]) -> str:
    texts = "".join(
        f'<text x="{x}" y="{y}" fill="{color}">'
        f"{t.replace('&', '&amp;').replace('<', '&lt;')}</text>"
        for x, color, t in cells
    )
    return (
        f'<g opacity="0">{texts}'
        f'<set attributeName="opacity" to="1" begin="{begin}s" fill="freeze"/></g>'
    )


header = row_line(
    186,
    3.2,
    [
        (COL_RULE, DIM, "Rule"),
        (COL_A, DIM, "A with/wo"),
        (COL_B, DIM, "B with/wo"),
        (COL_V, DIM, "Verdict on B"),
    ],
)

row_els = []
y = 214
for rule, a, b, verdict, color, note, begin in rows:
    cells = [
        (COL_RULE, FG, rule),
        (COL_A, DIM, a),
        (COL_B, DIM, b),
        (COL_V, color, verdict),
    ]
    if note:
        cells.append((COL_NOTE, DIM, note))
    row_els.append(row_line(y, begin, cells))
    y += 27

svg = f"""<svg width="860" height="600" viewBox="0 0 860 600" xmlns="http://www.w3.org/2000/svg" font-family="ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace" font-size="15">
  <defs>
    {clip}
  </defs>

  <!-- window -->
  <rect x="1" y="1" width="858" height="598" rx="12" fill="{BG}" stroke="{BORDER}" stroke-width="1.5"/>
  <circle cx="26" cy="24" r="7" fill="#ff5f57"/>
  <circle cx="48" cy="24" r="7" fill="#febc2e"/>
  <circle cx="70" cy="24" r="7" fill="#28c840"/>
  <text x="430" y="29" text-anchor="middle" fill="{DIM}" font-size="13">hypergeometric — migration grid</text>
  <line x1="1" y1="44" x2="859" y2="44" stroke="#21262d"/>

  <!-- typed command -->
  <text x="28" y="82" fill="{GREEN}" opacity="0">$<set attributeName="opacity" to="1" begin="0.15s" fill="freeze"/></text>
  {cmd_body}
  <rect x="46" y="68" width="9" height="18" fill="{FG}" opacity="0"><set attributeName="opacity" to="0.85" begin="0.15s"/><animate attributeName="x" values="{';'.join(str(46 + i * CW) for i in range(len(CMD) + 1))}" calcMode="discrete" begin="0.4s" dur="1.6s" fill="freeze"/><set attributeName="opacity" to="0" begin="2.2s" fill="freeze"/></rect>

  {reveal(114, 2.3, [(DIM, "plan: 5 rules (3 real + 2 planted) x 30 probes x 2 arms x 2 models = 600 calls")])}
  {reveal(140, 2.8, [(DIM, "generating probes... running grid on "), (CYAN, "model-A"), (DIM, " vs "), (CYAN, "model-B"), (DIM, " ...")])}

  <!-- grid header -->
  {header}
  <line x1="28" y1="196" x2="832" y2="196" stroke="#21262d" opacity="0"><set attributeName="opacity" to="1" begin="3.2s" fill="freeze"/></line>
  {chr(10).join('  ' + r for r in row_els)}

  {reveal(366, 5.7, [(DIM, "controls sane · Wilson 95% CI · exact McNemar "), (CYAN, "p = 0.012"), (DIM, " · BH-corrected")])}

  <!-- math panel -->
  <g opacity="0">
    <set attributeName="opacity" to="1" begin="6.3s" fill="freeze"/>
    <rect x="28" y="394" width="804" height="176" rx="8" fill="{PANEL}" stroke="{BORDER}"/>
    <text x="48" y="428" fill="{GREEN}"># why ~200 probes — no claim without the math</text>
  </g>
  {reveal(464, 6.7, [(FG, "P[miss | p≥10%] = (1−p)ⁿ ≤ 10⁻⁹   ⇒   n ≥ ln 10⁻⁹ / ln 0.9 ≈ "), (PURPLE, "197 → 200")], x=48)}
  {reveal(498, 7.1, [(FG, "P[miss all] = C(90,84) / C(100,84) ≈ "), (PURPLE, "4.6×10⁻¹⁰"), (DIM, "   (hypergeometric: N=100, K=10, n=84)")], x=48)}
  {reveal(532, 7.5, [(FG, "rule of three: 200 clean probes ⇒ violation rate "), (PURPLE, "≤ 1.5% @ 95%"), (DIM, "  confidence")], x=48)}
  {reveal(556, 7.9, [(DIM, "certified, not vibed — DESIGN.md §2.9")], x=48)}
</svg>
"""

with open("assets/hero.svg", "w") as f:
    f.write(svg)
print(f"written: {len(svg)} bytes")
