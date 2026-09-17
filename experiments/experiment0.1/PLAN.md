# Experiment0.1 schema-driven expansion plan

Authorized scope: implement and validate locally; no paid inference, weight training, remote staging, commit or push. Preserve experiment0.0 and unrelated dirty work.

- [ ] Define versioned JSON schemas: general facts, scoped likes/dislikes, category attributes and sizes, hard/soft rule operators, rendering templates, event rates/time gaps/category selection.
- [ ] Implement a generic engine. Category extension using the supported types/operators must require JSON edits only. Keep general, category and intent state separate; never infer taste, department or sizes from demographics.
- [ ] Generate seeded stochastic timestamped sessions. Respect transition preconditions; retain explicit validity intervals and provenance; derive age from disclosed birthday; distinguish retraction, dislike, absence, expiry and completion.
- [ ] Build per-session supported questions and catalog recommendations from revealed prefix evidence only. Include general-current/historical facts and preferences, hard feasibility/soft ranking, ties, no suitable products and unknown sizing. Include cross-category distractors.
- [ ] Integrate paired frozen-model harness: identical current context, prior notes only in memory arm, both answers before update, isolated users, schema-driven note validation/prompts, offline replay.
- [ ] Test JSON-only new category, selection, stochastic variation/reproducibility, chronology/support/leakage, category/recipient scopes, hard-vs-soft ranking and temporal boundaries. Execute 10×10 mock/replay, full tests, unchanged0.0 validation.
- [ ] Update documentation/config/validation with exact supported expressiveness and limitations; report completion to originating task.

Time semantics: canonical UTC; evidence valid intervals [valid_from, valid_until), deadline actionable through its exact instant, expired strictly later. No blanket TTL; future/open intents persist until their semantics or explicit changes deactivate them. Questions use only already disclosed evidence, never latent/unrevealed values.

Additional authorized profile changes: restrict gender domain to male/female; add explicit synthetic race; JSON nationality-based name pools; include sampled general hobby/noncommercial likes/dislikes; preserve prior sample and export a fresh one. Naming is the only nationality-conditioned sampler; do not infer race, languages, tastes or sizing from it.
