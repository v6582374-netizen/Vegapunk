---
status: superseded by ADR-0101
---

# Use ElegantPaper for the Paper

Vegapunk will use ElegantPaper as the default LaTeX template family for the Paper instead of its conference-specific ICLR 2026 template or PaperOrchestra's bundled ICLR 2025 and CVPR 2025 templates. ElegantPaper is a general-purpose class with an explicit Chinese mode, so it supports a Chinese-first publication-oriented manuscript while Target Venue remains deferred. Template choice governs presentation rather than the Adaptive Argument Structure under ADR-0051, and the PDF compilation path must support XeLaTeX because ElegantPaper requires it for Chinese content.

Vegapunk will import the complete ElegantPaper project source and maintain an adapted project-local copy rather than relying on a globally installed CTAN package or copying only `elegantpaper.cls`. This keeps the upstream examples, build metadata, license, and provenance available while allowing the template project to evolve with the Paper. Any modified upstream component must remain distinguishable from the original and carry the notices required by the LaTeX Project Public License 1.3c; integration-specific files should be added separately when modifying the class itself is unnecessary.

The imported source will live at `tex_templates/elegantpaper/` as ordinary files tracked by Vegapunk, not as a nested Git repository or submodule. The directory will retain the upstream README and license and add an `UPSTREAM.md` recording the source URL, imported version and commit, and local adaptation history. This makes every PaperOrchestra Run independent of another repository checkout while keeping the origin and changes auditable.

The default `template.tex` will use ElegantPaper's Chinese mode, and PaperOrchestra will write the title, abstract, section headings, and explanatory prose of the Paper in Chinese. Model names, code identifiers, dataset names, cited paper titles, and technical terms may remain in their authoritative original language. The initial workflow will not generate mirrored Chinese and English bodies, because duplicated prose introduces avoidable translation drift and makes the two narratives difficult to keep evidentially aligned.

The upstream `elegantpaper-cn.tex` will remain unchanged as a usage guide and compilation example. Vegapunk will keep a separate, concise `template.tex` containing the ElegantPaper document setup, paper metadata placeholders, bibliography declaration, and empty document body without a fixed scientific section skeleton. This shared template source remains read-only at runtime while each PaperOrchestra Run owns its editable Paper source.

The first runnable integration guarantees only the built-in `tex_templates/elegantpaper/` path from shared template use through writing, XeLaTeX/Biber compilation, and PDF review. The runtime will not add a template registry, plugin interface, or capability-description system. Additional selectable templates will be integrated only after the ElegantPaper path runs end to end.

This decision supersedes ADR-0005's choice of Vegapunk's ICLR 2026 directory as the default template source. It does not change ADR-0005's rejection of a runtime template translation layer: the selected template directory remains directly consumable by the writing and compilation runtime.

**Considered Options**

- Continue with Vegapunk's ICLR 2026 template. Rejected because it is tied to a specific conference and its official shell is less suitable as the basis of a Chinese-first, general Paper.
- Use PaperOrchestra's bundled ICLR 2025 or CVPR 2025 template. Rejected because both are older, venue-specific templates and neither addresses the Chinese typesetting requirement.
- Keep ElegantPaper as a nested Git repository or submodule. Rejected because Vegapunk must own and reproduce the adapted template without requiring a separately published fork or a second repository checkout.
