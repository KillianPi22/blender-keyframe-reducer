"""Cooperative Graph Editor preview. All Blender access stays on the main thread.

SPDX-License-Identifier: GPL-3.0-or-later
"""
from array import array
from dataclasses import asdict, dataclass, field
import hashlib
import json
import time
import uuid

import bpy
from bpy.app.handlers import persistent

from .core import complete
from .engine import BONE_PATH, Settings, find_slot, reduce_action_steps

DEBOUNCE = .18
TICK_BUDGET = .012
TICK_INTERVAL = .01
_session = None
_inside_tick = False


def _curves(action):
    for layer in action.layers:
        for strip in layer.strips:
            for bag in getattr(strip, 'channelbags', ()):
                for curve in bag.fcurves:
                    yield bag.slot_handle, curve


def _rna_values(item):
    result = []
    for prop in item.bl_rna.properties:
        if prop.identifier == 'rna_type':
            continue
        value = getattr(item, prop.identifier)
        if prop.type in {'BOOLEAN', 'INT', 'FLOAT', 'STRING', 'ENUM'}:
            result.append((prop.identifier, tuple(value) if getattr(prop, 'is_array', False) else value))
        elif prop.type == 'COLLECTION':
            result.append((prop.identifier, [_rna_values(child) for child in value]))
    return result


def _id_value(value):
    if hasattr(value, 'to_dict'):
        return {key: _id_value(item) for key, item in value.to_dict().items()}
    if hasattr(value, 'to_list'):
        return [_id_value(item) for item in value.to_list()]
    if isinstance(value, dict):
        return {key: _id_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_id_value(item) for item in value]
    if isinstance(value, bpy.types.ID):
        return type(value).__name__, value.name_full
    return value


def action_digest_steps(action):
    """Native bulk reads avoid walking a large Action's keys in Python each tick.

    Selection flags are intentionally excluded: changing the visible selection
    does not redefine the captured scope or count as editing the animation.
    """
    digest = hashlib.sha256()
    def add(value):
        digest.update(json.dumps(value, sort_keys=True, default=str).encode())
    add([(slot.identifier, slot.target_id_type) for slot in action.slots])
    add([(layer.name, getattr(layer, 'influence', None), getattr(layer, 'mix_mode', None), getattr(layer, 'mute', None),
          [strip.type for strip in layer.strips]) for layer in action.layers])
    add({key: _id_value(action[key]) for key in action.keys() if not key.startswith('_kr_preview_')})
    add([getattr(action, name, None) for name in ('use_frame_range', 'frame_start', 'frame_end', 'use_cyclic')])
    add([(marker.name, marker.frame) for marker in action.pose_markers])
    for slot, fc in _curves(action):
        yield
        add((slot, fc.data_path, fc.array_index, fc.extrapolation, fc.auto_smoothing,
             fc.lock, fc.mute, fc.hide, fc.color_mode, tuple(fc.color),
             fc.group.name if fc.group else None, [_rna_values(m) for m in fc.modifiers]))
        count = len(fc.keyframe_points)
        add((count, len(fc.sampled_points)))
        for name, code, width in (
                ('co', 'f', 2), ('handle_left', 'f', 2), ('handle_right', 'f', 2),
                ('interpolation', 'i', 1), ('easing', 'i', 1), ('type', 'i', 1),
                ('handle_left_type', 'i', 1), ('handle_right_type', 'i', 1),
                ('amplitude', 'f', 1), ('back', 'f', 1), ('period', 'f', 1)):
            yield
            data = array(code, [0])*(count*width)
            fc.keyframe_points.foreach_get(name, data)
            digest.update(data.tobytes())
        if fc.sampled_points:
            data = array('f', [0])*(2*len(fc.sampled_points))
            fc.sampled_points.foreach_get('co', data)
            digest.update(data.tobytes())
    return digest.hexdigest()


def _selection(action):
    result = []
    for _, fc in _curves(action):
        flags = []
        for name in ('select_control_point', 'select_left_handle', 'select_right_handle'):
            data = array('i', [0])*len(fc.keyframe_points)
            fc.keyframe_points.foreach_get(name, data)
            flags.append((name, data))
        result.append((fc, fc.select, flags))
    return result


@dataclass
class Session:
    ob: object
    scene: object
    view_layer: object
    source: object
    original: object
    original_slot: str
    identifier: str
    base: object
    selection: list
    bones: object
    original_selection: list
    bone_selection: tuple
    token: str
    generation: int = 0
    published_generation: int = -1
    due: float = 0.
    job: object = None
    candidate: object = None
    displayed: object = None
    source_digest: str = ''
    display_digest: str = ''
    status: str = 'WAITING'
    error: str = ''
    report: object = None
    settings: object = None
    show_original: bool = False
    progress: float = 0.
    max_tick: float = 0.
    last_redraw: float = 0.
    owned: list = field(default_factory=list)


def session(ob=None):
    return _session if _session and (ob is None or _session.ob == ob) else None


def _redraw(full=False):
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type in {'GRAPH_EDITOR', 'VIEW_3D'}:
                if full:
                    area.tag_redraw()
                else:
                    for region in area.regions:
                        if region.type == 'UI':
                            region.tag_redraw()


def _discard(s, action):
    if action is None:
        return
    try:
        if action.get('_kr_preview_owner') == s.token:
            s.owned.remove(action)
            if action.users == 0:
                bpy.data.actions.remove(action)
            else:
                # A result linked elsewhere is no longer disposable session data.
                _release(action)
    except (ReferenceError, ValueError):
        pass


def _copy(s, source, name):
    action = source.copy()
    action.name = name
    action.use_fake_user = False
    action['_kr_preview_owner'] = s.token
    action['_kr_preview_return'] = s.original
    action['_kr_preview_slot'] = s.original_slot
    s.owned.append(action)
    return action


def _release(action):
    for key in list(action.keys()):
        if key.startswith('_kr_preview_'):
            del action[key]


def _guard(s):
    if s.ob.name not in bpy.data.objects or s.view_layer.objects.active != s.ob:
        raise ValueError('Preview stopped: active object changed.')
    ad = s.ob.animation_data
    if ad is None or ad.use_tweak_mode:
        raise ValueError('Preview stopped: animation context changed.')
    if s.source.name not in bpy.data.actions or find_slot(s.source, s.identifier) is None:
        raise ValueError('Preview stopped: source Action or slot changed.')
    if ad.action not in (s.original, s.source, s.displayed) or ad.action is None:
        raise ValueError('Preview stopped: active Action changed.')
    expected = s.original_slot if ad.action == s.original else s.identifier
    if ad.action_slot is None or ad.action_slot.identifier != expected:
        raise ValueError('Preview stopped: active slot changed.')
    if s.ob.kr_settings.method != 'SIMPLIFY' or s.ob.kr_settings.simplify_mode != 'FIT':
        raise ValueError('Preview stopped: curve workflow changed.')


def request(ob):
    s = session(ob)
    if s:
        s.generation += 1
        s.due = time.monotonic()+DEBOUNCE
        s.status, s.error = 'WAITING', ''
        _redraw()


def start(context):
    global _session
    from . import assign, capture_key_selection, current_pair
    if _session:
        raise ValueError('Finish or cancel the current preview first.')
    ob = context.active_object
    if ob is None or ob.animation_data is None or ob.animation_data.action is None:
        raise ValueError('Assign an active Action first.')
    if context.area is None or context.area.type != 'GRAPH_EDITOR' or context.space_data.mode != 'FCURVES':
        raise ValueError('Start preview from the Graph Editor in F-Curves mode.')
    ad, st = ob.animation_data, ob.kr_settings
    if ad.use_tweak_mode or ad.action_slot is None:
        raise ValueError('Exit NLA Tweak Mode and choose an Action slot first.')
    if st.method != 'SIMPLIFY' or st.simplify_mode != 'FIT':
        raise ValueError('Interactive preview uses Simplify Curve / Editable Bezier.')
    reuse = current_pair(ob)
    source = st.source if reuse else ad.action
    identifier = st.slot_identifier if reuse else ad.action_slot.identifier
    bones = None
    if st.selected_only:
        if ob.type != 'ARMATURE' or ob.mode != 'POSE':
            raise ValueError('Switch to Pose Mode and select bones first.')
        bones = {bone.name for bone in ob.pose.bones if bone.select}
        if not bones:
            raise ValueError('Select at least one bone.')
    selection = (json.loads(st.selection_json) if reuse and st.last_scope == 'KEYS' and st.selection_json
                 else capture_key_selection(context, ad.action, ad.action_slot, selected_bones=bones))
    if bones is not None:
        selection = [entry for entry in selection if (match := BONE_PATH.match(entry['data_path'])) and
                     json.loads(match.group(1)) in bones]
    if not selection:
        raise ValueError('No selected keys in the captured bone selection.')
    token = uuid.uuid4().hex
    s = Session(ob, context.scene, context.view_layer, source, ad.action, ad.action_slot.identifier,
                identifier, None, selection, bones, _selection(ad.action),
                tuple((b.name, b.select) for b in ob.pose.bones) if ob.type == 'ARMATURE' else (), token)
    try:
        s.base = _copy(s, source, 'KR_Preview_Source')
        _session = s
        st.preview_notice = ''
        request(ob)
        if not bpy.app.timers.is_registered(tick):
            bpy.app.timers.register(tick, first_interval=TICK_INTERVAL)
    except Exception:
        _session = None
        _discard(s, s.base)
        raise
    _redraw()
    return s


def _settings(s):
    st = s.ob.kr_settings
    return Settings(method='SIMPLIFY', simplify_mode='FIT', strength=st.preview_amount,
        position_error=st.position_error, rotation_error=st.rotation_error, scale_error=st.scale_error,
        preserve_extrema=st.preserve_extrema, preserve_marked=st.preserve_marked,
        sample_step=.25 if st.dense_check else .5, selected_bones=s.bones, key_selection=s.selection)


def _generate(s, generation):
    if not s.source_digest:
        s.source_digest = yield from action_digest_steps(s.base)
    yield
    settings = _settings(s)
    s.candidate = _copy(s, s.base, 'KR_Preview_Work')
    yield
    def progress(done, total):
        s.progress = done/total
    report = yield from reduce_action_steps(s.candidate, find_slot(s.candidate, s.identifier), settings, progress)
    if report.scope_before == 0:
        raise ValueError('No transform keys in the captured bone selection.')
    if (yield from action_digest_steps(s.source)) != s.source_digest:
        raise ValueError('Preview stopped: source animation was edited.')
    if s.displayed and (yield from action_digest_steps(s.displayed)) != s.display_digest:
        raise ValueError('Preview stopped: edited preview kept for manual work.')
    fingerprint = yield from action_digest_steps(s.candidate)
    _guard(s)
    if generation != s.generation:
        return
    from . import assign
    old = s.displayed
    s.displayed, s.candidate = s.candidate, None
    s.displayed.name = s.source.name+'_Preview'
    s.display_digest, s.report, s.settings = fingerprint, report, settings
    s.published_generation, s.status = generation, 'READY'
    if not s.show_original:
        assign(s.ob, s.displayed, s.identifier)
    _discard(s, old)
    s.scene.frame_set(s.scene.frame_current, subframe=s.scene.frame_subframe)
    _redraw(full=True)


def ready(ob=None):
    s = session(ob)
    return bool(s and s.status == 'READY' and s.published_generation == s.generation and s.displayed)


def tick():
    global _inside_tick
    s = _session
    if s is None:
        return None
    started = time.monotonic()
    _inside_tick = True
    try:
        _guard(s)
        if s.status == 'WAITING':
            if s.job:
                s.job.close()
                s.job = None
                _discard(s, s.candidate)
                s.candidate = None
            if started >= s.due:
                s.status, s.progress = 'COMPUTING', 0.
                s.job = _generate(s, s.generation)
        if s.job:
            while time.monotonic()-started < TICK_BUDGET:
                try:
                    next(s.job)
                except StopIteration:
                    s.job = None
                    break
        if s.status == 'COMPUTING' and started-s.last_redraw >= .05:
            s.last_redraw = started
            _redraw()
    except Exception as error:
        # Failed work is never assigned. Keep the last valid result available;
        # context changes or edits terminate the session without overwriting them.
        if isinstance(error, (ReferenceError, ValueError)) and str(error).startswith('Preview stopped:'):
            cancel(notice=str(error), preserve_edits=True)
        elif isinstance(error, ReferenceError):
            cancel(notice='Preview stopped: data was removed.', preserve_edits=True)
        else:
            if s.job:
                s.job.close()
            s.job = None
            _discard(s, s.candidate)
            s.candidate = None
            s.status, s.error = 'ERROR', str(error)
            _redraw()
    finally:
        s.max_tick = max(s.max_tick, time.monotonic()-started)
        _inside_tick = False
    return (TICK_INTERVAL if s.status == 'COMPUTING' else .05) if _session else None


def compare(ob, original):
    from . import assign
    s = session(ob)
    if s is None or (not original and s.displayed is None):
        raise ValueError('No completed preview is available.')
    _guard(s)
    s.show_original = original
    assign(ob, s.source if original else s.displayed, s.identifier)
    s.scene.frame_set(s.scene.frame_current, subframe=s.scene.frame_subframe)
    _redraw(full=True)


def cancel(notice='', preserve_edits=True):
    global _session
    s, _session = _session, None
    if not s:
        return
    if not _inside_tick and bpy.app.timers.is_registered(tick):
        bpy.app.timers.unregister(tick)
    if s.job:
        s.job.close()
    try:
        edited = bool(preserve_edits and s.displayed and
                      complete(action_digest_steps(s.displayed)) != s.display_digest)
    except ReferenceError:
        edited = False
    try:
        from . import assign
        ad = s.ob.animation_data
        if edited:
            s.displayed.use_fake_user = True
            s.source.use_fake_user = True
            _release(s.displayed)
            notice = 'Preview stopped: edited preview kept for manual work.'
        elif ad and not ad.use_tweak_mode and ad.action in (s.source, s.displayed, s.original):
            assign(s.ob, s.original, s.original_slot)
            if not notice:
                for fc, selected, flags in s.original_selection:
                    if len(fc.keyframe_points) == len(flags[0][1]):
                        fc.select = selected
                        for name, data in flags:
                            fc.keyframe_points.foreach_set(name, data)
                for name, selected in s.bone_selection:
                    bone = s.ob.pose.bones.get(name)
                    if bone:
                        bone.select = selected
        s.ob.kr_settings.preview_notice = notice
        s.scene.frame_set(s.scene.frame_current, subframe=s.scene.frame_subframe)
    except (ReferenceError, ValueError, RuntimeError):
        pass
    for action in list(s.owned):
        _discard(s, action)
    _redraw(full=True)


def apply(context):
    global _session
    s = session(context.active_object)
    if not ready(context.active_object):
        raise ValueError('Wait for the current preview to finish before applying.')
    _guard(s)
    if complete(action_digest_steps(s.source)) != s.source_digest:
        cancel(notice='Preview stopped: source animation was edited.')
        raise ValueError('The source changed. Start a new preview.')
    if complete(action_digest_steps(s.displayed)) != s.display_digest:
        cancel()
        raise ValueError('The preview was edited and has been kept for manual work.')
    from . import assign
    result = s.displayed
    # Retain an ordinary result before closing the runtime. Undo returns to the
    # starting assignment; the committed Action remains available for recovery.
    result.use_fake_user = True
    result.name = s.source.name+'_Editable'
    _release(result)
    cancel(preserve_edits=False)
    bpy.ops.ed.undo_push(message='Before Apply Curve Preview')
    s.source.use_fake_user = True
    result['kr_source_name'] = s.source.name
    result['kr_report'] = json.dumps(asdict(s.report))
    settings = asdict(s.settings)
    if s.bones is not None:
        settings['selected_bones'] = sorted(s.bones)
    result['kr_settings'] = json.dumps(settings)
    st = s.ob.kr_settings
    st.source = st.reduced = None
    st.slot_identifier = st.selection_json = ''
    st.selection_count = 0
    assign(s.ob, result, s.identifier)
    s.scene.frame_set(s.scene.frame_current, subframe=s.scene.frame_subframe)
    return result


@persistent
def _before_history(*_args):
    cancel(notice='Preview closed before undo/redo.')


@persistent
def _before_save(*_args):
    cancel(notice='Unapplied preview cancelled before saving.')


@persistent
def _before_load(*_args):
    cancel()


@persistent
def _recover(*_args):
    """Undo may restore a temporary ID captured during a slider edit."""
    if _session:
        return
    owned = [action for action in bpy.data.actions if action.get('_kr_preview_owner')]
    if not owned:
        return
    from . import assign
    for ob in bpy.data.objects:
        action = ob.animation_data.action if ob.animation_data else None
        if action and action.get('_kr_preview_owner'):
            original = action.get('_kr_preview_return')
            identifier = action.get('_kr_preview_slot', '')
            if isinstance(original, bpy.types.Action) and find_slot(original, identifier):
                assign(ob, original, identifier)
    for action in owned:
        if action.users == 0:
            bpy.data.actions.remove(action)


_HANDLERS = (('undo_pre', _before_history), ('redo_pre', _before_history),
             ('save_pre', _before_save), ('load_pre', _before_load),
             ('undo_post', _recover), ('redo_post', _recover), ('load_post', _recover))


def register():
    for name, callback in _HANDLERS:
        callbacks = getattr(bpy.app.handlers, name)
        if callback not in callbacks:
            callbacks.append(callback)


def shutdown():
    cancel()
    for name, callback in _HANDLERS:
        callbacks = getattr(bpy.app.handlers, name)
        if callback in callbacks:
            callbacks.remove(callback)
