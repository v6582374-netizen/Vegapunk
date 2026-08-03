---
status: accepted
---

# Complete a Web Discovery Launch After PaperOrchestra

The Web product keeps one Discovery Launch active through its configured Discovery work and the automatically triggered PaperOrchestra Run, and exposes the Launch as terminal only after PaperOrchestra itself reaches a terminal outcome. This preserves the existing `launch_discovery.py` contract, prevents the browser from reporting completion while Paper generation is still running, and avoids duplicate starts caused by a prematurely completed Launch.

**Considered Options**

- Mark the Launch completed when `discovery_summary.json` is written and run PaperOrchestra separately. Rejected because the current production flow synchronously hands off to PaperOrchestra and the user-facing Launch would have an ambiguous owner and completion time.
- Make PaperOrchestra a new Web resource unrelated to the Launch. Rejected because one Launch owns at most one automatic Paper and its artifacts.
