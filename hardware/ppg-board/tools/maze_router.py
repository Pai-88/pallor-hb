"""Multi-layer maze router for the last few nets.

PLANE_LAYERS are excluded from routing: In1.Cu is the ground plane and In4.Cu the
3V3 plane. Letting the router use them would undo the plane clearing.

A* over a 0.25 mm grid across all six copper layers. Layer changes cost a via and
are only allowed where a through-hole via clears every layer. Board outline and
the optical barrier slots are rasterised as hard obstacles, so a route can never
cross a slot -- fab would sever such a trace and DRC would not flag it.
"""
import heapq
import sys

import pcbnew

GRID = 250000          # 0.25 mm
TRACK_W = 250000
VIA_PAD, VIA_DRILL = 600000, 300000
CLEAR = 230000        # > rule 0.20 mm, absorbs grid quantisation
EDGE_CLEAR = 350000
VIA_COST = 10          # in grid steps
DIAG = 1.41421356


class Grid:
    def __init__(self, board, netcode, layers):
        self.board = board
        self.net = netcode
        self.layers = layers                      # list of layer ids
        self.li = {l: i for i, l in enumerate(layers)}
        bb = board.GetBoardEdgesBoundingBox()
        self.ox = bb.GetX() - GRID * 2
        self.oy = bb.GetY() - GRID * 2
        self.nx = bb.GetWidth() // GRID + 5
        self.ny = bb.GetHeight() // GRID + 5
        n = self.nx * self.ny
        self.block = [bytearray(n) for _ in layers]   # per-layer copper
        self.vblock = bytearray(n)                    # via sites
        self._build()

    def cell(self, x, y):
        return (int(round((x - self.ox) / GRID)), int(round((y - self.oy) / GRID)))

    def pos(self, cx, cy):
        return (self.ox + cx * GRID, self.oy + cy * GRID)

    def idx(self, cx, cy):
        return cy * self.nx + cx

    def _stamp(self, x0, y0, x1, y1, rad, layer_ids, via_rad):
        """Mark every cell within `rad` of segment (x0,y0)-(x1,y1)."""
        vrad = via_rad if via_rad is not None else -1
        maxr = max(rad, vrad)
        # scan box must use maxr, not rad: via_rad exceeds rad by (via - track)/2,
        # and a box sized on rad silently leaves that annulus un-marked for vias.
        lo_x = max(0, int((min(x0, x1) - maxr - self.ox) / GRID) - 1)
        hi_x = min(self.nx - 1, int((max(x0, x1) + maxr - self.ox) / GRID) + 1)
        lo_y = max(0, int((min(y0, y1) - maxr - self.oy) / GRID) - 1)
        hi_y = min(self.ny - 1, int((max(y0, y1) + maxr - self.oy) / GRID) + 1)
        vx, vy = x1 - x0, y1 - y0
        L2 = vx * vx + vy * vy
        for cy in range(lo_y, hi_y + 1):
            py = self.oy + cy * GRID
            for cx in range(lo_x, hi_x + 1):
                px = self.ox + cx * GRID
                wx, wy = px - x0, py - y0
                t = 0.0 if L2 == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / L2))
                dx, dy = px - (x0 + t * vx), py - (y0 + t * vy)
                d = (dx * dx + dy * dy) ** 0.5
                if d > maxr:
                    continue
                i = self.idx(cx, cy)
                if d <= rad:
                    for lid in layer_ids:
                        if lid in self.li:
                            self.block[self.li[lid]][i] = 1
                if vrad > 0 and d <= vrad:
                    self.vblock[i] = 1

    def _build(self):
        b, half = self.board, TRACK_W / 2
        vr = VIA_PAD / 2
        alll = list(self.li.keys())

        # board outline + slots: blocked on every layer, and no vias
        for d in b.GetDrawings():
            if d.GetLayer() != pcbnew.Edge_Cuts:
                continue
            try:
                sh = d.GetEffectiveShape()
                bb = sh.BBox()
            except Exception:
                continue
            lo_x = max(0, int((bb.GetX() - EDGE_CLEAR - self.ox) / GRID) - 2)
            hi_x = min(self.nx - 1, int((bb.GetRight() + EDGE_CLEAR - self.ox) / GRID) + 2)
            lo_y = max(0, int((bb.GetY() - EDGE_CLEAR - self.oy) / GRID) - 2)
            hi_y = min(self.ny - 1, int((bb.GetBottom() + EDGE_CLEAR - self.oy) / GRID) + 2)
            for cy in range(lo_y, hi_y + 1):
                for cx in range(lo_x, hi_x + 1):
                    p = pcbnew.VECTOR2I(*self.pos(cx, cy))
                    i = self.idx(cx, cy)
                    # a via is wider than a track, so it needs its own, larger radius
                    if sh.Collide(p, int(EDGE_CLEAR + vr)):
                        self.vblock[i] = 1
                    if sh.Collide(p, int(EDGE_CLEAR + half)):
                        for L in self.block:
                            L[i] = 1

        for t in b.GetTracks():
            if t.GetNetCode() == self.net:
                continue
            if t.GetClass() == "PCB_VIA":
                p = t.GetPosition()
                self._stamp(p.x, p.y, p.x, p.y,
                            CLEAR + VIA_PAD / 2 + half, alll, CLEAR + VIA_PAD / 2 + vr)
            else:
                self._stamp(t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y,
                            CLEAR + (t.GetWidth() + TRACK_W) / 2, [t.GetLayer()],
                            CLEAR + t.GetWidth() / 2 + vr)

        for fp in b.GetFootprints():
            for pad in fp.Pads():
                if pad.GetNetCode() == self.net:
                    continue
                bb = pad.GetBoundingBox()
                # circumradius, not max half-dimension: a rectangular pad reaches
                # further at its corners, so a circle of max(w,h)/2 lets diagonal
                # approaches sit too close (this is what put a via 0.175 mm off R516).
                r = ((bb.GetWidth() / 2) ** 2 + (bb.GetHeight() / 2) ** 2) ** 0.5
                c = bb.GetCenter()
                lids = [l for l in alll if pad.IsOnLayer(l)]
                self._stamp(c.x, c.y, c.x, c.y, CLEAR + r + half, lids,
                            CLEAR + r + vr)


def route(grid, start_xy, start_layer, goals):
    """A*. goals = set of (layer_id, cell) -- returns list of (layer, cx, cy)."""
    sx, sy = grid.cell(*start_xy)
    sl = grid.li[start_layer]
    goalset = {(grid.li[l], c) for l, c in goals if l in grid.li}
    if not goalset:
        return None
    gcells = [c for _, c in goalset]

    def h(cx, cy):
        return min(max(abs(cx - gx), abs(cy - gy)) for gx, gy in gcells)

    start = (sl, sx, sy)
    openq = [(h(sx, sy), 0.0, start)]
    came, gsc = {}, {start: 0.0}
    NB = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
          (1, 1, DIAG), (1, -1, DIAG), (-1, 1, DIAG), (-1, -1, DIAG)]
    seen = set()
    while openq:
        _, g, cur = heapq.heappop(openq)
        if cur in seen:
            continue
        seen.add(cur)
        cl, cx, cy = cur
        if (cl, (cx, cy)) in goalset:
            path, n = [], cur
            while n in came:
                path.append(n)
                n = came[n]
            path.append(start)
            return path[::-1]
        for dx, dy, w in NB:
            nx_, ny_ = cx + dx, cy + dy
            if not (0 <= nx_ < grid.nx and 0 <= ny_ < grid.ny):
                continue
            i = grid.idx(nx_, ny_)
            if grid.block[cl][i] and (cl, (nx_, ny_)) not in goalset:
                continue
            if dx and dy:   # no corner-cutting past blocked orthogonals
                if grid.block[cl][grid.idx(cx + dx, cy)] and \
                   grid.block[cl][grid.idx(cx, cy + dy)]:
                    continue
            nxt = (cl, nx_, ny_)
            ng = g + w
            if ng < gsc.get(nxt, 1e18):
                gsc[nxt] = ng
                came[nxt] = cur
                heapq.heappush(openq, (ng + h(nx_, ny_), ng, nxt))
        if not grid.vblock[grid.idx(cx, cy)]:
            for nl in range(len(grid.layers)):
                if nl == cl:
                    continue
                i = grid.idx(cx, cy)
                if grid.block[nl][i] and (nl, (cx, cy)) not in goalset:
                    continue
                nxt = (nl, cx, cy)
                ng = g + VIA_COST
                if ng < gsc.get(nxt, 1e18):
                    gsc[nxt] = ng
                    came[nxt] = cur
                    heapq.heappush(openq, (ng + h(cx, cy), ng, nxt))
    return None


def emit(board, grid, path, netcode, start_xy, end_xy):
    """Turn a cell path into merged tracks + vias."""
    pts = [(l, *grid.pos(cx, cy)) for l, cx, cy in path]
    pts[0] = (pts[0][0], start_xy[0], start_xy[1])
    pts[-1] = (pts[-1][0], end_xy[0], end_xy[1])

    runs, cur = [], [pts[0]]
    for p in pts[1:]:
        if p[0] != cur[-1][0]:
            runs.append(cur)
            cur = [p]
        else:
            cur.append(p)
    runs.append(cur)

    nseg = nvia = 0
    for ri, run in enumerate(runs):
        if ri > 0:
            prev = runs[ri - 1][-1]
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I(prev[1], prev[2]))
            v.SetWidth(VIA_PAD); v.SetDrill(VIA_DRILL)
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            v.SetNetCode(netcode); board.Add(v)
            nvia += 1
        # merge collinear
        simp = [run[0]]
        for i in range(1, len(run) - 1):
            ax, ay = run[i][1] - simp[-1][1], run[i][2] - simp[-1][2]
            bx, by = run[i + 1][1] - run[i][1], run[i + 1][2] - run[i][2]
            if ax * by - ay * bx != 0:
                simp.append(run[i])
        if len(run) > 1:
            simp.append(run[-1])
        lid = grid.layers[run[0][0]]
        for a, b in zip(simp, simp[1:]):
            if (a[1], a[2]) == (b[1], b[2]):
                continue
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(a[1], a[2]))
            t.SetEnd(pcbnew.VECTOR2I(b[1], b[2]))
            t.SetWidth(TRACK_W); t.SetLayer(lid)
            t.SetNetCode(netcode); board.Add(t)
            nseg += 1
    return nseg, nvia


def clusters(board, code):
    board.BuildConnectivity()
    conn = board.GetConnectivity()
    items = [t for t in board.GetTracks() if t.GetNetCode() == code]
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetCode() == code:
                items.append(pad)
    out, rest = [], list(items)
    while rest:
        s = rest.pop(0)
        g = {s.m_Uuid.AsString(): s}
        for o in conn.GetConnectedItems(s):
            g[o.m_Uuid.AsString()] = o
        out.append(list(g.values()))
        rest = [r for r in rest if r.m_Uuid.AsString() not in g]
    return out


def anchors(board, group, layers):
    """(layer_id, x, y) attach points for a cluster."""
    out = []
    for it in group:
        c = it.GetClass()
        if c == "ZONE":
            continue          # a plane is a valid connection but not an attach point
        if c == "PAD":
            p = it.GetPosition()
            for l in layers:
                if it.IsOnLayer(l):
                    out.append((l, p.x, p.y))
        elif c == "PCB_VIA":
            p = it.GetPosition()
            for l in layers:
                out.append((l, p.x, p.y))
        else:
            for p in (it.GetStart(), it.GetEnd()):
                out.append((it.GetLayer(), p.x, p.y))
    return out


def ripup_edge_violators(board, layers):
    """Delete tracks closer than EDGE_CLEAR to the outline or a barrier slot.

    Returns the set of netcodes left broken, for the router to reconnect.
    """
    shapes = []
    for d in board.GetDrawings():
        if d.GetLayer() == pcbnew.Edge_Cuts:
            try:
                shapes.append(d.GetEffectiveShape())
            except Exception:
                pass
    doomed, nets = [], set()
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA" or not pcbnew.IsCopperLayer(t.GetLayer()):
            continue
        # Any signal track still sitting on a reserved plane layer goes, whether or
        # not it violates edge clearance: it fragments the plane, and it would also
        # give the router an anchor on a layer it is not allowed to route on.
        if t.GetLayer() not in layers:
            doomed.append(t)
            nets.add(t.GetNetCode())
            continue
        lim = int(EDGE_CLEAR + t.GetWidth() / 2)
        a, b = t.GetStart(), t.GetEnd()
        probes = [pcbnew.VECTOR2I(int(a.x + (b.x - a.x) * i / 16),
                                  int(a.y + (b.y - a.y) * i / 16)) for i in range(17)]
        if any(sh.Collide(p, lim) for sh in shapes for p in probes):
            doomed.append(t)
            nets.add(t.GetNetCode())
    for t in doomed:
        board.Remove(t)
    print(f"ripped up {len(doomed)} edge-violating tracks on {len(nets)} nets")
    return nets


def main(path, nets):
    board = pcbnew.LoadBoard(path)
    planes = {"In1.Cu", "In4.Cu"}          # ground / 3V3 -- must stay solid
    layers = [l for l in board.GetEnabledLayers().Seq()
              if pcbnew.IsCopperLayer(l) and board.GetLayerName(l) not in planes]
    netmap = {ni.GetNetname(): c for c, ni in board.GetNetsByNetcode().items()}
    codename = {c: ni.GetNetname() for c, ni in board.GetNetsByNetcode().items()}

    # Rip-up is a SEPARATE process invocation (`RIPUP`): board.Remove() leaves the
    # SWIG board proxy stale, and even LoadBoard afterwards returns a broken object.
    if nets and nets[0] == "RIPUP":
        broken = ripup_edge_violators(board, layers)
        pcbnew.SaveBoard(path, board)
        print("BROKEN_NETS=" + ",".join(sorted(
            codename[c] for c in broken if codename.get(c))))
        return

    for net in nets:
        code = netmap[net]
        for attempt in range(24):
            cl = clusters(board, code)
            if len(cl) < 2:
                print(f"{net}: connected")
                break
            cl.sort(key=len, reverse=True)
            tgt, src = cl[0], cl[-1]
            grid = Grid(board, code, layers)
            ta = anchors(board, tgt, layers)
            goals = {(l, grid.cell(x, y)) for l, x, y in ta}
            best = None
            for sl, sx, sy in anchors(board, src, layers):
                p = route(grid, (sx, sy), sl, goals)
                if p and (best is None or len(p) < len(best[0])):
                    best = (p, (sx, sy))
            if not best:
                print(f"{net}: NO PATH ({len(cl)} clusters)")
                break
            p, sxy = best
            end_cell = (p[-1][1], p[-1][2])
            exy = min(((x, y) for l, x, y in ta
                       if grid.li[l] == p[-1][0] and grid.cell(x, y) == end_cell),
                      key=lambda q: 0, default=grid.pos(*end_cell))
            ns, nv = emit(board, grid, p, code, sxy, exy)
            print(f"{net}: routed {ns} segs, {nv} vias")

    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(path, board)
    print("saved")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
