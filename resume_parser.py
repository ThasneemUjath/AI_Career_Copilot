import re
import pymupdf as fitz

BULLET_RE = re.compile(r"^[^\w\s(\[{\"'“‘]{1,2}\s+")


def _get_lines(page):
    lines = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            text = "".join(span["text"] for span in line["spans"]).strip()
            if text:
                x0, y0, x1, y1 = line["bbox"]
                lines.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "text": text})
    return lines


def _side(line, mid):
    if line["x0"] >= mid - 5:
        return "R"
    if line["x1"] <= mid + 5:
        return "L"
    return "F"  # full width: crosses the middle


def _merge_rows(lines):
    """Join pieces on the same row, sort top to bottom, and detect bullet markers."""
    lines = sorted(lines, key=lambda l: ((l["y0"] + l["y1"]) / 2, l["x0"]))
    rows = []
    for l in lines:
        c = (l["y0"] + l["y1"]) / 2
        if rows and abs(c - rows[-1]["c"]) < 3:
            rows[-1]["parts"].append(l)
            rows[-1]["y1"] = max(rows[-1]["y1"], l["y1"])
        else:
            rows.append({"c": c, "y0": l["y0"], "y1": l["y1"], "parts": [l]})

    out = []
    for r in rows:
        r["parts"].sort(key=lambda p: p["x0"])
        texts = [p["text"] for p in r["parts"]]
        bullet = False
        first = texts[0].strip()
        # case 1: the bullet symbol is its own piece on the row
        if len(texts) > 1 and len(first) <= 2 and not any(ch.isalnum() for ch in first):
            bullet = True
            texts = texts[1:]
        text = " ".join(texts).strip()
        # case 2: the bullet symbol is the first character of the text
        if not bullet and BULLET_RE.match(text):
            bullet = True
            text = BULLET_RE.sub("", text, count=1).strip()
        out.append({"y0": r["y0"], "y1": r["y1"], "text": text, "bullet": bullet})
    return out

def _find_gutter(lines, width):
    """x position crossed by the fewest lines, searched in the middle 70% of the page."""
    best_x, best_n = None, len(lines) + 1
    for x in range(int(width * 0.15), int(width * 0.85), 2):
        n = sum(1 for l in lines if l["x0"] + 2 < x < l["x1"] - 2)
        if n < best_n:
            best_x, best_n = x, n
    return best_x


def _page_text(page):
    lines = _get_lines(page)
    if not lines:
        return ""

    mid = _find_gutter(lines, page.rect.width) or page.rect.width / 2
    sides = [_side(l, mid) for l in lines]
    n_left, n_right, n_full = sides.count("L"), sides.count("R"), sides.count("F")
    two_columns = n_left >= 8 and n_right >= 8 and n_full / len(lines) < 0.2

    if not two_columns:
        result = _merge_rows(lines)
    else:
        ordered = sorted(lines, key=lambda l: (l["y0"], l["x0"]))
        result, left, right = [], [], []
        prev_full = False

        def flush():
            result.extend(_merge_rows(left))
            result.extend(_merge_rows(right))
            left.clear()
            right.clear()

        for l in ordered:
            s = _side(l, mid)
            if s == "F":
                if not prev_full:
                    # a heading sitting just above a full-width block stays attached to it
                    near = lambda x: x["y1"] >= l["y0"] - 25
                    pull_l = [x for x in left if near(x)]
                    pull_r = [x for x in right if near(x)]
                    left[:] = [x for x in left if not near(x)]
                    right[:] = [x for x in right if not near(x)]
                    flush()
                    result.extend(_merge_rows(pull_l))
                    result.extend(_merge_rows(pull_r))
                result.extend(_merge_rows([l]))
                prev_full = True
            else:
                prev_full = False
                (left if s == "L" else right).append(l)
        flush()

    # typical line spacing of this resume (median gap), used to detect a new block
    gaps = [result[i + 1]["y0"] - result[i]["y1"]
            for i in range(len(result) - 1)
            if result[i + 1]["y0"] > result[i]["y0"]]
    gaps = sorted(g for g in gaps if g > 0)
    typical = gaps[len(gaps) // 2] if gaps else 3
    threshold = typical * 2.5

    out, prev, in_bullet = [], None, False
    for r in result:
        new_block = (prev is None
                     or r["y0"] < prev["y0"]               # jumped back up = new column
                     or r["y0"] - prev["y1"] > threshold)  # big gap = new section
        if new_block and prev is not None:
            out.append("")

        if r["bullet"]:
            out.append("- " + r["text"])
            in_bullet = True
        elif in_bullet and not new_block and out and out[-1].startswith("- ") and not r["text"].isupper():
            out[-1] += " " + r["text"]          # wrapped line: continues the previous bullet
        else:
            out.append(r["text"])
            in_bullet = False
        prev = r
    return "\n".join(out)


def extract_text(pdf_bytes: bytes) -> str:
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        text = "\n\n".join(_page_text(page) for page in doc).strip()
        links = []
        for page in doc:
            for link in page.get_links():
                uri = link.get("uri")
                if uri and uri not in links:
                    links.append(uri)
    if links:
        text += "\n\nHyperlinks found in the PDF:\n" + "\n".join(links)
    return text