"""Which model arrays does mj_setConst rewrite, on the model we actually build?"""
import numpy as np
from vegapunk.embodied.simulation import SimulatedG1, SimulatedSupervision

SUP = SimulatedSupervision(True, False, True, True)
r = SimulatedG1(supervision=SUP)
m, d = r._model, r._data

def snap(model):
    out = {}
    for name in dir(model):
        if name.startswith("_"):
            continue
        try:
            v = getattr(model, name)
        except Exception:
            continue
        if isinstance(v, np.ndarray) and v.dtype.kind == "f":
            out[name] = np.array(v, copy=True)
    return out

before = snap(m)
m.body_mass[r._end_effector_body_id] += 1.0
import mujoco
mujoco.mj_setConst(m, d)
after = snap(m)
changed = sorted(k for k in before if not np.array_equal(before[k], after[k]))
print("changed by mass-edit + setConst:", changed)
print("current snapshot list:", sorted(r._pristine_model))
missing = [k for k in changed if k not in r._pristine_model]
print("MISSING from snapshot:", missing)
r.close()
