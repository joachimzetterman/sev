"""Render the annotation reference from the exact definitions supplied to models."""

from pathlib import Path

from sev.taxonomy import EVALS, STATE_DEFINITIONS, VERSION


def main():
    lines = ["# Security eval taxonomy", "", f"Version: `{VERSION}`. Generated from `sev/taxonomy.py`.", "",
             "## Annotation rules", "",
             "Judge the before-to-after behaviour using only the supplied diff and context. "
             "Labels describe relevance or change, except the explicitly directional PRIVILEGE_INCREASE. "
             "A fix can be YES. NO never certifies security. Pure renames and comments do not change runtime behaviour.", ""]
    for state, definition in STATE_DEFINITIONS.items():
        lines.extend([f"- **{state}:** {definition}"])
    lines.extend(["", "UNKNOWN records conflicting or semantically ambiguous evidence. "
                  "INSUFFICIENT_CONTEXT identifies a specific missing deciding fact. An algorithm that cannot answer "
                  "may separately abstain (`probabilities: null`); this is not a gold semantic state. "
                  "A model's low confidence is also not an annotation of UNKNOWN.", "",
                  "An absent route-level check does not establish a vulnerability. A supplied applicable middleware "
                  "check can establish control evidence, while authorization relevance remains YES in both cases. "
                  "PRIVILEGE_INCREASE often needs effective policy, not just a changed Allow statement. "
                  "A future control-evidence eval should be separately defined if the pilot needs it.", "",
                  "## Overlap and excluded labels", "",
                  "AUTHORIZATION_RELEVANT is broad; AUTHORIZATION_BOUNDARY_CHANGE concerns enforcement; "
                  "PRIVILEGE_INCREASE is directional; TENANT_BOUNDARY_CHANGE concerns an explicit partition. "
                  "They may all be YES on one change, but a correctly protected new route can be relevant "
                  "without proving an altered gate or effective privilege increase. Do not enforce these relations "
                  "as automatic gold labels; measure annotation consistency first.", "",
                  "SENSITIVE_DATA_HANDLING asks what data is handled; DATA_EXPOSURE_CHANGE asks who can observe it. "
                  "NETWORK_EGRESS_CHANGE is concrete transport behaviour; TRUST_BOUNDARY_CHANGE requires "
                  "explicit trust-domain evidence. The latter is a candidate for removal if raters cannot agree.", "",
                  "SECRET_EXPOSURE_RISK is deferred to deterministic scanners plus contextual data handling. "
                  "EXTERNAL_INTERACTION_CHANGE overlaps egress, exposure and trust. AUDIT_EVENT_REQUIRED and "
                  "SECURITY_REVIEW_REQUIRED require an organisation's policy and are deferred to routing. "
                  "Keep the 14 definitions provisional until the independent annotation pilot is complete.", "",
                  "## Per-eval definitions and examples", ""])
    for name, entry in EVALS.items():
        lines.extend([f"### {name}", "", entry["question"], "", entry["definition"], ""])
        for key, title in (("positive", "YES"), ("negative", "NO"), ("ambiguous", "UNKNOWN"), ("insufficient_context", "INSUFFICIENT_CONTEXT")):
            lines.append(f"- **{title}:** {entry[key]}")
        lines.append("")
    target = Path(__file__).resolve().parents[1] / "docs/taxonomy.md"
    target.parent.mkdir(exist_ok=True)
    target.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
