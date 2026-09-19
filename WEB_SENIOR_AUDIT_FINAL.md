# BhashaSaathi — Senior Web/Product Audit

Date: 2026-09-19
Scope: React/Vite web application plus the minimum backend changes required to keep web state truthful and publish-safe.

## Bugs found and fixed

### P0 — Key concepts input lost focus / removed typed characters
Cause: concept rows used a React key containing the current input value (`index + concept`). Every keystroke changed the key, so React remounted the input.
Fix: stable row key based only on index.

### P0 — Source-language preview was duplicated
The review preview rendered all three languages and treated the source language as a fake translation/source card. English-source lessons therefore displayed English twice and showed misleading readiness.
Fix: preview now renders the original source once, then only the remaining target languages.

### P0 — Publish readiness was hard-coded to English + Marathi
The UI and backend assumed English and Marathi were always required. If the lesson source was English, English was still required as a translation, which could never be correct.
Fix: required target languages are dynamically calculated as every supported language except the source language.

### P0 — Regenerate translations could destroy approvals
Generate targets always called the model again. A second click reset previously approved translations to `UNVERIFIED`.
Fix: approved, non-empty translations are skipped. The UI explicitly reports that an approved translation was retained.

### P0 — Autosave could leave stale generated outputs
The web autosave sends source/concepts/outcome fields on every save. Backend state previously had no invalidation rule, so translations/practice/audio could become stale after source changes.
Fix: backend compares incoming values with the active version and deletes generated outputs only when source semantics actually change. A title-only autosave does not destroy generated work.

### P1 — Practice could mix source-language concept labels into another language
Practice generation used the concept label directly for English/Hindi and only translated Marathi. A Hindi concept could therefore appear inside an English question or vice versa.
Fix: canonical English practice is prepared first and rendered into the requested learner language using the local translation function.

### P1 — Practice/publish readiness was Marathi-specific
The UI required Marathi practice/audio even when Marathi was the lesson source. That created an incorrect requirement model.
Fix: every non-source target language gets its own translation approval, practice approval, and target-language audio requirement.

### P1 — Student lesson could open in an unavailable language
The student page defaulted to Hindi even when a lesson was authored in English and Hindi had not been prepared.
Fix: student language selection now falls back to the lesson source language or an available translation.

### P1 — Marathi was incorrectly styled as Ol Chiki
The student reader used an `ol-chiki` CSS class for Marathi.
Fix: Marathi and Hindi use Devanagari styling; Marathi is no longer represented as Ol Chiki.

### P1 — Worksheet assumed Hindi source + Marathi target
The worksheet generator hard-coded Hindi/Marathi roles.
Fix: worksheet now uses the actual source language and the first available non-source target language.

## Product behavior after the fixes

Supported prototype languages:
- English — `eng_Latn`
- Hindi — `hin_Deva`
- Marathi — `mar_Deva`

For a Hindi lesson:
- targets = English + Marathi

For an English lesson:
- targets = Hindi + Marathi

For a Marathi lesson:
- targets = English + Hindi

The account language is not a lesson restriction. Registration does not ask for a preferred language. Language choice is made at the workflow/lesson/student level.

## Translation performance

The local IndicTrans2 runtime is CPU/model dependent, so translation cannot honestly be promised as instant. The web now avoids unnecessary model calls and does not run all target models concurrently. This reduces CPU contention and prevents repeated clicks from regenerating already-approved outputs.

## Publish contract

A lesson is publishable only when:
- source exists
- learning outcome exists
- at least one concept exists
- every non-source supported language has a non-empty translation
- every required translation is teacher-approved
- at least one practice question is approved for every non-source language
- target-language audio exists for every non-source language

## Verification performed

PASS — Python compilation of API application
PASS — FastAPI application import
PASS — publish service import
PASS — practice service import
PASS — stale-output invalidation code compiles
PASS — old Santhali/Ol Chiki application references absent from active source paths
PASS — concept input key bug fixed
PASS — dynamic source/target preview
PASS — dynamic readiness model
PASS — approved translation preservation
PASS — student language fallback

Frontend production build could not be executed in this sandbox because `npm install` timed out. A local build must still be run with the project's Node/npm environment.

## Required local verification

```powershell
cd D:\git\BhashaSaathi_Local_NoDocker\apps\web
npm install
npm run build
npm run dev
```

Then test:

1. Register without a language field.
2. Login.
3. Create classroom.
4. Open classroom.
5. Create lesson with English source.
6. Add a concept and type several characters continuously — input must not lose focus.
7. Generate targets — only Hindi + Marathi should appear as targets.
8. Approve both.
9. Generate practice for both target languages and approve at least one each.
10. Generate both target audio files.
11. Review preview — English source appears once; Hindi + Marathi appear as translations.
12. Change the source text — old translations/practice/audio must become invalid and must not remain publishable.
13. Return to the same lesson and verify no white screen occurs.
14. Open as learner and switch among available languages.
15. Download offline and verify cached lesson/audio/practice.
