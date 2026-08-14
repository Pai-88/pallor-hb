# Workflow rules for this board
- Always read constraints.md and fab.md before routing or sourcing parts.
- Use JLCPCB DRC at ~/hw/drc/JLCPCB.kicad_dru (symlinked as JLCPCB.kicad_dru in this repo).
- Prefer JLC Basic parts; escalate to Preferred only when required. Never Extended without approval.
- Every release goes through ~/hw/scripts/build_release.sh — do not hand-export gerbers.
- Update bringup.md as the board evolves.
