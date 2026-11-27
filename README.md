# Block Runner

A GTA San Andreas–style open-city browser game: three.js r128, a single HTML page, mobile-first (landscape, full screen).

- `dist/index.html`: ready-to-play build. Open it in a browser; it needs internet access for the three.js CDN.
- `src/index.html`: the source. Edit this one.
- `build.py`: run `python3 build.py` to embed `assets/` into `src/` and write `dist/index.html`.
- `assets/`: the Blender-exported car and character models (.glb) and the menu art.
- `blender/`: the Blender (bpy) scripts that generate the models.
  - `human.py exportonly` re-exports the characters.
  - `cars.py` rebuilds the cars.
  - The scripts use absolute `/home/claude/blender/...` paths, so adjust them to your setup, and point the exports at `assets/`.
- `HANDOFF_PROMPT.md`: the full brief for whoever continues the project.
