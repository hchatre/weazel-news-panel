# Phase 4 — AI workspace

Status: implemented and tested locally with the **mock** provider and with simulated HTTP transports. **It has never been run against a real Ollama, OpenAI-compatible or hosted model.** Not pushed.

## Principles (and where they are enforced)

| Principle | Enforcement |
|---|---|
| A model only suggests; a person decides | The provider interface is text in, text out: no tools, no database access. No endpoint applies AI output to an article, entry, verification state or workflow. Test: counts, versions and verification states are unchanged after runs |
| Never auto-publish or auto-verify | Same as above; "accepted" records a decision in `ai_runs` only, the person copies text themselves |
| Respects permissions | Needs `ai.use` (Journalist and above by default; configurable). The model sees only records the requester can already open, built through the same access helpers as the API. Confidential cases and unreadable articles answer 404/403 and nothing reaches the model |
| Least data | Never sent: source identities, source codes/descriptions, free-text source references, internal notes, evidence file contents, entries the person cannot see (restricted entries are sent only to people allowed to read them) |
| Grounded | Timeline entries are sent as `[E<id>] (verification label) …`. The model must cite `[E<id>]`. After the reply, citations that do not match an entry actually sent are removed and listed as "unsupported". Verification labels travel with each entry, and the system prompt forbids calling anything verified |
| Prompt injection | Case/article text is wrapped in `<data>…</data>` (a closing tag inside the data is stripped) and the system prompt says it is untrusted. This is a mitigation, not a guarantee: because the model has no tools and its output is only shown as text, a successful injection can at worst produce a misleading suggestion |
| Labelled | Every result carries "AI-generated suggestion. Not verified…" in the API and the UI |
| Auditable, private | Audit stores task, subject ids, provider and input size, never prompt or output text. The prompt is not stored (only its SHA-256 and size). Runs are visible only to their author, and only while they still have access to the subject |
| Cost / abuse | Daily per-user limit (`WEAZEL_AI_DAILY_LIMIT`, failed runs count), input cap (`WEAZEL_AI_MAX_INPUT_CHARS`, most recent entries kept) |
| Provider failures | The client gets a generic 502; details go only to the server log; the key never appears in errors |

## Tasks
* Article: headline ideas, proofread, summarise, translate (EN/FR), claims to verify (a checklist, never a verdict).
* Investigation: summarise timeline, open questions, suggest leads.

## Configuration (environment only)
| Variable | Default | Notes |
|---|---|---|
| `WEAZEL_AI_PROVIDER` | `none` | `none` (feature off, API answers 503 and the UI says so), `mock` (offline stub; refused in production), `ollama`, `openai_compat` |
| `WEAZEL_AI_BASE_URL`, `WEAZEL_AI_MODEL` | empty | required for ollama / openai_compat |
| `WEAZEL_AI_API_KEY` | empty | environment only; never stored, logged or returned |
| `WEAZEL_AI_ALLOW_EXTERNAL` | false | the API refuses to start if the model server is not on this computer unless this is true, because case data would leave the PC |
| `WEAZEL_AI_TIMEOUT_SECONDS`, `_MAX_INPUT_CHARS`, `_DAILY_LIMIT` | 60, 24000, 50 | |

Local example (Ollama on the same PC): `WEAZEL_AI_PROVIDER=ollama`, `WEAZEL_AI_BASE_URL=http://127.0.0.1:11434`, `WEAZEL_AI_MODEL=<a model you have pulled>`.

## Also fixed in this phase (found while building it)
* **Evidence upload bug:** attaching evidence to a timeline entry called a helper with the wrong arguments and would have crashed (500). Fixed; covered by a new test (entry visibility, other-case entries refused).
* **Seed upgrade gap:** adding a new permission key never reached existing roles. Now a new permission is granted once, to the default roles that define it, at the moment it first appears; an administrator's later removal is respected. Tested, and confirmed on the dev database (`ai.use` reached Journalist and above, not Intern).

## Tests
Backend: 107 passed (13 AI tests, plus the two fixes above). Deliberately broken checks were caught: (1) giving the model restricted entries, (2) skipping the subject access check. Browser smoke test passes with the AI panel (label shown, citations, accept records a decision, timeline unchanged).

## Not done / limits
* No real model was ever called. HTTP providers are tested against simulated servers only; request shape for real servers is unverified. Output quality, hallucination rate and French/Arabic quality are **not evaluated**.
* The citation check proves a cited id was in the data, not that the sentence is actually supported by it.
* Article tasks have no citations (the text is one block). No streaming, no chat history, no embeddings or search over the library, no per-record "AI disabled" switch, no AI over evidence files (only text records).
* No Arabic UI/outputs (output languages are EN/FR).
