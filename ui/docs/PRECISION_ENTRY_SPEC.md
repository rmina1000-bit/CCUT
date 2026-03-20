# Precision Entry Spec

## Main Board Contract

- Every board divider is a precision entry handle.
- Same-source boundary, synthetic seam, and cross-source junction all use the same open attempt rule.
- Main board direct boundary drag is not allowed.

## Scope Resolution

### Same-source

- Input: left fragment id, right fragment id
- Output: inclusive structural chain between anchors
- Excluded fragments inside the chain are included
- Held fragments are not included
- Reject if more than 4 fragments are required

### Synthetic Seam

- Input: left visible fragment id, right visible fragment id, hidden fragment ids
- Output: `[leftVisible, ...hiddenIds, rightVisible]`
- Synthetic seam is entry-only and is removed inside the editor
- Reject if more than 4 fragments are required

### Cross-source

- Input: left visible fragment id, right visible fragment id
- Output: `[L, next(L)?, prev(R)?, R]`
- Only immediate same-source neighbors are allowed
- Ordering stays structural
- Reject if more than 4 fragments are required

## Editor Open State

- `activeBoundaryId = null`
- All relevant fragments are revealed
- All real internal boundaries are visible
- Synthetic seam does not remain inside the editor
- Only one internal boundary may be active at a time

## Editor Internal Rule

- Local preview updates only inside the editor
- Main board remains visually stable during drag
- Apply commits once
- Cancel and Close discard local changes

## Chat Entry

- Explicit precision chat requests with exactly two fragment ids may open the editor
- If no explicit ids are given, exactly two selected edit fragments plus a precision instruction may open the editor
- The system resolves scope only
- The system does not auto-select the active boundary

## Reject Cases

- more than 4 fragments required
- pair is not a local correction on the active edit chain
- held fragment reintroduction is required
