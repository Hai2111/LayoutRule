#!/usr/bin/env python3
"""Deterministic candidate gate; never equate technical quality with owner acceptance."""


def compare(previous, proposed):
    """Return (accept, reason). Reject technical regressions before aesthetics."""
    needed = ("drc_errors", "unconnected", "audit_fail", "keepout_fail", "via_count", "trace_mm")
    for record in (previous, proposed):
        for key in needed:
            value = record.get(key)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                return False, f"invalid measurement: {key}"
        if not record.get("board_sha256"):
            return False, "missing board SHA"
    if previous["board_sha256"] == proposed["board_sha256"]:
        return False, "unchanged PCB"
    hard = ("drc_errors", "unconnected", "audit_fail", "keepout_fail")
    regressed = [k for k in hard if proposed[k] > previous[k]]
    if regressed:
        return False, "technical regression: " + ", ".join(regressed)
    improved = [k for k in hard if proposed[k] < previous[k]]
    if improved:
        return True, "improved: " + ", ".join(improved)
    if proposed["via_count"] > previous["via_count"]:
        return False, "via count increased without technical improvement"
    if proposed["trace_mm"] > previous["trace_mm"] + 0.01:
        return False, "trace length increased without technical improvement"
    if proposed["via_count"] < previous["via_count"] or proposed["trace_mm"] < previous["trace_mm"] - 0.01:
        return True, "lower via or copper complexity without checked regression"
    return False, "no independently measured improvement"
