# V19 Publish White-Screen Fix

## Root cause
`LessonBuilderPage.tsx` had this dependency set on the background preparation poller:

```ts
}, [lessonId, pack, refresh, requiredLanguages]);
```

`syncPreparations()` calls `refresh()` when preparation status changes. `refresh()` calls `setPack()`. Because `pack` was a dependency of `syncPreparations`, every `setPack()` created a new callback, restarted the polling effect, and immediately called the API again while jobs were still active.

After Publish, TTS/practice jobs are often active, so this could create a rapid refresh/render/fetch feedback loop and make the page appear blank/frozen.

## Fix
The poller only uses `lessonId` and the stable `refresh` callback, so the dependency list is now:

```ts
}, [lessonId, refresh]);
```

The existing `setTimeout(..., 1600)` now actually controls the polling cadence.

## Secondary issue to address next
The editor autosave can still race with Publish. A pending autosave after a lesson becomes `PUBLISHED` can create a new draft version. This is not the primary white-screen trigger, but it should be guarded in a follow-up patch.
