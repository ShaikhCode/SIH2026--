# BhashaSaathi account model — final

## Registration contract
A new account asks for exactly:
1. Username / full name
2. Email
3. Password

It does **not** ask for:
- creator/student role
- preferred language
- classroom
- grade
- subject

## Capability model
A user is a single account. Capabilities are determined by classroom relationships:

- `Group.owner_id == user.id` → creator/educator capabilities for that classroom.
- `Membership.role == student` → learner capabilities for that classroom.
- The same user can own one classroom and be a student in another.

The user record does not drive teaching vs learning UI.

## Language model
Language is a workflow preference, not an account property.

- Workspace language lives in local UI state/localStorage.
- Lesson source language is stored on the lesson.
- Translation target language is selected in the lesson workflow.
- Student learning language is selected per learning session/workspace.

This prevents an account-level Hindi/English/Marathi choice from restricting translation.

## Security
The existing internal `account_role` column is retained only for legacy/admin JWT compatibility. It is not exposed in the public user object and is not used to decide classroom teaching/learning capability.
