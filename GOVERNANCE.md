# GOVERNANCE — LayoutRule is the authoritative rule source

Updated: 2026-11-16
Owner/reviewer: repository owner (human). This document records workflow policy; actual server-side enforcement requires GitHub branch protection/rulesets configured by the owner.

## One-way dependency contract

```text
LayoutRule (approved versioned rules) ----read-only----> Training / KiCadAutoLayout / other project repos
                                                       |
                                                       v
                                               local review evidence
                                                       |
                                                       v
                                                change proposal
                                                       |
                                              owner approval gate
                                                       |
                                                       v
                                         human-reviewed change in LayoutRule
```

- Downstream repos **consume** LayoutRule rules and should pin a commit SHA or release tag in their run manifests. Downstream project files, AI agents, CI outputs and user PCB revisions NEVER automatically mutate LayoutRule rules.
- A user edit in a downstream KiCad project is evidence of a candidate layout change, NOT proof that a universal placement/routing rule should change.
- Rule changes to the canonical default branch require the repository owner's explicit review and approval. AI agents must not independently merge, push to the default branch, bypass review, or infer permission from silence.
- A pull request/draft and a downstream evidence report are proposals only, never approved policies. Where GitHub permissions allow, propose a PR rather than direct commit; otherwise leave a local Markdown report for owner review.
- New research/catalog entries are **unverified evidence**, not new rules; do not present them as approved. Avoid direct default-branch research writes unless the owner explicitly requests them.
- Existing documented heuristics are not automatically elevated to verified electrical standards; preserve their evidence status. PT17 is a proposed heuristic (user discussion, no CAD validation), not a verified release gate.

## Approval states and required evidence

- `DRAFT`: idea from one board, source or discussion, not checked.
- `PROPOSED`: structured candidate with ID, applicability, scope, exceptions, risk, source and reproducible validation plan.
- `VALIDATED`: explicit test evidence on identified board(s) and exact commit hashes; native ERC/DRC when applicable, plus electrical/topological reasoning. Validation alone is not owner approval.
- `APPROVED`: owner explicitly approved *this specific rule/revision* and the canonical rulebook update was merged by an authorized person.
- `REJECTED` / `RETIRED`: preserved with rationale for traceability.

Rule review proposal must include:
1. Provenance: downstream repo URL, branch, PCB/SCH SHA256 and rulebook commit.
2. Exact change: rule ID, before/after wording, scope (devices/protocols/stackups), constraints, exception and counterexample.
3. Evidence: vendor datasheet/app note or CAD reference when available; measured PCB geometry; trial placement/routing logs; KiCad ERC/DRC outputs; alternatives and tradeoffs.
4. Outcome: proposed tier HARD/CONDITIONAL/HEURISTIC, accepted/rejected cases, reproducibility, rollback path.
5. Reviewer action: named owner decision and scope; no invented or implied approval.

## Review cycle — downstream to upstream

1. **Read:** downstream agent loads pinned LayoutRule release/commit; local schematic, PCB, BOM and project constraints take precedence for applicability.
2. **Analyze:** run schematic validity/ERC, placement and routing reviews; preserve baseline and record hashes.
3. **Propose locally:** create a report (for example `reviews/layout_rule_proposals/PR_<topic>.md`) in the downstream repo or an unmerged PR. Do not rewrite canonical rules or sync generated reports upstream.
4. **Independent check:** compare reference designs/datasheets and test the hypothesis on a copy, including possible negative counterexamples.
5. **Owner adjudication:** owner may approve, reject, request changes, or defer. Approval must refer to an exact rule/revision; explicit scope is binding.
6. **Promote:** only approved change is merged into LayoutRule by an authorized actor. Update relevant rule sources, IDs, index and changelog consistently, and publish new commit/tag.
7. **Consume:** downstream repos opt into the new pinned revision, run regression tests and retain their previous lockfile/reference if it regresses.

## Required separation

- `Training`: test cases, PCB snapshots, measurements and **proposals only**.
- `LayoutRule`: canonical documentation and evidence catalog, with reviewed rule changes.
- `KiCadAutoLayout`: tool implementation and rule execution; must report which exact LayoutRule revision was used.
- No unattended jobs may write from Training/KiCadAutoLayout into LayoutRule.
- No project-agent changes to LayoutRule's rule files merely because a proposed placement scored better or DRC passed.
- In case of ambiguous authorization, do not modify LayoutRule rule contents; produce a proposal for the owner.

## Practical GitHub controls (not configured by this document)

Require a pull request with the owner's review, branch protection/rulesets for `main`, and a required check validating source IDs, references, rule evidence and index parity. CODEOWNERS alone does not enforce review without repository protection settings. Do not claim the policy is technically enforced until settings and bypass permissions are verified.
