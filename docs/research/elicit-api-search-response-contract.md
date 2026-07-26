# Elicit Paper Search Response Contract

## Scope and source standard

This note verifies the public contract available before choosing a presentation for Elicit-backed Paper Search output.

All product facts below are cited to Elicit's own `elicit/api-examples` repository at commit `89e24c1b28510079aad24fcd73f8052858cc7257` or to Elicit's published OpenAPI URL.

No Elicit credential was available for this research, so no authenticated request was sent and no undocumented live payload has been inferred.

## Decision-driving conclusion

Elicit supports an immediate academic-paper search through `POST https://elicit.com/api/v2/search/papers`; the official material calls this operation "Search Papers", not "Quick Search". [Elicit API reference](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L34-L74)

The official integration guidance describes this Search operation as instant and separately describes report creation as asynchronous, so the product's "快速搜索" mode can submit once and render the response directly without polling. [Search versus report guidance](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L197-L218) [Asynchronous report contract](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L103-L130)

For this project, "快速搜索" should be a UI label mapped to Elicit Paper Search rather than an assumption that Elicit exposes another endpoint with that exact name.

## Authentication and request contract

Every API request uses `Authorization: Bearer $ELICIT_API_KEY`, and POST requests also use `Content-Type: application/json`; Elicit instructs users to obtain the key from account settings. [Authentication requirements](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L20-L32) [Official setup example](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/README.md#L5-L11)

The key must remain in the backend environment and the browser must call the local product API instead of Elicit directly.

The minimum supported request is a JSON object with required `query` and optional `maxResults`. [Paper-search request schema](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L50-L58)

`query` is a natural-language research question or topic. [Paper-search request schema](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L50-L58)

`maxResults` accepts integers from 1 through 10,000 and defaults to 10 when omitted. [Paper-search request schema](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L50-L58)

```json
{
  "query": "recent papers on seawater desalination reverse osmosis",
  "maxResults": 10
}
```

`corpus` may be `"elicit"` for the default full index or `"pubmed"`, and `searchMode` may be the default `"semantic"` or `"keyword"`; keyword mode cannot be combined with `filters`. [Paper-search request schema](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L50-L58)

The optional `filters` object supports year, study-type, keyword, PDF-availability, PubMed-only, journal-quartile, and retraction controls. [Documented paper filters](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L60-L72)

The fixed domain chips for the "高热论文" placeholder are unrelated to this request contract and must not be silently serialized into Elicit filters.

## Lifecycle, response, and pagination

Paper Search returns its paper records in the top-level `papers` array. [Documented response shape](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L74)

The cited Elicit material does not document a `sessionId`, `status`, polling operation, or asynchronous state for `POST /search/papers`; those mechanics belong to report and systematic-review endpoints instead. [Instant search guidance](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L197-L218) [Report polling contract](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L103-L130)

The cited sources document cursor pagination and `nextCursor` for `GET /api/v2/sessions`, but do not document a cursor, offset, page token, or `nextCursor` for Paper Search. [Sessions pagination contract](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L171-L177)

Therefore, the first product UI should request a bounded `maxResults` value and should not expose "load more" until the published OpenAPI schema or an authenticated response confirms a Paper Search pagination mechanism.

## Documented fields available to a future presentation

Elicit documents the following paper-record field names: `title`, `authors`, `year`, `abstract`, `doi`, `pmid`, `venue`, `citedByCount`, and `urls`. [Documented response shape](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L74)

The official CLI treats `authors` as a flat array of strings and demonstrates terminal formatting of title, year, authors, venue, citation count, abstract preview, and DOI. [Author representation](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/cli/elicit.py#L91-L103) [Official formatting example](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/cli/elicit.py#L109-L150)

The following field availability constrains a future product decision but does not choose a UI component, visual hierarchy, or visible-field set.

| Available information | Elicit field | Contract observation |
| --- | --- | --- |
| Title | `title` | Named by the response contract. |
| Authors | `authors` | Official CLI treats it as a flat string array. |
| Publication metadata | `year`, `venue` | Both fields are named by the response contract. |
| Citation count | `citedByCount` | Named by the response contract. |
| Abstract | `abstract` | Named by the response contract. |
| DOI | `doi` | Named by the response contract. |
| Future identifier | `pmid` | Named by the response contract. |

Any future UI cannot rely on `urls` because the cited official material names that field but does not specify its nested shape or which URL is canonical. [Documented response shape](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L74)

Any future UI must tolerate omitted values because Elicit's official CLI conditionally renders every metadata, abstract, and DOI field rather than treating any of them as guaranteed. [Official CLI fallback behavior](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/cli/elicit.py#L120-L150)

## Rate limits and externally observable errors

Elicit advises sending one request at a time and waiting 60 seconds before retrying an HTTP 429 response. [Rate-limit guidance](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L297-L305)

The official material identifies HTTP 401 as an invalid or expired API key and HTTP 402 as exhausted plan quota. [Authentication and quota errors](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L302-L305)

The official CLI expects HTTP error payloads in the form `{ "error": { "code": ..., "message": ... } }` and falls back to raw response text when that envelope is absent. [Official error-handling implementation](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/cli/elicit.py#L45-L78)

The first backend adapter should normalize 401, 402, 429, other non-2xx HTTP failures, invalid JSON, and connection failures into product-safe errors without returning the Elicit API key or raw internal details to the browser.

## Unknown or not documented by the cited official material

- The official material does not give a distinct endpoint or response schema named "Quick Search"; the product label must map to `POST /search/papers`. [Paper Search endpoint](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L34-L74)
- The exact JSON types, nullability, and completeness guarantees for individual paper fields are not stated in the cited response summary. [Documented response shape](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L74)
- The structure and canonical-link semantics of `urls` are not stated in the cited response summary. [Documented response shape](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L74)
- The Paper Search endpoint's success status code, total-result count, result ordering, pagination token, rate-limit quota, reset headers, validation-error codes, CORS policy, and plan entitlement are not specified in the cited material. [Paper-search request and response summary](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L34-L74) [Rate-limit guidance](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L297-L305)
- Elicit points readers to `https://docs.elicit.com/openapi.json` for complete schemas and says that document itself does not require authentication; obtain and snapshot that source before depending on any of the unknown details above. [OpenAPI pointer](https://github.com/elicit/api-examples/blob/89e24c1b28510079aad24fcd73f8052858cc7257/integrations/claude-code-skill/skill.md#L185-L193) [Published OpenAPI URL](https://docs.elicit.com/openapi.json)

## Presentation boundary for the pending decision

The contract establishes an immediate response with a bounded `papers` list, or an externally observable failure.

It does not determine whether the product uses cards, a table, a list, or another presentation form.
