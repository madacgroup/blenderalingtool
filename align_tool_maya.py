bl_info = {
    "name": "Align Tool (Maya style)",
    "author": "Diego",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Ctrl+Alt+A  |  Sidebar > Align Tool  |  Object menu",
    "description": "Align Tool estilo Maya: o primeiro objeto e a ancora; as pecas selecionadas depois alinham nele por alcas Min/Centro/Max",
    "category": "Object",
}

import bpy
import gpu
import blf
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from bpy_extras.view3d_utils import location_3d_to_region_2d

AXIS_COL = [(0.95, 0.30, 0.30), (0.45, 0.80, 0.20), (0.25, 0.55, 1.00)]
AXIS_NAME = ["X", "Y", "Z"]
CYAN = (0.17, 0.72, 0.86)
MODE_NAME = ["Off", "Min", "Centro", "Max"]

S = {"anchor": None, "A": None, "objs": [], "b": [], "BL": None, "BH": None, "modes": [0, 0, 0],
     "handles": [], "hover": None, "h3d": None, "h2d": None}


def bounds_of(o, dg):
    ev = o.evaluated_get(dg)
    pts = [ev.matrix_world @ Vector(c) for c in ev.bound_box]
    lo = Vector((min(p[i] for p in pts) for i in range(3)))
    hi = Vector((max(p[i] for p in pts) for i in range(3)))
    return lo, hi


def refresh(context):
    dg = context.evaluated_depsgraph_get()
    anc = S["anchor"]
    S["A"] = bounds_of(anc, dg)
    S["BL"], S["BH"] = S["A"]
    objs, bounds = [], []
    for o in context.selected_objects:
        if o == anc:
            continue
        objs.append(o)
        bounds.append(bounds_of(o, dg))
    S["objs"], S["b"] = objs, bounds


def target_value(a, mode):
    L, H = S["BL"][a], S["BH"][a]
    return L if mode == 1 else H if mode == 3 else (L + H) * 0.5


def deltas():
    out = []
    for lo, hi in S["b"]:
        d = Vector((0, 0, 0))
        for a in range(3):
            m = S["modes"][a]
            if not m:
                continue
            v = target_value(a, m)
            cur = lo[a] if m == 1 else hi[a] if m == 3 else (lo[a] + hi[a]) * 0.5
            d[a] = v - cur
        out.append(d)
    return out


def box_lines(lo, hi):
    c = [Vector((hi[0] if i & 1 else lo[0], hi[1] if i & 2 else lo[1], hi[2] if i & 4 else lo[2])) for i in range(8)]
    pts = []
    for i in range(8):
        for b in (1, 2, 4):
            if not i & b:
                pts += [c[i], c[i | b]]
    return pts


def plane_pts(a, v, lo, hi):
    b, c = (a + 1) % 3, (a + 2) % 3

    def q(bv, cv):
        p = Vector((0, 0, 0))
        p[a], p[b], p[c] = v, bv, cv
        return p
    return [q(lo[b], lo[c]), q(hi[b], lo[c]), q(hi[b], hi[c]), q(lo[b], hi[c])]


def _draw(kind, pts, col, width=1.0):
    sh = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(sh, kind, {"pos": [tuple(p) for p in pts]})
    gpu.state.line_width_set(width)
    gpu.state.point_size_set(7.0)
    sh.uniform_float("color", col)
    batch.draw(sh)


def handle_off():
    return (S["BH"] - S["BL"]).length * 0.12 + 0.02


def handle_world(a, t, off):
    BL, BH = S["BL"], S["BH"]
    if a == 0:
        return Vector((t, BH[1] + off, BL[2]))
    if a == 1:
        return Vector((BH[0] + off, t, BL[2]))
    return Vector((BL[0] - off, BH[1] + off, t))


def draw_3d():
    if S["A"] is None:
        return
    gpu.state.depth_test_set('NONE')
    gpu.state.blend_set('ALPHA')
    BL, BH, modes = S["BL"], S["BH"], S["modes"]
    diag = (BH - BL).length
    off = handle_off()
    dl = deltas()
    active = any(modes)

    _draw('LINES', box_lines(BL, BH), (0.35, 0.95, 0.45, 1.0), 2.5)
    ac = (BL + BH) * 0.5
    for a in range(3):
        e = Vector((0, 0, 0))
        e[a] = max(max(BH - BL) * 0.35, diag * 0.03)
        _draw('LINES', [ac - e, ac + e], AXIS_COL[a] + (1.0,), 2.0)
    _draw('POINTS', [ac], (1, 1, 1, 1))

    for lo, hi in S["b"]:
        _draw('LINES', box_lines(lo, hi), (1, 1, 1, 0.25), 1.0)
        c = (lo + hi) * 0.5
        r = max(max((hi - lo)) * 0.35, diag * 0.03)
        for a in range(3):
            e = Vector((0, 0, 0))
            e[a] = r
            _draw('LINES', [c - e, c + e], AXIS_COL[a] + (1.0,), 2.0)
        _draw('POINTS', [c], (1, 1, 1, 1))

    for a in range(3):
        p0 = handle_world(a, BL[a], off)
        p1 = handle_world(a, BH[a], off)
        _draw('LINES', [p0, p1], AXIS_COL[a] + (0.6,), 1.5)

    if active:
        dest = [(lo + d, hi + d) for (lo, hi), d in zip(S["b"], dl)]
        allb = S["b"] + dest + [S["A"]]
        ul = Vector((min(b[0][i] for b in allb) for i in range(3))) - Vector((diag * 0.08,) * 3)
        uh = Vector((max(b[1][i] for b in allb) for i in range(3))) + Vector((diag * 0.08,) * 3)
        for a in range(3):
            m = modes[a]
            if not m:
                continue
            col = AXIS_COL[a]
            v = target_value(a, m)
            pp = plane_pts(a, v, ul, uh)
            _draw('TRI_FAN', pp, col + (0.08,))
            _draw('LINE_LOOP', pp, col + (0.7,), 1.5)
            for dlo, dhi in dest:
                rp = plane_pts(a, v, dlo, dhi)
                _draw('TRI_FAN', rp, col + (0.28,))
                _draw('LINE_LOOP', rp, col + (1.0,), 2.5)
        for (lo, hi), (dlo, dhi), d in zip(S["b"], dest, dl):
            if d.length > 1e-5:
                _draw('LINES', box_lines(dlo, dhi), (1.0, 0.85, 0.3, 0.9), 1.5)
                _draw('LINES', [(lo + hi) * 0.5, (dlo + dhi) * 0.5], CYAN + (0.9,), 1.5)
    gpu.state.blend_set('NONE')


def draw_quad(x, y, s, col, filled):
    pts = [(x - s, y - s), (x + s, y - s), (x + s, y + s), (x - s, y + s)]
    sh = gpu.shader.from_builtin('UNIFORM_COLOR')
    if filled:
        b = batch_for_shader(sh, 'TRI_FAN', {"pos": pts})
        sh.uniform_float("color", col + (1.0,))
        b.draw(sh)
    b = batch_for_shader(sh, 'LINE_LOOP', {"pos": pts})
    gpu.state.line_width_set(1.5)
    sh.uniform_float("color", col + (1.0,))
    b.draw(sh)


def draw_2d():
    ctx = bpy.context
    S["handles"] = []
    if S["A"] is None:
        return
    region, rv3d = ctx.region, ctx.region_data
    if rv3d is None:
        return
    gpu.state.blend_set('ALPHA')
    off = handle_off()
    for a in range(3):
        for m in (1, 2, 3):
            t = target_value(a, m)
            p = location_3d_to_region_2d(region, rv3d, handle_world(a, t, off))
            if p is None:
                continue
            S["handles"].append((a, m, p))
            hov = S["hover"] == (a, m)
            on = S["modes"][a] == m
            draw_quad(p.x, p.y, 8 if hov else 6, AXIS_COL[a], on)
            if hov:
                blf.size(0, 13)
                blf.color(0, 1, 1, 1, 1)
                blf.position(0, p.x + 12, p.y + 10, 0)
                blf.draw(0, "%s %s" % (AXIS_NAME[a], MODE_NAME[m]))
    cp = location_3d_to_region_2d(region, rv3d, (S["BL"] + S["BH"]) * 0.5)
    if cp is not None:
        blf.size(0, 13)
        blf.color(0, 0.35, 0.95, 0.45, 1)
        blf.position(0, cp.x + 10, cp.y + 10, 0)
        blf.draw(0, "Âncora")
    gpu.state.blend_set('NONE')


class OBJECT_OT_align_tool_maya(bpy.types.Operator):
    bl_idname = "object.align_tool_maya"
    bl_label = "Align Tool"
    bl_description = "Alinha objetos selecionados usando alcas Min/Centro/Max por eixo (estilo Maya)"
    bl_options = {'REGISTER', 'UNDO'}

    def _status(self, context):
        parts = ["%s:%s" % (AXIS_NAME[a], MODE_NAME[S["modes"][a]]) for a in range(3)]
        context.workspace.status_text_set(
            "Align Tool  |  Ancora: %s  |  " % S["anchor"].name + "  ".join(parts) +
            "  |  Selecione a peca e clique nas alcas  |  X/Y/Z alterna eixo  |  Enter aplica  |  A nova ancora (ativo)  |  R zera  |  Esc sai")

    def _end(self, context):
        if S["h3d"]:
            bpy.types.SpaceView3D.draw_handler_remove(S["h3d"], 'WINDOW')
        if S["h2d"]:
            bpy.types.SpaceView3D.draw_handler_remove(S["h2d"], 'WINDOW')
        S["h3d"] = S["h2d"] = None
        context.workspace.status_text_set(None)
        if context.area:
            context.area.tag_redraw()

    def invoke(self, context, event):
        if context.area is None or context.area.type != 'VIEW_3D':
            self.report({'WARNING'}, "Execute no viewport 3D")
            return {'CANCELLED'}
        if not context.selected_objects:
            self.report({'WARNING'}, "Selecione o objeto que sera a ancora")
            return {'CANCELLED'}
        act = context.view_layer.objects.active
        S["anchor"] = act if act in context.selected_objects else context.selected_objects[0]
        S["modes"] = [0, 0, 0]
        S["hover"] = None
        refresh(context)
        S["h3d"] = bpy.types.SpaceView3D.draw_handler_add(draw_3d, (), 'WINDOW', 'POST_VIEW')
        S["h2d"] = bpy.types.SpaceView3D.draw_handler_add(draw_2d, (), 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self)
        self._status(context)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _apply(self, context):
        dl = deltas()
        for o, d in zip(S["objs"], dl):
            if d.length > 1e-6:
                mw = o.matrix_world.copy()
                mw.translation += d
                o.matrix_world = mw
        bpy.ops.ed.undo_push(message="Align Tool")
        S["modes"] = [0, 0, 0]
        context.view_layer.update()
        refresh(context)

    def modal(self, context, event):
        if context.area:
            context.area.tag_redraw()
        try:
            refresh(context)
        except ReferenceError:
            self._end(context)
            return {'CANCELLED'}

        if event.type == 'MOUSEMOVE':
            mx, my = event.mouse_region_x, event.mouse_region_y
            S["hover"] = None
            best = 14.0
            for a, m, p in S["handles"]:
                d = ((p.x - mx) ** 2 + (p.y - my) ** 2) ** 0.5
                if d < best:
                    best, S["hover"] = d, (a, m)
            return {'PASS_THROUGH'}

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and S["hover"]:
            a, m = S["hover"]
            S["modes"][a] = 0 if S["modes"][a] == m else m
            self._status(context)
            return {'RUNNING_MODAL'}

        if event.value == 'PRESS':
            if event.type in {'X', 'Y', 'Z'}:
                a = "XYZ".index(event.type)
                S["modes"][a] = (S["modes"][a] + 1) % 4
                self._status(context)
                return {'RUNNING_MODAL'}
            if event.type in {'RET', 'NUMPAD_ENTER', 'SPACE'}:
                if any(S["modes"]):
                    self._apply(context)
                    self._status(context)
                return {'RUNNING_MODAL'}
            if event.type == 'A':
                act = context.view_layer.objects.active
                if act:
                    S["anchor"] = act
                    S["modes"] = [0, 0, 0]
                    self._status(context)
                return {'RUNNING_MODAL'}
            if event.type == 'R':
                S["modes"] = [0, 0, 0]
                self._status(context)
                return {'RUNNING_MODAL'}
            if event.type in {'ESC', 'RIGHTMOUSE'}:
                self._end(context)
                return {'FINISHED'}
        return {'PASS_THROUGH'}


class VIEW3D_PT_align_tool_maya(bpy.types.Panel):
    bl_label = "Align Tool"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Align Tool"

    def draw(self, context):
        col = self.layout.column(align=True)
        col.operator("object.align_tool_maya", icon='ALIGN_CENTER')
        col.label(text="Ctrl+Alt+A no viewport")


def menu_func(self, context):
    self.layout.operator("object.align_tool_maya", icon='ALIGN_CENTER')


addon_keymaps = []
classes = (OBJECT_OT_align_tool_maya, VIEW3D_PT_align_tool_maya)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.VIEW3D_MT_object.append(menu_func)
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name='Object Mode', space_type='EMPTY')
        kmi = km.keymap_items.new("object.align_tool_maya", 'A', 'PRESS', ctrl=True, alt=True)
        addon_keymaps.append((km, kmi))


def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    bpy.types.VIEW3D_MT_object.remove(menu_func)
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
