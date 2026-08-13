# Define the initial registered-skill boundary

Type: grilling
Status: resolved
Labels: wayfinder:grilling
Parent: ../map.md
Assignee: Claude
Blocked by: none
Blocks: 03-define-g1-deployment-validation-evidence.md, 04-define-macro-action-safety-and-human-gate.md, 05-define-training-data-and-model-promotion.md

## Question

What is the initial constrained physical-operation boundary for the Embodied Execution Profile?

## Resolution

Version 1 does **not** choose one canonical natural-language task or one fixed action such as `press_physical_button`. It accepts a selectable catalog of already implemented physical actions. The concrete actions may change as laboratory capability changes; the Version 1 product goal is to establish the complete governed execution loop around them.

Every selectable action must still be a registered, reviewable Physical Skill with an explicit input contract, preconditions, postconditions, automatic safety verification, human confirmation, and hard-failure semantics. Arbitrary natural-language-to-motor control is deferred. Natural language is not a Version 1 input boundary.

The next decision is therefore the common Skill Registry and Execution Loop contract, not the semantics of one button-press example.
