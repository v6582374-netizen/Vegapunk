# Map single-active Launch lifecycle and desktop transport

Type: task
Status: open
Labels: wayfinder:task
Parent: ../map.md
Assignee:
Blocked by: 01-audit-native-desktop-sidecar-and-discovery-service-ownership.md
Blocks: 07-define-rightrail-adapter-and-artifact-access-contract.md, 08-define-native-desktop-acceptance-and-migration-boundary.md

## Question

Which durable state and native `/v1/discovery` transport expose one active Launch, read-only history, status changes, raw runtime output, Stop, Resume, reconnect, and restart recovery to the desktop GUI?
This ticket is the local contract-mapping work needed before deciding the adapter and UI behavior, not a product implementation of those endpoints.

