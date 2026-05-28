# The Advanced AI Engineering Learning Rubric (v2)

## The strategic statement

Move from *building AI applications* to *engineering AI systems*. The difference
is measurement, reliability, specialization, and economic awareness. This is a
**capability roadmap, not a course syllabus** — each tier is defined by what
you can *do* after it that you couldn't before, and is closed by a concrete
skill check.

## The core truth

**Tier 1 (evaluation) is the spine.** Every later tier is only meaningful if
you can measure whether it made things better. Do the tiers in order; resist
parallel pursuit. Foundation knowledge (transformers, attention, embeddings,
inference internals) runs underneath all tiers — read papers and run small
experiments throughout, never as a separate phase.

## What is intentionally NOT in scope

- **Building a transformer from scratch.** Read about it, run small attention
  experiments to build intuition, but do not reimplement it. You are an
  engineer, not a researcher.
- **ML research methodology** (designing novel architectures, publishing).
- **Pure theory without a skill check.** Every tier here is provable in code.

Everything else is on the table.

---

# The Capability Map

| Tier | You can now… | Trap avoided | Skill check |
|---|---|---|---|
| **1. Evaluation & Observability** | Prove a change improved things — and explain *why*. Find specific failure modes (hallucination, miscalibration, judge blindness) instead of saying "it seems off." | Optimizing on vibes. Believing the demo because it looks good. | Take an agent you built. Score it. Change one thing. Show the score moved (or didn't) — and explain the cause. |
| **2. Agent Reliability** | Ship agents that don't behave randomly under real conditions. State machines, structured outputs, retries, tool contracts. | Demo-quality agents that collapse in production. | Show an agent that recovers gracefully from a tool failure instead of producing garbage. |
| **3. Retrieval & Context Engineering** | Feed the LLM the right context — usually *the* bottleneck. Hybrid search, reranking, chunking. | Reaching for bigger models when retrieval is the problem. | Hybrid + rerank beats vector-only on a held-out eval set, shown with numbers. |
| **4. Prompt Engineering as a Discipline** | Write prompts that are specific, robust, and *measurably* better. Align prompt to rubric to schema. | Trial-and-error prompt tweaking with no measurement loop. | Take a failing case from your eval, change the prompt, show the score climb, and explain why. |
| **5. Fine-Tuning & Specialization** | Take expensive frontier-model behavior and run it cheap/fast on a specialized small model. | Paying frontier prices for tasks a fine-tuned 7B nails. | Distill a workflow onto Llama/Qwen via QLoRA. Re-run your eval. Show it holds. |
| **6. Inference Infrastructure** | Reason about cost/latency/VRAM/concurrency. Deploy models yourself when it pays. | Treating "the API" as the only deployment path. Inability to estimate cost at scale. | Stand up vLLM with a quantized model. Benchmark tokens/sec at concurrency 1 vs 8. Explain the curve. |
| **7. Multi-Modal Capabilities** | Build systems that handle images, audio, scanned documents, or code with the same rigor as text. | Bolting modalities on without re-thinking the eval, pipeline, or failure modes. | Build a doc-QA system over scanned PDFs. Eval it. Defend the choice of OCR+text vs vision-QA. |
| **8. Safety & Adversarial Robustness** | Find how your system fails, defend against it, and monitor for it in production. | Shipping systems whose failure modes you've never explored adversarially. | Red-team your own agent. Find a prompt that breaks it. Fix it. Document the failure class. |
| **9. Distributed Systems** *(optional)* | Scale a *mature* system across nodes when that's the actual constraint. | Solving infra problems before you have a quality problem to solve. | Don't bother unless you have a real concurrency constraint. If you can't articulate why you need it, you don't. |

---

# Cross-cutting layers (apply at every tier)

These aren't tiers — they're capabilities that grow continuously as you go.

### Foundation knowledge (perpetual)
Enough intuition to predict why a system behaves the way it does. Read papers
and blogs continuously; run small experiments to confirm understanding. Topics
to chip away at, in rough order of leverage: transformer architecture,
attention mechanisms, embeddings & vector geometry, tokenization,
KV cache behavior, quantization theory, decoder sampling strategies, LoRA /
QLoRA mechanics, RLHF / DPO, mixture-of-experts, context window dynamics. You
are aiming for *engineering intuition*, not the ability to reimplement the
papers.

### Cost & economics (perpetual)
Every system you build needs a TCO model: tokens per request, cost per
request, latency budget, peak concurrency, infrastructure cost. If you can't
name your unit economics, you'll get blindsided at scale.

### Production observability (extends Tier 1 into production)
Tracing every real request, drift detection (input distribution, output
quality), user feedback capture, cost monitoring. Eval is a CI artifact;
observability is the production version of the same skill.

### Agent design patterns (extends Tier 2)
Planner/executor separation, hierarchies, swarms, validator nodes, the
review-and-revise loop, the gate-and-route loop. Architectural vocabulary for
reasoning about multi-step systems.

---

# Per-tier deep dives

---

## Tier 1 — Evaluation & Observability

### Capability gained
Prove a change improved things and explain *why*. Find specific failure modes
instead of waving at "it seems off." Build measurable systems where every
modification is testable.

### Trap avoided
Vibes-based optimization. Believing your prompt is good because the demo
looked good. Confusing the score going up with the system getting better
(measurement bugs are common; the score can lie).

### Core concepts
Golden datasets and case authoring. Binary, numeric, rubric, and structured
evaluators. LLM-as-judge — its strengths (recognition > generation), its
weaknesses (variance, scope blindness, rubric drift). Regression detection
across experiments. Measurement-bug diagnostics: distinguishing real quality
drops from scoring artifacts. Trace analysis (what node fired, in what order,
with what tool calls).

### Tools to know
- **DeepEval, Ragas** — pre-built metrics for common patterns (faithfulness,
  contextual precision, hallucination detection); useful when you have RAG.
- **Phoenix (Arize)** — observability-first, framework-agnostic; strong on
  RAG metrics and production monitoring.
- **LangSmith** — experiment tracking, dataset management, trace UI; the
  native fit for LangGraph systems.
- **Custom evaluator frameworks** — when domain-specific scoring matters.

### Skill check
Take an agent you've built. Score it across at least three evaluators (one
binary, one rubric judge, one structured). Change one thing. Re-run. Show
which scores moved, by how much, and explain the cause. Distinguish a real
improvement from variance, and a real failure from a measurement bug.

### When to start
**Now. Always. Never finished.** Every later tier needs this loop to be
honest.

---

## Tier 2 — Agent Reliability Engineering

### Capability gained
Ship agents that behave predictably under real conditions: structured outputs,
typed contracts, graceful recovery from tool failures, bounded loops, explicit
state machines.

### Trap avoided
Demo-quality agents that fall over under production traffic. Free-text outputs
that downstream code can't parse. Infinite ReAct loops. Silent tool failures
that produce confidently wrong answers.

### Core concepts
Structured output as a first-class contract (Pydantic / Instructor / JSON
Schema). State machines as the orchestration vocabulary (LangGraph: nodes,
reducers, conditional edges). Iteration caps and forced-exit patterns
(`MAX_LOGISTICS_ITERATIONS`-style). Synthetic tool-result patches when loops
are cut mid-flight (`_balance_dangling_tool_calls`-style). Failure
taxonomies. Retry / fallback policies. Verification passes (a separate node
that checks the prior node's output before continuing).

### Tools to know
- **LangGraph** — state-machine orchestration with typed state and reducers.
- **Pydantic, Instructor** — structured output enforcement.
- **JSON Schema** — provider-agnostic structured output contracts.
- **Guardrails** — output validators and re-asking patterns.

### Skill check
Build an agent with a ReAct loop, an iteration cap, a tool-failure recovery
path, and structured output. Force a tool to fail. Show the agent recovers
and still produces a valid structured response — not garbage, not a crash.

### When to start
In parallel with Tier 1. They reinforce each other: reliable agents are
testable, tested agents become more reliable.

---

## Tier 3 — Retrieval & Context Engineering

### Capability gained
Feed the LLM the right context at the right time. Diagnose retrieval failure
modes vs. generation failure modes. Tune the layer that is, in practice, the
real bottleneck for most production AI systems.

### Trap avoided
Reaching for a bigger model when the actual problem is that the retriever
fetched the wrong chunks. Treating embeddings as a one-knob solution when the
real win is hybrid retrieval and reranking.

### Core concepts
Hybrid search (semantic + keyword) and why pure-vector loses on
keyword-dependent queries. Reciprocal Rank Fusion. Cross-encoder reranking
(FlashRank, BGE rerankers). Chunking strategy (size, overlap, structural
boundaries). Embedding model selection and trade-offs. Context compression
when the retrieved set is too large. Retrieval evaluation: contextual
precision, contextual recall, faithfulness — and why these only become
meaningful once you have retrieval to evaluate.

### Tools to know
- **pgvector** — vector storage with Postgres ergonomics.
- **Postgres FTS / `tsvector`** — keyword half of hybrid search.
- **FlashRank, BGE rerankers** — cross-encoder reranking.
- **DSPy** — programmatic prompt optimization, including retrieval pipelines.

### Skill check
On a project with non-trivial unstructured text (journals, docs, transcripts):
build pure vector retrieval as baseline; add hybrid + rerank; show the
contextual-precision score climbs on a held-out evaluation set. Explain *which
queries* improved and why.

### When to start
When you have a project that actually needs retrieval. Don't learn it
abstractly. The `journal_agent` project is the natural vehicle if the wildfire
sim doesn't expose this need.

---

## Tier 4 — Prompt Engineering as a Discipline

### Capability gained
Write prompts that are specific, robust, and measurably effective. Align the
prompt, the schema it expects to produce, and the rubric used to grade it —
the three are one system.

### Trap avoided
Trial-and-error prompt tweaking with no measurement loop. Prompts that ask
for X but produce Y because schema fields silently route the output elsewhere
(the exact bug surfaced in this project's logistics eval). Prompt rot — small
changes accumulating into incoherent instructions.

### Core concepts
Few-shot vs. zero-shot trade-offs. Chain-of-thought and when it actually
helps. Self-consistency and majority voting. Schema-driven prompts (the schema
*is* the prompt). Rubric-prompt-schema alignment: every requirement in the
rubric must be producible by the prompt and capturable by the schema. Prompt
versioning. Self-critique / self-refine patterns and their bounded payoff
(recognition is easier than generation; the same model can grade what it
struggles to produce one-shot).

### Tools to know
- **DSPy** — programmatic prompt optimization; treat prompts as
  hyperparameters.
- **Custom template engines** (Jinja, with versioned templates per registry).
- **PromptLayer / LangSmith prompts** — versioning and diff tracking.

### Skill check
Take a failing case from your Tier-1 eval. Without changing the model or the
schema, change the prompt. Show the rubric score improves. Explain *which
prompt language* caused *which behavioral change*. Bonus: catch a case where
the prompt produced what was asked but the eval couldn't see it, and fix the
measurement instead of the prompt.

### When to start
Integrated with Tier 1 from day one. You can't improve prompts you can't
measure, and measurement teaches you what prompts actually do.

---

## Tier 5 — Fine-Tuning & Model Specialization

### Capability gained
Take expensive frontier-model behavior, distill it onto a small open model,
and serve it cheap, fast, and consistent. Curate training data from your own
production traces.

### Trap avoided
Paying frontier prices forever for tasks a well-trained 7B model handles fine.
Fine-tuning before you have eval coverage, so you can't tell if the fine-tune
got worse.

### Core concepts
Supervised fine-tuning (SFT). Low-Rank Adaptation (LoRA) and QLoRA (quantized
LoRA — fine-tune large models on small GPUs). Dataset curation: turning
production traces into clean training pairs. Chat templates per model family
(Llama 3, Qwen 2.5, Mistral — they differ in tokens and formatting).
Distillation (use a strong model to label data for the small one).
Overfitting detection. Eval-driven curation (only train on examples your eval
already says are good).

### Tools to know
- **Unsloth** — fast QLoRA training on consumer GPUs.
- **Axolotl** — config-driven training, broader feature set.
- **Hugging Face TRL / PEFT** — the underlying ecosystem.

### Skill check
Identify a workflow you currently run on a frontier model. Curate ~500–2,000
high-quality examples. Train a QLoRA adapter on Llama-3-8B or Qwen-2.5-7B.
Re-run your eval. Show the fine-tune holds within an acceptable delta of the
frontier model, at meaningfully lower cost and latency.

### When to start
After you have a real workload with cost/latency pressure *and* solid eval
coverage. Fine-tuning without eval is gambling.

---

## Tier 6 — Inference Infrastructure & Self-Hosting

### Capability gained
Reason about throughput, latency, VRAM, and concurrency. Stand up self-hosted
inference. Know what to quantize, what to batch, what to cache.

### Trap avoided
Treating "the API" as the only deployment path. Inability to estimate cost
at scale because you've never measured tokens/sec on your own hardware.
Overpaying for inference for workloads that fit on a single GPU.

### Core concepts
KV cache (why prompt caching matters, what it costs). Continuous batching
(why vLLM throughput beats naive batching). Quantization: FP16, INT8, INT4 —
the quality/memory trade-off. AWQ vs. GGUF vs. GPTQ formats and where each
fits. VRAM economics: model size + KV cache + activations vs. available
memory. Time-to-first-token vs. tokens-per-second — different SLOs.
Concurrent inference and the throughput curve.

### Tools to know
- **vLLM** — production-grade inference server with OpenAI-compatible API.
- **llama.cpp** — CPU and Apple Silicon inference; the GGUF ecosystem.
- **Ollama** — developer-friendly wrapper around llama.cpp.
- **AWQ, GGUF, GPTQ** — quantization formats; know which serves which need.

### Skill check
Stand up vLLM with a quantized open model. Benchmark tokens/sec at
concurrency 1, 4, and 8. Explain the throughput curve and where it saturates.
Bonus: compare AWQ vs. GGUF vs. FP16 on the same model and show the quality
delta on your eval.

### When to start
When you have a real cost or latency constraint, or a project that benefits
from running locally (offline, privacy, latency-critical).

---

## Tier 7 — Multi-Modal Capabilities

### Capability gained
Build systems that handle images, audio, scanned documents, or code with the
same engineering rigor you bring to text. Choose the right modality and the
right model for each problem.

### Trap avoided
Bolting modalities on without re-thinking the eval (image generation needs
different judges than text), the pipeline (OCR vs. vision-QA is a real
choice), or the failure modes (visual hallucination, audio transcription
errors).

### Core concepts
Vision models: CLIP-style retrieval vs. vision-language models (GPT-4V,
Claude vision, Gemini, Qwen-VL). Audio: ASR (Whisper) vs. TTS (ElevenLabs,
OpenAI). Document understanding: when to use vision models directly vs.
OCR-plus-text. Code models (DeepSeek Coder, Qwen Coder) and their place
beside general models. Modality-specific eval: BLEU/ROUGE for translation,
WER for ASR, multi-modal LLM-as-judge for image generation.

### Tools to know
- **OpenAI / Anthropic / Google vision APIs**.
- **Whisper** (open) and **ElevenLabs / OpenAI TTS** (hosted).
- **Open VLMs**: Qwen-VL, Llama-3.2-Vision, Pixtral.
- **Document parsers**: LayoutLMv3, Donut, Marker.

### Skill check
Build a doc-QA system over scanned PDFs. Implement two paths: OCR→text→LLM
and direct vision-QA. Evaluate both on a representative set. Defend the
choice for production based on what your eval showed.

### When to start
When a real problem needs it. Otherwise genuinely skippable — don't learn
multi-modal speculatively.

---

## Tier 8 — Safety & Adversarial Robustness

### Capability gained
Find how your system breaks, defend against it, and monitor for it in
production. Treat adversarial behavior as a first-class quality dimension,
not an afterthought.

### Trap avoided
Shipping user-facing systems whose failure modes you've never explored
adversarially. Treating safety as a content-moderation problem when the
real issue is prompt injection, tool abuse, or data exfiltration.

### Core concepts
Prompt injection (direct and indirect — instructions embedded in retrieved
data). Jailbreak resistance and the limits of prompt-based defenses. Tool
abuse (what happens when the LLM calls a tool with bad arguments). Output
filtering and content safety. PII detection. Red-teaming as a discipline:
systematic probing for failure classes. Hallucination as a *safety* concern
when the system grounds decisions, not just a quality concern.

### Tools to know
- **Garak** — automated LLM vulnerability scanner.
- **PyRIT** (Microsoft) — red-teaming framework.
- **Guardrails** and structured output schemas (already in your toolkit).
- Custom adversarial test suites integrated into your Tier-1 eval framework.

### Skill check
Take one of your own agents. Red-team it for ~30 minutes. Find at least one
prompt or tool-input that causes it to misbehave. Fix the failure. Add a
regression test that captures the failure class so it stays fixed.

### When to start
Before shipping anything user-facing, or anything that touches data you
wouldn't want exfiltrated. For learning, after Tier 2 (you need reliable
agents to meaningfully break them).

---

## Tier 9 — Distributed AI Systems *(optional, often last)*

### Capability gained
Scale a *mature* system across nodes when that's the actual constraint.

### Trap avoided
Solving infrastructure problems before you have a quality problem to solve.
Distributed systems do not fix hallucination, reasoning errors, or retrieval
quality — they scale whatever you already have.

### Core concepts
Multi-node orchestration, autoscaling, GPU scheduling, distributed inference
(model parallelism, tensor parallelism), event pipelines for asynchronous
workloads.

### Tools to know
- **Kubernetes** — orchestration.
- **Ray, Ray Serve** — distributed Python execution.
- **Kafka** — event streaming.
- **vLLM distributed**, **TGI** — distributed inference.

### Skill check
*Honest test:* if you can't articulate the specific concurrency, throughput,
or multi-GPU constraint that's forcing this on you, you don't need it yet.

### When to start
Last. Maybe never.

---

# Where you are now

Honest read on this project's state, so you can pick the next move without
the FOMO:

- **Tier 1 (Evaluation):** Deeper than most people who claim it. You built a
  custom eval framework with proper separation of dataset / task / evaluator
  / runner, surfaced multiple measurement bugs (phantom-zero scoring, judge
  blindness), and have used the eval loop to drive real prompt and
  architecture improvements. This stays the loop you live in.
- **Tier 2 (Agent Reliability):** Substantial. The wildfire system uses
  LangGraph state machines, structured outputs throughout, iteration caps,
  synthetic tool-call balancing, and tool injection for testability. You're
  already practicing this tier without having explicitly named it.
- **Tier 3 (Retrieval):** Not yet. The wildfire sim doesn't have retrieval
  — it queries structured DB data. The `journal_agent` project already has
  pgvector and cosine similarity; it's the natural vehicle for hybrid search,
  reranking, and RRF when you're ready.
- **Tier 4 (Prompt Engineering):** Substantial but not formalized. Today's
  session was exactly this work — schema/prompt/rubric alignment, the
  recognition-vs-generation gap, when to tighten the prompt vs. fix the
  measurement.
- **Tiers 5–9:** Future. Pick them up when a real project needs them, not
  before.
- **Foundation knowledge:** Continuous. Always ongoing. Never a separate
  phase.

# The honest closing

You will never be "done." The frontier moves. The compass is *capabilities
you can demonstrate*, not topics you've read about. Hold this rubric loosely
— let real problems pick the next tier, and let the skill checks tell you
when you've actually arrived versus when you've just read about something.

Courses teach the *surface* of tools. The work in front of you teaches what
the tools are for, where they break, and why the textbook explanation
oversimplifies. That difference is the whole game.
