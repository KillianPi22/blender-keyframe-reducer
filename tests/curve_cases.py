"""Generated animation curves for fitting studies; no private motion data."""
import math

from keyframe_reducer.fitting import hermite


def shoulder(t):
    anchors = [(0, 0), (30, 40), (60, -10), (90, 38), (120, 43),
               (150, -10), (180, 40), (210, 0), (240, 60)]
    for (a, av), (b, bv) in zip(anchors, anchors[1:]):
        if t <= b:
            return hermite((math.radians(av),), (math.radians(bv),),
                           (0,), (0,), b-a, (t-a)/(b-a))[0]


def hold(t):
    u = max(0., min(1., (t-80)/40))
    v = max(0., min(1., (t-220)/40))
    return .8*(u*u*(3-2*u)-v*v*(3-2*v))


def weighted_ease(t):
    # A time-weighted cubic baked to ordinary F-curve samples. It is deliberately
    # not a polynomial in time, unlike the fitter's unweighted cubic segments.
    x, lo, hi = t/240, 0., 1.
    for _ in range(36):
        u = (lo+hi)/2
        bx = 3*(1-u)**2*u*.08 + 3*(1-u)*u*u*.25 + u**3
        if bx < x:
            lo = u
        else:
            hi = u
    return u*u*(3-2*u)


def bone_cases():
    return [
        ('shoulder', 241, shoulder),
        ('fast_transitions', 241, lambda t: .8/(1+math.exp(-(t-70)/3)) -
                                          .9/(1+math.exp(-(t-160)/7))),
        ('long_holds', 361, hold),
        ('small_ripple', 361, lambda t: .5*math.sin(t/60)+.003*math.sin(t*1.7)),
        ('mixed_arcs', 1241, lambda t: .5*math.sin(t/60)+.15*math.sin(t/17)),
        ('weighted_ease', 241, weighted_ease),
        ('brief_gesture', 361, lambda t: .8*math.sin(math.pi*(t-120)/20)**2
                                       if 120 < t < 140 else 0.),
        ('visible_oscillation', 241, lambda t: .5*math.sin(t/45)+.03*math.sin(t*1.7)),
    ]
