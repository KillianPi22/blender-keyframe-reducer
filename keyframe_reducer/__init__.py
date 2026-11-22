"""Keyframe Reducer: reduce an Action on a protected copy.

SPDX-License-Identifier: GPL-3.0-or-later
"""
bl_info = {
    'name': 'Keyframe Reducer',
    'author': 'Killian Pichon / Codex',
    'version': (1, 5, 0),
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
import textwrap
from dataclasses import asdict

import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, IntProperty,
                       PointerProperty, StringProperty)

# Blender can reload only this package when installing over an enabled version.
# Refresh cached submodules before binding their classes/functions. Selection
# imports engine helpers; simplify also imports selection.
# On a cold start none of these modules is cached, so normal imports suffice.
_cached_preview = sys.modules.get(f'{__package__}.preview')
if _cached_preview is not None:
    _cached_preview.shutdown()
del _cached_preview
for _submodule_name in ('core', 'fitting', 'engine', 'selection', 'simplify', 'preview'):
    _cached_module = sys.modules.get(f'{__package__}.{_submodule_name}')
    if _cached_module is not None:
        importlib.reload(_cached_module)
del _submodule_name, _cached_module

from .engine import BONE_PATH, Settings, find_slot, slot_curves, reduce_action
from . import preview


def _preview_changed(self, context):
    preview.request(self.id_data)


class KR_Settings(bpy.types.PropertyGroup):
    method: EnumProperty(name='Tool', items=[
        ('REDUCE', 'Key Reducer', 'Rebuild grouped transform curves within local error tolerances'),
        ('SIMPLIFY', 'Simplify Curve', 'Simplify selected transform curves within local shape tolerances')],
        default='REDUCE', update=_preview_changed)
    simplify_mode: EnumProperty(name='Curve Style', items=[
        ('KEEP', 'Keep Existing Handles', 'Remove keys using source interpolation and existing manual handles, as in version 1.2'),
        ('FIT', 'Editable Bezier', 'Fit fewer keys with aligned interior tangents. Rebuilds selected tangents, including manual handles; keeps marked key times and values')],
        default='KEEP', update=_preview_changed)
    scope: EnumProperty(name='Scope', items=[
        ('ACTION', 'Entire Action', 'Reduce the transforms in the active Action'),
        ('KEYS', 'Selected Keys', 'Reduce only selected, visible keyframe runs in the Graph Editor')],
        default='ACTION')
    strength: FloatProperty(name='Strength', description='Tolerance multiplier: higher values allow fewer keys',
                            default=1.0, min=0.01, max=20.0, soft_max=5.0, precision=2)
    position_error: FloatProperty(name='Position', description='LOCAL units before armature scale: vector error in Key Reducer, per-axis error in Simplify Curve',
                                  default=0.1, min=0.000001, max=100.0, precision=4, update=_preview_changed)
    rotation_error: FloatProperty(name='Rotation', description='Quaternion angular error; unwrapped Euler vector error in Key Reducer or per-axis error in Simplify Curve',
                                  default=math.radians(0.5), min=0.000001, max=math.pi, subtype='ANGLE', update=_preview_changed)
    scale_error: FloatProperty(name='Scale', description='Scale-factor vector error in Key Reducer, per-axis error in Simplify Curve',
                               default=0.001, min=0.000001, max=1.0, precision=4, update=_preview_changed)
    interpolation: EnumProperty(name='Curves', items=[
        ('BEZIER', 'Smooth Bezier', 'Auto Clamped handles with error validation'),
        ('LINEAR', 'Linear', 'Linear interpolation, useful for mocap imports')], default='BEZIER')
    selected_only: BoolProperty(name='Selected Bones Only', default=False,
                               description='Use bone selection in Pose Mode; otherwise use all transform channels in the active slot')
    preserve_extrema: BoolProperty(name='Keep Significant Extremes', default=True,
                                  description='Protect meaningful direction changes; quaternion rotations are checked by angular error', update=_preview_changed)
    preserve_marked: BoolProperty(name='Protect Extreme / Breakdown Keys', default=True,
                                 description='Keep the times of keys marked Extreme or Breakdown across the XYZ/WXYZ group', update=_preview_changed)
    preserve_manual: BoolProperty(name='Protect Manual Tangents', default=True,
                                 description='Keep Bezier keys with Free or Aligned handles. Disable to allow their removal within the tolerance')
    dense_check: BoolProperty(name='Validate Every 0.25 Frame', default=False,
                             description='Add a 0.25-frame grid instead of 0.5. Simplify also checks between source keys', update=_preview_changed)
    preview_amount: FloatProperty(name='Reduction', default=1.0, min=.1, max=10.0,
        soft_min=.25, soft_max=4., precision=2, update=_preview_changed,
        description='Interactive tolerance multiplier. Higher values allow more shape change and usually fewer keys; this is not a target key count')
    preview_notice: StringProperty()
    show_advanced: BoolProperty(name='Tolerances and Options', default=False)
    source: PointerProperty(type=bpy.types.Action)
    reduced: PointerProperty(type=bpy.types.Action)
    slot_identifier: StringProperty()
    owner_token: StringProperty()
    before: IntProperty()
    after: IntProperty()
    scope_before: IntProperty(default=-1)
    scope_after: IntProperty(default=-1)
    groups: IntProperty()
    message: StringProperty()
    last_scope: StringProperty(default='ACTION')
    last_method: StringProperty(default='REDUCE')
    last_simplify_mode: StringProperty(default='KEEP')
    last_settings_signature: StringProperty()
    selection_json: StringProperty()
    selection_count: IntProperty()


def current_pair(ob):
    st = ob.kr_settings
    ad = ob.animation_data
    return bool(ad and st.source and st.reduced and ad.action in (st.source, st.reduced))


def settings_signature(ob):
    """Small effective-settings record; never parse the large captured selection in draw."""
    st = ob.kr_settings
    simplify = st.method == 'SIMPLIFY'
    return json.dumps((st.method, 'KEYS' if simplify else st.scope,
        st.simplify_mode if simplify else st.interpolation,
        1.0 if simplify else st.strength, st.position_error, st.rotation_error,
        st.scale_error, st.preserve_extrema, st.preserve_marked, st.dense_check,
        st.preserve_manual if simplify and st.simplify_mode == 'KEEP' else False,
        st.selected_only, sorted(b.name for b in ob.pose.bones if b.select)
        if st.selected_only and ob.type == 'ARMATURE' else None))


def result_needs_update(ob):
    st = ob.kr_settings
    return bool(current_pair(ob) and st.last_settings_signature and
                st.last_settings_signature != settings_signature(ob))


def assign(ob, action, identifier):
    slot = find_slot(action, identifier)
    if slot is None:
        raise ValueError('The original slot no longer exists in this Action.')
    ad = ob.animation_data_create()
    ad.action = action
    ad.action_slot = slot
    ob.update_tag()


def capture_key_selection(context, action, slot, selected_bones=None):
    if context.area is None or context.area.type != 'GRAPH_EDITOR':
        raise ValueError('Select keys and start the reduction from the Graph Editor.')
    if context.space_data.mode != 'FCURVES':
        raise ValueError('Switch the Graph Editor to F-Curves mode instead of Drivers.')
    visible = {fc.as_pointer() for fc in context.visible_fcurves}
    captured = []
    for fc in slot_curves(action, slot):
        if fc.as_pointer() not in visible or fc.hide or fc.lock:
            continue
        if selected_bones is not None:
            match = BONE_PATH.match(fc.data_path)
            if not match or json.loads(match.group(1)) not in selected_bones:
                continue
        frames = [float(k.co.x) for k in fc.keyframe_points if k.select_control_point]
        if frames:
            captured.append({'data_path': fc.data_path, 'array_index': fc.array_index, 'frames': frames})
    if not captured:
        raise ValueError('No visible keys selected. Select key points, not just their handles.')
    return captured


def run_reduction(context, new_selection=False):
    ob = context.active_object
    if preview.session(ob):
        raise ValueError('Apply or cancel the interactive preview first.')
    if ob is None or ob.animation_data is None or ob.animation_data.action is None:
        raise ValueError('Assign an active Action, or bake your NLA sequence first.')
    ad = ob.animation_data
    if ad.use_tweak_mode:
        raise ValueError('Exit NLA Tweak Mode with Tab before reducing keys.')
    st = ob.kr_settings
    scope = 'KEYS' if st.method == 'SIMPLIFY' else st.scope
    reuse = current_pair(ob) and not new_selection
    if reuse:
        source, identifier = st.source, st.slot_identifier
    else:
        source = ad.action
        if ad.action_slot is None:
            raise ValueError('Choose the armature slot in the Action Editor.')
        identifier = ad.action_slot.identifier
    key_selection = None
    if scope == 'KEYS':
        if reuse and st.last_scope == scope and st.selection_json:
            key_selection = json.loads(st.selection_json)
        else:
            key_selection = capture_key_selection(context, ad.action, ad.action_slot)
    selected = None
    if st.selected_only:
        if ob.type != 'ARMATURE' or ob.mode != 'POSE':
            raise ValueError('Switch to Pose Mode to reduce selected bones.')
        selected = {bone.name for bone in ob.pose.bones if bone.select}
        if not selected:
            raise ValueError('Select at least one bone.')
    settings = Settings(strength=1.0 if st.method == 'SIMPLIFY' else st.strength, position_error=st.position_error,
                        rotation_error=st.rotation_error, scale_error=st.scale_error,
                        interpolation=st.interpolation, preserve_extrema=st.preserve_extrema,
                        preserve_marked=st.preserve_marked,
                        sample_step=0.25 if st.dense_check else 0.5, selected_bones=selected,
                        key_selection=key_selection, method=st.method,
                        preserve_manual=st.preserve_manual, simplify_mode=st.simplify_mode)
    result = source.copy()
    result.name = source.name + ('_Editable' if st.method == 'SIMPLIFY' and st.simplify_mode == 'FIT'
                                else '_Simplified' if st.method == 'SIMPLIFY' else '_KR')
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
    st.last_scope = scope
    st.last_method = st.method
    st.last_simplify_mode = st.simplify_mode
    st.last_settings_signature = settings_signature(ob)
    st.selection_json = json.dumps(key_selection) if key_selection is not None else ''
    st.selection_count = sum(len(entry['frames']) for entry in key_selection) if key_selection is not None else 0
    st.before, st.after = report.before, report.after
    st.scope_before, st.scope_after = report.scope_before, report.scope_after
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


class KR_OT_animation_profile(bpy.types.Operator):
    bl_idname = 'kr.animation_profile'
    bl_label = 'Bone Animation'
    bl_description = ('Prepare Editable Bezier on selected bones with significant extremes and marked poses protected. '
                      'Keeps your error tolerances; select keys and recalculate to create the result')
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(context.active_object and context.active_object.type == 'ARMATURE'
                    and not preview.session(context.active_object))

    def execute(self, context):
        st = context.active_object.kr_settings
        st.method, st.simplify_mode, st.selected_only = 'SIMPLIFY', 'FIT', True
        st.preserve_extrema = st.preserve_marked = True
        self.report({'INFO'}, 'Bone Animation ready. Select bone keys, then recalculate. Tolerances unchanged.')
        return {'FINISHED'}


class KR_OT_preview_start(bpy.types.Operator):
    bl_idname = 'kr.preview_start'
    bl_label = 'Start Interactive Preview'
    bl_description = 'Capture selected curve runs and bones, then adjust Reduction with automatic preview updates'
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return bool(context.active_object and context.area and context.area.type == 'GRAPH_EDITOR'
                    and not preview.session())

    def execute(self, context):
        try:
            preview.start(context)
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        return {'FINISHED'}


class KR_OT_preview_apply(bpy.types.Operator):
    bl_idname = 'kr.preview_apply'
    bl_label = 'Apply Preview'
    bl_description = 'Keep the completed current preview as an editable Action and end automatic updates'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return preview.ready(context.active_object)

    def execute(self, context):
        try:
            preview.apply(context)
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        return {'FINISHED'}


class KR_OT_preview_cancel(bpy.types.Operator):
    bl_idname = 'kr.preview_cancel'
    bl_label = 'Cancel Preview'
    bl_description = 'Stop pending work, restore the starting Action and selection, and remove unused temporary previews'
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return bool(preview.session())

    def execute(self, context):
        preview.cancel()
        return {'FINISHED'}


class KR_OT_preview_compare(bpy.types.Operator):
    bl_idname = 'kr.preview_compare'
    bl_label = 'Compare Preview'
    bl_options = {'REGISTER'}
    original: BoolProperty(default=False)

    def execute(self, context):
        try:
            preview.compare(context.active_object, self.original)
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        return {'FINISHED'}


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
        if preview.session(ob):
            self.report({'ERROR'}, 'Use the interactive preview comparison controls.')
            return {'CANCELLED'}
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
        if preview.session(ob):
            self.report({'ERROR'}, 'Use Apply Preview to keep the interactive result.')
            return {'CANCELLED'}
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


class KR_OT_cancel(bpy.types.Operator):
    bl_idname = 'kr.cancel'
    bl_label = 'Restore Original'
    bl_description = 'Restore the source Action and end comparison, retaining the result as an available Action'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ob = context.active_object
        if preview.session(ob):
            self.report({'ERROR'}, 'Use Cancel Preview to stop the interactive session.')
            return {'CANCELLED'}
        if not ob or not current_pair(ob) or ob.animation_data.use_tweak_mode:
            self.report({'ERROR'}, 'No comparison available, or Tweak Mode is active.')
            return {'CANCELLED'}
        st = ob.kr_settings
        try:
            assign(ob, st.source, st.slot_identifier)
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


def draw_preview(layout, ob, session):
    st = ob.kr_settings
    layout.label(text='Interactive Curve Preview', icon='FCURVE')
    layout.label(text='Source: '+session.source.name, icon='ACTION')
    count = sum(len(entry['frames']) for entry in session.selection)
    layout.label(text=f'Captured selection: {count:,} keys')
    if session.bones is not None:
        layout.label(text=f'Frozen bone filter: {len(session.bones)} bones')
    layout.label(text='Selection stays fixed during preview.')
    box = layout.box()
    box.prop(st, 'preview_amount', slider=True)
    box.label(text='More detail  <->  Fewer keys')
    box.label(text=f'Allowed rotation: {math.degrees(st.rotation_error*st.preview_amount):.3g}°')
    box.label(text=f'Position / axis: {st.position_error*st.preview_amount:.4g} local')
    box.label(text=f'Scale / axis: {st.scale_error*st.preview_amount:.4g}')
    # Keep the controls at fixed positions while progress/results change below.
    row = box.row(align=True)
    row.operator('kr.preview_compare', text='Original', depress=session.show_original).original = True
    column = row.row(align=True)
    column.enabled = session.displayed is not None
    column.operator('kr.preview_compare', text='Preview', depress=not session.show_original).original = False
    row = box.row(align=True)
    row.operator_context = 'EXEC_DEFAULT'
    apply = row.row(align=True)
    apply.enabled = preview.ready(ob)
    apply.operator('kr.preview_apply', icon='CHECKMARK')
    row.operator('kr.preview_cancel', text='Cancel', icon='X')
    status = {'WAITING': 'Waiting for slider...', 'COMPUTING': f'Calculating... {session.progress:.0%}',
              'READY': 'Preview ready', 'ERROR': 'Preview failed'}[session.status]
    box.label(text=status, icon='ERROR' if session.status == 'ERROR' else 'TIME' if session.status != 'READY' else 'CHECKMARK')
    if session.error:
        for line in textwrap.wrap(session.error, 38):
            box.label(text=line)
    if session.report:
        report = session.report
        if not preview.ready(ob):
            box.label(text='Showing the previous result.')
        box.label(text=f'{report.scope_before:,} -> {report.scope_after:,} keys')
        box.label(text=f'{100*(1-report.scope_after/report.scope_before):.1f}% removed')
        box.label(text=f'Result at Reduction {session.settings.strength:.2f}')
        if report.warnings:
            box.label(text='Some curves were preserved.', icon='INFO')
    layout.label(text='Apply before editing keys or saving.')
    layout.prop(st, 'show_advanced', text='Base Tolerances and Options',
                icon='TRIA_DOWN' if st.show_advanced else 'TRIA_RIGHT', emboss=False)
    if st.show_advanced:
        box = layout.box()
        box.label(text='At Reduction = 1.00')
        box.prop(st, 'position_error')
        box.prop(st, 'rotation_error')
        box.prop(st, 'scale_error')
        box.prop(st, 'preserve_extrema')
        box.prop(st, 'preserve_marked')
        box.prop(st, 'dense_check')
    layout.label(text='Local tolerance; no foot contact locking.')


def draw_panel(self, context):
    layout = self.layout
    ob = context.active_object
    if ob is None:
        layout.label(text='Select your armature.', icon='INFO')
        return
    st = ob.kr_settings
    active_preview = preview.session(ob)
    if active_preview:
        draw_preview(layout, ob, active_preview)
        return
    if st.preview_notice:
        for line in textwrap.wrap(st.preview_notice, 38):
            layout.label(text=line)
    ad = ob.animation_data
    action = ad.action if ad else None
    if action is None:
        layout.label(text='No active Action.', icon='INFO')
        layout.label(text='Bake the NLA sequence, then reduce.')
        return
    pair = current_pair(ob)
    simplify = st.method == 'SIMPLIFY'
    scope = 'KEYS' if simplify else st.scope
    reuse = pair
    captured = reuse and st.last_scope == scope and bool(st.selection_json)
    layout.label(text='Source: ' + (st.source.name if reuse else action.name), icon='ACTION')
    if ad.use_tweak_mode:
        layout.label(text='Exit Tweak Mode (Tab).', icon='ERROR')
        return
    if ad.use_nla and any(not t.mute for t in ad.nla_tracks):
        box = layout.box()
        box.label(text='NLA tracks are active.', icon='INFO')
        box.label(text='Only the active Action is reduced.')
    layout.prop(st, 'method', expand=True)
    if ob.type == 'ARMATURE':
        layout.operator('kr.animation_profile', text='Use Bone Animation Profile', icon='BONE_DATA')
    if simplify:
        layout.label(text='Simplify selected transform curves')
        layout.prop(st, 'simplify_mode')
        if st.simplify_mode == 'FIT':
            layout.operator('kr.preview_start', icon='PLAY')
    else:
        layout.prop(st, 'scope')
    if scope == 'KEYS':
        if captured:
            layout.label(text=f'Captured selection: {st.selection_count:,} keys')
            if st.selection_count > 100000 and ob.type == 'ARMATURE' and not st.selected_only:
                layout.label(text='Large scope: try Selected Bones Only.', icon='INFO')
        else:
            layout.label(text='Select keys in the Graph Editor.')
        layout.label(text='Unselected gaps are preserved.')
    if ob.type == 'ARMATURE':
        layout.prop(st, 'selected_only')
        if st.selected_only and ob.mode == 'POSE':
            count = sum(bone.select for bone in ob.pose.bones)
            layout.label(text=f'Bone filter: {count} selected')
    if simplify:
        box = layout.box()
        box.label(text='Allowed Shape Change')
        box.prop(st, 'position_error', text='Position / Axis')
        box.prop(st, 'rotation_error', text='Rotation')
        box.prop(st, 'scale_error', text='Scale / Axis')
        box.label(text='Lower values keep more detail.')
        if st.simplify_mode == 'KEEP':
            layout.prop(st, 'preserve_manual')
        else:
            layout.label(text='Selected tangents will be rebuilt.')
    else:
        layout.prop(st, 'strength', slider=True)
        layout.prop(st, 'interpolation')
    layout.label(text='Independent axes / full WXYZ' if simplify else 'Selected channels / full WXYZ' if scope == 'KEYS'
                 else 'XYZ / quaternion keys stay aligned', icon='LINKED')
    layout.prop(st, 'show_advanced', icon='TRIA_DOWN' if st.show_advanced else 'TRIA_RIGHT', emboss=False)
    if st.show_advanced:
        box = layout.box()
        if not simplify:
            box.label(text='Tolerances at Strength = 1')
            box.prop(st, 'position_error')
            box.prop(st, 'rotation_error')
            box.prop(st, 'scale_error')
        box.label(text='Position: local rig units')
        box.prop(st, 'preserve_extrema')
        box.prop(st, 'preserve_marked')
        box.prop(st, 'dense_check')
    row = layout.row()
    row.enabled = scope != 'KEYS' or captured or context.area.type == 'GRAPH_EDITOR'
    row.operator('kr.reduce', text='Recalculate from Source' if captured or (reuse and scope == 'ACTION')
                 else 'Simplify Selected Keys' if simplify else 'Reduce on a Copy', icon='MOD_DECIM')
    layout.label(text='Change settings, then recalculate.')
    if scope == 'KEYS' and captured:
        row = layout.row()
        row.enabled = context.area.type == 'GRAPH_EDITOR'
        row.operator('kr.reduce', text='Simplify New Selection' if simplify else 'Reduce New Selection',
                     icon='RESTRICT_SELECT_OFF').new_selection = True
    if pair:
        box = layout.box()
        if result_needs_update(ob):
            row = box.row()
            row.alert = True
            row.label(text='Settings changed: Recalculate', icon='FILE_REFRESH')
        if st.last_method == 'SIMPLIFY':
            box.label(text='Result: Editable Bezier' if st.last_simplify_mode == 'FIT'
                      else 'Result: Keep Existing Handles')
        percent = 100*(1-st.after/st.before) if st.before else 0
        if st.scope_before >= 0:
            percent = 100*(1-st.scope_after/st.scope_before) if st.scope_before else 0
            box.label(text=f'{st.scope_before:,} -> {st.scope_after:,} keys in scope')
        else:
            box.label(text=f'{st.before:,} -> {st.after:,} Action keys')
        box.label(text=f'-{percent:.1f}% / {st.groups} groups changed')
        row = box.row(align=True)
        row.operator('kr.compare', text='Original', depress=action == st.source).reduced = False
        row.operator('kr.compare', text='Simplified' if st.last_method == 'SIMPLIFY' else 'Reduced',
                     depress=action == st.reduced).reduced = True
        box.operator('kr.finish', icon='CHECKMARK')
        box.operator('kr.cancel', icon='LOOP_BACK')
        box.label(text='Keep the copy before editing keys.')
        if st.message:
            box.label(text='Some channels were preserved.', icon='INFO')
            for message in st.message.split(' / '):
                if message.startswith('Quaternion selection:'):
                    box.label(text='Quaternion: select W, X, Y, Z.')
                elif message.startswith('Selection'):
                    box.label(text='Select at least 3 consecutive keys.')
                elif message.startswith('Unsupported'):
                    box.label(text='Only transform curves are supported.')
                elif message.startswith('Manual tangent'):
                    box.label(text='Manual tangent keys are protected.')
                elif message.startswith('No simpler') or message.startswith('Bezier validation'):
                    box.label(text='Fit kept keys to meet the tolerance.')
            box.label(text='Details: Action property kr_report.')
    layout.separator()
    layout.label(text='Local tolerance; no foot contact locking.')


class KR_PT_graph(bpy.types.Panel):
    bl_label = 'Keyframe Reducer 1.5.0 (Dev)'
    bl_idname = 'KR_PT_graph'
    bl_space_type = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Key Reducer'
    draw = draw_panel


class KR_PT_view(bpy.types.Panel):
    bl_label = 'Keyframe Reducer 1.5.0 (Dev)'
    bl_idname = 'KR_PT_view'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Key Reducer'
    draw = draw_panel


CLASSES = (KR_Settings, KR_OT_animation_profile, KR_OT_preview_start, KR_OT_preview_apply,
           KR_OT_preview_cancel, KR_OT_preview_compare, KR_OT_reduce, KR_OT_compare,
           KR_OT_finish, KR_OT_cancel, KR_PT_graph, KR_PT_view)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Object.kr_settings = PointerProperty(type=KR_Settings)
    preview.register()


def unregister():
    preview.shutdown()
    del bpy.types.Object.kr_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == '__main__':
    register()
