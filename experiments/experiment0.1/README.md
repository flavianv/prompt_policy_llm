> Archived exploratory shopping prototype. This document describes its schema-v3 snapshot; schema-v4 samples are also preserved. The active explicit-state checkpoint and live results are in [experiment0.2](../experiment0.2/README.md). The shared profile_generation contract is version1.1. Historical mock counts below are not live quality results.

# Experiment0.1: JSON-defined temporal shopping memory

Current environment schema: **schema-v3**, superseding the earlier local footwear/apparel prototypes. Implemented and validated locally; **no live Qwen/Luna inference or weight training has run for this version**. Experiment0.0 and its original AdaptGym harness remain unchanged.

The project owns this generator, oracle and paired-session extension. It reuses only the unchanged Qwen loader/generator from `adaptgym_pilot.py`; it does not modify or claim to be an upstream AdaptGym release. No new dependencies were introduced.

## Files and quick start

- `environment.json`: category/general schemas, preference mappings, event rates, session gaps, counts, selection and evidence templates.
- `config.json`: seeds and frozen-model run settings.
- `src/prompt_policy_llm/shopping_schema.py`: generic generator, constraints, oracle, note validation and public prompts.
- `src/prompt_policy_llm/shopping_memory.py`: paired execution, traces, scoring and offline replay.
- `PLAN.md`: executed implementation plan; `validation.json`: validation record.
- `samples/seed17/sessions_and_questions.md`: one actual generated user, all ten sessions and 56 questions, without answers. `catalogs.md` contains model-visible candidates. `hidden_profile.md`, `answer_key.md` and full `episode.json` are separate evaluator artifacts. No assistant replies are simulated.

From repository root, no credentials/models required:

```bash
python3 experiments/experiment0.1/reproduce.py --output /tmp/shopping-schema-mock
python3 experiments/experiment0.1/reproduce.py --audit /tmp/shopping-schema-mock
python3 experiments/experiment0.1/reproduce.py --categories shoes,shirts --output /tmp/shopping-two-categories
python3 experiments/experiment0.1/export_sample.py --seed 17 --output /tmp/shopping-user17
PYTHONPATH=experiments/experiment0.0/vendor/adaptgym/src:src python3 -m pytest -q
python3 experiments/experiment0.0/reproduce.py --validate
```

`--environment /path/to/spec.json` selects another JSON definition. `--categories` selects keys at load; omitted selection uses the JSON default. New output directories are required. The default mock chooses the first fact option, `NONE/uncertain` for recommendations, and only reads/finishes notes. Its scores are plumbing checks, not quality results.

## Three separate user layers

**General facts and preferences.** The JSON defines birth date and derived age; gender; education; income with currency/period; marital status; weight/height with units; build; hair/eye color; residence; nationality; languages. Preference topics cover cities, countryside, clothing brands, other brands, movies, authors and hobbies. Likes, dislikes and retractions are different states, with explicit global/category scope.

A complete initial general/category profile is sampled into the evaluator-only `sampled_user`. Values become usable only after an evidence event discloses them. Current revealed state, not the hidden draw, drives questions and recommendations. General facts are background unless a question asks about them; they never infer size, taste, department, or medical requirements. General brand preferences affect shopping only through an explicit topic-to-product-field mapping opted into by that category. Other topics are background context. A dislike is a hard exclusion; a like adds a soft rule; retraction removes the effect. Gifts never inherit the shopper's general preferences.

**Category profiles.** Each category has its own sizes, hard requirements and soft preferences. Floral shirts imply nothing about shoes. Sizes are string labels keyed by brand + category + sizing system. No universal size conversion, body-measurement inference or cross-brand equivalence exists.

**Purchase intents.** Multiple named intents carry recipient, category, overrides, deadline, status and evidence. Self intents inherit only their category profile; gifts carry their own explicit requirements and sizes. Intent rules replace same-field category rules; explicit removal lists relax only those category rules. General exclusions remain unless explicitly excluded by ID. Temporary changes and gifts never mutate enduring category profiles.

## Shipped categories and attributes

| Category key | Explicit sizing systems | Category-specific fields |
|---|---|---|
| `shoes` | EU, US_MEN | width, comfort |
| `shirts` | ALPHA, US_COLLAR_IN | clothing size labels |
| `pants` | W_IN_L_IN, EU | waist/inseam strings, e.g. `32x30` |
| `outerwear` | ALPHA, EU | clothing size labels |
| `hats` | CM, ALPHA | circumference/alpha labels |

All shipped products have category, brand, style, color, material, fit, occasion/intended use, department (`mens/womens/unisex`), price, delivery timestamp, size and sizing system; shoes additionally have width and comfort. IDs are fresh. Department is a product attribute used only when explicitly requested, never inferred from a person's gender. Cross-category candidates are deliberately included when two or more categories are selected. With one selected category, cross-category distractors are unavailable and omitted.

## JSON expressiveness and extension

Add a key under `categories`, define attributes with finite domains, declare zero or more sizing systems, list applicable preference topics, and supply profile/intent rule samplers. Add it to `generation.selected_categories` or use `--categories`. No Python category switch or category-specific renderer is required.

Supported attribute types: nonempty string enums, finite-domain integers, finite-domain numbers. Generic unary operators: `eq`, `ne`, `in`, `not_in`, `lte`, `gte`. Numeric bounds can fall between domain values. All soft rules score one point each when matched; multiple explicit soft rules can concern the same field. No arbitrary code, unrestricted expressions, nonlinear utility, unit conversion or relations between product fields are evaluated. Sizes are exact configured string domains scoped by brand/category/system; an empty system map means the category is unsized. General fact values can be JSON literals/objects/lists from declared domains. The only derived fact operator is `age_years` from an explicitly disclosed birth date.

The category-only fixture `tests/fixtures/shopping_backpacks.json` adds capacity in liters and waterproofness, with no size system. Tests load this JSON, select backpacks plus shirts, generate episodes, check cross-category candidates and constraints, and run offline replay **without editing the engine**.

Category profile/intent sampling templates and event rates are excluded from model prompts. Prompts contain public field domains, size systems, supported operators and relevance mappings; they never contain sampled hidden state or future events.

## Stochastic sessions and time

Each seeded trajectory samples event mixtures, selected categories, values, time gaps and ordering. It is not a fixed ten-step storyline. JSON controls event weights/counts, initial disclosures/intents, maximum retained intent count, deadlines, gift probability, catalogs and question counts. Supported event families: reveal/update/correct a fact, like/dislike/retract a preference, category update, create/complete/cancel/reopen/mark-uncertain an intent, temporary override/restore, and irrelevant observations. Event preconditions prevent closing a nonexistent or already inactive intent; reopening is explicit. Stable facts use explicit correction events; age is never independently randomized.

Timestamps are canonical UTC. General facts and preference histories use **[valid_from, valid_until)**. At a change boundary the newer statement applies; if multiple statements share the session timestamp, the last statement wins and an earlier interval may be empty. Past-time questions use retained disclosed histories. Age follows birthday at the asked date, including explicit birthday corrections valid from the correction time.

An active intent remains actionable through its deadline and expires strictly after it. Open/future intents persist despite elapsed days; completed, cancelled and uncertain plans are inactive. There is no blanket TTL. Tests cover tomorrow's deadline five days later, a future trip still active after ten days, exact deadline boundaries, reopening and open-ended persistence. Default stories use explicit deadlines; common-sense inference of an unstated lunch deadline is not implemented.

## Questions and mechanical scoring

Every session samples current/historical general-fact questions, scoped preference questions and recommendation/intent-status questions. Questions are drawn only from revealed state. Answer support IDs must belong to the observed prefix. Unrevealed initial values cannot silently become requirements or answer keys.

Recommendations first enforce category, hard rules, known size and timely delivery. Among verified feasible items, maximize matched soft rules. Any tied best item is accepted. `NONE` is correct for inactive intents or no suitable product. `ASK_SIZE` is correct only when no verified feasible item exists but some candidate passes non-size requirements and its brand/category/system size is unknown. A known feasible option takes precedence over asking about unverified alternatives. Unknown size is different from a known wrong size.

Catalog construction samples finite domains and can construct ranked, tied, no-suitable and unknown-size cases. If a requested construction is impossible for a custom schema, the actual feasible set determines the oracle; no label is forced. Catalogs include no hidden target/rejection labels. Synthetic distribution shortcuts remain possible and this is not a realistic retailer simulator.

Metrics separate fact/preference/recommendation accuracy, choice/status accuracy, hard-constraint violations, missed feasible choices, suboptimal feasible selections, preference regret and sizing decisions. Reports split by category and decision type. Note diagnostics separately compare disclosed histories, category facts and intent status/deadline/scope; exact structured matching is narrower than judging semantically equivalent prose. No reward is fed back to either model and no RL optimizer is implemented.

## Paired execution and notes

Both Luna calls receive exactly the same current evidence and questions/catalogs; only the memory arm also receives **prior-session notes**. Calls are independent, including session one. Both answers are scored before Qwen updates. Qwen receives only current timestamped evidence and notes through tools—not questions, catalogs, Luna outputs, truth, rewards or future observations. Notes reset between users; only explicit notes cross sessions. Traces persist them to disk; automatic process-resume is not implemented.

Notes have four kinds: general fact histories, scoped preference histories, category profiles and intents. Strict textual JSON tools are `read_notes`, complete-note `put_note`, `delete_note`, `no_op`; these are local dispatcher calls, not native API tool calls. Reads must precede writes. Invalid edits are transactional. Inactive intent history may remain stored. Limits are JSON-configured (currently 64 notes, 6,500 serialized words, 65,000 characters, 20 rounds/session). Edits acknowledge only the changed name, avoiding repeated full-memory echoes.

Frozen Qwen3-1.7B uses the existing bfloat16 loader, no thinking, greedy decoding and a 384-token output cap. A context-budget guard stops oversized calls. Luna uses low reasoning, 1,536 output tokens, no retries, `store=False`. Invalid/incomplete generations remain failures in denominators. Whether Qwen can reliably produce this richer history schema within those limits is **not live-tested**.

## Validation and remaining limits

The 10×10 local mock contains **579 paired questions**: 200 facts, 100 preferences and 279 recommendations, using 200 independent answer calls and 100 note updates. It includes every shipped category. Recommendation outcomes: 205 inactive, 20 missing-size clarification, 15 no suitable item, 20 uniquely ranked choices, 19 ties. This sample is heavily weighted toward inactive intents; do not report its aggregate as a balanced recommendation benchmark. Rates can be adjusted in JSON; this validation does not optimize them.

Offline replay regenerates episodes, verifies source hashes and exact prompt boundaries, checks support chronology, replays note tools and recomputes scores/diagnostics. Tests cover a JSON-only category extension, category selection, stochastic seed reproducibility, cross-category distractors, scoping, provenance, hard/soft rules, temporal boundaries, hidden-data isolation, user resets and corruption detection. See `validation.json` for final counts.

Still limited: finite value domains and templated user statements, no assistant-dialogue simulation, no unrestricted natural-language parsing, no unseen-template generalization claim, no real inventory/returns/payment execution, no inferred-expiry benchmark, no live model-quality/cost/runtime evidence. Split names change seeded trajectories but reuse the same schemas/event families; that is not a held-out-template evaluation.

## Prepared live command — not executed

After staging the new project-owned files into the existing Coder checkout, from its repository root:

```bash
/home/criteo/verl-venv/bin/python experiments/experiment0.1/reproduce.py \
  --real-run \
  --model-path /home/criteo/qwen17b-work/model \
  --credentials /home/criteo/reco-rl/app/backend/.env \
  --output runs/experiment01-schema-v3-live
```

This explicitly enables paid Luna calls/GPU inference. It verifies local Qwen files against the pinned manifest. It has not been run or staged remotely. API cost estimates use repository rates and exclude hardware cost. A live compatibility/smoke check remains necessary before interpreting any result.
