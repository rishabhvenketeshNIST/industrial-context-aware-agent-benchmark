# TEP Simulator

## What ICAB uses

ICAB's process foundation is the Tennessee Eastman Process (TEP). The
`icab.tep.simulator.TEPSimulator` class (added in the M2 milestone) wraps the
[`tep-studio`](https://github.com/khalidlabs/tep-studio) package (PyPI:
`tep-studio`, pinned to `0.1.1` — the last release with prebuilt wheels at the
time of integration), which provides a Python interface around a native kernel
compiled from `temexd_mod.c`: the widely used C port of the Downs & Vogel
(1993) Tennessee Eastman Process, modified per Bathelt, Ricker & Jelali,
*"Revision of the Tennessee Eastman Process Model"* (IFAC PapersOnLine, 2015).
Closed-loop operation (ICAB's default) uses the decentralized PI controller
described in Ricker, *"Decentralized control of the Tennessee Eastman
Challenge Process"* (J. Proc. Cont. 6(4), 205-221, 1996), as reference-encoded
by `tep-studio`.

This is a real, published, citable dynamic simulation — 50 continuous states,
12 manipulated variables, 28 disturbances (IDV 1-20 documented faults, IDV
21-28 documented random variations), and 41 online measurements, integrated
with an RK4 fixed-step solver. It is **not** a simulator ICAB invented.

## Why this dependency

The other well-known TEP Python wrapper found during Phase 1 research,
`pytep` (PyPI), requires a licensed MATLAB/Simulink installation and the
MATLAB Engine for Python pinned to Python 3.7 — impractical for a
locally-reproducible, CI-friendly benchmark. `tep-studio` ships prebuilt
`cp311-win_amd64`/`manylinux`/`macosx` wheels for its native extension, so no
Fortran/C/MATLAB toolchain is required to install or run it.

## What ICAB adds on top

`TEPSimulator` (`src/icab/tep/simulator.py`) is the *only* place in ICAB that
imports `tep_studio`, so the rest of the benchmark depends on an ICAB-owned
abstraction (`reset`, `step`, `get_state`, `get_measurements`,
`inject_fault`, `get_events`), not the specific simulator package.

Two implementation notes worth recording:

- **Control interval sensitivity.** The bundled decentralized controller's PI
  loops are tuned for a ~0.0005 h (~1.8 s) update rate. Calling it at a
  coarser interval (e.g. every simulated 3 minutes) was found, empirically,
  to destabilize the closed loop and trip the plant almost immediately.
  `TEPSimulator.step()` therefore always drives the controller at the native
  `NATIVE_CONTROL_INTERVAL`, internally sub-stepping up to the caller's
  requested (coarser) checkpoint, which is what is actually reported.
- **Event provenance.** `get_events()` tags each event with its `source`:
  `"simulator"` for a real kernel-reported plant trip/shutdown, `"icab"` for
  ICAB's own fault-injection bookkeeping (i.e. *when ICAB asked* the
  simulator to activate a disturbance — not something the plant itself
  reported). Keeping this distinction explicit matters for a benchmark that
  must not blur real simulator output with benchmark-generated metadata.

## Relationship to the existing static prototype path

`icab.tep.state`, `icab.tep.scenarios`, and the four `TEP_VARIABLES` /
`TEPAdapter` methods introduced before M2 remain unchanged and continue to
back the static `normal_001` prototype scenario. `TEPSimulator` and the
additive `TEPAdapter.build_real_environment(...)` / `get_real_*` methods are a
parallel, real-simulator-backed path used by everything built from here on
(MQTT publishing, D1-D4 investigation scenarios, architecture comparisons).
The two paths use disjoint canonical-id namespaces (`tep_pv_*` vs. the real
measurement names) so they cannot collide if both are ever loaded together.
