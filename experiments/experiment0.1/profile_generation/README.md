# Coherent initial user profile contract

`user_profile.schema.json` defines version1.1 (JSON Schema Draft2020-12); `clothing_categories.json` defines extensible category attributes and sizing-system identifiers. The bundled Python validator implements the keywords used by this schema plus cross-field/domain constraints; it is not a general JSON Schema engine.

`conditional_profile_prompt.md` receives the schema, category definitions and fixed constraints and asks the external LLM for one coherent profile. Clothing subprofiles are part of that initial call. `example_profile.json` is a hand-authored illustrative example, not a live result. Actual Luna-generated profiles and raw attempts are under experiment0.2/dataset_v1.

Fixed constraints support nested partial objects through `fixed_values` and exact RFC6901 paths through `fixed_paths`. Arrays supplied as values are fixed in full, including order. A path into an array fixes that element or leaf. Explicit null and empty lists are preserved exactly. Unknown paths, incompatible overlaps, invalid types and impossible age/birth-date constraints are rejected. Unspecified fields are generated, not inferred by the evaluator.

General facts, general preference stances, clothing defaults, brand/system-specific sizes, scoped subtype/season/occasion overrides, and purchase intents/budgets are separate. Preference attributes accept lists (empty or multiple values) or null. Null means explicitly unknown; an empty list means no stated preference; an omitted scoped attribute inherits the category default. Unrevealed facts are represented in the hidden initial profile but excluded from observations until revealed.

Matching scoped overrides apply from least to most specific; later entries break ties. A default size does not imply a brand-specific size or permit conversions. Intent state and deadlines are explicit; gift intents can opt out of the user's general preferences. Preference stance/effect consistency, unique identifiers/categories/sizes, units, dates and hard-rule contradictions are validated.

No live API is needed to validate an example or render the generation prompt. `src/prompt_policy_llm/profile_contract.py` provides the local CLI and reusable validator. Invalid live output is retained and repaired with explicit errors; constraints are not relaxed silently.
