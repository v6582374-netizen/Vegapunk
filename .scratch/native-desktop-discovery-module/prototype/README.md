# Native Desktop Discovery Preparation prototype

This is a throwaway UI prototype for `Prototype Discovery Preparation intake and conversion flow`.

It explores three structurally different layouts on one route.

- `?variant=A` is the dense Preparation workbench.
- `?variant=B` makes the formatted input the primary document canvas.
- `?variant=C` makes the lifecycle stages and Run gate persistent.

The prototype keeps state in memory and does not call the production sidecar.

Run it from the repository root with:

```sh
python3 -m http.server 4178 --directory .scratch/native-desktop-discovery-module/prototype
```

Then open `http://127.0.0.1:4178/?variant=A`.

Use the bottom switcher or the left and right arrow keys to compare variants.

The demo controls expose adding accepted files, showing a rejected file, explicit conversion, editing, saving a formatted revision, and the final Run gate.
