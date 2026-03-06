# ⚖ CCUT Engine Constitution

All development must follow:
docs/constitution/CCUT_ENGINE_CONSTITUTION_v1.0.md

> **The Constitution governs implementation. When code and constitution conflict, the constitution wins.**

---

# CCUT 1.0.1

Creative Cut — deterministic, append-only video fragment editing system.

## Quick Start

**Backend:**
```bash
cd ccut_ui
python app/server.py
```

**Frontend:**
```bash
cd ui
npm install && npm run dev
```

## Manual Verify
```bash
python -m ccut_core.edit_log.verify_edit_log
```
