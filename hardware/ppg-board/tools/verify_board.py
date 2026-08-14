"""Independent post-route audit: plane integrity + slot crossings.

A track crossing a routed slot is severed at fab and produces NO DRC error, so
this is checked separately from DRC rather than trusted to it.
"""
import sys, pcbnew

b = pcbnew.LoadBoard(sys.argv[1])
names = {l: b.GetLayerName(l) for l in b.GetEnabledLayers().Seq()}

seg = {}
for t in b.GetTracks():
    if t.GetClass() == "PCB_VIA":
        seg["VIA"] = seg.get("VIA", 0) + 1
    else:
        n = names[t.GetLayer()]
        seg[n] = seg.get(n, 0) + 1
print("segments per layer:")
for k in sorted(seg):
    flag = "  <-- PLANE, must be 0" if k in ("In1.Cu", "In4.Cu") else ""
    print(f"   {k:<8} {seg[k]:>5}{flag}")

# slots = closed Edge.Cuts shapes that are not the outer board outline
outer = b.GetBoardEdgesBoundingBox()
slots = []
for d in b.GetDrawings():
    if d.GetLayer() != pcbnew.Edge_Cuts:
        continue
    bb = d.GetBoundingBox()
    if bb.GetWidth() < outer.GetWidth() * 0.9 or bb.GetHeight() < outer.GetHeight() * 0.9:
        slots.append((d.GetEffectiveShape(), bb))
print(f"\ninterior Edge.Cuts features (slots): {len(slots)}")

cross = 0
for t in b.GetTracks():
    if t.GetClass() == "PCB_VIA":
        pts = [t.GetPosition()]
    else:
        a, e = t.GetStart(), t.GetEnd()
        pts = [pcbnew.VECTOR2I(int(a.x + (e.x - a.x) * i / 40),
                               int(a.y + (e.y - a.y) * i / 40)) for i in range(41)]
    for sh, bb in slots:
        if any(sh.Collide(p, 0) for p in pts):
            print("   CROSSES SLOT:", t.GetClass(), names.get(t.GetLayer(), "?"))
            cross += 1
            break
print(f"tracks/vias crossing a slot: {cross}")
