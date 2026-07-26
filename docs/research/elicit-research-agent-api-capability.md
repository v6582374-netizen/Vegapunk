# Elicit Research Agent and Public API Capability

## Scope and source standard

This note evaluates whether Elicit's public API can reproduce the web Research Agent experience requested for Paper Tools: a topic question, an evidence-grounded answer, cited claims, follow-up conversation, and a visibly progressive response.

Every externally sourced claim below comes from Elicit's own Help Center or Elicit-owned `api-examples` repository at commit [`89e24c1b28510079aad24fcd73f8052858cc7257`](https://github.com/elicit/api-examples/tree/89e24c1b28510079aad24fcd73f8052858cc7257).

No Elicit API key was available, so this note does not infer undocumented payload fields from a live request.

## Decision-driving conclusion

The public API can produce the core of a **one-question, cited literature report** through the asynchronous Report session endpoints, but it cannot be verified as a public API equivalent of Elicit's web Research Agent.

`POST /api/v2/sessions/reports` is the documented API for a synthesized literature review, whereas `POST /api/v2/search/papers` is an instant paper-record search and does not itself generate a research answer. [Elicit API endpoint guide](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L34-L74) [Search versus Report guidance](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L197-L218)

The documented Report workflow is asynchronous: creation returns a `sessionId`, `status: "processing"`, and a report `url`; the documented client then polls `GET /api/v2/sessions/reports/{sessionId}` until the status changes. [Report creation and status contract](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L103-L130) [Official polling guidance](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L284-L305)

The public examples document polling, not a token stream, Server-Sent Events, WebSocket events, or incremental citation events. [Official polling implementation](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/javascript/3_create_report.js#L1-L38) [Official REST-tool inventory](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/mcp/README.md#L5-L16)

Therefore, a first integration can show its own progress state while polling and render Elicit's completed result in a conversation-shaped UI, but it must not claim that Elicit is streaming the answer or its citations to the browser.

Elicit's web Research Agent is a broader product capability than Reports or Systematic Reviews: Elicit describes it as an ongoing workspace with follow-up questions, source filtering and export, real-time visibility into the sources consulted, and clickable citations. [Elicit Research Agent product documentation](https://support.elicit.com/en/articles/14756886-elicit-s-research-agent)

The same official web documentation explicitly distinguishes the Research Agent from Reports and Systematic Reviews, which it says are limited to Elicit's academic, journal, and clinical-trial corpus; the Research Agent can also use sources such as public filings, press releases, product labels, the broader web, clinical databases, and user-uploaded files. [Research Agent scope and supported sources](https://support.elicit.com/en/articles/14756886-elicit-s-research-agent)

Elicit's published public-API examples do not document a `research-agent` endpoint, a multi-message conversation/session API, an endpoint for following up on an agent workspace, or a stream that exposes the web Agent's plan, retrieved sources, or partial answer. [Official REST-tool inventory](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/mcp/README.md#L5-L16) [Official Reports and sessions contract](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L103-L183)

This is a documentation boundary, not proof that Elicit has no private implementation behind its web app.

## What the public API can deliver

### 1. Paper Search is not Research Agent output

Paper Search accepts a natural-language `query` and returns a `papers` array containing paper records such as `title`, `authors`, `year`, `abstract`, `doi`, `pmid`, `venue`, `citedByCount`, and `urls`. [Paper Search request and response summary](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L34-L74)

The official integration guide treats this as an instant reference lookup and directs a caller that needs an answer to a nuanced question or evidence synthesis to create a Report instead. [Search versus Report guidance](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L197-L218)

The same guide instructs a separate Claude Code client to compose a short answer from the returned abstracts when a user asks a specific question; that instruction describes the caller's formatting behavior, not an Elicit Search response that already contains a generated answer. [Official Search-result formatting instructions](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L230-L256)

### 2. Research Report is the closest public API match

The Report create request accepts `researchQuestion` plus optional `maxSearchPapers`, `maxExtractPapers`, `title`, and `isPublic`; the documented defaults are 50 searched papers and 10 extracted papers when the limits are omitted. [Report tool reference](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/mcp/README.md#L224-L243)

Elicit describes completed Reports as structured literature reviews that synthesize findings across dozens of papers and include summaries, evidence tables, and citations. [Elicit API integration overview](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/README.md#L7-L15)

The direct REST guide documents `?include=reportBody` on the Report-status request for the full Markdown content. [Report status contract](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L122-L130)

The Elicit MCP documentation describes the corresponding completed retrieval as containing the report title, summary, full Markdown body with citations, and PDF/DOCX download links. [Completed Report retrieval example](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/mcp/README.md#L111-L123)

The direct REST response summary names `result.title`, `result.summary`, `url`, `pdfUrl`, and `docxUrl` after completion. [Report status contract](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L122-L130)

The `url` points to the Elicit report, and `pdfUrl` and `docxUrl` are report-artifact links; none of those documented fields is a structured per-claim source link. [Report status contract](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L122-L130)

### 3. Reports are not documented as abstract-only

Elicit's own API integration documentation contrasts instant Search with Reports and states that Reports read the full text of papers, extract findings, and write a report with proper citations. [Elicit's Search versus Report explanation](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/README.md#L57-L62)

This supports the conclusion that the public Report workflow is not merely a synthesis of the Paper Search `abstract` fields.

The heavier Systematic Review API separately documents abstract screening, full-text screening, extraction, and report generation, which further confirms that Elicit's public workflows distinguish abstract-level and full-text stages. [Systematic Review request contract](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/mcp/README.md#L245-L268)

Elicit's public Research Agent help article describes the Agent's source categories and its planning/execution behavior, but it does not specify whether every academic or web-source claim is based on a full document, an abstract, a snippet, an upload, or another representation. [Research Agent workflow and source list](https://support.elicit.com/en/articles/14756886-elicit-s-research-agent)

Accordingly, it is supported to say that the public **Report** workflow reads full text, but it is not supported to claim a precise retrieval pipeline for the web Research Agent.

## Citation and provenance boundary

Elicit publicly promises that the Report body is Markdown with citations. [Completed Report retrieval example](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/mcp/README.md#L111-L123)

Elicit publicly promises that web Research Agent claims are grounded in evidence, have citations traceable to their source, and can be opened by clicking the cited source. [Research Agent workflow](https://support.elicit.com/en/articles/14756886-elicit-s-research-agent)

However, the published API material does not define the inline citation syntax in `reportBody`, a structured citation array, a claim-to-paper mapping, a citation identifier, a bibliography object, or a canonical per-source URL field for the Report response. [Report status and body summary](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L122-L130) [Completed Report retrieval example](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/mcp/README.md#L111-L123)

The Paper Search response's `doi`, `pmid`, and `urls` fields do not close that gap because the published response summary does not define the nested `urls` structure or relate its records to individual Report-body citations. [Paper Search response summary](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L34-L74)

As a result, the first API integration can render the returned report body as an answer, but it cannot safely promise Elicit-web-style superscript interactions, citation hover cards, or direct per-claim source links until a real authenticated payload confirms both the Markdown citation syntax and its provenance mapping.

## Product implication for Paper Tools

If the intended experience is exactly Elicit's web Research Agent - ongoing chat, clarifying questions, real-time source activity, web and user-file sources, clickable citations, and follow-up turns - that capability should remain a separate future integration decision because Elicit's public API documentation does not expose its needed conversation or streaming contract.

If the intended first release is a single research question answered from academic literature with Elicit-generated citations, the documented path is a **Research Report** session rather than Paper Search.

That first release should represent itself honestly as an asynchronous report: submit one question, persist the `sessionId` on the backend, show a non-deceptive processing state while polling, then render the completed Markdown answer and link to Elicit's report page.

It should not use token-by-token typing animation, progressive cited-claim rendering, or clickable source superscripts until Elicit's public contract is verified from a real authenticated Report result.

## Uncertainties requiring an authenticated contract check

- The exact `reportBody` JSON property and Markdown citation syntax are not shown in the published REST response summary.
- The public documentation does not specify a structured citation-to-source mapping, whether citations contain URLs, or how a Report body relates to the Paper Search `urls` field.
- The public documentation does not define a public Research Agent conversation endpoint, follow-up endpoint, streaming protocol, or agent-progress event schema.
- The public documentation does not state that the web Research Agent uses the Report endpoints, so their output quality, source scope, and behavior must not be treated as identical.
- The public documentation does not specify the Report full-text acquisition rules, any fallback when full text is unavailable, or the exact material the web Research Agent reads for each source type.

## Sources consulted

- [Elicit Research Agent help article](https://support.elicit.com/en/articles/14756886-elicit-s-research-agent)
- [Elicit API examples - Claude Code Skill README](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/README.md)
- [Elicit API examples - Claude Code Skill API reference](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md)
- [Elicit API examples - MCP tool reference](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/mcp/README.md)
