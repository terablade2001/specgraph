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
    pg.mouse.click(cb["x"] + cb["width"] - 330, cb["y"] + cb["height"] - 120, button="right")
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
        pg.click("text=Export SVG")
    svg = open(dl.value.path(), encoding="utf-8").read()
    assert svg.startswith("<svg") and "REQ-001" in svg and "data-ui" not in svg
    with pg.expect_download() as dl:
        pg.click("text=Export PNG")
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
