# BhashaSaathi — Final Audit & Fix Report

**Audit Date:** 2026-09-23  
**Build status after fixes:** Python compileall ✅ · Frontend `npm run build` ✅ (exit 0)

---

## Issues Found and Fixed

### 1. Frontend Build Failure — 6 TypeScript Errors

| Error | Location | Fix Applied |
|-------|----------|-------------|
| `{}` not assignable to `Record<Lang, boolean>` | `LessonBuilderPage.tsx:47` | Changed to `Partial<Record<Lang, boolean>>`, all accesses guarded with `?.` |
| `string` not assignable to `SetStateAction<Lang>` | `LessonBuilderPage.tsx:306` | Changed `PromiseFulfilledResult<string>` to `PromiseFulfilledResult<Lang>` |
| `Languages` identifier not found | `LessonBuilderPage.tsx:649` | Added `Languages` to lucide-react import |
| `Button` does not accept `size` prop (×2) | `LiveTranslatePage.tsx:556` | Added `size?: string` to Button component |
| `Button` does not accept `title` prop | `LiveTranslatePage.tsx:575` | Added `title?: string` to Button component |

**Result:** `tsc -b && vite build` exits 0, bundle ~403 kB JS.

---

### 2. Student Answer Security Leak

**Root cause:** `_practice_view()` included `correct_answer` and `explanation` and was used for both
teacher and student API responses. Students could read correct answers from the JSON payload.

**Fix applied:**
- Added `_practice_student_view()` omitting `correct_answer` and `explanation`
- `pack()` now selects student view when `viewer_id` is set, teacher view otherwise
- Server-side evaluation in `evaluate_attempt()` is unaffected

---

### 3. Global `busy` State Blocked Publish Button

**Root cause:** `disabled={!readiness.publish || !!busy}` — generating practice or audio set `busy`,
disabling Publish even when the lesson was ready.

**Fix applied:** Added dedicated `publishBusy` state. Publish button is now independent.

---

### 4. Subtitle Hardcoded "English is the main lesson language"

**Fix applied:** Dynamic subtitle reflects actual `sourceLanguage` selection.

---

## Verified as Passing

| Requirement | Status |
|-------------|--------|
| Publish never waits for TTS / translations / Santali | ✅ |
| Santali does not require approval | ✅ |
| TTS job deduplication via UniqueConstraint | ✅ |
| Polling stops when no active jobs | ✅ |
| Autosave cancelled before publish | ✅ |
| Per-language translation busy states | ✅ |
| source_language stored and restored | ✅ |
| Python compileall | ✅ |
| Frontend build (npm run build) | ✅ |

---

## UNVERIFIED (requires running models)

- Full API startup with IndicTrans2, FasterWhisper, Parler-TTS
- Live Translate WebSocket pipeline
- TTS GPU usage on RTX 2050 (4 GB VRAM)
- Background prep job thread isolation

---

## Files Modified

| File | Change |
|------|--------|
| `apps/web/src/components/UI.tsx` | Added `size` and `title` props to Button |
| `apps/web/src/pages/LessonBuilderPage.tsx` | Languages import, translationBusy type, setTarget cast, publishBusy, subtitle |
| `apps/api/app/api/routes/lessons.py` | Added `_practice_student_view()`, updated `pack()` |
