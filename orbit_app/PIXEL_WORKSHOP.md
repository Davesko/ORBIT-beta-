# ORBIT Pixel Workshop

The office is live SVG tile/sprite artwork, not a screenshot layered over the app. `web/pixel_world.js` owns original room furniture, corridors and character art. `web/map_math.js` retains the legacy projection function names for gesture compatibility but now uses invertible orthographic coordinates. Custom room colours, sizes, furnishings, membership, connections, pan and anchored zoom remain editable.

`web/pixel_ui.js` groups frequent actions into Add, workspace options and Start. Model storage, connections and authorized folders remain available in Settings. Publication and trend analysis retain their separate navigation entries. New video creation passes actual requirements and one/multiple source URLs to the existing backend; it does not create a second schedule. Schedules stay in Automations.

The automation map reads configured agent links or real run/job payloads. Planned nodes are labelled as planned; observed running, failed and complete states come from jobs. Clicking a node opens agent settings or its actual task details. Animations never imply that a model is working unless there is corresponding runtime evidence. There is no fake pause/resume feature: the run stop button cancels the selected run's outstanding jobs.

`pixel_layout.migrate` reflows room geometry and palettes once, preserving project/room/agent IDs, tools, instructions, connections, files and automation settings. Subsequent customizations are preserved. Deployment saves a database and UI backup before this migration.

Header mascot: `web/assets/guardian-pixel-peek.png`, generated using the built-in imagegen tool from the user's approved reference. Prompt: faithfully reconstruct the same green goblin with purple hood and yellow eyes as a transparent, deliberate pixel-art head and hands peeking over a toolbar; preserve identity, no UI or text. At rest CSS clips to its eyes; hover/focus reveals the same sprite. Click pins the existing cross-project assistant. Reduced-motion preferences disable animation.

UI verification: desktop/laptop/mobile rendering, clickable agents/chat, add-room dialog, short production form, hover assistant/Escape, automation nodes and Settings access were exercised in a headless local Chrome with a native bridge fixture. No production or upload is triggered by those tests.

## Interaction refinement

`web/pixel_refine.js` groups navigation into workshop and output sections, provides an automation overview (task, schedule, goal), separates one-off execution from schedule enablement, and collapses run history. Planned empty-state artwork no longer dominates onboarding.

Goblin image geometry keeps the original resting eye crop and aligns the hovering sprite's hands to the header baseline. Agent connections use visible directional ports outside sprites/nameplates and emphasize the selected agent's incoming/outgoing links.

Characters have separate raven, jellyfish, hologram, dragon and electric-mouse artwork. Idle sprites follow bounded room paths with rest/seated phases. On real work, they approach their seat smoothly. Sitting/walking are visual states; working indicators still reflect actual jobs. Reduced-motion preferences keep sprites stationary.

## Workshop life (2026-11-12)

`web/pixel_life.js` + `pixel_life.css` redraw every room with more detail and fifteen room types (the nine earlier ones plus Játékterem, Konyha, Edzőterem, Terasz, Könyvtár, Szerverterem). The interior is designed for a compact room and scaled with the room, so furniture keeps the characters' size. Every piece of furniture leaves an activity spot: computer, sofa (rest, Rubik cube, laptop, nap), floor (sit, Rubik cube, phone), beanbag (console), arcade, window (smoking), coffee machine and water cooler, stools, armchairs (reading), treadmill, dumbbells, punching bag, microphone, whiteboard, campfire (warming, guitar), deck chairs, plus a running lap in any room. Idle characters pick spots by themselves, reserve them and walk there, with a short emote bubble; the map's corner HUD counts what the crew is doing. Only a real running job sends a character to a desk to type (accent nameplate, work light) — the idle "Játszik a gépen" never shows the work light.

Room nameplates float above the rooms (wall art stays visible) and carry a delete button: an empty room is deleted with one click, a room with agents asks only where they move. Every delete is reversible from the undo bar, which also moves the agents back. Deleting stays an archive (`room_archive`), never permanent.

`web/theme_motion.js` + `theme_motion.css` add four moving scene themes, drawn on a canvas behind the main chat and the workshop map: Hullócsillag (shooting stars and Mystify-like trails), Hullám (flowing lines), Kódoló (falling code and typed lines), Tábortűz (fire glow, embers, bokeh). 30 fps at most, paused in the background, a still frame with the motion switch off or reduced motion.
