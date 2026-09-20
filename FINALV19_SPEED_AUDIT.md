# FinalV19 Speed Audit

## Findings addressed

| Area | Earlier behavior | FinalV19 |
|---|---|---|
| Long translation input | Tokenizer used `truncation=True, max_length=256` on the full lesson | Token-safe sentence/word chunking, no silent truncation |
| Translation output | Small fixed generation ceiling | Adaptive ceiling up to 512 + targeted retry |
| Long lesson | One oversized inference path | Safe chunks + batches of 4 |
| Concurrent target clicks | Separate HTTP writes could hold SQLite transactions during model inference | Source transaction is committed before transformer inference |
| Builder GET | Worksheet/flashcard generation happened on every pack | Worksheet is on-demand; flashcards removed |
| Publish | Required practice + audio completion | Only source + teacher-approved translations are blocking |
| Background workers | One queue mixed TTS and practice | Dedicated TTS and practice executors |
| Audio | Could make UI look stuck | Persistent background job state + publish does not wait |

## Static verification

- Python `compileall`: PASS
- Target Python module `py_compile`: PASS
- FastAPI application import: PASS
- 23 TS/TSX files syntax parsed: PASS
- Translation chunk coverage test: PASS
- No flashcard references remain in active API/web code: PASS

## Runtime verification limitations

The final browser production build and real model latency require the user's Windows environment, local model weights, and audio devices. Those cannot be physically reproduced in this build sandbox.
