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
    return {"label": None, "description": "", "fill": fill, "border": border, "icon": icon, "shape": shape,
            "labelPrefix": prefix, "statuses": None, "retired": False, "fields": fields or {}}


def default_stereotypes():
    owner = {"owner": _f("Owner")}
    priority = {"priority": _f("Priority", "enum", ["Must", "Should", "Could"]), "owner": _f("Owner")}
    levels = ["Low", "Medium", "High"]
    table = {
        "ADR": ("#dbeafe", "#1d4ed8", "⚖", "rounded", "ADR", owner),
        "REQ": ("#dcfce7", "#15803d", "☑", "rect", "REQ", priority),
        "NAMESPACE": ("#e0e7ff", "#4338ca", "◫", "rect", "NS", None),
        "RISK": ("#fee2e2", "#b91c1c", "⚠", "ellipse", "RISK",
                 {"severity": _f("Severity", "enum", levels), "likelihood": _f("Likelihood", "enum", levels)}),
        "ISSUE": ("#ffedd5", "#c2410c", "⚑", "rounded", "ISS", owner),
        "B-REQ": ("#d1fae5", "#047857", "◆", "rect", "B-REQ", priority),
        "U-REQ": ("#ccfbf1", "#0f766e", "☺", "rounded", "U-REQ", priority),
        "CONSTRAINT": ("#fef3c7", "#b45309", "⊗", "hexagon", "CON", owner),
        "TEMPORAL-ADR": ("#cffafe", "#0e7490", "◷", "rounded", "T-ADR", owner),
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
        out[key]["description"] = STEREOTYPE_DESCRIPTIONS[key]
    return out


# Short generic meanings of the initial types (ADR-033). A project rewrites them for its own domain;
# the tool stores and shows them and never interprets them.
STEREOTYPE_DESCRIPTIONS = {
    "ADR": "Architecture decision: a choice made, the options considered and why. Usually implements requirements.",
    "REQ": "System requirement: one behaviour or quality the product must have, specific enough to test.",
    "NAMESPACE": "Grouping element that gives a name to a part of the system; carries no requirement itself.",
    "RISK": "Something that may go wrong, with its severity and likelihood. Decisions mitigate it.",
    "ISSUE": "An open problem or question found during the work, to be resolved.",
    "B-REQ": "Business requirement: a goal of the organisation that pays for the product. User requirements refine it.",
    "U-REQ": "User requirement: what a user needs to do, in the user's words. Features refine it.",
    "CONSTRAINT": "A limit the solution must respect (law, policy, budget, existing systems), not chosen by the project.",
    "TEMPORAL-ADR": "A decision meant to hold only for a while; its notes say when it is reviewed.",
    "FEAT": "Feature: a coherent piece of product functionality that delivers user requirements.",
    "TEST-E2E": "End-to-end test: checks a requirement through the whole system as a user would.",
    "TEST-INT": "Integration test: checks a requirement across two or more components.",
    "ASSET": "Something the system uses or produces (data, device, document) that requirements refer to.",
    "DOC": "A document outside the model that elements refer to.",
}


def default_config():
    return {
        "stereotypes": default_stereotypes(),
        "statuses": {
            "proposed": {"description": "Written down, not yet agreed.", "label": "Proposed", "color": "#6b7280", "symbol": "?", "order": 10, "retired": False},
            "approved": {"description": "Agreed by the people who decide; work may start.", "label": "Approved", "color": "#2563eb", "symbol": "✓", "order": 20, "retired": False},
            "validated": {"description": "Checked to be right, for example reviewed or tested, but not yet delivered.", "label": "Validated", "color": "#7c3aed", "symbol": "✔", "order": 30, "retired": False},
            "implemented": {"description": "Delivered in the product.", "label": "Implemented", "color": "#15803d", "symbol": "●", "order": 40, "retired": False},
            "rejected": {"description": "Considered and turned down; kept for the record.", "label": "Rejected", "color": "#dc2626", "symbol": "✕", "order": 50, "retired": False},
            "deprecated": {"description": "Was valid, no longer is; kept for the record.", "label": "Deprecated", "color": "#78716c", "symbol": "⊘", "order": 60, "retired": False},
        },
        "linkTypes": {
            "depends_on": {"description": "The source needs the target: if the target changes, the source may have to change.", "label": "depends on", "lineStyle": "solid", "color": "#374151",
                           "sourceArrow": "none", "targetArrow": "open", "showLabel": True,
                           "routing": "auto", "traceable": True, "sources": None, "targets": None,
                           "retired": False},
            "trace": {"description": "General traceability from the source to the target, when no more specific type fits.", "label": "trace", "lineStyle": "dashed", "color": "#6b7280",
                      "sourceArrow": "none", "targetArrow": "open", "showLabel": False,
                      "routing": "straight", "traceable": True, "sources": None, "targets": None,
                      "retired": False},
            "implements": {"description": "The source realises the target, for example a decision that meets a requirement.", "label": "implements", "lineStyle": "dashed", "color": "#1d4ed8",
                           "sourceArrow": "none", "targetArrow": "hollow-triangle", "showLabel": True,
                           "routing": "auto", "traceable": True, "sources": None,
                           "targets": None, "retired": False},
            "refines": {"description": "The source details the target: a more concrete statement of the same need.", "label": "refines", "lineStyle": "solid", "color": "#15803d",
                        "sourceArrow": "none", "targetArrow": "triangle", "showLabel": True,
                        "routing": "auto", "traceable": True, "sources": None, "targets": None,
                        "retired": False},
            "mitigates": {"description": "The source reduces the target risk.", "label": "mitigates", "lineStyle": "solid", "color": "#b91c1c",
                          "sourceArrow": "none", "targetArrow": "open", "showLabel": True,
                          "routing": "auto", "traceable": True, "sources": None,
                          "targets": None, "retired": False},
            "relates_to": {"description": "A loose association for orientation only; not followed for traceability.", "label": "relates to", "lineStyle": "dotted", "color": "#9ca3af",
                           "sourceArrow": "none", "targetArrow": "none", "showLabel": False,
                           "routing": "straight", "traceable": False, "sources": None,
                           "targets": None, "retired": False},
            "association": {"description": "A plain connection between two elements, as on a diagram; not followed for traceability.", "label": "association", "lineStyle": "solid", "color": "#6b7280",
                            "sourceArrow": "none", "targetArrow": "none", "showLabel": True,
                            "routing": "auto", "traceable": False, "sources": None,
                            "targets": None, "retired": False},
        },
        "coverageRules": {},
    }
