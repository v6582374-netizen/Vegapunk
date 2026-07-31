# Define single-Preparation upload persistence and error contract

Type: grilling
Status: open
Labels: wayfinder:grilling
Parent: ../map.md
Assignee:
Blocked by: 01-audit-native-desktop-sidecar-and-discovery-service-ownership.md
Blocks: 08-define-native-desktop-acceptance-and-migration-boundary.md

## Question

How does the single Native Desktop Discovery Preparation save multiple uploaded files and free-form text, replace or remove sources, report invalid or failed uploads, and recover after an application restart?
The decision must preserve the confirmed no-folder rule and existing file whitelist while defining atomicity, user-visible errors, storage ownership, and whether incomplete upload state is ever persisted.

