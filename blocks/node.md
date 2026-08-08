<!-- BEGIN shared:node -->
## Package manager

- This project uses **pnpm** exclusively. NEVER use `npm`, `bun`, `yarn`,
  or any other package manager.
- Run CLI tools through `pnpm`, preferring the `package.json` scripts over
  hand-written equivalents — the scripts encode the exact gates CI runs.
  NEVER use `npx`.
- Do not add a dependency for something an existing dependency already
  provides, and do not add one without a stated reason.

## TypeScript

- Do not use `any`. When a type is genuinely unknown at a boundary, use
  `unknown` and narrow it explicitly.
- Do not silence the type checker with `@ts-ignore` or `@ts-expect-error`
  without a comment explaining why the suppression is correct.
- Do not use non-null assertions (`!`) to satisfy the compiler. Narrow the
  value, or handle the absent case.
- Prefer discriminated unions over optional fields when a finite set of
  shapes is expected.
- Never interpolate a secret into a log line, an error message, or a
  serialized response.
<!-- END shared:node -->
