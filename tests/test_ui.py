"""Browser tests of the editor (REQ-USE-01, REQ-DGM-02/05/06/07/08, REQ-SRC-03/04,
REQ-LCK-03). Optional: they need the 'playwright' package and Chrome/Chromium,
which are development-only tools and not needed to run the tool itself.
Skipped automatically when those are missing."""
import os
import shutil
import sys
import threading

import pytest

from conftest import HERE, pub, do
from specgraph import validate as V
from specgraph.server import start
from specgraph.store import Store

sync_api = pytest.importorskip("playwright.sync_api")
CHROME = os.environ.get("CHROME") or shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
pytestmark = pytest.mark.skipif(not CHROME, reason="no Chrome/Chromium found")

sys.path.insert(0, os.path.join(os.path.dirname(HERE), "sample"))


@pytest.fixture
def sample(tmp_path, keys):
    """REQ-DOC-05: the demo model, built through the tool's own operations."""
    import build_sample
    store = build_sample.build(str(tmp_path / "demo"), key=keys["ada"], user="ada")
    do(store, "user.add", name="bob", key=pub(keys["bob"]))
    return store


@pytest.fixture
def page_for(sample):
    opened = []

    def open_as(store):
        httpd, url = start(store, 18900 + len(opened) * 7, token="t")
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        pw = sync_api.sync_playwright().start()
        browser = pw.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = browser.new_page(viewport={"width": 1500, "height": 900})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(url)
        pg.wait_for_selector("#tree .row")
        for _ in range(3):
            for tw in pg.query_selector_all("#tree .row[data-kind=folder] .tw"):
                if tw.inner_text() == "▸":
                    tw.click()
        opened.append((httpd, browser, pw))
        return pg, errors

    yield open_as
    for httpd, browser, pw in opened:
        browser.close()
        pw.stop()
        httpd.shutdown()
        httpd.server_close()


def ids(store):
    m = store.load()
    by = {e["label"]: i for i, e in m["elements"].items()}
    dg = {d["name"].split()[0]: i for i, d in m["diagrams"].items()}
    return m, by, dg


def test_sample_model_is_valid(sample):
    """REQ-DOC-05: a few elements per stereotype, diagrams sharing elements, a locked folder."""
    m = sample.load()
    assert not V.validate(m)
    per = {}
    for e in m["elements"].values():
        per[e["stereotype"]] = per.get(e["stereotype"], 0) + 1
    assert all(per[s] >= 2 for s in ("ADR", "REQ", "CONSTRAINT", "RISK")) and len(m["diagrams"]) == 3
    shared = [e for e in m["elements"] if sum(e in d["nodes"] for d in m["diagrams"].values()) > 1]
    assert shared and any(f["lock"] for f in m["folders"].values())


def test_editor_end_to_end(sample, page_for):
    pg, errors = page_for(sample)
    m, by, dg = ids(sample)
    # REQ-USE-01: tree, diagram, properties panel
    pg.dblclick("#tree .row[data-kind=diagram] >> text=Numbering overview")
    pg.wait_for_selector("#canvas g[data-kind=node]")
    assert pg.locator("#canvas g[data-kind=node]").count() == 5
    # REQ-DGM-07: links between elements on the diagram are drawn from the model
    assert pg.locator("#canvas g[data-kind=link]").count() == 6
    # REQ-CFG-02/03 + DGM-05: stereotype marker and status readable together; REQ-LCK-03: lock mark
    node = pg.locator('#canvas g[data-kind=node][data-id="%s"]' % by["CON-001"])
    text = node.text_content()
    assert "«CONSTRAINT»" in text and "Approved" in text and "\U0001f512" in text
    assert "ada" in pg.inner_text("#tree .lk")
    # REQ-DGM-06: link look follows its type (implements = dashed blue)
    lid = [i for i, l in m["links"].items() if l["type"] == "implements" and l["target"] == by["REQ-001"]][0]
    path = pg.locator('#canvas g[data-kind=link][data-id="%s"] path' % lid).first
    assert path.get_attribute("stroke") == "#1d4ed8" and path.get_attribute("stroke-dasharray")
    # REQ-SRC-01/02/03: search by label, diagrams listed, double-click opens + focuses + selects
    pg.fill("#q", "REQ-002")
    pg.press("#q", "Enter")
    pg.wait_for_selector("#panel .dg")
    assert len(pg.query_selector_all("#panel .dg")) == 2
    pg.dblclick("#panel .dg >> text=Decisions")
    pg.wait_for_selector("#tabs .tab.on >> text=Decisions")
    assert pg.inner_text("#props .idline .idtext") == by["REQ-002"]
    box = pg.query_selector('#canvas g[data-kind=node][data-id="%s"]' % by["REQ-002"]).bounding_box()
    cb = pg.query_selector("#canvas").bounding_box()
    assert abs(box["x"] + box["width"] / 2 - (cb["x"] + cb["width"] / 2)) < 15  # centred in view
    # REQ-ELM-05: edit once in the properties panel
    pg.select_option("#props select >> nth=0", "implemented")
    pg.wait_for_timeout(400)
    assert sample.load()["elements"][by["REQ-002"]]["status"] == "implemented"
    # REQ-DGM-02: move by dragging
    before = dict(m["diagrams"][dg["Decisions"]]["nodes"][by["REQ-002"]])
    pg.mouse.move(box["x"] + 40, box["y"] + 40)
    pg.mouse.down()
    pg.mouse.move(box["x"] + 240, box["y"] + 70, steps=5)
    pg.mouse.up()
    pg.wait_for_timeout(400)
    after = sample.load()["diagrams"][dg["Decisions"]]["nodes"][by["REQ-002"]]
    assert (after["x"], after["y"]) == (before["x"] + 200, before["y"] + 30)
    assert sample.load()["diagrams"][dg["Numbering"]]["nodes"][by["REQ-002"]] == m["diagrams"][dg["Numbering"]]["nodes"][by["REQ-002"]]
    # REQ-DGM-02: new element placed from the diagram, then linked by dragging
    spot = pg.evaluate("""() => {                     // an empty place with room for a new node and its link dot
        const c = document.getElementById('canvas').getBoundingClientRect();
        const free = (x, y) => { const u = document.elementFromPoint(x, y); return u && u.id === 'canvas'; };
        for (let y = c.top + 40; y < c.bottom - 140; y += 20) for (let x = c.left + 20; x < c.right - 450; x += 20) {
          let ok = true;
          for (let dx = 0; dx <= 240 && ok; dx += 20) for (let dy = 0; dy <= 110 && ok; dy += 10) ok = free(x + dx, y + dy);
          if (ok) return [x, y];
        }
        return null; }""")
    pg.mouse.click(spot[0], spot[1], button="right")
    pg.click("#menu >> text=New RISK here")
    pg.fill(".modal input", "Created from the UI")
    pg.press(".modal input", "Enter")
    pg.wait_for_timeout(500)
    m2 = sample.load()
    new = [i for i, e in m2["elements"].items() if e["topic"] == "Created from the UI"][0]
    assert new in m2["diagrams"][dg["Decisions"]]["nodes"]
    c = pg.query_selector("#canvas [data-kind=connect]").bounding_box()
    tb = pg.query_selector('#canvas g[data-kind=node][data-id="%s"]' % by["REQ-002"]).bounding_box()
    pg.select_option("#dtools select", "depends_on")
    pg.mouse.move(c["x"] + 6, c["y"] + 6)
    pg.mouse.down()
    pg.mouse.move(tb["x"] + 30, tb["y"] + 30, steps=6)
    pg.mouse.up()
    pg.wait_for_timeout(500)
    m2 = sample.load()
    made = [i for i, l in m2["links"].items() if l["source"] == new and l["target"] == by["REQ-002"]]
    assert len(made) == 1 and m2["links"][made[0]]["type"] == "depends_on"
    # REQ-DGM-04: user-defined routing on this diagram only, via the properties panel
    pg.select_option("#props select >> nth=1", "straight")
    pg.wait_for_timeout(400)
    assert sample.load()["diagrams"][dg["Decisions"]]["links"][made[0]] == {"routing": "straight"}
    free = pg.evaluate("""(lid) => { const p = document.querySelector('#canvas g[data-kind=link][data-id="' + lid + '"] path[data-ui]');
        const m = p.getScreenCTM(), n = p.getTotalLength();
        for (let i = 1; i < 40; i++) { const q = p.getPointAtLength(n * i / 40), x = m.a * q.x + m.e, y = m.d * q.y + m.f;
          const u = document.elementFromPoint(x, y), g = u && u.closest('[data-kind]');
          if (g && g.getAttribute('data-id') === lid) return [x, y]; }
        return null; }""", made[0])
    pg.mouse.dblclick(free[0], free[1])
    pg.wait_for_timeout(400)
    o = sample.load()["diagrams"][dg["Decisions"]]["links"][made[0]]
    assert o["routing"] == "custom" and len(o["points"]) == 1
    # REQ-ELM-06: Delete key only removes from the diagram; model delete asks and shows usage
    nb = pg.query_selector('#canvas g[data-kind=node][data-id="%s"]' % new).bounding_box()
    pg.mouse.click(nb["x"] + nb["width"] / 2, nb["y"] + nb["height"] / 2)
    pg.wait_for_timeout(450)  # not a double-click with the previous one
    pg.keyboard.press("Delete")
    pg.wait_for_timeout(400)
    m2 = sample.load()
    assert new in m2["elements"] and new not in m2["diagrams"][dg["Decisions"]]["nodes"]
    # REQ-SRC-05: unused list
    pg.check("#qun")
    pg.fill("#q", "")
    pg.click("#bar >> text=Search")
    pg.wait_for_function("() => document.getElementById('panel').innerText.includes('on no diagram')")
    assert "Created from the UI" in pg.inner_text("#panel") and "on no diagram" in pg.inner_text("#panel")
    pg.uncheck("#qun")
    # REQ-SRC-04: find in all diagrams from the element's context menu
    pg.click("#tree .row[data-kind=element] >> text=REQ-001", button="right")
    pg.click("#menu >> text=Find in all diagrams")
    pg.wait_for_function("() => document.getElementById('panel').innerText.includes('REQ-001')")
    assert len(pg.query_selector_all("#panel .dg")) == 2
    pg.click("#props >> text=Delete from model")
    pg.wait_for_selector("#confirmDelete")
    assert "Used on 2 diagram(s)" in pg.inner_text(".modal") and by["REQ-001"] in sample.load()["elements"]
    pg.click(".modal >> text=Cancel")
    # REQ-TRC-01: multi-level trace panel
    pg.click("#props >> text=Trace")
    pg.wait_for_selector("#panel .cols")
    t = pg.inner_text("#panel")
    assert "CON-001" in t and "ADR-001" in t and "[object" not in t
    # REQ-CFG-01: an ordinary user adds a link type in the tool
    pg.click("#bar >> text=Configure")
    pg.click(".modal >> text=Link types")
    pg.click(".modal >> text=+ new")
    pg.fill(".modal .form input[type=text]", "verifies")
    pg.click("#cfgSave")
    pg.wait_for_timeout(500)
    assert "verifies" in sample.load()["config"]["linkTypes"]
    pg.click(".modal >> text=Close")
    # REQ-TRC-04: matrix
    pg.click("#bar >> text=Matrix")
    pg.wait_for_selector(".modal table.mx")
    assert "→" in pg.inner_text(".modal table.mx")
    pg.click(".modal >> text=Close")
    # REQ-DGM-08: export as image
    with pg.expect_download() as dl:
        pg.click("#btnExport")
        pg.click("#menu >> text=SVG file")
    svg = open(dl.value.path(), encoding="utf-8").read()
    assert svg.startswith("<svg") and "REQ-001" in svg and "data-ui" not in svg
    with pg.expect_download() as dl:
        pg.click("#btnExport")
        pg.click("#menu >> text=PNG file")
    assert open(dl.value.path(), "rb").read(4) == b"\x89PNG"
    assert errors == [] and not V.errors(sample.load())


def test_locked_content_cannot_be_edited_by_others_in_ui(sample, page_for, keys):
    """REQ-LCK-01/03 in the UI: bob sees the lock and his edit is refused."""
    bob = Store(path=sample.path, key=keys["bob"])
    pg, errors = page_for(bob)
    m, by, dg = ids(sample)
    pg.click("#tree .row[data-kind=element] >> text=CON-001")
    assert "Locked by ada" in pg.inner_text("#props .note")
    assert pg.locator("#props textarea").first.is_disabled()
    code = pg.evaluate("op('element.update', {id: '%s', topic: 'hacked'}).then(r => r === null)" % by["CON-001"])
    assert code is True and "locked by ada" in pg.inner_text("#toast")
    assert sample.load()["elements"][by["CON-001"]]["topic"].startswith("Invoice numbers")
    assert errors == []


def test_tree_order_collapse_and_pane_sizes(sample, page_for):
    """REQ-FLD-03, USE-07, USE-08 (ADR-024): reorder by dragging, collapse/expand a folder with its
    sub-folders, resize the panes by dragging the lines between them."""
    from specgraph import ops as O
    pg, errors = page_for(sample)
    m, by, dg = ids(sample)
    folder = {f["name"].split()[0]: i for i, f in m["folders"].items()}
    row = lambda kind, id_: pg.locator('#tree .row[data-kind=%s][data-id="%s"]' % (kind, id_))
    shown = lambda kind: [r.get_attribute("data-id") for r in pg.query_selector_all("#tree .row[data-kind=%s]" % kind)]

    def drag(src, dst, where):
        a, b = src.bounding_box(), dst.bounding_box()
        pg.mouse.move(a["x"] + 60, a["y"] + a["height"] / 2)
        pg.mouse.down()
        y = b["y"] + (2 if where == "before" else b["height"] - 2 if where == "after" else b["height"] / 2)
        pg.mouse.move(b["x"] + 60, y, steps=6)
        pg.mouse.move(b["x"] + 62, y, steps=2)
        pg.mouse.up()
        pg.wait_for_timeout(500)

    # REQ-FLD-03: an element before another one of the same folder
    num = folder["Numbering"]
    first = O.tree_order(m, "elements", num)
    assert [i for i in shown("element") if i in first] == first
    drag(row("element", first[-1]), row("element", first[0]), "before")
    want = [first[-1]] + first[:-1]
    assert O.tree_order(sample.load(), "elements", num) == want
    assert [i for i in shown("element") if i in want] == want
    # ... and into another folder at a chosen place: one change, moved and ordered
    arch = O.tree_order(sample.load(), "elements", folder["Architecture"])
    drag(row("element", want[0]), row("element", arch[0]), "after")
    m2 = sample.load()
    assert m2["elements"][want[0]]["folder"] == folder["Architecture"]
    assert O.tree_order(m2, "elements", folder["Architecture"]) == [arch[0], want[0]] + arch[1:]
    # top-level folders; dropping on the middle of a folder still moves into it
    tops = O.tree_order(m2, "folders", None)
    drag(row("folder", tops[-1]), row("folder", tops[0]), "before")
    assert O.tree_order(sample.load(), "folders", None) == [tops[-1]] + tops[:-1]
    drag(row("diagram", dg["Risks"]), row("folder", folder["Architecture"]), "into")
    assert sample.load()["diagrams"][dg["Risks"]]["folder"] == folder["Architecture"]
    # REQ-USE-07: a folder with its sub-folders, from the context menu
    inv = folder["Invoicing"]
    assert num in shown("folder")
    row("folder", inv).click(button="right")
    pg.click("#menu >> text=Collapse with sub-folders")
    assert num not in shown("folder")
    pg.evaluate("(a) => { S.expanded.add(a); renderTree(); }", inv)
    assert row("folder", num).locator(".tw").inner_text() == "▸"          # the sub-folder was closed too
    row("folder", inv).click(button="right")
    pg.click("#menu >> text=Expand with sub-folders")
    assert row("folder", num).locator(".tw").inner_text() == "▾" and len(shown("element")) == len(m["elements"])
    # REQ-USE-08: drag the lines between the panes
    def pull(bar, dx, dy):
        b = pg.query_selector(bar).bounding_box()
        pg.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
        pg.mouse.down()
        pg.mouse.move(b["x"] + b["width"] / 2 + dx, b["y"] + b["height"] / 2 + dy, steps=4)
        pg.mouse.up()

    size = lambda sel, dim: round(pg.query_selector(sel).bounding_box()[dim])
    w = size("#tree", "width")
    pull("#splitL", 80, 0)
    assert size("#tree", "width") == w + 80
    tree_w = w + 80
    w = size("#props", "width")
    pull("#splitR", -60, 0)
    assert size("#props", "width") == w + 60
    assert not pg.is_visible("#splitB")
    pg.click("#btnCheck")
    pg.wait_for_selector("#panel h3")
    hgt = size("#panel", "height")
    pull("#splitB", 0, -70)
    assert size("#panel", "height") == hgt + 70
    pg.reload()                                                            # the sizes are remembered by the browser
    pg.wait_for_selector("#tree .row")
    assert size("#tree", "width") == tree_w
    pg.dblclick("#splitL")
    assert size("#tree", "width") == 270
    assert errors == [] and not V.errors(sample.load())


def test_use09_10_explorer_double_click_and_find(sample, page_for):
    """REQ-USE-09: double-click in the explorer opens a diagram and opens/closes a folder (Ctrl: with all
    sub-folders, Alt: closes all). REQ-USE-10: Find in explorer opens the folders and shows the item."""
    pg, errors = page_for(sample)
    m, by, dg = ids(sample)
    folder = {f["name"].split()[0]: i for i, f in m["folders"].items()}
    row = lambda kind, id_: pg.locator('#tree .row[data-kind=%s][data-id="%s"]' % (kind, id_))
    arrow = lambda fid: row("folder", fid).locator(".tw").inner_text()

    def twice(loc, mods=None):
        # two separate clicks as a person makes them; the first one re-draws the tree
        loc.click(modifiers=mods or [])
        pg.wait_for_timeout(120)
        loc.click(modifiers=mods or [])
        pg.wait_for_timeout(200)

    twice(row("diagram", dg["Risks"]).locator(".t"))
    assert pg.evaluate("S.active") == dg["Risks"]
    inv, num = folder["Invoicing"], folder["Numbering"]
    pg.evaluate("setExpanded(null, false)")
    twice(row("folder", inv).locator(".t"))
    assert arrow(inv) == "▾" and arrow(num) == "▸"
    twice(row("folder", inv).locator(".t"))
    assert arrow(inv) == "▸"
    twice(row("folder", inv).locator(".t"), ["Control"])
    assert arrow(inv) == "▾" and arrow(num) == "▾"
    twice(row("folder", inv).locator(".t"), ["Alt"])
    assert arrow(inv) == "▸"
    pg.evaluate("(a) => { S.expanded.add(a); renderTree(); }", inv)
    assert arrow(num) == "▸"                                           # Alt closed the sub-folders too

    # REQ-USE-10: from the diagram, with a short explorer that must scroll
    pg.set_viewport_size({"width": 1500, "height": 420})
    pg.evaluate("setExpanded(null, true)")
    eid = sorted(m["diagrams"][dg["Risks"]]["nodes"], key=lambda i: m["elements"][i]["folder"] != num)[0]
    pg.evaluate("setExpanded(null, false)")
    pg.evaluate("(d) => openDiagram(d)", dg["Risks"])
    pg.locator('#canvas [data-kind=node][data-id="%s"]' % eid).first.click(button="right")
    pg.click("#menu >> text=Find in explorer")
    pg.wait_for_timeout(300)

    def shown_in_tree(kind, id_):
        return pg.evaluate("""([k, i]) => { const r = document.querySelector('#tree .row[data-kind=' + k + '][data-id="' + i + '"]');
            if (!r) return false; const a = r.getBoundingClientRect(), t = document.getElementById('tree').getBoundingClientRect();
            return r.classList.contains('sel') && a.top >= t.top && a.bottom <= t.bottom; }""", [kind, id_])
    assert shown_in_tree("element", eid)
    # from the properties pane, for an element and for a diagram
    other = [i for i in m["elements"] if m["elements"][i]["folder"] != m["elements"][eid]["folder"]][0]
    pg.evaluate("setExpanded(null, false)")
    pg.evaluate("(i) => select('element', i)", other)
    pg.click("#props >> text=Find in explorer")
    assert shown_in_tree("element", other)
    pg.evaluate("setExpanded(null, false)")
    pg.evaluate("(i) => select('diagram', i)", dg["Risks"])
    pg.click("#props >> text=Find in explorer")
    assert shown_in_tree("diagram", dg["Risks"])
    pg.evaluate("setExpanded(null, false)")
    pg.evaluate("(i) => select('folder', i)", num)
    pg.click("#props >> text=Find in explorer")
    assert shown_in_tree("folder", num)
    assert errors == []


def test_dgm09_10_select_several_move_and_align(sample, page_for):
    """REQ-DGM-09: Ctrl+click and Shift+drag select several nodes. REQ-DGM-10: a selection moves as one
    (links follow while dragging, bend points between selected nodes move along, one undo step).
    REQ-DGM-11: align edges or centres to the last selected node, from the menu and the keyboard (ADR-027, ADR-028)."""
    m = sample.load()
    top = {e["topic"]: i for i, e in m["elements"].items()}
    d1 = [i for i, d in m["diagrams"].items() if d["name"] == "Numbering overview"][0]
    r1, r2 = top["Every invoice gets a unique number"], top["Numbering has no gaps"]
    a1 = top["Allocate numbers from a database sequence table"]
    k1 = top["Rollback leaves a gap in the sequence"]
    dep = [i for i, l in m["links"].items() if (l["source"], l["target"]) == (r2, r1)][0]
    imp = [i for i, l in m["links"].items() if (l["source"], l["target"]) == (a1, r1)][0]
    do(sample, "diagram.link", diagram=d1, link=dep, routing="custom", points=[[400, 150]])
    sample.undo_steps = 20                                             # as `serve` sets it
    pg, errors = page_for(sample)
    pg.evaluate("(d) => openDiagram(d)", d1)
    node = lambda i: pg.locator('#canvas [data-kind=node][data-id="%s"]' % i).first
    nodes = lambda: sample.load()["diagrams"][d1]["nodes"]
    chosen = lambda: pg.evaluate("selNodes()")

    def centre(i):
        b = node(i).bounding_box()
        return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2

    def click(i, mods=None):
        pg.mouse.move(*centre(i))
        node(i).click(position={"x": 20, "y": 30}, modifiers=mods or [])
        pg.wait_for_timeout(450)                                      # not a double-click

    # REQ-DGM-09: Ctrl+click adds and removes
    click(r1)
    click(r2, ["Control"])
    click(a1, ["Control"])
    assert chosen() == [r1, r2, a1]
    click(a1, ["Control"])
    assert chosen() == [r1, r2]
    # REQ-DGM-10: drag one of them, the other follows; the link to a node outside follows while dragging
    before, path0 = nodes(), pg.locator('#canvas [data-kind=link][data-id="%s"] path' % imp).first.get_attribute("d")
    steps0 = pg.evaluate("S.undo.steps")
    x, y = centre(r1)
    pg.mouse.move(x, y)
    pg.mouse.down()
    pg.mouse.move(x + 60, y + 40, steps=5)
    assert pg.locator('#canvas [data-kind=link][data-id="%s"] path' % imp).first.get_attribute("d") != path0
    pg.mouse.up()
    pg.wait_for_timeout(500)
    after = nodes()
    dx, dy = after[r1]["x"] - before[r1]["x"], after[r1]["y"] - before[r1]["y"]
    assert dx > 0 and dy > 0
    assert (after[r2]["x"] - before[r2]["x"], after[r2]["y"] - before[r2]["y"]) == (dx, dy)
    assert after[a1] == before[a1] and after[k1] == before[k1]
    assert sample.load()["diagrams"][d1]["links"][dep]["points"] == [[400 + dx, 150 + dy]]
    assert pg.evaluate("S.undo.steps") == steps0 + 1 and chosen() == [r1, r2]
    # a click without moving on one of them selects only that one
    click(r2)
    assert chosen() == [r2]
    # Shift+drag over empty canvas: every node touching the rectangle
    a, k = node(a1).bounding_box(), node(k1).bounding_box()
    pg.keyboard.down("Shift")
    pg.mouse.move(a["x"] + 20, a["y"] + a["height"] + 30)
    pg.mouse.down()
    pg.mouse.move(k["x"] + 10, k["y"] + 10, steps=5)
    pg.mouse.up()
    pg.keyboard.up("Shift")
    pg.wait_for_timeout(300)
    assert sorted(chosen()) == sorted([a1, k1])
    # REQ-DGM-11: align to the last selected node, from the Align submenu, the keyboard and the properties
    do(sample, "diagram.layout", diagram=d1, element=r1, w=250, h=120)     # sizes differ: left, centre, right differ
    pg.evaluate("load()")
    pg.wait_for_timeout(300)
    click(r1)
    click(k1, ["Control"])
    click(a1, ["Control"])
    ref = nodes()[a1]

    def scatter():
        do(sample, "diagram.layout", diagram=d1, element=r1, x=13, y=7)
        do(sample, "diagram.layout", diagram=d1, element=k1, x=900, y=650)
        pg.evaluate("load()")
        pg.wait_for_timeout(300)

    edge = {("x", "start"): lambda n: n["x"], ("x", "center"): lambda n: n["x"] + n["w"] / 2,
            ("x", "end"): lambda n: n["x"] + n["w"], ("y", "start"): lambda n: n["y"],
            ("y", "center"): lambda n: n["y"] + n["h"] / 2, ("y", "end"): lambda n: n["y"] + n["h"]}

    def aligned(axis, where):
        n = nodes()
        f = edge[(axis, where)]
        return f(n[r1]) == f(n[k1]) == f(n[a1]) and n[a1] == ref

    for path, axis, where in ((["Align", "Horizontal", "Left"], "x", "start"), (["Align", "Vertical", "Bottom"], "y", "end")):
        scatter()
        node(r1).click(button="right", position={"x": 20, "y": 30})
        for label in path[:-1]:
            pg.hover("#menu .sub >> text=%s" % label)
        pg.click("#menu .submenu >> text=%s" % path[-1])
        pg.wait_for_timeout(400)
        assert aligned(axis, where), path
    for key, axis, where in (("Control+Shift+Digit1", "x", "start"), ("Control+Shift+Digit2", "x", "center"),
                             ("Control+Shift+Digit3", "x", "end"), ("Alt+Shift+Digit1", "y", "start"),
                             ("Alt+Shift+Digit2", "y", "center"), ("Alt+Shift+Digit3", "y", "end")):
        scatter()
        pg.keyboard.press(key)
        pg.wait_for_timeout(400)
        assert aligned(axis, where), key
    for axis, where in (("x", "center"), ("y", "start")):
        scatter()
        pg.click('#props button[data-align="%s:%s"]' % (axis, where))
        pg.wait_for_timeout(400)
        assert aligned(axis, where), (axis, where)
    assert pg.locator("#props .note").inner_text().startswith("3 elements are selected")
    pg.locator("#canvas").click(position={"x": 5, "y": 5})                # leave the properties pane
    pg.evaluate("(ids) => selectNodes(ids)", [r1, k1, a1])
    pg.keyboard.press("Delete")
    pg.wait_for_timeout(400)
    assert set(nodes()) == set(before) - {r1, k1, a1}
    assert set(sample.load()["elements"]) == set(m["elements"])          # still in the model
    assert errors == [] and not V.errors(sample.load())


def test_dgm12_snap_to_grid(sample, page_for):
    """REQ-DGM-12 (ADR-027): a grid size and a snap switch in the diagram tools, the same default for
    everyone (20, on), kept by the browser; the snap grid replaces the plain background dots. With snap on, created, moved and resized nodes land on the grid."""
    m = sample.load()
    top = {e["topic"]: i for i, e in m["elements"].items()}
    d1 = [i for i, d in m["diagrams"].items() if d["name"] == "Numbering overview"][0]
    r1, r2 = top["Every invoice gets a unique number"], top["Numbering has no gaps"]
    r3 = top["Corrections are made by credit note"]
    pg, errors = page_for(sample)
    pg.evaluate("(d) => openDiagram(d)", d1)
    node = lambda i: pg.locator('#canvas [data-kind=node][data-id="%s"]' % i).first
    nodes = lambda: sample.load()["diagrams"][d1]["nodes"]
    plain_dots = lambda: pg.evaluate("getComputedStyle(document.getElementById('canvas')).backgroundImage") != "none"
    assert pg.input_value("#gridSize") == "20" and pg.is_checked("#gridSnap")
    assert pg.locator("#canvas #grid").count() == 1 and not plain_dots()  # the snap grid replaces the plain dots
    pg.uncheck("#gridSnap")
    assert pg.locator("#canvas #grid").count() == 0 and plain_dots()
    pg.fill("#gridSize", "25")
    pg.press("#gridSize", "Enter")
    pg.check("#gridSnap")
    assert pg.locator("#canvas #grid").count() == 1 and not plain_dots()
    on = lambda v: v % 25 == 0

    def drag(loc, dx, dy, at=None):
        b = loc.bounding_box()
        x, y = (b["x"] + at[0], b["y"] + at[1]) if at else (b["x"] + 20, b["y"] + 30)
        pg.mouse.move(x, y)
        pg.mouse.down()
        pg.mouse.move(x + dx, y + dy, steps=5)
        pg.mouse.up()
        pg.wait_for_timeout(500)

    # move: one node, then a selection keeps its spacing and the dragged one lands on the grid
    drag(node(r1), 37, 23)
    n = nodes()
    assert on(n[r1]["x"]) and on(n[r1]["y"])
    gap = (n[r2]["x"] - n[r1]["x"], n[r2]["y"] - n[r1]["y"])
    pg.evaluate("(ids) => selectNodes(ids)", [r2, r1])
    drag(node(r1), 61, 12)
    n = nodes()
    assert on(n[r1]["x"]) and on(n[r1]["y"]) and (n[r2]["x"] - n[r1]["x"], n[r2]["y"] - n[r1]["y"]) == gap
    # resize: the lower right corner lands on the grid
    pg.evaluate("(i) => select('element', i)", r1)
    drag(pg.locator('#canvas [data-kind=resize][data-id="%s"]' % r1), 33, 19, at=(5, 5))
    n = nodes()
    assert on(n[r1]["x"] + n[r1]["w"]) and on(n[r1]["y"] + n[r1]["h"])
    # create: dropped from the tree
    pg.locator('#tree .row[data-kind=element][data-id="%s"]' % r3).drag_to(pg.locator("#canvas"), target_position={"x": 333, "y": 211})
    pg.wait_for_timeout(500)
    n = nodes()
    assert r3 in n and on(n[r3]["x"]) and on(n[r3]["y"])
    # kept by the browser; with snap off nothing is rounded
    pg.reload()
    pg.wait_for_selector("#tree .row")
    pg.evaluate("(d) => openDiagram(d)", d1)
    assert pg.input_value("#gridSize") == "25" and pg.is_checked("#gridSnap")
    pg.uncheck("#gridSnap")
    drag(node(r2), 7, 3)
    assert not (on(nodes()[r2]["x"]) and on(nodes()[r2]["y"]))
    assert errors == [] and not V.errors(sample.load())


def test_elm07_type_change_in_the_editor_shows_the_new_label(sample, page_for):
    """REQ-ELM-07 (ADR-026): picking another stereotype in the properties gives the generated label of
    the new type, in the properties, the tree and on the diagram."""
    m = sample.load()
    eid = [i for i, e in m["elements"].items() if e["topic"] == "Allocate numbers from a database sequence table"][0]
    want = "REQ-" + eid.replace("-", "")[:8]
    pg, errors = page_for(sample)
    pg.evaluate("(i) => select('element', i)", eid)
    pg.select_option('#props .f:has(label:text-is("Stereotype")) select', "REQ")
    pg.wait_for_timeout(400)
    assert sample.load()["elements"][eid]["label"] == want
    assert pg.input_value('#props .f:has(label:text-is("Label")) input') == want
    assert want in pg.locator('#tree .row[data-kind=element][data-id="%s"]' % eid).inner_text()
    pg.evaluate("(i) => openDiagram(Object.keys(S.model.diagrams).find((d) => S.model.diagrams[d].nodes[i]), i)", eid)
    assert want in pg.locator('#canvas [data-kind=node][data-id="%s"]' % eid).first.text_content()
    assert errors == [] and not V.errors(sample.load())



def test_dgm13_overview_moves_the_view(sample, page_for):
    """REQ-DGM-13 (ADR-028): a small overview of the whole diagram at the bottom right with a box for the
    part in view. A click centres the view there; dragging the box moves the view; it can be hidden."""
    m = sample.load()
    top = {e["topic"]: i for i, e in m["elements"].items()}
    d1 = [i for i, d in m["diagrams"].items() if d["name"] == "Numbering overview"][0]
    k1 = top["Rollback leaves a gap in the sequence"]
    pg, errors = page_for(sample)
    pg.evaluate("(d) => openDiagram(d)", d1)
    pg.evaluate("() => { const v = view(S.active); v.k = 2; v.x = 0; v.y = 0; renderDiagram(); }")   # zoomed in: part in view
    assert pg.is_visible("#miniWrap")
    assert pg.locator("#mini [data-mini-node]").count() == len(m["diagrams"][d1]["nodes"])
    canvas = pg.locator("#canvas").bounding_box()
    mid = (canvas["x"] + canvas["width"] / 2, canvas["y"] + canvas["height"] / 2)

    def centre(loc):
        b = loc.bounding_box()
        return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2

    # a click on k1 in the overview brings k1 to the middle of the canvas
    pg.mouse.click(*centre(pg.locator('#mini [data-mini-node="%s"]' % k1)))
    pg.wait_for_timeout(200)
    x, y = centre(pg.locator('#canvas [data-kind=node][data-id="%s"]' % k1).first)
    assert abs(x - mid[0]) < 12 and abs(y - mid[1]) < 12
    # dragging the box moves it and the view with it
    box = pg.locator("#miniView")
    b0, v0 = box.bounding_box(), pg.evaluate("Object.assign({}, view(S.active))")
    bx, by = centre(box)
    pg.mouse.move(bx, by)
    pg.mouse.down()
    pg.mouse.move(bx - 20, by - 10, steps=4)
    b1, v1 = box.bounding_box(), pg.evaluate("Object.assign({}, view(S.active))")
    pg.mouse.up()
    assert abs(b1["x"] - b0["x"] + 20) < 2 and abs(b1["y"] - b0["y"] + 10) < 2
    assert v1["x"] > v0["x"] and v1["y"] > v0["y"] and v1["k"] == v0["k"]
    assert sample.load()["diagrams"][d1] == m["diagrams"][d1]               # the view is not model data
    # it can be hidden, and the browser remembers that
    pg.uncheck("#miniOn")
    assert not pg.is_visible("#miniWrap")
    pg.reload()
    pg.wait_for_selector("#tree .row")
    pg.evaluate("(d) => openDiagram(d)", d1)
    assert not pg.is_visible("#miniWrap") and not pg.is_checked("#miniOn")
    pg.check("#miniOn")
    assert pg.is_visible("#miniWrap")
    assert errors == []



def test_dgm08_14_copy_to_clipboard_and_zoom_out_far(sample, page_for):
    """REQ-DGM-08: the Export menu also copies the diagram to the clipboard as a PNG image.
    REQ-DGM-14: Fit and the mouse wheel zoom out down to 2%, so a large diagram fits."""
    m = sample.load()
    d1 = [i for i, d in m["diagrams"].items() if d["name"] == "Numbering overview"][0]
    far = sorted(m["diagrams"][d1]["nodes"])[0]
    do(sample, "diagram.layout", diagram=d1, element=far, x=30000, y=12000)
    pg, errors = page_for(sample)
    pg.context.grant_permissions(["clipboard-read", "clipboard-write"])
    pg.evaluate("(d) => openDiagram(d)", d1)
    pg.click("#btnExport")
    pg.click("#menu >> text=Copy image to clipboard")
    pg.wait_for_selector("#toast >> text=copied")
    got = pg.evaluate("""async () => { const items = await navigator.clipboard.read();
        const b = await items[0].getType('image/png'); return [items[0].types, b.size]; }""")
    assert "image/png" in got[0] and got[1] > 1000
    with pg.expect_download() as dl:                                       # large: the PNG is scaled down, not refused
        pg.click("#btnExport")
        pg.click("#menu >> text=PNG file")
    assert open(dl.value.path(), "rb").read(4) == b"\x89PNG"
    # Fit shows every node, far below the old 20% limit
    pg.click("#dtools >> text=Fit")
    k = pg.evaluate("view(S.active).k")
    assert 0.02 <= k < 0.05
    canvas = pg.locator("#canvas").bounding_box()
    for i in m["diagrams"][d1]["nodes"]:
        b = pg.locator('#canvas [data-kind=node][data-id="%s"]' % i).first.bounding_box()
        assert canvas["x"] <= b["x"] and b["x"] + b["width"] <= canvas["x"] + canvas["width"] + 1
        assert canvas["y"] <= b["y"] and b["y"] + b["height"] <= canvas["y"] + canvas["height"] + 1
    assert pg.locator("#canvas #grid").count() == 0                       # too dense to show at this zoom
    # the wheel stops at 2%
    pg.mouse.move(canvas["x"] + 300, canvas["y"] + 300)
    for _ in range(30):
        pg.mouse.wheel(0, 300)
    pg.wait_for_timeout(200)
    assert pg.evaluate("view(S.active).k") == 0.02
    assert errors == []



def test_dgm09_use11_12_shift_click_notes_mark_and_icon(sample, page_for):
    """REQ-DGM-09: Shift+click adds or removes an element like Ctrl+click (Shift+drag still selects a
    rectangle). REQ-USE-11: elements with notes are marked on the diagram and in the tree.
    REQ-USE-12: the page has its own icon for the browser tab (ADR-029)."""
    m = sample.load()
    top = {e["topic"]: i for i, e in m["elements"].items()}
    d1 = [i for i, d in m["diagrams"].items() if d["name"] == "Numbering overview"][0]
    r1, r2 = top["Every invoice gets a unique number"], top["Numbering has no gaps"]
    br1 = top["Invoice numbers are consecutive per fiscal year"]                # has notes, in a locked folder
    pg, errors = page_for(sample)
    pg.evaluate("(d) => openDiagram(d)", d1)
    node = lambda i: pg.locator('#canvas [data-kind=node][data-id="%s"]' % i).first

    def click(i, mods=None):
        node(i).click(position={"x": 20, "y": 30}, modifiers=mods or [])
        pg.wait_for_timeout(450)

    click(r1)
    click(r2, ["Shift"])
    assert pg.evaluate("selNodes()") == [r1, r2]
    click(r2, ["Shift"])
    assert pg.evaluate("selNodes()") == [r1]
    # notes mark: on the diagram next to the lock, in the tree; appears when notes are added
    badge = lambda i: pg.locator('#canvas [data-kind=node][data-id="%s"] [data-badge=notes]' % i)
    tree_mark = lambda i: pg.locator('#tree .row[data-kind=element][data-id="%s"] .nt' % i)
    assert badge(br1).count() == 1 and tree_mark(br1).count() == 1
    assert "Tax authority rule" in badge(br1).locator("title").text_content()
    assert badge(r1).count() == 0 and tree_mark(r1).count() == 0
    do(sample, "element.update", id=r1, notes="Asked by the auditors.")
    pg.evaluate("load()")
    pg.wait_for_timeout(300)
    assert badge(r1).count() == 1 and tree_mark(r1).count() == 1
    do(sample, "element.update", id=r1, notes="   ")
    pg.evaluate("load()")
    pg.wait_for_timeout(300)
    assert badge(r1).count() == 0                                          # blank notes are no notes
    # the tab icon
    icon = pg.evaluate("""async () => { const l = document.querySelector('link[rel=icon]'), r = await fetch(l.href);
        return [l.getAttribute('href'), r.status, r.headers.get('content-type'), (await r.text()).slice(0, 4)]; }""")
    assert icon == ["favicon.svg", 200, "image/svg+xml", "<svg"]
    assert errors == []


def test_dgm15_auto_size_keeps_text_visible_and_landscape(sample, page_for):
    """REQ-DGM-15 (ADR-030): with Auto size on (the default), a node is sized so that its whole topic, type and
    label show, with width / height above 1.2: when it is created, when its topic, label or type change (on every
    diagram, one undo step) and when its width is dragged. Off: sizes stay manual, any shape. Fit to text works
    either way."""
    m = sample.load()
    top = {e["topic"]: i for i, e in m["elements"].items()}
    d1 = [i for i, d in m["diagrams"].items() if d["name"] == "Numbering overview"][0]
    a1 = top["Allocate numbers from a database sequence table"]              # on all three diagrams
    r2 = top["Numbering has no gaps"]
    sample.undo_steps = 20
    pg, errors = page_for(sample)
    pg.evaluate("(d) => openDiagram(d)", d1)
    assert pg.is_checked("#autoSize")
    on_diagrams = lambda i: {d: dd["nodes"][i] for d, dd in sample.load()["diagrams"].items() if i in dd["nodes"]}
    landscape = lambda n: n["w"] / n["h"] > 1.2
    shows_all = lambda i: pg.evaluate("""(i) => { const g = document.querySelector('#canvas [data-kind=node][data-id="' + i + '"]');
        return !!g && ![...g.querySelectorAll('text')].some((t) => t.textContent.includes('…')); }""", i)
    long_topic = ("Allocate invoice numbers from a database sequence table that is locked per fiscal year, "
                  "reset on the first of January and audited every quarter by the finance team")
    # a topic change resizes the node on every diagram (not locked by someone else), as one undo step
    steps = pg.evaluate("S.undo.steps")
    pg.evaluate("(i) => select('element', i)", a1)
    pg.fill('#props .f:has(label:text-is("Topic")) textarea', long_topic)
    pg.locator("#canvas").click(position={"x": 5, "y": 5})                 # leave the field: saved
    pg.wait_for_timeout(500)
    sizes = on_diagrams(a1)
    assert len(sizes) == 3 and all(landscape(n) for n in sizes.values()), sizes
    assert all(n["h"] > 96 for n in sizes.values())                          # grew to show the text
    assert shows_all(a1) and pg.evaluate("S.undo.steps") == steps + 1
    # shorter text: the height shrinks again, the width stays
    pg.evaluate("(i) => select('element', i)", a1)
    pg.fill('#props .f:has(label:text-is("Topic")) textarea', "Use a sequence")
    pg.locator("#canvas").click(position={"x": 5, "y": 5})
    pg.wait_for_timeout(500)
    short = on_diagrams(a1)[d1]
    assert short["h"] < sizes[d1]["h"] and short["w"] == sizes[d1]["w"] and landscape(short)
    # dragging the width: the height follows, and it never turns portrait
    pg.evaluate("(i) => select('element', i)", r2)
    do(sample, "element.update", id=r2, topic=long_topic)
    pg.evaluate("load()")
    pg.wait_for_timeout(300)
    h = pg.locator('#canvas [data-kind=resize][data-id="%s"]' % r2).bounding_box()
    pg.mouse.move(h["x"] + 5, h["y"] + 5)
    pg.mouse.down()
    pg.mouse.move(h["x"] - 150, h["y"] + 200, steps=5)
    pg.mouse.up()
    pg.wait_for_timeout(500)
    n = on_diagrams(r2)[d1]
    assert landscape(n) and shows_all(r2), n
    # a new element is created at its fitted size
    pg.evaluate("() => { const v = view(S.active); v.k = 0.5; v.x = 20; v.y = 20; renderDiagram(); }")
    spot = pg.evaluate("""() => {                      // an empty place: the diagram fills the top left only
        const c = document.getElementById('canvas').getBoundingClientRect(), v = view(S.active), d = S.model.diagrams[S.active];
        const b = bounds(d); return [c.left + Math.min(c.width - 400, v.x + (b.x + b.w) * v.k + 30), c.top + 30]; }""")
    pg.mouse.click(spot[0], spot[1], button="right")
    pg.click("#menu >> text=New RISK here")
    pg.fill(".modal input", long_topic)
    pg.press(".modal input", "Enter")
    pg.wait_for_timeout(500)
    new = [i for i, e in sample.load()["elements"].items() if e["topic"] == long_topic and e["stereotype"] == "RISK"][0]
    n = on_diagrams(new)[d1]
    assert landscape(n) and n["h"] > 96 and shows_all(new), n
    # switched off: nothing is resized, and a manual resize may make any shape
    pg.uncheck("#autoSize")
    before = on_diagrams(a1)
    pg.evaluate("(i) => select('element', i)", a1)
    pg.fill('#props .f:has(label:text-is("Topic")) textarea', long_topic)
    pg.locator("#canvas").click(position={"x": 5, "y": 5})
    pg.wait_for_timeout(500)
    assert on_diagrams(a1) == before and not shows_all(a1)
    pg.evaluate("(i) => select('element', i)", r2)
    h = pg.locator('#canvas [data-kind=resize][data-id="%s"]' % r2).bounding_box()
    pg.mouse.move(h["x"] + 5, h["y"] + 5)
    pg.mouse.down()
    pg.mouse.move(h["x"] - 120, h["y"] + 300, steps=5)
    pg.mouse.up()
    pg.wait_for_timeout(500)
    assert not landscape(on_diagrams(r2)[d1])                                # portrait on purpose
    # Fit to text works with the switch off, for one element or a selection
    pg.locator('#canvas [data-kind=node][data-id="%s"]' % a1).first.click(button="right", position={"x": 20, "y": 30})
    pg.click("#menu >> text=Fit to text")
    pg.wait_for_timeout(500)
    assert landscape(on_diagrams(a1)[d1]) and shows_all(a1)
    pg.evaluate("(ids) => selectNodes(ids)", [a1, r2])
    pg.locator('#canvas [data-kind=node][data-id="%s"]' % r2).first.click(button="right", position={"x": 20, "y": 30})
    pg.click("#menu >> text=Fit to text")
    pg.wait_for_timeout(500)
    assert landscape(on_diagrams(r2)[d1]) and shows_all(r2)
    assert errors == [] and not V.errors(sample.load())


def test_dgm16_badges_fit_room_select_all_and_switching_auto_size_on(sample, page_for):
    """ADR-030: the label stays clear of the lock and notes badges, also in the fitted size; Fit keeps nodes out
    from under the overview; Ctrl+A selects every node of the diagram; switching Auto size on fits the selection."""
    m = sample.load()
    top = {e["topic"]: i for i, e in m["elements"].items()}
    d1 = [i for i, d in m["diagrams"].items() if d["name"] == "Numbering overview"][0]
    br1 = top["Invoice numbers are consecutive per fiscal year"]                # locked folder and notes: two badges
    r1, r2 = top["Every invoice gets a unique number"], top["Numbering has no gaps"]
    do(sample, "diagram.layout", diagram=d1, element=r1, w=90, h=200)          # unfitted
    pg, errors = page_for(sample)
    pg.evaluate("(d) => openDiagram(d)", d1)
    nodes = lambda: sample.load()["diagrams"][d1]["nodes"]

    def clear_of_badges(i):
        return pg.evaluate("""([i, label]) => { const g = document.querySelector('#canvas [data-kind=node][data-id="' + i + '"]');
            const t = [...g.querySelectorAll('text')].find((x) => x.textContent === label).getBoundingClientRect();
            const marks = [...g.querySelectorAll('circle')].map((c) => c.getBoundingClientRect()).filter((c) => c.top < t.bottom);
            return marks.length > 0 && marks.every((c) => t.right <= c.left); }""", [i, m["elements"][i]["label"]])
    assert clear_of_badges(br1)
    pg.evaluate("(i) => select('element', i)", br1)
    do(sample, "folder.unlock", id=m["elements"][br1]["folder"])              # ada's own lock; still the notes badge
    do(sample, "element.update", id=br1, label="CONSTRAINT-LONG-LABEL-0001")
    m = sample.load()
    pg.evaluate("load()")
    pg.wait_for_timeout(300)
    pg.locator('#canvas [data-kind=node][data-id="%s"]' % br1).first.click(button="right", position={"x": 60, "y": 50})
    pg.click("#menu >> text=Fit to text")
    pg.wait_for_timeout(400)
    assert clear_of_badges(br1)
    # Fit: no node under the overview
    pg.click("#dtools >> text=Fit")
    mini = pg.locator("#miniWrap").bounding_box()
    for i in nodes():
        b = pg.locator('#canvas [data-kind=node][data-id="%s"]' % i).first.bounding_box()
        assert b["x"] + b["width"] <= mini["x"] or b["y"] + b["height"] <= mini["y"], i
    # Ctrl+A selects every node of the open diagram
    pg.locator("#canvas").click(position={"x": 5, "y": 5})
    pg.keyboard.press("Control+a")
    assert sorted(pg.evaluate("selNodes()")) == sorted(nodes())
    # in the tree: the last selected is blue (sel), the others grey (sel2), the rest unmarked
    last = pg.evaluate("S.sel.id")
    marks = pg.evaluate("""() => Object.fromEntries([...document.querySelectorAll('#tree .row[data-kind=element]')]
        .map((r) => [r.getAttribute('data-id'), r.classList.contains('sel') ? 'sel' : r.classList.contains('sel2') ? 'sel2' : '']))""")
    assert marks[last] == "sel" and all(marks[i] == "sel2" for i in nodes() if i != last)
    assert all(v == "" for i, v in marks.items() if i not in nodes())
    # switching Auto size on fits the selected nodes, and only those
    pg.uncheck("#autoSize")
    pg.evaluate("(ids) => selectNodes(ids)", [r1])
    before = nodes()
    pg.check("#autoSize")
    pg.wait_for_timeout(400)
    after = nodes()
    assert after[r1]["w"] / after[r1]["h"] > 1.2 and after[r1] != before[r1]
    assert {i: n for i, n in after.items() if i != r1} == {i: n for i, n in before.items() if i != r1}
    assert errors == [] and not V.errors(sample.load())


def test_use13_ctrl_and_shift_click_in_the_explorer(sample, page_for):
    """REQ-USE-13: Ctrl+click and Shift+click on elements in the explorer add or remove them from the one selection
    the explorer and the open diagram share; those on the diagram are selected there too."""
    m = sample.load()
    top = {e["topic"]: i for i, e in m["elements"].items()}
    d1 = [i for i, d in m["diagrams"].items() if d["name"] == "Numbering overview"][0]
    r1, r2 = top["Every invoice gets a unique number"], top["Numbering has no gaps"]
    a1 = top["Allocate numbers from a database sequence table"]
    r3 = top["Corrections are made by credit note"]                         # not on this diagram
    pg, errors = page_for(sample)
    pg.evaluate("(d) => openDiagram(d)", d1)
    row = lambda i: pg.locator('#tree .row[data-kind=element][data-id="%s"] .t' % i)
    mark = lambda i: pg.evaluate("""(i) => { const r = document.querySelector('#tree .row[data-kind=element][data-id="' + i + '"]');
        return r.classList.contains('sel') ? 'last' : r.classList.contains('sel2') ? 'also' : ''; }""", i)
    row(r1).click()
    row(r2).click(modifiers=["Control"])
    row(a1).click(modifiers=["Shift"])
    assert pg.evaluate("selNodes()") == [r1, r2, a1]
    assert [mark(i) for i in (r1, r2, a1)] == ["also", "also", "last"]
    # an element that is not on the diagram joins the explorer selection only
    row(r3).click(modifiers=["Control"])
    assert mark(r3) == "last" and mark(a1) == "also"
    assert pg.evaluate("selNodes()") == [r1, r2, a1]                          # a1 is now the diagram's reference
    # clicking a selected one again removes it, in the explorer and on the diagram
    row(r2).click(modifiers=["Control"])
    assert mark(r2) == "" and pg.evaluate("selNodes()") == [r1, a1]
    # the diagram keeps the explorer-only element when it adds its own
    k1 = top["Rollback leaves a gap in the sequence"]
    pg.locator('#canvas [data-kind=node][data-id="%s"]' % k1).first.click(position={"x": 40, "y": 40}, modifiers=["Control"])
    assert mark(r3) == "also" and mark(k1) == "last" and pg.evaluate("selNodes()") == [r1, a1, k1]
    # a plain click starts again
    row(r1).click()
    assert pg.evaluate("selNodes()") == [r1] and mark(a1) == "" and mark(r3) == ""
    # dragging one of several selected rows takes them all: onto the diagram ...
    r4 = top["Invoices can be exported as PDF"]                             # not on this diagram either
    row(r3).click()
    row(r4).click(modifiers=["Control"])
    row(r4).drag_to(pg.locator("#canvas"), target_position={"x": 400, "y": 600})
    pg.wait_for_timeout(500)
    n = sample.load()["diagrams"][d1]["nodes"]
    assert r3 in n and r4 in n and n[r3]["y"] == n[r4]["y"] and n[r3]["x"] + n[r3]["w"] < n[r4]["x"]
    # ... and into another folder
    arch = [i for i, f in m["folders"].items() if f["name"] == "Architecture"][0]
    row(r3).click()
    row(r4).click(modifiers=["Shift"])
    pg.locator('#tree .row[data-kind=folder][data-id="%s"] .t' % arch).hover()
    row(r3).drag_to(pg.locator('#tree .row[data-kind=folder][data-id="%s"]' % arch))
    pg.wait_for_timeout(500)
    els = sample.load()["elements"]
    assert els[r3]["folder"] == arch and els[r4]["folder"] == arch
    # ... and before another element of that folder, as a block in their order
    from specgraph import ops as O
    first = O.tree_order(sample.load(), "elements", arch)[0]
    assert first not in (r3, r4)
    row(r3).click()
    row(r4).click(modifiers=["Control"])
    row(r4).drag_to(pg.locator('#tree .row[data-kind=element][data-id="%s"]' % first), target_position={"x": 60, "y": 2})
    pg.wait_for_timeout(500)
    assert O.tree_order(sample.load(), "elements", arch)[:3] == [r3, r4, first]
    assert errors == [] and not V.errors(sample.load())
