"""
architecture_diagram.py - Draws the ASCII architecture diagram in docs/ARCHITECTURE.md
and checks that every border has the same width and every connector lines up.

Run:  python docs/architecture_diagram.py
Then paste the output into docs/ARCHITECTURE.md if the layout changed.
"""

W = 68

def box(lines, width, top=(), bottom=()):
    """A box; `top`/`bottom` = column offsets (inside the box) of arrows in / lines out."""
    t = ["─"] * (width - 2); b = ["─"] * (width - 2)
    for c in top: t[c - 1] = "▼"
    for c in bottom: b[c - 1] = "┬"
    out = ["┌" + "".join(t) + "┐"]
    out += ["│ " + l.ljust(width - 4) + " │" for l in lines]
    out += ["└" + "".join(b) + "┘"]
    return out

def row(boxes, gap=2, indent=0):
    h = max(len(b) for b in boxes)
    boxes = [b + [" " * len(b[0])] * (h - len(b)) for b in boxes]
    return [" " * indent + (" " * gap).join(parts) for parts in zip(*boxes)]

def wires(cols):
    line = [" "] * W
    for c in cols: line[c] = "│"
    return "".join(line).rstrip()

half = (W - 2) // 2                     # two boxes side by side
lc, rc = half // 2, half + 2 + half // 2  # their centre columns
q = [13, 13, 13, 13, 12]                # five boxes at the bottom (gap 1), total = W
qx = [sum(q[:i]) + i for i in range(5)]
qc = [x + w // 2 for x, w in zip(qx, q)]

client_w = 22; cx = (W - client_w) // 2; ccol = cx + client_w // 2
out = []
out += row([box(["Client · UI · eval"], client_w, bottom=[client_w // 2])], indent=cx)
out += [wires([ccol])]
out += box(["api/  FastAPI",
            "/ingest  /jobs  /documents  /ask  /health"], W, top=[ccol], bottom=[lc, rc])
out += [wires([lc, rc])]
out += row([box(["ingest/", "1 ids", "2 pdf_reader", "3 chunker", "4 embeddings", "5 store"],
                half, top=[lc], bottom=[lc]),
            box(["query/", "search", "answer", "", "", ""], half, top=[half // 2], bottom=[half // 2])])
out += [wires([lc, rc])]
out += box(["utils/",
            "llm factory   vectorstore factory   metadata factory",
            "prompts       page_cache            vector_cache       ocr"], W, top=[lc, rc], bottom=qc)
out += [wires(qc)]
out += row([box([n], w, top=[w // 2]) for n, w in zip(["Gemini", "Qdrant", "Postgres", "Tesseract", "Disk"], q)], gap=1)
print("\n".join(out))

# sanity: every full-width line is exactly W characters
full = [l for l in out if l.startswith(("┌", "│", "└")) and len(l) > 40]
assert all(len(l) == W for l in full), {len(l) for l in full}
for i in range(len(out) - 1):
    is_wire_line = set(out[i].strip()) <= {"│", " "}
    for c, ch in enumerate(out[i]):
        if ch == "┬" or (is_wire_line and ch == "│"):
            below = out[i + 1][c] if c < len(out[i + 1]) else " "
            assert below in "│▼", (i, c)
print("\nOK: all box borders same width, every connector lines up")
