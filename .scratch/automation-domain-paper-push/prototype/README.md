# Daily Research Brief - throwaway UI prototype

This prototype answers: “What is the minimum static Daily Research Brief placeholder inside the existing OpenWorker desktop shell?”

It deliberately explores three different placements while keeping the state static and unavailable:

- Variant A - First-class page: replace the old Automations nav row with a top-level Daily Research Brief row and a quiet full-page unavailable state.
- Variant B - Sidebar card: place the placeholder under a Tools section and keep the unavailable state as a compact tool surface with an explicit boundary note.
- Variant C - Session home card: add no new first-class navigation entry and show the placeholder only in the idle session home.

All variants use the existing OpenWorker shell shape: a 264px sidebar, OpenWorker brand row, New session and Search controls, Recent sessions, account footer, absolute main topbar, cool paper palette, cobalt accent, and compact typography.

The copy is intentionally explicit about what is not present.
There is no paper list, paper detail, unread state, refresh, retry, domain control, schedule control, subscription state, API call, or persistence.

Run it with one command from the repository root:

```sh
python3 -m http.server 4174 --directory .scratch/automation-domain-paper-push/prototype
```

Open `http://localhost:4174/?variant=A`.
Use `?variant=B` or `?variant=C`, or use the bottom switcher and the left/right arrow keys.

This is explicitly throwaway prototype code.
It is not a product implementation and must not be merged into the OpenWorker runtime.
