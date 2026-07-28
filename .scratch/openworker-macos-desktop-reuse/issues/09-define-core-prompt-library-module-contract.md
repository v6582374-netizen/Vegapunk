# 定义 OpenWorker 设置中的核心 Prompt 库功能契约

Type: grilling
Status: closed
Assignee: Claude
Labels: wayfinder:grilling
Parent: ../map.md
Blocked by: none
Blocks: 10-prototype-openworker-native-prompt-library-module.md, 11-define-minimal-prompt-library-api-connection.md

## Resolution

The OpenWorker setting is named **Prompt Library** and migrates only Vegapunk's core Registered Prompt workflow.

- Browse existing Registered Prompts by their system-maintained **workflow → stage** structure, with search across name, stable ID, description, workflow, stage, and body.
- Keep the catalogue concise; selecting a Prompt opens an OpenWorker-native detail/editor surface rather than placing long textareas in the list or opening a separate window.
- Show the Prompt body as the only editable field. ID, name, description, workflow, stage, invocation type, order, and Prompt Template Contract are read-only metadata.
- Editing creates a Pending Prompt Revision. Saving is always explicit; switching or closing with unsaved changes offers continue editing or discard. There is no autosave.
- Provide immediate client-side guidance for obvious empty/template problems, but the Vegapunk API performs authoritative validation on save. A failed save preserves the draft and leaves the active Prompt source unchanged.
- Concurrent external source modification is not addressed in V1; last successful save may replace the current active body.
- Each Registered Prompt retains a **System-Original Prompt** supplied by the currently installed Vegapunk version. “Reset to system original” loads that one default into the draft and still requires explicit Save; it does not immediately overwrite the active Prompt.
- No intermediate user revision history is stored. Only the active body and current-version system original are available through this module.
- After save, state explicitly that the change affects only subsequently started Vegapunk work; running work and resumed Launches retain their captured Prompt snapshot.
- Fetch only when entering the module. Loading and API failures stay local to Prompt Library, preserve the rest of OpenWorker, and present an OpenWorker-native unavailable state with service information and Retry.
- Exclude Chinese Prompt Mirrors, translation and batch synchronization, creation, deletion, renaming, import/export, batch editing, and system metadata editing.

Visual composition is intentionally unresolved here and belongs to [原型化符合 OpenWorker 视觉语言的 Prompt 库设置模块](10-prototype-openworker-native-prompt-library-module.md).

## Question

Which existing Vegapunk core Prompt Library capabilities must the OpenWorker settings module expose in V1, and which existing behaviors must be deliberately excluded?
How should Registered Prompt metadata, browsing, search, editing, template validation, explicit save, activation timing, error recovery, and unsaved-change protection behave without importing Chinese mirror or translation workflows?
