#!/usr/bin/env python3
"""tools/build_index.py orders hub entries naturally: Chapter 1, 2, ... 10, 11, 14 (not 1, 10, 11, 2), Part 2 right
after its Part 1, case-insensitive; dated pages still come first by date."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_index as B

def it(title, date="", path=None):
    return {"grade": "G3", "subject": "Kangaroo", "title": title, "test_date": date, "path": path or "G3/Kangaroo/%s/" % title.replace(" ", "-")}

titles = ["Ch10 Nets and dice", "Ch1 Mirrors", "ch2 Number sense (Part 2)", "Ch11 Shapes", "Ch2 Number sense", "Ch14 Patterns",
          "Ch2 Number sense (Part 1)", "Ch3 Counting smart", "chapter 9 Paths"]
got = [x["title"] for x in sorted([it(t) for t in titles], key=B.hub_order)]
want = ["Ch1 Mirrors", "Ch2 Number sense", "Ch2 Number sense (Part 1)", "ch2 Number sense (Part 2)", "Ch3 Counting smart",
        "Ch10 Nets and dice", "Ch11 Shapes", "Ch14 Patterns", "chapter 9 Paths"]
assert got == want, got
got = [x["title"] for x in sorted([it("Chapter 10"), it("Chapter 2"), it("Chapter 1"), it("Chapter 11")], key=B.hub_order)]
assert got == ["Chapter 1", "Chapter 2", "Chapter 10", "Chapter 11"], got
# a test date still wins over the title; pages without one come after
got = [x["title"] for x in sorted([it("Ch1 A"), it("Ch9 Mock", "2026-12-01"), it("Ch2 B")], key=B.hub_order)]
assert got == ["Ch9 Mock", "Ch1 A", "Ch2 B"], got
assert sorted(["G10", "G3"], key=B.natural_key) == ["G3", "G10"]
print("build_index natural order test passed")
