# Context Studio revision

- Public source search preserves names, recognizes 2okos / 2 okos / két okos, and can discover real YouTube URLs through configured Tavily / public web search. It records attempted searches. Authentication blocks remain explicit; discovery cannot guarantee download access.
- Source speech supports Hungarian, English and automatic Whisper language detection. Captions preserve original speech, not synthetic translation.
- Edit decisions include grounded source timestamps, coherent setup/payoff, contextual reasons and allowlisted effects. Only reliable tracked reframes enable a subtle 9% punch-in or vignette spotlight. There is no pixel segmentation/rotoscoping engine.
- Render effects are deterministic FFmpeg filters, not code supplied by a model. Unrecognized effects are rejected. The manifest retains input decisions.
- Thirteen characters: operator, hacker, robot, astronaut, hologram, Pikachu, goblin, wizard, cyberfox, samurai, dragon, raven, jellyfish. Preferences validate the same IDs on frontend and backend.
- Rooms retain editable dimensions, colors and membership; new editing/marketing/office/audio decors add corresponding furniture. Board lettering uses the saved short description; it is not an independent drawing canvas.
- Shared theme variables control app surfaces and selected controls. Background choices remain independent from room floor/wall colors.
- `upgrade_context_studio.py` backs up the installed UI/core, SQLite and the project brief before this one-time migration. It resets this project's palette to Obsidian and replaces outdated role prompts without a fixed subject.
