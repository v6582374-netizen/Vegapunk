# Open User-Visible PDFs in the Browser-Native Reader

Type: specification
Status: ready-for-agent
Labels: ready-for-agent

## Problem Statement

The Unified Workspace currently shows a static, invented paper PDF in an Artifact Preview side panel.
That test-only surface consumes core workspace width, misrepresents a real artifact as available, and cannot provide the browser's established PDF reading experience.
The product has one Unified Workspace for the Sole Researcher and no administrator-facing product surface.

## Solution

Remove the test-only PDF from Project Space and remove its Artifact Preview side panel completely.
When the Unified Workspace later presents a real user-visible PDF artifact, it must open the artifact URL in a separate browser tab through the Browser PDF Reader.
The browser, rather than the Workspace, owns zoom, search, pagination, printing, downloading, and any user browser setting that elects to download instead of display the file.

## User Stories

1. As the Sole Researcher, I want the Unified Workspace to omit a fabricated paper PDF when no real paper artifact exists, so that the workspace never implies that research output is available when it is not.
2. As the Sole Researcher, I want Project Space to use its full primary work area after the test preview is removed, so that research context is not compressed by a nonessential side panel.
3. As the Sole Researcher, I want a real PDF artifact to open in a separate browser tab, so that I can use the browser's native PDF reading controls.
4. As the Sole Researcher, I want the original Unified Workspace tab to remain unchanged when I open a PDF, so that I can return to my research context without restoring a transient preview state.
5. As the Sole Researcher, I want browser search, zoom, printing, downloading, and accessibility features to operate on a real PDF, so that document reading follows familiar browser behavior.
6. As the Sole Researcher, I want PDF opening to be a normal user-initiated link action, so that the browser does not treat it as an unsolicited popup.
7. As the Sole Researcher, I want a browser setting that downloads PDFs instead of displaying them to be respected, so that the product does not override my local browser preferences.
8. As the Sole Researcher, I want closing a PDF tab to return me to the exact Workspace state I left, so that reading a paper does not interrupt the active module or its context.
9. As the Sole Researcher, I want all future user-visible PDF links to follow one opening rule, so that document behavior is predictable across Unified Workspace modules.
10. As the Sole Researcher, I want non-PDF artifact behavior to remain independent of PDF opening behavior, so that removing the PDF preview does not regress other Workspace capabilities.
11. As the Sole Researcher, I want PDF opening to remain inside the single Unified Workspace product boundary, so that it never requires an administrator route, sign-in, or role-specific navigation.
12. As the Sole Researcher, I want the workspace to contain only genuine research artifacts, so that test material cannot be confused with research output.

## Implementation Decisions

- The product vocabulary is Browser PDF Reader: the browser-native PDF viewer opened in a separate tab for every user-visible PDF artifact.
- The existing test-only Project Space PDF row, its side-panel Artifact Preview, its preview-open state, and CSS that exists solely for that preview will be removed.
- The removal must leave the Unified Workspace layout in its normal full-width central-work-area state.
- A future genuine PDF artifact will be rendered through one user-facing PDF-link seam that navigates directly to the artifact URL in a separate tab.
- The link must be activated by the user and must include the standard protection for a newly opened browsing context.
- No embedded PDF frame, in-page PDF canvas, custom PDF controls, modal PDF reader, or simulated first-page preview will be introduced.
- The browser response for a future real PDF must be usable by the browser as a PDF document.
- The application must not force an operating-system desktop PDF application, because a browser Web application cannot reliably do so.
- The scope is the active Unified Workspace only.
- Legacy administrator components, administrator APIs, administrator-route retirement, and System Settings API migration are separate work and are not implementation targets for this specification.

## Testing Decisions

- The highest and only product seam is the Unified Workspace's user-visible artifact-opening action.
- Tests must assert observable behavior rather than component state, class names, or internal rendering details.
- The removal verification must show that Project Space no longer presents the fabricated PDF or a right-side PDF reader and that the central workspace remains usable at the supported desktop layout.
- When a genuine PDF artifact source is introduced, one browser-level test must verify that activating its Workspace link opens the direct PDF URL in a separate tab rather than an embedded reader or administrator route.
- The browser-level test must accept the browser's configured download behavior as valid after the direct PDF navigation is initiated.
- Frontend linting and production building remain required checks.
- The existing single-page frontend-hosting tests are prior art for validating the deployed Unified Workspace entry point and must continue to pass.

## Out of Scope

- Adding a real PDF artifact source, paper-generation workflow, artifact catalog, or document storage API.
- Preserving, replacing, or enhancing the removed test PDF with a sample document.
- Creating a custom PDF reader, side panel, modal, iframe, canvas renderer, annotation system, or document-history feature.
- Opening PDFs through the operating system's default desktop application.
- Restoring an administrator route or making legacy administrator components part of the Unified Workspace.
- Deleting or migrating legacy administrator backend code and APIs.
- Changes to non-PDF artifact presentation.

## Further Notes

The decision supersedes the prior test-only PDF side-preview behavior.
It is consistent with the Unified Workspace boundary: one desktop browser interface for the Sole Researcher without sign-in, administrator routes, or role-specific navigation.
No currently active Unified Workspace screen supplies a genuine PDF URL, so this work removes the false preview now and establishes the mandatory behavior for the first genuine PDF link.
