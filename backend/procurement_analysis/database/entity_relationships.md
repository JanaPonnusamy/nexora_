# Entity Relationship Documentation — OrderNMC (Legacy)

> Document relationships **as discovered** (declared FKs and *implied* joins seen in code/SP/queries).
> Mark each relationship's basis. Read-only. Status: `Empty`.

## 1. Relationship register

| Parent | Child | Cardinality | Join Keys | Basis | Evidence |
|--------|-------|-------------|-----------|-------|----------|
| | | 1:N / 1:1 / N:M | parent.col = child.col | Declared FK / Implied (code) / Implied (SP) | reference |

## 2. Core procurement entity map (textual ERD)

> Build incrementally as a text diagram. Example structure (replace with discovered entities):

```
Stores ─1:N─ <order/cycle entity> ─1:N─ <refresh entity> ─1:N─ <workspace/row entity>
                                                              │
                                          <assignment entity> ┘ ─N:1─ Suppliers
<purchase/GRN entity> ─N:1─ Products
<customer demand entity> ─N:1─ Products
```

## 3. Implied relationships (no declared FK)

| From | To | Inferred via | Confidence | Evidence |
|------|----|--------------|-----------|----------|

## 4. Notes

- Record where the legacy schema relies on **convention rather than constraints** (string store names,
  un-keyed joins, etc.) — these are facts about the legacy design, not criticisms.
