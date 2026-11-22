---
trigger: always_on
description: "OnePlus Nord 6 ColorOS 17 port kit: ground rules and where the instructions are"
---

# OnePlus Nord 6 ColorOS 17 port kit

Antigravity loads `AGENTS.md` from the workspace root by itself; follow it. It has the ground rules (never flash or
wipe the phone without the user asking, never store the PIN, every fix must become a build step, Melody popup work
stays out of the kit), the user's setup (adb path, phone serial), the commands, the layout and how to test.

Before changing any build step, patch or test, read `DECISIONS.md` in the workspace root: everything already
verified on the device, including the dead ends not to repeat. Open the `port_kit` folder itself as the workspace
(rules are read from the workspace folder and its parents, not from subfolders).
