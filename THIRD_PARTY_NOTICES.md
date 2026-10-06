# Third-party attribution and local code scope

`third_party/CHILS/` is unmodified source from [KarlsruheMIS/CHILS](https://github.com/KarlsruheMIS/CHILS), pinned at commit `515952724cd3dcc6c4365a340ecf0f1da782119a`. The source was recovered from the archived source used by the local experiment evidence. Its complete MIT license is preserved in `third_party/CHILS/LICENSE`.

Copyright (c) 2025 Kenneth Langedal, Ernestine Großmann, and Christian Schulz.

Publication: *Concurrent Iterated Local Search for the Maximum Weight Independent Set Problem*, SEA 2025, DOI [10.4230/LIPIcs.SEA.2025.22](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SEA.2025.22).

`adapters/` contains local experiment code: original transport wrappers or exact selected definitions with minimal imports. `scripts/` contains newly added public packaging, input export and verification utilities. These are not official upstream CHILS files, and are not attributed to the upstream authors.

No separate license for the local adapter files was found in the experiment project. This release does not apply the upstream MIT copyright notice to locally authored adapters or add a new blanket license to them.
