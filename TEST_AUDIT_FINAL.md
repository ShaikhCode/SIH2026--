# BhashaSaathi Final Web Audit — 2026-09-19

## Critical white-screen bug fixed
The classroom page had a JavaScript temporal-dead-zone bug:
`isOwner` was calculated from `group` before the `group` state variable was declared.

Old order:
- `const isOwner = group?.owner_id === user?.id`
- `const [group, setGroup] = useState(...)`

This can throw `ReferenceError: Cannot access 'group' before initialization` during the first render and produces the reported white screen.

New order:
- `const [group, setGroup] = useState(...)`
- `const isOwner = group?.owner_id === user?.id`

## Tests performed
- Python source compilation: PASS (`python -m compileall -q apps/api core`)
- Verified 17 TSX source files are present.
- Verified the classroom route is `/groups/:id` and classroom cards navigate to `/groups/{id}`.
- Verified the classroom page now safely renders before API data exists (`group` initially null).
- Verified API group endpoint returns the owner id used by the frontend ownership check.
- Verified registration request contains only name, email, password.
- Verified login request contains only email and password.
- Verified language is selected per workspace/lesson and not required during account creation.
- Verified supported frontend language registry is English, Hindi, Marathi.
- Verified no `sat_Olck` or Santhali references remain in the web/layer2 application source.
- Verified Marathi (`mar_Deva`) exists across translation, TTS, STT, glossary, worksheet/flashcard and publish paths.

## Environment limitation
The sandbox did not have the project's frontend dependencies installed. Two attempts to run `npm install --no-audit --no-fund` timed out, so a Vite/TypeScript production build could not be truthfully claimed here. The package was therefore tested with source/static checks and Python compilation, and the exact browser white-screen defect was identified and fixed from code inspection.

## Local final verification
Run on Windows in `apps/web`:

```powershell
npm install
npm run build
npm run dev
```

Then test:
1. Login.
2. Open Classrooms.
3. Create classroom.
4. Click the newly created classroom card.
5. Confirm classroom page loads instead of white screen.
6. Create lesson and open builder.
7. Change source and target languages independently.
8. Confirm English -> Hindi, Hindi -> English, Hindi -> Marathi and Marathi -> Hindi can be selected.
