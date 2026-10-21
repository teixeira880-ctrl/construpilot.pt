import json
import sys

import pymupdf

sys.path.insert(0, "/app/backend")
from collections import Counter  # noqa: E402

from engines.plan_vector_pdf import extract_vector_dimensions, pdf_lines  # noqa: E402
from engines.plan_walls import analyze_walls  # noqa: E402

doc = pymupdf.open(sys.argv[1] if len(sys.argv) > 1 else "/tmp/houilles.pdf")
page = doc[0]
V = pdf_lines(page)
tb = [{"text": sp["text"].strip(), "x": sp["bbox"][0], "y": sp["bbox"][1], "w": sp["bbox"][2] - sp["bbox"][0], "h": sp["bbox"][3] - sp["bbox"][1]}
      for b in page.get_text("dict")["blocks"] if b["type"] == 0 for ln in b["lines"] for sp in ln["spans"] if sp["text"].strip()]
px = 200 / 72
dims = extract_vector_dimensions(V, tb, px)
ppm = dims["pt_per_m"]
r = analyze_walls(V, [{**d, "index": i + 1} for i, d in enumerate(dims["dimensions"])], tb, ppm, px)
print("stats", r["stats"])
print("validation", r["validation"]["failed_checks"])
for w in r["walls"]:
    print(w["wall_id"], w["orientation"], w["thickness_m"], w["length_m"], w["source"], "amb" if w["ambiguous"] else "", w["intersections"])
for m in r["interior_measurements"][:60]:
    print(m["measurement_id"], m["from_wall"], "->", m["to_wall"], "geo", m["geometric_dimension_m"], "written", m["written_dimension_m"], "axis", m["axis_cote_m"], m["status"])
for row in r["closure_equations"][:12]:
    print(row["row_id"], row["sum_m"], row["written_exterior_m"], row["geometric_exterior_m"], row["status"], [t["value_m"] for t in row["terms"]])
print(Counter(c["reference_type"] for c in r["cotes"]))
print([(c["raw_text"], c["reference_type"], c["from_wall"], c["to_wall"]) for c in r["cotes"] if c["reference_type"] != "unresolved"])
print("unresolved", [c["raw_text"] for c in r["cotes"] if c["reference_type"] == "unresolved"])
json.dump(r, open("/tmp/houilles_walls.json", "w"))
