"""Does a long alternating campaign leave the model where a fresh one starts?"""
import numpy as np
from vegapunk.embodied.regime import DEFAULT_CONTACT_REGIME
from vegapunk.embodied.simulation import SimulatedG1, SimulatedSupervision

SUP = SimulatedSupervision(True, False, True, True)

def float_arrays(model):
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

regime = DEFAULT_CONTACT_REGIME
samples = [regime.sample(i) for i in range(regime.samples)]

# The drifting robot: 50 resets, alternating worlds, plus real motion between.
drifting = SimulatedG1(supervision=SUP)
for step in range(50):
    s = samples[step % len(samples)]
    drifting.reset(joint_offsets_rad=[s.value("joint_offset_rad", 0.0)] * 7,
                   sample=s)
    tgt = np.asarray(drifting.stand_positions_rad) + 0.05
    for _ in range(3):
        drifting.command_joint_positions(tgt)
    drifting.read_state()

# Now park it on a chosen sample and compare against a virgin instance.
worst = {}
for probe in (samples[3], samples[7], None):
    drifting.reset(sample=probe)
    fresh = SimulatedG1(supervision=SUP)
    fresh.reset(sample=probe)
    a, b = float_arrays(drifting._model), float_arrays(fresh._model)
    diffs = [k for k in a if not np.array_equal(a[k], b[k], equal_nan=True)]
    label = "nominal" if probe is None else f"sample{probe.index}"
    worst[label] = diffs
    fresh.close()
drifting.close()
print("differing arrays per probe:", worst)

# And the physics itself: same sample must give the same trajectory.
def trajectory(sample):
    r = SimulatedG1(supervision=SUP)
    r.reset(joint_offsets_rad=[0.01] * 7, sample=sample)
    tgt = np.asarray(r.stand_positions_rad) + 0.08
    seen = []
    for _ in range(6):
        r.command_joint_positions(tgt)
        st = r.read_state()
        seen.append((st.joint_positions_rad, st.joint_velocity_rps,
                     st.end_effector_force_n))
    r.close()
    return seen

a, b = trajectory(samples[5]), trajectory(samples[5])
print("same sample reproduces exactly:", a == b)
c = trajectory(samples[6])
print("different sample differs:", a != c)
