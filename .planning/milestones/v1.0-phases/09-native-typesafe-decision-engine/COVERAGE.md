# API Coverage — TypeSafe Native System One

> Full coverage by default. Opt-outs are explicit, reasoned decisions.
> Phase 09 adds a third decision engine: Jev via TypeSafe's native API
> alongside the Phase 8 OpenRouter and Ollama engines (MODEL-04).
> The plan-time detector ran over the phase scope (`detected:true`);
> this matrix is written at plan time so the seal-time gate finds a
> decided surface. Produced via the generic-agent workaround; labeled
> accordingly.

| capability | decision | reason |
|---|---|---|
| Native: decision call (`POST /v1/systemone` with model/state/questions) | INTEGRATE | |
| Native: `Authorization: Bearer` via `TYPESAFE_API_KEY` read from env at call time | INTEGRATE | |
| Native: serving snapshot (`model` field) logged per answer | INTEGRATE | |
| Native: spend computed code-side (input tokens × published $0.042/1M input-only rate) | INTEGRATE | |
| Native: shared retry classes (4xx holds, 429/529/5xx/timeout retries once) | INTEGRATE | |
| Native: validate live-ping (cheap decision call catching bad keys and wrong model strings) | INTEGRATE | |
| Native: `GET /v1/models` catalog fetch in setup | OPT-OUT | lists aliases only and needs a key — D-05 pinned list is strictly better |
| Native: retry on 4xx | OPT-OUT | wrong key/model/body — hold instead per D-08 |
| Native: moving preview alias in the setup list | OPT-OUT | drifting target — pin plus latest alias only |
| Native: `keep_alive` request field | OPT-OUT | Ollama-only; native docs show no extra fields |
| Native: multimodal inputs | OPT-OUT | routing state is text-only (ask/directives/side) |
| Native: TypeSafe SDK dependency | OPT-OUT | SDK wraps the same single POST — stdlib urllib only |
