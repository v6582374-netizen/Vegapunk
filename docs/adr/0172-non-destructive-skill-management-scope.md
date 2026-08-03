---
status: accepted
---

# Keep Skill Management Non-Destructive for Skill Bodies

Skill Management will not provide direct Skill-content editing or Skill deletion in the current scope.
This removes the high-risk body mutation and cleanup responsibilities from the manager; the remaining inventory, inspection, provenance, and Tool-projection boundaries are decided separately.
The mutation rules in ADR 0171 for synchronized editing and deletion are therefore not implementation requirements for this scope.
Tool projection management remains in scope: an explicit Apply may create or repair a symlink, and On -> Off may remove only that Tool's symlink projection without touching the Skill Body.
Evidence-backed Manual Removal Commands also remain as read-only guidance; Skill Management never executes them or treats copying one as deletion intent.
Manager-owned metadata such as favorites, tags, ordering, and local notes remains editable because it affects only the manager's presentation and not any Skill Body, Tool path, or source file.
Risk scanning, LLM review, Skill translation, and other AI analysis are outside the current V1 scope; the manager does not require a model provider for discovery, inspection, metadata, or projection.
The previous analysis-result persistence rule is deferred with those capabilities and is not a current implementation requirement.
Skill Usage Monitor is outside the scope: Skill Management does not install or manage tool hooks, collect invocation counts, or store Skill usage history.
Skill acquisition is outside the scope: Skill Management does not install, download, import, copy, or move Skill Bodies; external installers and Tool-native workflows provide the bodies that Refresh discovers.
Skill creation is also outside the scope; the manager never creates a new Skill Body or a body-less placeholder Skill.
Project-level Skill management is outside the scope: Version 1 has no ProjectBinding, active project selection, project-scoped Skill identity, project Skill discovery, project Apply, or project projection removal.
Native Tools may continue to read project-level Skill directories through their own behavior, but Skill Management does not inspect or modify those directories.
Tool support is a fixed allowlist of exactly five predefined Skill Tool Targets in Version 1.
Custom Tool registration and Custom Tool create, edit, or delete operations are outside the scope.
The allowlist replaces the former Antigravity entry with Kimi Code.
Kimi Code's canonical Tool ID is `kimi-code`, its display name is `Kimi Code`, and its CLI command is `kimi`.
The official Kimi Code configuration directory is `~/.kimi-code/`, relocatable through `KIMI_CODE_HOME`.
Its user Skill root is `$KIMI_CODE_HOME/skills/` (`~/.kimi-code/skills/` by default), and its shared user Skill root is `~/.agents/skills/`.
Its project Skill roots are native Tool sources outside Skill Management's discovery and projection boundary.
These paths come from the native Kimi Code adapter and must not be inferred from or mapped to `.antigravity`.
See the [Kimi Code configuration files documentation](https://moonshotai.github.io/kimi-code/en/configuration/config-files) and [Agent Skills documentation](https://moonshotai.github.io/kimi-code/en/customization/skills).
Each predefined Tool adapter may expose one or more native Tool Skill Roots.
The UI and Skill metadata present one Tool row per predefined Tool, while discovery retains every concrete root path and its installation provenance.
Tool Skill Applicability is aggregated across the roots: it is On when at least one usable root contains readable Skill content and Off when no root does.
If any root contains the real Skill Body, the aggregate state takes the Body-Hosting form: green On with a disabled switch, even when another root contains a valid symlink projection for the same Skill.
In that mixed state, the symlink remains visible as detail-level provenance but the aggregate On -> Off action does not remove it, because the Tool is already applicable through the real Body.
If no real Body exists and one or more valid symlink projections exist, the aggregate state is yellow On with an enabled switch.
If broken symlink roots coexist with those valid projections, they remain visible as error details while the aggregate state stays yellow On.
On -> Off removes all valid and broken symlink entries for that Skill under that Tool in one atomic Tool-level operation and never removes the resolved Skill Body.
Each Tool adapter declares one Canonical Tool Projection Root for Apply.
If the canonical root does not exist, an explicit Apply may create the directory before creating or repairing the symlink; Refresh never creates it implicitly.
Apply writes only that canonical root's directory entry and symlink; additional user, shared, or fallback roots remain discovery and inspection sources and do not receive implicit Apply writes.
This target is an adapter fact and never comes from an implicit active project or global/project UI context.
For Kimi Code, the Canonical Tool Projection Root is `~/.kimi-code/skills/`; its `.agents/skills/` is discovery-only, and its project roots are outside Skill Management's boundary.
Projection changes are explicit and per Tool; the current scope does not provide batch Apply or batch projection removal.
Read-only Skill Body inspection remains in scope, including a native Open in Finder action; inspection and reveal actions never write to Skill content or filesystem structure.
The card-level reveal targets the resolved Skill Body, while a Tool-level reveal targets that Tool's installation entry; their detailed presentation is deferred to a later prototype.
Skill applicability distinguishes an available Tool with no current installation (`Off`) from an unavailable or unconfigured Tool (`Unavailable`); Apply is offered only for the former.
