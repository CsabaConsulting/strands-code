# API Coverage — OpenRouter Decisions + Ollama System One

> Full coverage by default. Opt-outs are explicit, reasoned decisions.
> Phase 08 integrates two external Decision-API engines (per D-06). The plan-time
> detector ran over an empty plan set (`detected:false`); this matrix is written
> proactively so the seal-time gate finds a decided surface.

| capability | decision | reason |
|---|---|---|
| OpenRouter: submit decisions request (`POST /api/alpha/decisions`) | INTEGRATE | |
| OpenRouter: models catalog filtered to decisions output modality | INTEGRATE | |
| OpenRouter: response `model` snapshot logging per answer | INTEGRATE | |
| OpenRouter: `usage.cost` spend passthrough to `/cost` | INTEGRATE | |
| OpenRouter: `session_id` grouping | OPT-OUT | pure observability; omit unless session UUID reachable at hook |
| OpenRouter: `trace` / `user` / `provider` fields | OPT-OUT | observability extras, not needed |
| OpenRouter: chat completions as a decision engine | OPT-OUT | rejected by D-06 — chat JSON is not a decision engine |
| OpenRouter: streaming | OPT-OUT | unsupported by the Decisions API |
| OpenRouter: retry on 4xx | OPT-OUT | wrong request/key/model — hold instead per D-08 |
| Ollama: decide via `POST /v1/systemone` | INTEGRATE | |
| Ollama: `keep_alive` on decision requests | INTEGRATE | |
| Ollama: `/api/version` preflight (>= 0.35 floor) | INTEGRATE | |
| Ollama: `/api/tags` pull-presence check | INTEGRATE | |
| Ollama: `/api/chat` for decision models | OPT-OUT | filler-token runaway observed — forbidden |
| Ollama: images / multimodal inputs | OPT-OUT | unused for text routing |
| Ollama: generation controls | OPT-OUT | unsupported by the System One API |
