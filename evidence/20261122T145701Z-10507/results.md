# Acceptance checks

Run: 20261122T145701Z-10507

| Check | Expected | Actual | Result |
|---|---|---|---|
| normal | A and B complete the workflow | Both completed it; own lists and history verified | PASS |
| isolation | A is rejected; B data stays intact | All 4 A requests return 404; B record and history unchanged | PASS |
| limit | A sixth fails; B sixth succeeds | A: 403 and 5 objects; B: 201 and 6 objects | PASS |
