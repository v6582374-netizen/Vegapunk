# Discovery Current Launch — Human Review Checkpoints prototype

This is a throwaway UI prototype for the second design pass. It is embedded in a faithful approximation of the existing Native Desktop Discovery `Current Launch` surface; it is not a separate review application and it does not call production APIs.

## Design question

Can a researcher keep the terminal/runtime output as the primary workspace while seeing all three fixed checkpoint slots in one Current Launch surface?

The first-principles constraints are:

- the terminal gets the largest continuous area;
- all three seam artifact bundles are visible from the start;
- an unreached bundle stays greyed out and cannot be opened;
- the active seam is visibly inactive (`Execution inactive`) and exposes one `Resume` action;
- completed bundles remain available as read-only Launch history;
- no editing, feedback form, duplicate status copy, or standalone review page is introduced.

## Run

From the repository root:

```sh
python3 -m http.server 4180 --directory .scratch/discovery-human-review-checkpoints/prototype
```

Open the default MAS checkpoint state:

```text
http://127.0.0.1:4180/?v=1&stage=mas&rev=2
```

The previous links remain compatible:

```text
http://127.0.0.1:4180/?variant=A&seam=mas&rev=2
```

Preview states:

- `stage=before` — Launch admitted, no seam reached
- `stage=running` — active execution before a seam
- `stage=mas` — MAS checkpoint active
- `stage=method` — method checkpoint active
- `stage=handoff` — PaperOrchestra handoff checkpoint active
- `stage=complete` — all bundles available as read-only history

## Directions

| Variant | Axis | What to evaluate | Cost |
| --- | --- | --- | --- |
| Console First | terminal-led layout | Whether the console and its inactive/resume state stay primary | The fixed seam rail is narrower |
| Stage Strip | pipeline-led layout | Whether all three checkpoint slots are scannable before reading the logs | Uses a row above the terminal |
| Review Dock | checkpoint-led layout | Whether the current bundle can be understood directly under the console | The lower dock consumes vertical space |

Use the fixed picker at the bottom, number keys `1–3`, or `←`/`→` to switch variants. Press `R` to remount the current variant. Change `stage=` in the URL to inspect each lifecycle point. Append `&theme=dark` to compare the Desktop dark palette.

The picker is harness chrome; the application shell, terminal, Current Launch header, checkpoint slots, timeline, and artifact preview are the design under evaluation.
