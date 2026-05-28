# Editing Pattern Memory Specification

This spec outlines the SQLite schema, updates, and decay mechanisms applied to the `editing_pattern_memory` table.

---

## 1. Schema Definitions

The `editing_pattern_memory` table holds target weights for the 8 primary YouTube vlog and cinematic editing patterns:

| Field | Type | Description |
| :--- | :--- | :--- |
| `pattern_id` | String | Primary Key (e.g. `PAT_REACTION_HOLD`). |
| `pattern_type` | String | Categorization matching the heuristic engine (e.g. `reaction_hold`). |
| `conditions` | JSON | Key-value mapping representing triggers. |
| `recommended_action` | JSON | Mutator multipliers applied during scoring. |
| `success_count` | Integer | Counter representing positive user selection outcomes. |
| `failure_count` | Integer | Counter representing rejected proposal outcomes. |
| `avg_user_acceptance` | Float | Acceptance ratio: $\frac{\text{Success}}{\text{Success} + \text{Failure}}$. Defaults to $0.50$. |
| `avg_hrs_delta` | Float | Average impact on the final Human Reality Score. |

---

## 2. Dynamic Update Algorithm

When a user selects Proposal A over B, CCUT scans the sequences to calculate pattern overlap:

1. Identify which patterns (e.g., `hook_3sec`) were active in the Winner sequence.
2. Increment `success_count` for active winner patterns.
3. Identify which patterns were exclusive to the Loser sequence.
4. Increment `failure_count` for these rejected patterns.
5. Re-evaluate `avg_user_acceptance` and update DB.
