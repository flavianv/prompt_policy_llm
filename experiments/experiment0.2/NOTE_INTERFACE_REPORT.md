# Bounded note-interface repair

The original ten-session run produced no accepted note calls (120/120 invalid). Its artifacts and scores remain unchanged. Two separate one-session note-only smokes used the same frozen verified Qwen3-1.7B checkpoint, first Maya session, greedy decoding, thinking disabled, a768-token completion cap and at most12 rounds. Neither smoke made any Luna calls or trained weights.

## Changes

The original prompt described an application JSON protocol `{tool, arguments}` in prose. The repair passes exact function schemas through Qwen's `apply_chat_template(..., tools=TOOLS)`, parses exactly one native `<tool_call>{name, arguments}</tool_call>`, records assistant tool calls and tool-role results, and returns specific validation errors. Tool names are never silently renamed. The mapping from the native `name` field to the existing dispatcher's `tool` field is explicit transport adaptation, with strict argument checks unchanged. Notes always come from Qwen output, never the hidden profile or answer key.

Version1 included an example write whose text was “Dated explicit facts with evidence IDs”. Qwen copied that placeholder exactly. All three read/write/finish calls were valid, but the note had no substantive user information. This was protocol success and content failure.

Version2 removed that write example and explicitly instructed Qwen to use actual facts, omit placeholders and save all explicit personal facts before finishing. It completed in5 rounds: valid read, two rejected calls, valid write, valid finish. The exact persisted note was:

```json
{
  "Maya Okafor": "For my own records, my preferred materials for pants in context summer: linen, cotton."
}
```

## Content assessment

The note preserves a supported scoped preference and the name as its key. It excludes café filler. It omits the unknown hat size, explicit empty accessories-pattern preference, accessories brands and both purchase intents with deadlines. It also omits the statement date/evidence ID. This demonstrates that the model can write a real fact through the repaired interface, but does not establish adequate coverage, historical recall, or multi-session reliability.

No replacement paired evaluation was run. Repair stopped after these two bounded smokes. The next comparison requires a stronger note-coverage criterion in addition to syntactic validity; the original40%/50% figures must not be attributed to useful memory.

Exact prompts, rendered chat templates, model outputs, errors, before/after notes and results are saved under `remote_artifacts/note_interface_smoke_v1/` and `remote_artifacts/note_interface_smoke_v2/`. `result.json` reports protocol validity only; this document supplies the substantive assessment.
