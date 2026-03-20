# Precision Entry Baseline Addendum

This addendum supersedes the earlier locked baseline entry:

- Retired: `#6 normal boundary drag only`

It is replaced by the following precision-entry contract baselines:

- `#6 board boundary click -> precision editor open only`
- `#6a same-source boundary click opens precision scope`
- `#6b synthetic seam click opens precision scope`
- `#6c cross-source junction click opens precision scope`
- `#6d >4 fragment case rejects precision open`

## Effective Contract

- Main board boundaries and seams are click-only precision entry handles.
- Main board direct boundary drag is retired.
- Precision Boundary Editor opens with `activeBoundaryId = null`.
- The system resolves only local scope.
- Maximum reveal size is 4 fragments.
- Excluded fragments are included when structurally relevant.
- Held fragments are excluded from precision scope.
- If more than 4 fragments are required, precision open is rejected and the user is guided to structural recomposition through Original Panorama or Hold Area.

## Explicit Entry Modes

- `boundary-click`
- `seam-click`
- `chat`
- `pair-chat`

## Locked Verification Cases

- same-source boundary click -> open
- synthetic seam click -> open
- cross-source junction click -> open
- `>4` fragment case -> reject
- open state starts with `activeBoundaryId = null`
- chat instruction with exactly two fragment ids -> open attempt
- exactly two selected edit fragments plus chat instruction -> open attempt
