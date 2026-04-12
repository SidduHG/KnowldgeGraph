# Architecture Flow

This document describes the flow of data through the system, based on the provided flowchart.

**Triggers:**
1. **Initial startup** (one-time full scan)
2. **File event fires** (fs change event)

*Both triggers lead to:*

**Hash registry check**
- *Action:* compare SHA-256 vs stored
- *Path A (no change):* **Skip — no work**
- *Path B (changed):* Proceed to...

**Build dirty set**
- *Action:* collect files to re-analyze

**Propagate to reverse dependents**
- *Action:* importers of dirty files -> also dirty

**tree-sitter parser**
- *Action:* incremental, multi-language

**SQLite store — upsert + update hash**
- *Action:* nodes · edges · file_hashes · file_deps
