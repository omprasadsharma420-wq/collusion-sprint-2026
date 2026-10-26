"""One-time, offline extraction of researcher-approved V7 visible bytes."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "researcher_analysis_20261026_v7/CBS_V7_APPROVAL_AND_OFFLINE_RESULTS.md"
HANDOFF = Path("C:/Users/ompra/.codex/attachments/a90b477a-fb4c-4bfd-8521-f2d4a291e837/Pasted text.txt")
OUT = ROOT / "v7_approved_interface"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    report_bytes = REPORT.read_bytes()
    report = report_bytes.decode("utf-8").replace("\r\n", "\n")
    handoff_bytes = HANDOFF.read_bytes()
    handoff = handoff_bytes.decode("utf-8").replace("\r\n", "\n")
    systems = re.findall(r"#### Worker ([ABCD]); reporting_reminder=(OFF|ON)\s+```text\n(.*?)\n```", report, re.S)
    if len(systems) != 8 or len({(a, r) for a, r, _ in systems}) != 8:
        raise ValueError("Expected eight exact V7 candidate system messages")
    first_section = report.split("### Candidate first user messages (fully expanded)", 1)[1].split(
        "### Candidate complete tool JSON schemas", 1)[0]
    first = re.findall(r"#### Worker ([ABCD])\s+```text\n(.*?)\n```", first_section, re.S)
    if len(first) != 4 or len({a for a, _ in first}) != 4:
        raise ValueError("Expected four exact V7 first-user messages")
    tool_section = report.split("### Candidate complete tool JSON schemas", 1)[1].split(
        "### Candidate source artifacts", 1)[0]
    proposed = json.loads(re.search(r"```json\n(.*?)\n```", tool_section, re.S).group(1))
    marker = handoff.index('{\n  "type": "function",\n  "function": {\n    "name": "submit_work"')
    replacement, _ = json.JSONDecoder().raw_decode(handoff[marker:])
    names = [tool["function"]["name"] for tool in proposed]
    if len(names) != 12 or names.count("submit_work") != 1 or replacement["function"]["name"] != "submit_work":
        raise ValueError("Unexpected ordered tool set or replacement")
    approved = list(proposed)
    approved[names.index("submit_work")] = replacement
    if any(approved[i] != proposed[i] for i, name in enumerate(names) if name != "submit_work"):
        raise AssertionError("Non-submit tool changed")
    prompt_data = {"system": {reminder: {actor: text for a, r, text in systems
                                              if r == reminder for actor in (a,)}
                              for reminder in ("OFF", "ON")},
                   "first_user": {actor: text for actor, text in first}}
    OUT.mkdir(exist_ok=True)
    (OUT / "prompts.json").write_text(json.dumps(prompt_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "tools.json").write_text(json.dumps(approved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "source_provenance.json").write_text(json.dumps({
        "local_v7_report_sha256": sha(report_bytes),
        "researcher_handoff_sha256": sha(handoff_bytes),
        "reported_review_copy_sha256": "aa748cd96883a1c4f6955302bbf8bacce067efe1f9d66137facb8ae0882bee64",
        "prompt_source": str(REPORT), "replacement_schema_source": str(HANDOFF),
        "ordered_tool_names": names,
        "changed_tool_name": "submit_work",
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"local_report_sha256": sha(report_bytes),
                      "handoff_sha256": sha(handoff_bytes),
                      "prompt_variants": len(systems), "first_user_messages": len(first),
                      "tool_count": len(approved), "tool_names": names}, indent=2))


if __name__ == "__main__":
    main()
