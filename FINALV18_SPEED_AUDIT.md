# FinalV18 Speed Audit

## Main finding
The most important UX problem was not only model inference. The product was making downstream preparation part of the perceived foreground interaction.

FinalV18 separates the **human review path** from the **artifact preparation path**.

## Foreground path

`current editor text → resident IndicTrans2 → Translation Guard → show target text → teacher reviews/edits → approve`

No TTS, worksheet generation, practice generation, or full lesson refresh is awaited by the approval action.

## Background path

`approved translation → persisted preparation jobs → TTS / practice → saved DB/artifact state`

The worker is deliberately single-threaded for heavy background work. This is slower than launching multiple CPU-heavy model calls at once, but avoids making the foreground translation compete for the same CPU/RAM resources.

## Teacher accuracy workflow

The teacher can immediately inspect:

1. original source;
2. generated target text;
3. Translation Guard diagnostics;
4. optional source-language Meaning Check / back-translation.

A Meaning Check is cached in `validation_json` after the first request, so it does not have to run again for the same translation.

## Student feedback workflow

Students can confirm a published translation or report an issue. This is deliberately not used as an automatic publication or safety gate.

## Learning outcome removal

The old step was removed because it added an extra interaction and became a publication dependency without being central to the product's immediate translation/demo value. Legacy storage is kept for compatibility.

## Warm-up

When the teacher opens a lesson, the server and client background-warm only the two routes required for the current source language. The warm-up is sequential so two CPU-heavy model loads do not compete with each other.

## Short-input decode ceiling

Interactive translation uses a dynamic maximum output length based on source word count, bounded by the existing configured maximum. Short phrases therefore have a smaller decoding ceiling without removing headroom for language expansion.

## What cannot honestly be guaranteed

This release does not claim a literal 100x model-inference speedup. IndicTrans2 and Parler-TTS inference time remains hardware/model dependent. The release instead removes avoidable waiting and moves nonessential downstream work off the foreground path.
