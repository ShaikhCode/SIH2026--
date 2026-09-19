# Final account model audit

## Product decision
BhashaSaathi has **one account type**. Registration is deliberately minimal:

- Username / full name
- Email
- Password

There is no creator/student selection and no language selection at registration.

## How capabilities work
Capabilities are contextual and classroom-scoped:

- A user who owns a classroom is its educator/creator.
- A user who joins another classroom is a learner there.
- The same account can own multiple classrooms and join multiple classrooms.
- A user can therefore teach and learn simultaneously without changing account type.

The frontend does not use a global user role to decide whether the person can teach or learn.

## Language model
Language is also contextual:

- UI/workspace language is a local preference.
- Lesson source language is selected when creating the lesson.
- Translation target languages are selected in the lesson workflow.
- Student learning language is selected per learning session.

Therefore selecting Hindi in the sidebar never prevents English → Hindi, Hindi → English, English → Marathi, etc.

## Legacy compatibility
The database still has an old `account_role` column because existing local databases may contain it and the internal admin JWT path may rely on it. It is not exposed in the public `/auth/me`, registration response, or frontend account model and is not used for classroom capabilities.

## Additional fix
Classroom API responses now expose `is_owner` and `membership_role`. This lets the UI correctly separate:

- Teaching: classrooms the user owns.
- Learning: classrooms the user joined.

This avoids the previous global-role assumption in dashboard metrics and classroom cards.
