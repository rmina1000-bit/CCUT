# QA Gates And Phase Report

## Baseline SSOT

- Locked baseline SSOT and QA checklist:
  - [LOCKED_BASELINE_SSOT_AND_QA_CHECKLIST.md](D:/CCUT%201.0.2/ui/docs/LOCKED_BASELINE_SSOT_AND_QA_CHECKLIST.md)
- Precision entry baseline addendum:
  - [PRECISION_ENTRY_BASELINE_ADDENDUM.md](D:/CCUT%201.0.2/ui/docs/PRECISION_ENTRY_BASELINE_ADDENDUM.md)
- Precision entry spec:
  - [PRECISION_ENTRY_SPEC.md](D:/CCUT%201.0.2/ui/docs/PRECISION_ENTRY_SPEC.md)

## Build Gates

- `npm run verify:gates`
- Required order:
  1. `npm run typecheck`
  2. `npm run lint`
  3. `npm run build`
- Rule:
  - phase completion cannot be declared from `vite build` alone
  - if `typescript` is missing locally, the gate fails until it is installed
  - lint is included when ESLint is installed and configured

## Mount Smoke

- `npm run smoke:mount`
- Required mount targets:
  - `ReservedFragments`
  - `FragmentMap`
  - `OriginalPanorama`
  - `FragmentTile`
  - `BoundaryPrecisionOverlay`
- Pass condition:
  - each component mounts with base props
  - `console.error` count is `0`
  - `pageerror` count is `0`

## Browser Sanity

- `npm run sanity:browser`
- Required checks:
  - fresh browser load
  - `#root` is not empty
  - `.ccut-shell` exists
  - `console.error` count is `0`
  - `pageerror` count is `0`
  - screenshot is saved

## Phase Report Template

- Files changed
- Implemented exactly
- Implemented partially
- Not implemented yet
- Known debt
- Render Success: Pass/Fail
- No Console Error: Pass/Fail
- Interaction Sanity: Pass/Fail
- Spec Parity: Pass/Fail

## ReservedFragments Regression Guard

- Why it happened:
  - the props interface and the function destructuring drifted apart
  - build passed because no real typecheck gate was running
  - no component mount smoke test was run before the phase report
- What would have blocked it:
  - `typecheck`
  - `ReservedFragments` mount smoke
  - browser sanity before reporting completion
- Required verification order:
  1. build gates
  2. mount smoke
  3. browser sanity
  4. phase report
