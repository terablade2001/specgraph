"""Initial configuration (REQ-CFG-08). Everything here is editable in the tool."""

SHAPES = ("rect", "rounded", "hexagon", "ellipse")
LINE_STYLES = ("solid", "dashed", "dotted")
ARROWS = ("none", "open", "triangle", "hollow-triangle", "diamond", "hollow-diamond")
ROUTINGS = ("straight", "auto", "custom")
FIELD_TYPES = ("string", "text", "number", "boolean", "enum", "date")


def _f(label, type_="string", options=None):
    field = {"label": label, "type": type_}
    if options:
        field["options"] = options
    return field


def _stereotype(fill, border, icon, shape, prefix, fields=None):
    return {"label": None, "fill": fill, "border": border, "icon": icon, "shape": shape,
            "labelPrefix": prefix, "statuses": None, "retired": False, "fields": fields or {}}


def default_stereotypes():
    owner = {"owner": _f("Owner")}
    priority = {"priority": _f("Priority", "enum", ["Must", "Should", "Could"]), "owner": _f("Owner")}
    levels = ["Low", "Medium", "High"]
    table = {
        "ADR": ("#dbeafe", "#1d4ed8", "⚖", "rounded", "ADR",
                {"decisionDate": _f("Decision date", "date"), "owner": _f("Owner")}),
        "REQ": ("#dcfce7", "#15803d", "☑", "rect", "REQ", priority),
        "NAMESPACE": ("#e0e7ff", "#4338ca", "◫", "rect", "NS", None),
        "RISK": ("#fee2e2", "#b91c1c", "⚠", "ellipse", "RISK",
                 {"severity": _f("Severity", "enum", levels), "likelihood": _f("Likelihood", "enum", levels)}),
        "ISSUE": ("#ffedd5", "#c2410c", "⚑", "rounded", "ISS", owner),
        "B-REQ": ("#d1fae5", "#047857", "◆", "rect", "B-REQ", priority),
        "U-REQ": ("#ccfbf1", "#0f766e", "☺", "rounded", "U-REQ", priority),
        "CONSTRAINT": ("#fef3c7", "#b45309", "⊗", "hexagon", "CON", owner),
        "TEMPORAL-ADR": ("#cffafe", "#0e7490", "◷", "rounded", "T-ADR",
                         {"decisionDate": _f("Decision date", "date"), "owner": _f("Owner")}),
        "FEAT": ("#fef9c3", "#a16207", "★", "rounded", "FEAT", owner),
        "TEST-E2E": ("#ede9fe", "#6d28d9", "⇄", "rect", "E2E", owner),
        "TEST-INT": ("#fae8ff", "#a21caf", "⇆", "rect", "INT", owner),
        "ASSET": ("#f3f4f6", "#4b5563", "▤", "rect", "ASSET", None),
        "DOC": ("#f1f5f9", "#475569", "☰", "rect", "DOC", None),
    }
    out = {}
    for key, (fill, border, icon, shape, prefix, fields) in table.items():
        out[key] = _stereotype(fill, border, icon, shape, prefix, fields)
        out[key]["label"] = key
    return out


def default_config():
    return {
        "stereotypes": default_stereotypes(),
        "statuses": {
            "proposed": {"label": "Proposed", "color": "#6b7280", "symbol": "?", "order": 10, "retired": False},
            "approved": {"label": "Approved", "color": "#2563eb", "symbol": "✓", "order": 20, "retired": False},
            "validated": {"label": "Validated", "color": "#7c3aed", "symbol": "✔", "order": 30, "retired": False},
            "implemented": {"label": "Implemented", "color": "#15803d", "symbol": "●", "order": 40, "retired": False},
            "rejected": {"label": "Rejected", "color": "#dc2626", "symbol": "✕", "order": 50, "retired": False},
            "deprecated": {"label": "Deprecated", "color": "#78716c", "symbol": "⊘", "order": 60, "retired": False},
        },
        "linkTypes": {
            "depends_on": {"label": "depends on", "lineStyle": "solid", "color": "#374151",
                           "sourceArrow": "none", "targetArrow": "open", "showLabel": True,
                           "routing": "auto", "traceable": True, "sources": None, "targets": None,
                           "retired": False},
            "trace": {"label": "trace", "lineStyle": "dashed", "color": "#6b7280",
                      "sourceArrow": "none", "targetArrow": "open", "showLabel": False,
                      "routing": "straight", "traceable": True, "sources": None, "targets": None,
                      "retired": False},
            "implements": {"label": "implements", "lineStyle": "dashed", "color": "#1d4ed8",
                           "sourceArrow": "none", "targetArrow": "hollow-triangle", "showLabel": True,
                           "routing": "auto", "traceable": True, "sources": None,
                           "targets": None, "retired": False},
            "refines": {"label": "refines", "lineStyle": "solid", "color": "#15803d",
                        "sourceArrow": "none", "targetArrow": "triangle", "showLabel": True,
                        "routing": "auto", "traceable": True, "sources": None, "targets": None,
                        "retired": False},
            "mitigates": {"label": "mitigates", "lineStyle": "solid", "color": "#b91c1c",
                          "sourceArrow": "none", "targetArrow": "open", "showLabel": True,
                          "routing": "auto", "traceable": True, "sources": None,
                          "targets": None, "retired": False},
            "relates_to": {"label": "relates to", "lineStyle": "dotted", "color": "#9ca3af",
                           "sourceArrow": "none", "targetArrow": "none", "showLabel": False,
                           "routing": "straight", "traceable": False, "sources": None,
                           "targets": None, "retired": False},
            "association": {"label": "association", "lineStyle": "solid", "color": "#6b7280",
                            "sourceArrow": "none", "targetArrow": "none", "showLabel": True,
                            "routing": "auto", "traceable": False, "sources": None,
                            "targets": None, "retired": False},
        },
        "coverageRules": {},
    }
