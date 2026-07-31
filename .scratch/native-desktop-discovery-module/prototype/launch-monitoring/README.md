# Discovery Launch monitoring prototype

Question: what concrete Native Desktop flow best supports one active Discovery Launch, read-only history, Stop, Resume, and reusable Progress, Artifacts, and Access modules?

Assumption: the existing native GUI shell remains the host, while Discovery owns an internal Active Launch and Launch history navigation.

This is throwaway UI prototype code and does not change the production Native Desktop GUI.

## Run

From the repository root, run `python3 -m http.server 4179`.

Open `http://127.0.0.1:4179/.scratch/native-desktop-discovery-module/prototype/launch-monitoring/`.

The prototype is a single route with three shareable variants:

- `?variant=A` is Runtime Desk, with a central lifecycle and a persistent right rail.
- `?variant=B` is Launch Index, with a history-first master/detail arrangement.
- `?variant=C` is Observatory, with a stage strip, facts grid, and raw console.

Use the bottom switcher or the left and right arrow keys to change variants.

The prototype simulates Stop and Resume for the active Launch.

Selecting a completed or failed Launch shows read-only history.

Progress, Artifacts, and Access are expandable adapter sections in every runtime arrangement.

## Evaluation prompts

Which variant makes the active Launch state understandable within one glance?

Does the history-first arrangement make the active Launch too easy to confuse with read-only history?

Does the right rail remain useful as an adapter, or should one of its sections move into the central runtime view?
