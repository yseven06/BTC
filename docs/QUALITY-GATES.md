# Zate Trade — Quality Gates (Local Hooks + CI)

Two enforcement layers guard every change: **Husky hooks** (pre-commit, local) and
**GitHub Actions** (post-push, remote). Same checks, two places — the local layer
gives fast feedback, the remote layer proves the code is not machine-dependent.

Related: [`DEPLOYMENT.md`](DEPLOYMENT.md) · [`RELEASE-RUNBOOK.md`](RELEASE-RUNBOOK.md) · [`SECURITY.md`](SECURITY.md)

---

## 1. Local layer — Husky

Hooks live in `frontend/.husky/` and are activated repo-wide via
`core.hooksPath=frontend/.husky`. The `prepare` script in `frontend/package.json`
re-applies this config automatically after `npm install`, so a fresh clone is
covered without manual setup.

| Hook | Runs | Blocks commit on |
|---|---|---|
| `pre-commit` | `lint-staged` → `npm run typecheck` → `npm run lint:design:strict` | TS type error · ESLint error on staged files · Stylelint error · design-gate violation |
| `commit-msg` | `commitlint` (`@commitlint/config-conventional`) | Non-conventional commit message |

**lint-staged scope** (`frontend/package.json`):

| Glob | Command |
|---|---|
| `*.{ts,tsx,js,jsx}` | `eslint` |
| `*.css` | `stylelint` |

> ⚠️ `lint-staged` runs plain `eslint` (no `--max-warnings=0`). This is deliberate:
> the repo carries pre-existing warnings (see §4), and a zero-warning gate would
> block any commit that merely *touches* a file carrying old debt. Errors still block.

**Commit message format** — Conventional Commits, `header-max-length: 100`,
`body-max-line-length` disabled. Examples in repo history: `feat(deploy):`,
`fix(a11y):`, `refactor(brand):`, `chore(ci):`.

> ⚠️ `git commit --no-verify` bypasses both hooks. Per the project's baseline
> development discipline, it is **not to be used** — if a hook fails, fix the cause.

---

## 2. Remote layer — GitHub Actions

`.github/workflows/ci.yml` — triggers on push and PR to `main`.
Concurrency group cancels superseded runs on the same ref.

### Job: `frontend`

Node 20, npm cache keyed on `frontend/package-lock.json`, working dir `frontend/`.

| Step | Command | Purpose |
|---|---|---|
| Install | `npm ci --no-audit --no-fund` | Lockfile-exact install |
| Typecheck | `npm run typecheck` (`tsc --noEmit`) | Type safety |
| Lint | `npm run lint` (`eslint .`) | Code correctness rules |
| Design gates | `npm run lint:design:strict` | Design Bible enforcement (`scripts/design-gates.mjs` + Stylelint plugin) |
| Build | `npm run build` | Full `next build` — proves the app compiles in a clean environment |

> ✅ `next build` is safe here. The local rule "never run `next build` while `next dev`
> is running" (it corrupts the `.next` cache) does not apply — CI has no dev server.

### Job: `secrets-scan`

Grep-based scan across tracked source files for credential patterns:
OpenAI (`sk-…`), GitHub PAT (`ghp_`/`gho_`), AWS access key (`AKIA…`), JWT
(`eyJhbGciOi…`), PEM private key headers. Excludes `node_modules`, `.next`, `.git`,
`dist`, `build`.

> ⚠️ This is a **pattern heuristic, not a secret manager**. It catches accidental
> paste-ins; it does not replace the env-var discipline in `DEPLOYMENT.md`
> ("secrets are never committed"). It also does not scan git *history* — a secret
> committed earlier and later removed will not be flagged.

---

## 3. ESLint configuration

`frontend/eslint.config.mjs` — ESLint 9 flat config bridging the official Next.js
presets via `FlatCompat`:

```
next/core-web-vitals + next/typescript
```

### Why not `next lint`

`next lint` is deprecated as of Next.js 15.5 and opens an **interactive setup
prompt** ("Strict / Base / Cancel") when no legacy `.eslintrc` is present. In a
non-interactive CI runner this exits with code 1 and no actionable output — the
failure mode that produced CI run #1. Replaced with the supported `eslint .` CLI.

### Deliberate rule adjustments

| Rule | Level | Scope | Rationale |
|---|---|---|---|
| `@typescript-eslint/no-explicit-any` | `warn` | Global | 72 pre-existing occurrences. Correcting them means writing real types, which carries runtime-behavior risk — deferred to a dedicated typing sprint rather than rushed inside a lint pass. |
| `@typescript-eslint/no-require-imports` | `off` | `**/*.cjs` | `require()` is canonical in CommonJS; the rule is a false positive there. |

**Ignored paths:** `.next/**`, `out/**`, `build/**`, `node_modules/**`,
`next-env.d.ts`, `take_screenshots.js` (one-off dev script, not app runtime).

Everything else in the Next.js presets is preserved at preset severity —
`react-hooks/rules-of-hooks`, `react/no-unescaped-entities`, and the Core Web
Vitals rules all remain errors.

---

## 4. Known lint debt

Surfaced when ESLint was first enforced end-to-end. These are **pre-existing**
findings the migration made visible, not regressions it introduced. All are
warn-level: reported on every run, blocking nothing.

**Current: 0 errors, 104 warnings** (measured at `41e2a23`).

| Rule | Count | Disposition |
|---|---|---|
| `@typescript-eslint/no-explicit-any` | 66 | Dedicated typing sprint. Do not batch-fix — each `any` needs its real type, and a wrong one is a runtime bug. |
| `@typescript-eslint/no-unused-vars` | 32 | Low-risk cleanup pass. Delete, or `_`-prefix if the binding is required by a signature. |
| `@next/next/no-img-element` | 4 | Evaluate `<Image>` migration case-by-case (each site needs explicit dimensions). |
| `react-hooks/exhaustive-deps` | 1 | Review individually — adding a dependency changes effect timing. |
| Unused `eslint-disable` directive | 1 | `signals/page.tsx:1027` — the suppressed rule no longer fires; the comment can be dropped. |

**Trend.** The migration cleared 108 errors → 0. Warning count has since fallen
from 128 to 104 through `chore(lint)` passes (`c83f3fc`, `e4afccd`) that cleaned
up files touched by other work — the intended way to retire this debt: opportunistically,
alongside changes already being made to a file.

> ⚠️ When reducing debt, do not silence rules with type assertions or blanket
> `eslint-disable` comments. Fix the underlying code, or leave the warning standing.

---

## 5. Local commands

Run any gate manually without committing:

```bash
cd frontend
npm run typecheck          # tsc --noEmit
npm run lint               # eslint .
npm run lint:design        # Stylelint + design-gates (advisory)
npm run lint:design:strict # Stylelint + design-gates (CI parity)
```

> ⚠️ `npm run build` locally: only with `next dev` stopped. See
> [`DEPLOYMENT.md`](DEPLOYMENT.md) — a concurrent build corrupts the `.next` cache.
> For routine verification, `typecheck` + a dev-server route check is sufficient.

---

## 6. Maintenance notes

- **Adding a check:** add it to both layers, or state explicitly in the PR why it
  belongs to only one. A CI-only check is fine for anything slow (full build);
  a hook-only check is rarely justified.
- **Node version:** CI pins Node 20 (`actions/setup-node@v4`); `package.json`
  declares `engines.node >= 20.11`. Keep these aligned when bumping.
- **Action deprecation warnings:** `actions/checkout@v4` and `actions/setup-node@v4`
  currently emit a Node 20 runtime deprecation notice. Non-blocking; bump to `@v5`
  when convenient.
- **Backend (Python) is not yet gated.** `pytest`/`ruff` in a parallel CI job is the
  natural next step — out of scope for the initial setup.

---

## Changelog

| Commit | Change |
|---|---|
| `399045b` | Initial setup: Husky hooks (`pre-commit`, `commit-msg`) + GitHub Actions CI. First run failed on the `next lint` interactive prompt. |
| `0c07b30` | ESLint flat-config migration (`next lint` → `eslint .`); 32 `no-unescaped-entities` errors mechanically escaped across 9 files; `no-explicit-any` set to warn. **CI green.** |
| `c83f3fc`, `e4afccd` | Opportunistic lint-debt reduction in files touched by the rebrand and landing work. |
