"""Keyframe Reducer: reduce an Action on a protected copy.

SPDX-License-Identifier: GPL-3.0-or-later
"""
bl_info = {
    'name': 'Keyframe Reducer',
    'author': 'Killian Pichon / Codex',
    'version': (1, 1, 1),
    'blender': (5, 2, 0),
    'location': 'Graph Editor > Sidebar > Key Reducer',
    'description': 'Reduce all or selected keys on a copy, with before/after comparison',
    'category': 'Animation',
}

import importlib
import json
import math
import sys
import uuid
from dataclasses import asdict

import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, IntProperty,
                       PointerProperty, StringProperty)

# Blender can reload only this package when installing over an enabled version.
# Refresh cached submodules before binding their classes/functions. Selection
# imports engine helpers, so the order must follow core -> engine -> selection.
# On a cold start none of these modules is cached, so normal imports suffice.
for _submodule_name in ('core', 'engine', 'selection'):
    _cached_module = sys.modules.get(f'{__package__}.{_submodule_name}')
    if _cached_module is not None:
        importlib.reload(_cached_module)
del _submodule_name, _cached_module

from .engine import Settings, find_slot, slot_curves, reduce_action


class KR_Settings(bpy.types.PropertyGroup):
    scope: EnumProperty(name='Scope', items=[
        ('ACTION', 'Entire Action', 'Reduce the transforms in the active Action'),
        ('KEYS', 'Selected Keys', 'Reduce only selected, visible keyframe runs in the Graph Editor')],
        default='ACTION')
    strength: FloatProperty(name='Strength', description='Tolerance multiplier: higher values allow fewer keys',
                            default=1.0, min=0.01, max=20.0, soft_max=5.0, precision=2)
    position_error: FloatProperty(name='Position', description='Vector error in LOCAL units, before armature scale',
                                  default=0.1, min=0.000001, max=100.0, precision=4)
    rotation_error: FloatProperty(name='Rotation', description='Quaternion angular error; vector error of unwrapped Euler angles',
                                  default=math.radians(0.5), min=0.000001, max=math.pi, subtype='ANGLE')
    scale_error: FloatProperty(name='Scale', description='Vector error of scale factors',
                               default=0.001, min=0.000001, max=1.0, precision=4)
    interpolation: EnumProperty(name='Curves', items=[
        ('BEZIER', 'Smooth Bezier', 'Auto Clamped handles with error validation'),
        ('LINEAR', 'Linear', 'Linear interpolation, useful for mocap imports')], default='BEZIER')
    selected_only: BoolProperty(name='Selected Bones Only', default=False,
                               description='Use bone selection in Pose Mode; otherwise use all transform channels in the active slot')
    preserve_extrema: BoolProperty(name='Keep Significant Extremes', default=True,
                                  description='Protect meaningful direction changes; quaternion rotations are checked by angular error')
    preserve_marked: BoolProperty(name='Protect Extreme / Breakdown Keys', default=True,
                                 description='Keep the times of keys marked Extreme or Breakdown across the XYZ/WXYZ group')
    dense_check: BoolProperty(name='Validate Every 0.25 Frame', default=False,
                             description='Use finer sampling; otherwise validate every 0.5 frame and at original key times')
    show_advanced: BoolProperty(name='Tolerances and Options', default=False)
    source: PointerProperty(type=bpy.types.Action)
    reduced: PointerProperty(type=bpy.types.Action)
    slot_identifier: StringProperty()
    owner_token: StringProperty()
    before: IntProperty()
    after: IntProperty()
    groups: IntProperty()
    message: StringProperty()
    last_scope: StringProperty(default='ACTION')
    selection_json: StringProperty()
    selection_count: IntProperty()


def current_pair(ob):
    st = ob.kr_settings
    ad = ob.animation_data
    return bool(ad and st.source and st.reduced and ad.action in (st.source, st.reduced))


def assign(ob, action, identifier):
    slot = find_slot(action, identifier)
    if slot is None:
        raise ValueError('The original slot no longer exists in this Action.')
    ad = ob.animation_data_create()
    ad.action = action
    ad.action_slot = slot
    ob.update_tag()


def capture_key_selection(context, action, slot):
    if context.area is None or context.area.type != 'GRAPH_EDITOR':
        raise ValueError('Select keys and start the reduction from the Graph Editor.')
    if context.space_data.mode != 'FCURVES':
        raise ValueError('Switch the Graph Editor to F-Curves mode instead of Drivers.')
    visible = {fc.as_pointer() for fc in context.visible_fcurves}
    captured = []
    for fc in slot_curves(action, slot):
        if fc.as_pointer() not in visible or fc.hide or fc.lock:
            continue
        frames = [float(k.co.x) for k in fc.keyframe_points if k.select_control_point]
        if frames:
            captured.append({'data_path': fc.data_path, 'array_index': fc.array_index, 'frames': frames})
    if not captured:
        raise ValueError('No visible keys selected. Select key points, not just their handles.')
    return captured


def run_reduction(context, new_selection=False):
    ob = context.active_object
    if ob is None or ob.animation_data is None or ob.animation_data.action is None:
        raise ValueError('Assign an active Action, or bake your NLA sequence first.')
    ad = ob.animation_data
    if ad.use_tweak_mode:
        raise ValueError('Exit NLA Tweak Mode with Tab before reducing keys.')
    st = ob.kr_settings
    reuse = current_pair(ob) and st.last_scope == st.scope and not new_selection
    if reuse:
        source, identifier = st.source, st.slot_identifier
    else:
        source = ad.action
        if ad.action_slot is None:
            raise ValueError('Choose the armature slot in the Action Editor.')
        identifier = ad.action_slot.identifier
    key_selection = None
    if st.scope == 'KEYS':
        if reuse and st.selection_json:
            key_selection = json.loads(st.selection_json)
        else:
            key_selection = capture_key_selection(context, ad.action, ad.action_slot)
    selected = None
    if st.selected_only:
        if ob.type != 'ARMATURE' or ob.mode != 'POSE':
            raise ValueError('Switch to Pose Mode to reduce selected bones.')
        selected = {bone.name for bone in ob.data.bones if bone.select}
        if not selected:
            raise ValueError('Select at least one bone.')
    settings = Settings(strength=st.strength, position_error=st.position_error,
                        rotation_error=st.rotation_error, scale_error=st.scale_error,
                        interpolation=st.interpolation, preserve_extrema=st.preserve_extrema,
                        preserve_marked=st.preserve_marked,
                        sample_step=0.25 if st.dense_check else 0.5, selected_bones=selected,
                        key_selection=key_selection)
    result = source.copy()
    result.name = source.name + '_KR'
    wm = context.window_manager
    wm.progress_begin(0, 100)
    try:
        report = reduce_action(result, find_slot(result, identifier), settings,
                               progress=lambda done, total: wm.progress_update(done/total*100))
    except Exception:
        bpy.data.actions.remove(result)
        raise
    finally:
        wm.progress_end()
    old_result = st.reduced if current_pair(ob) else None
    if not st.owner_token:
        st.owner_token = uuid.uuid4().hex
    result['_kr_owner'] = st.owner_token
    result['kr_report'] = json.dumps(asdict(report), ensure_ascii=False)
    serial_settings = asdict(settings)
    if selected is not None:
        serial_settings['selected_bones'] = sorted(selected)
    result['kr_settings'] = json.dumps(serial_settings, ensure_ascii=False)
    result['kr_source_name'] = source.name
    source.use_fake_user = True
    result.use_fake_user = True
    st.source = source
    st.reduced = result
    st.slot_identifier = identifier
    st.last_scope = st.scope
    st.selection_json = json.dumps(key_selection) if key_selection is not None else ''
    st.selection_count = sum(len(entry['frames']) for entry in key_selection) if key_selection is not None else 0
    st.before, st.after = report.before, report.after
    st.groups = report.reduced_groups
    st.message = ' / '.join(report.warnings)
    assign(ob, result, identifier)
    if old_result and old_result != source and old_result.get('_kr_owner') == st.owner_token:
        # Do not remove a result referenced by any other object, NLA strip,
        # or saved comparison. Only discard an unused generated preview.
        if old_result.users == int(old_result.use_fake_user):
            bpy.data.actions.remove(old_result)
    context.scene.frame_set(context.scene.frame_current, subframe=context.scene.frame_subframe)
    return report


class KR_OT_reduce(bpy.types.Operator):
    bl_idname = 'kr.reduce'
    bl_label = 'Reduce on a Copy'
    bl_description = 'Create a reduced copy. Recalculate always starts from the protected source'
    bl_options = {'REGISTER', 'UNDO'}
    new_selection: BoolProperty(default=False, options={'SKIP_SAVE'},
        description='Capture a new selection from the displayed Action, keeping its existing reductions')

    @classmethod
    def poll(cls, context):
        return bool(context.active_object)

    def execute(self, context):
        try:
            report = run_reduction(context, new_selection=self.new_selection)
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        percent = 100*(1-report.after/report.before) if report.before else 0
        self.report({'INFO'}, f'{report.before:,} -> {report.after:,} keys (-{percent:.1f}%)')
        return {'FINISHED'}


class KR_OT_compare(bpy.types.Operator):
    bl_idname = 'kr.compare'
    bl_label = 'Compare'
    bl_description = 'Show the source or reduced copy without modifying keys'
    bl_options = {'REGISTER', 'UNDO'}
    reduced: BoolProperty(default=False)

    def execute(self, context):
        ob = context.active_object
        if not ob or not current_pair(ob):
            self.report({'ERROR'}, 'No active comparison for this object.')
            return {'CANCELLED'}
        if ob.animation_data.use_tweak_mode:
            self.report({'ERROR'}, 'Exit Tweak Mode before comparing Actions.')
            return {'CANCELLED'}
        st = ob.kr_settings
        try:
            assign(ob, st.reduced if self.reduced else st.source, st.slot_identifier)
        except ValueError as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        context.scene.frame_set(context.scene.frame_current, subframe=context.scene.frame_subframe)
        return {'FINISHED'}


class KR_OT_finish(bpy.types.Operator):
    bl_idname = 'kr.finish'
    bl_label = 'Keep Copy for Editing'
    bl_description = 'Activate the reduced copy and finish comparison. The original remains available in the Actions'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ob = context.active_object
        if not ob or not current_pair(ob) or ob.animation_data.use_tweak_mode:
            self.report({'ERROR'}, 'No comparison available, or Tweak Mode is active.')
            return {'CANCELLED'}
        st = ob.kr_settings
        try:
            assign(ob, st.reduced, st.slot_identifier)
        except ValueError as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        st.source = None
        st.reduced = None
        st.slot_identifier = ''
        st.selection_json = ''
        st.selection_count = 0
        context.scene.frame_set(context.scene.frame_current, subframe=context.scene.frame_subframe)
        return {'FINISHED'}


def draw_panel(self, context):
    layout = self.layout
    ob = context.active_object
    if ob is None:
        layout.label(text='Select your armature.', icon='INFO')
        return
    st = ob.kr_settings
    ad = ob.animation_data
    action = ad.action if ad else None
    if action is None:
        layout.label(text='No active Action.', icon='INFO')
        layout.label(text='Bake the NLA sequence, then reduce.')
        return
    pair = current_pair(ob)
    reuse = pair and st.last_scope == st.scope
    layout.label(text='Source: ' + (st.source.name if reuse else action.name), icon='ACTION')
    if ad.use_tweak_mode:
        layout.label(text='Exit Tweak Mode (Tab).', icon='ERROR')
        return
    if ad.use_nla and any(not t.mute for t in ad.nla_tracks):
        box = layout.box()
        box.label(text='NLA tracks are active.', icon='INFO')
        box.label(text='Only the active Action is reduced.')
    layout.prop(st, 'scope')
    if st.scope == 'KEYS':
        if reuse and st.selection_json:
            layout.label(text=f'Captured selection: {st.selection_count:,} keys')
        else:
            layout.label(text='Select keys in the Graph Editor.')
        layout.label(text='Unselected gaps are preserved.')
    layout.prop(st, 'strength', slider=True)
    layout.prop(st, 'interpolation')
    if ob.type == 'ARMATURE':
        layout.prop(st, 'selected_only')
    layout.label(text='Selected channels / full WXYZ' if st.scope == 'KEYS'
                 else 'XYZ / quaternion keys stay aligned', icon='LINKED')
    layout.prop(st, 'show_advanced', icon='TRIA_DOWN' if st.show_advanced else 'TRIA_RIGHT', emboss=False)
    if st.show_advanced:
        box = layout.box()
        box.label(text='Tolerances at Strength = 1')
        box.prop(st, 'position_error')
        box.label(text='Position: local rig units')
        box.prop(st, 'rotation_error')
        box.prop(st, 'scale_error')
        box.prop(st, 'preserve_extrema')
        box.prop(st, 'preserve_marked')
        box.prop(st, 'dense_check')
    row = layout.row()
    row.enabled = st.scope != 'KEYS' or (reuse and bool(st.selection_json)) or context.area.type == 'GRAPH_EDITOR'
    row.operator('kr.reduce', text='Recalculate from Source' if reuse else 'Reduce on a Copy', icon='MOD_DECIM')
    if st.scope == 'KEYS' and reuse:
        row = layout.row()
        row.enabled = context.area.type == 'GRAPH_EDITOR'
        row.operator('kr.reduce', text='Reduce New Selection', icon='RESTRICT_SELECT_OFF').new_selection = True
    if pair:
        box = layout.box()
        percent = 100*(1-st.after/st.before) if st.before else 0
        box.label(text=f'{st.before:,} -> {st.after:,} keys')
        box.label(text=f'-{percent:.1f}% / {st.groups} groups reduced')
        row = box.row(align=True)
        row.operator('kr.compare', text='Original', depress=action == st.source).reduced = False
        row.operator('kr.compare', text='Reduced', depress=action == st.reduced).reduced = True
        box.operator('kr.finish', icon='CHECKMARK')
        box.label(text='Keep the copy before editing keys.')
        if st.message:
            box.label(text='Some channels were preserved.', icon='INFO')
            for message in st.message.split(' / '):
                if message.startswith('Quaternion selection:'):
                    box.label(text='Quaternion: select W, X, Y, Z.')
                elif message.startswith('Selection'):
                    box.label(text='Select at least 3 consecutive keys.')
            box.label(text='Details: Action property kr_report.')
    layout.separator()
    layout.label(text='Local tolerance; no foot contact locking.')


class KR_PT_graph(bpy.types.Panel):
    bl_label = 'Keyframe Reducer 1.1.1'
    bl_idname = 'KR_PT_graph'
    bl_space_type = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Key Reducer'
    draw = draw_panel


class KR_PT_view(bpy.types.Panel):
    bl_label = 'Keyframe Reducer 1.1.1'
    bl_idname = 'KR_PT_view'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Key Reducer'
    draw = draw_panel


CLASSES = (KR_Settings, KR_OT_reduce, KR_OT_compare, KR_OT_finish, KR_PT_graph, KR_PT_view)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Object.kr_settings = PointerProperty(type=KR_Settings)


def unregister():
    del bpy.types.Object.kr_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == '__main__':
    register()
