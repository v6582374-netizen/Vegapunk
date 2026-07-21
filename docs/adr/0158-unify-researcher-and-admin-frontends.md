Status: accepted

# Unify the Researcher Workspace and Admin Console Frontends

The Researcher Workspace becomes the single product entry point.

The Admin Console moves into the same React application under the protected `/admin` route.

The two surfaces share branding, same-origin hosting, and browser session handling, while the Admin Console keeps its own dense navigation and full diagnostic controls.

The application source lives in the root `frontend/` directory.

The Researcher Workspace uses product-facing routes such as `/research` and `/discovery`.

Admin routes use stable nested paths such as `/admin/queue`, `/admin/prompts`, and `/admin/catalog`.

Admin HTTP endpoints use the protected `/api/admin/*` namespace.

The service exposes authentication endpoints under `/api/auth/*`.

The first version is local-only and has one administrator with the default bootstrap credentials `admin` and `admin`.

Administrator sessions use an HttpOnly same-origin cookie backed by a local SQLite session store.

The user-facing surface exposes curated research workflows, while prompts, the full model catalog, global parameters, raw artifacts, and force-kill controls remain in the Admin Console.

The previous separate-frontend decision in ADR-0156 is superseded by this decision.
