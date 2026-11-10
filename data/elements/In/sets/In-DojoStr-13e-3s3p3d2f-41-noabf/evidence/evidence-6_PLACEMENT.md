# DF placement record

- observation time: 2026-09-14T22:39:00+08:00
- host: [host]
- compatible CPU partitions checked: 48cp1, 48cp2, 48cp3
- whole idle nodes observed: 48cp1=25, 48cp2=46, 48cp3=29
- common node shape: 48 CPU cores, 190000 MB scheduler memory
- selected partition: 48cp2, normal QoS
- request: 1 node, 20 MPI tasks, 1 thread per task, 190000 MB, 6 hours
- reason: all three partitions have the required CPU and memory shape; 48cp2
  had the largest current whole-node margin. The 20-rank layout is the existing
  SIAB generator contract used by the completed Se generation, not a full-node
  ABACUS/LibRPA production layout.
- duplicate state: retry1 remote directory absent and no matching retry1 job in
  the live queue before transfer
- final scheduler test: passed at 2026-09-14T22:40:38+08:00; Slurm reported
  immediate placement on `c21327` in `48cp2` for the exact request
