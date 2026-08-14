<!-- BEGIN shared:node -->
## Package manager

- This project uses **pnpm** exclusively. NEVER use `npm`, `bun`, `yarn`,
  or any other package manager.
- Run CLI tools through `pnpm`, preferring the `package.json` scripts over
  hand-written equivalents — the scripts encode the exact gates CI runs.
  NEVER use `npx`: where the name is not already installed it resolves and
  installs a remote package instead of failing, so a typo or a dependency
  someone dropped becomes a silent download. Run a project dependency with
  `pnpm exec <tool>`. Run a one-off that is deliberately not a dependency
  — a scaffolder, a utility a scheduled job reaches for — with
  `pnpm dlx <tool>@<version>`, naming an exact version and never a
  dist-tag: `@latest` pins nothing, so a scheduled run executes whatever
  was published since the last one.
- Install with the lockfile as the authority — CI runs
  `pnpm install --frozen-lockfile`, so a `package.json` change that never
  reached `pnpm-lock.yaml` fails there instead of resolving to something
  nobody chose.
- Do not add a dependency for something an existing dependency already
  provides, and do not add one without a stated reason.

## TypeScript

- Do not use `any`. Data crossing a boundary — a network response, a
  file, an environment variable, a third-party callback — enters as
  `unknown` and is validated or narrowed at that boundary, before
  anything downstream sees it.
- Do not suppress a TypeScript or Biome diagnostic — `@ts-expect-error`,
  `biome-ignore` — without a comment saying why the suppression is
  correct. Never `@ts-ignore`: it outlives the error it was written for
  and goes on hiding whatever appears on that line next, where
  `@ts-expect-error` fails once the error it names is gone.
- A suppression is not a substitute for a type. Where a rule here already
  names what to write instead — `unknown` and a narrowing, a discriminated
  union, the type a dependency already exports — write that. Suppressing
  the rule that forbids `any` still leaves an `any`, and a comment
  recording that the real type was inconvenient is not a reason. What
  makes one is a shape nobody here controls, or a test whose point is
  that the code under it does not type-check:

  ```ts
  // biome-ignore lint/suspicious/noExplicitAny: the vendor declares this
  // callback `any`; every value out of it is narrowed before use
  ```

- Never write a double assertion (`as unknown as T`). A single `as` still
  has to be plausible to the compiler; routing through `unknown` removes
  even that, so what is left asserts a relationship nothing checked. This
  binds the code you write — generated output belongs to whatever emits
  it, and editing it by hand is undone on the next run.
- Do not use non-null assertions (`!`) to satisfy the compiler. Narrow the
  value, or handle the absent case.
- Prefer discriminated unions over optional fields when a finite set of
  shapes is expected.
- Never interpolate a secret into a log line, an error message, or a
  serialized response.
<!-- END shared:node -->
