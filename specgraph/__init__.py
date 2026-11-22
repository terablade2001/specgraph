"""Repo-based graph of specifications.

Names and defaults used across the tool are defined here.
"""
TOOL_NAME = "specgraph"
VERSION = "0.4.0"
MODEL_FILENAME = "specmodel.json"
FORMAT = TOOL_NAME + "-model"
FORMAT_VERSION = 3          # 2: elements carry modified {at, by} (ADR-016); 3: types carry a description (ADR-033)
READABLE_VERSIONS = (1, 2, 3)  # older versions are upgraded by the first change
DEFAULT_UNDO = 20           # undo steps the editor keeps (ADR-017)
SIG_NAMESPACE = TOOL_NAME
