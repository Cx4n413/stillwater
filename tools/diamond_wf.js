export const meta = {
  name: 'chess-diamond-hunt',
  description: 'Massive divergent ideation across 14 lenses for a revolutionary chess-network idea, then hunt the pool for the diamond and verify it',
  phases: [
    { title: 'Diverge', detail: '14 lenses each flood ideas' },
    { title: 'Hunt', detail: 'judges sweep the full pool for diamonds' },
    { title: 'Shortlist', detail: 'dedupe nominations to the top candidates' },
    { title: 'Verify', detail: 'pressure-test each diamond' },
  ],
}

const PRE = [
  "You are an idea-generation agent on a mission to find a REVOLUTIONARY idea for the best possible chess-playing intelligence -- emphasis on the NETWORK/EVALUATOR, the true strength ceiling.",
  "CONTEXT: STILLWATER is a no-tree belief-lattice engine (~3432 CCRL) using a BORROWED Lc0 BT4 transformer (WDL+policy+moves-left) as evaluator. Measured on this hardware: lc0 on the SAME net plays ~3596 (near Stockfish ~3627). So our search under-extracts AND BT4 itself is the objective ceiling -- a better NETWORK is the only path to large gains. Known-dead here: faster search ~= 0 Elo (eval-bound); value-recalibration DETUNES the search; swapping search readouts is 5-for-5 negative in play; the local corpus is 3-4 orders too small to train a net from scratch. Public resources that DO exist: billions of human games (Lichess, much Stockfish-annotated), engine-game databases, perfect 3-7man Syzygy tablebases. Substrate STILLWATER uniquely has: distribution-native (W,D,L) beliefs, machine-checked PROOFS as variance-0 anchors, a persistent transposition DAG, and capacity for memory/generalization across a career.",
  "THE MANDATE: GENERATE MANY IDEAS -- wildly, from first principles -- for a categorically stronger chess intelligence. Do NOT pre-filter for feasibility; MOST ideas SHOULD be strange/abstract/probably-stupid -- that is wanted. We mine a flood for ONE diamond: a stupidly-large revolution (the magnitude of nets+MCTS over alpha-beta, or AlphaZero over everything). AVOID only verbatim restatements of standard AlphaZero/lc0/NNUE practice -- push past the known or deepen it into something new.",
  "Already-surfaced strong directions (go BEYOND or deepen, do NOT merely repeat): retrieval-augmented eval (embeddings + billion-position memory + kNN-condition); a searchless GM-transformer distilled from Stockfish that WE own and co-tune; learning the lattice BACKUP operator with a GNN; test-time training / never-frozen weights.",
  "For EACH idea give: name; one_line; mechanism (concrete: name the data/architecture/training/inference path); why_huge (the ceiling -- what it unlocks that nothing else does); novelty (why NOT standard practice); wildness 1-5 (an integer). Generate EXACTLY 8 ideas -- no more. Keep every field CONCISE: mechanism and why_huge are 1-3 sentences each, NOT essays (brevity is REQUIRED to keep output short and avoid overlong responses). Prioritize genuine novelty over volume.",
].join("\n\n")

phase('Diverge')

const IDEA_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['lens', 'ideas'],
  properties: {
    lens: { type: 'string' },
    ideas: { type: 'array', items: {
      type: 'object', additionalProperties: false,
      required: ['name', 'one_line', 'mechanism', 'why_huge', 'novelty', 'wildness'],
      properties: {
        name: { type: 'string' }, one_line: { type: 'string' },
        mechanism: { type: 'string' }, why_huge: { type: 'string' },
        novelty: { type: 'string' }, wildness: { type: 'number' },
      },
    } },
  },
}

const LENSES = [
  { key: 'data-scale', p: "LENS = DATA & SCALE. Reason from data that exists at massive scale: billions of human games (much Stockfish-eval-annotated), engine-game databases, perfect 3-7man Syzygy tablebases (INFINITE ground-truth labels). What intelligences become possible that BT4 self-play never captured? Distilling SF eval at billion-position scale into a net we own; perfect-endgame nets that internalize TB truth and EXTRAPOLATE it; learning from human blunder-distributions; mixing perfect(TB)+strong(SF)+human(style) supervision; a data-engine that GENERATES the positions a net is currently worst at. What single underused dataset unlocks the most?" },
  { key: 'architecture', p: "LENS = ARCHITECTURE. Beyond the BT4 transformer: graph neural nets over the piece attack/defense graph; NNUE-incremental fused with deep nets; mixture-of-experts routed by phase/structure/material; RECURRENT or LOOPED nets that think with adaptive computation (more compute on hard positions); differentiable-memory nets; state-space models; nets whose topology mirrors the board or the lattice. Which architecture has a fundamentally higher ceiling or a property (calibration, memory, adaptive depth, interpretability) BT4 lacks?" },
  { key: 'retrieval', p: "LENS = RETRIEVAL & EXTERNAL MEMORY (push hard, may be the diamond). Non-parametric chess: learn a position EMBEDDING, index a massive database (all games + all TB truth), at inference RETRIEVE similar positions and condition the eval on their known outcomes/continuations. Variants: kNN-eval; retrieve PLANS not just values; retrieve the right tablebase-analog for a middlegame; a learned similarity metric where near=same-correct-idea; hierarchical retrieval (structure->plan->move); retrieval to FIX BT4 errors. Why does this sidestep the corpus wall and give recall/generalization lc0+SF structurally cannot have?" },
  { key: 'objective', p: "LENS = TRAINING OBJECTIVE & LOSS. Non-standard learning signals: predict the DEEP settled verdict from the SHALLOW position (lookahead distillation = free depth); predict the SEARCH's own output so the net becomes the search; contrastive/self-supervised chess representations (no labels); curriculum/active-learning trained hardest where the net is most wrong; adversarial position mining; train a net to be CONSUMED by MAX-backup (calibrated to the lattice); multi-task heads (threats/plans/refutations/opponent-move). Which objective yields a categorically better eval, not just lower MAE?" },
  { key: 'codesign', p: "LENS = SEARCH-NETWORK CO-DESIGN. Net+lattice as ONE end-to-end system: a GNN that LEARNS the backup/relaxation operator (a learned near-sound search that out-extracts hand-crafted MAX); learn the broker/selection; make the dirty-queue relaxation differentiable and backprop through it; the net EMITS search control (where to look, when to stop, effort-conditioned trajectory head); AlphaZero co-evolution where the expert is STILLWATER's own lattice. Why would co-design break the per-eval gap to lc0 that bolt-ons never did?" },
  { key: 'test-time', p: "LENS = TEST-TIME ADAPTATION (never-frozen weights). Eval LEARNS during the game and across the career: fast-weights / test-time training; in-context adaptation; Palimpsest as true gradient descent at inference; per-opponent online fine-tuning; a net that updates from the current game's refutations in real time; meta-learned init that adapts in K positions. What can a never-frozen network do that a static net (lc0/SF) fundamentally cannot, and could it compound into a large edge?" },
  { key: 'searchless', p: "LENS = SEARCHLESS / DISTILLATION. DeepMind 2024 distilled Stockfish into a ~270M transformer reaching ~2895 Lichess with ZERO search. Push it: the STRONGEST instant policy/value net we could distill from public SF-annotated billion-position data, one we OWN and co-tune for the lattice (unlike borrowed BT4). Then lattice+proofs sit on top of strong instant intuition. Variants: distill an ENSEMBLE of teachers; distill SF's SEARCH TREE not just root eval; distill into tiny+fast so throughput stops mattering; a two-system design (fast net intuition + slow lattice calculation). Could an owned co-tuned distilled net + our lattice exceed lc0+BT4?" },
  { key: 'neurosymbolic', p: "LENS = NEURO-SYMBOLIC & LLM. Inject knowledge self-play nets lack. An LLM has read ALL chess literature (plans, prophylaxis, theory, annotated games, endgame principles). LLM proposes PLANS/candidate moves, lattice verifies/calculates (neuro-symbolic division of labor); learn SYMBOLIC eval terms via program synthesis / symbolic regression (interpretable, rediscover or exceed human principles); proof-guided learning (predict what STILLWATER can PROVE); a concept-bottleneck net whose features are nameable chess ideas. Could symbolic/linguistic knowledge be the orthogonal channel that breaks the eval ceiling?" },
  { key: 'lattice-unique', p: "LENS = WHAT STILLWATER UNIQUELY ENABLES. Amplify substrate superpowers lc0/SF cannot replicate: distribution-native (W,D,L) beliefs (a net that outputs and reasons over full distributions/higher moments); PROOFS as variance-0 training anchors and teacher signal; the persistent transposition DAG as a learned substrate; generalizing career memory. Design networks that READ, WRITE, or LEARN-FROM the lattice/proofs. What revolution is ONLY possible because of the belief-lattice paradigm?" },
  { key: 'cognitive', p: "LENS = COGNITIVE / GRANDMASTER MODELING. Decompose how the strongest HUMAN minds play -- chunked pattern recognition, schema retrieval, prophylaxis, candidate-move intuition + highly selective deep calculation, planning, feel -- and architect around that decomposition rather than uniform brute eval. A net that proposes a small candidate set + a plan + which lines to calculate deeply; explicit prophylaxis (model and prevent the opponent's plan); schema/chunk libraries; human-like effort allocation. Could a cognitively-structured intelligence leap past statistical eval?" },
  { key: 'first-principles', p: "LENS = INFORMATION-THEORETIC / FIRST PRINCIPLES. Attack eval at its mathematical root. What is the minimal sufficient statistic of a position for perfect play? Where exactly is the SLACK between BT4 and perfect play (a specific structure -- find it)? Value as the solution to a learned fixed-point/Bellman equation solved at inference; exploiting chess symmetries/invariances far harder than current nets; a potential function whose gradient IS the best move; compression-as-intelligence (best compressor of chess games = best player); eval decomposed into provably-separable components. Is there a mathematically-principled construction that is categorically better?" },
  { key: 'cross-domain', p: "LENS = CROSS-DOMAIN TRANSFER. Import breakthroughs from OTHER AI fields NOT applied to chess engines. For each: technique, concrete chess instantiation, why revolutionary. Consider and go beyond: diffusion models (diffuse over move/plan space); MuZero learned latent DYNAMICS (plan in an abstract space where transpositions/plans are natural); neural theorem proving / AlphaProof / AlphaGeometry hybrids (chess as proving); RLHF/preference learning; foundation-model scaling laws + emergent abilities; program synthesis; world models; in-context RL; extreme-scale sparse MoE. Which transplant is a chess revolution waiting to happen?" },
  { key: 'absurd', p: "LENS = DELIBERATELY ABSURD / LATERAL (the user EXPLICITLY wants this quadrant). Generate ideas that sound stupid, impossible, or insane on purpose -- the diamond may be disguised as absurd. No idea too strange: bizarre substrates, inverted objectives, self-referential training, exploiting weird game properties, intelligences that do not look like an engine at all, ideas that violate current assumptions about what a chess AI must be. Be genuinely weird and uninhibited. For any that are not pure nonsense, note the grain of a real mechanism hiding inside." },
  { key: 'blindspots', p: "LENS = THE EVALUATOR'S BLIND SPOTS. Attack BT4's SPECIFIC measured weaknesses with a net designed to lack them: the conversion/saturation failure (won positions read flat -> no gradient to mate); the non-monotonic value S-wave (under-values clearly-winning, over-values slight edges); middlegame DRIFT (good moves devalued by deeper search = a bad fixed point); and that BT4 was trained to be read by VISIT-MEAN MCTS, not MAX-backup. Nets that are calibrated/evidential, output gradients in won positions, trained on the exact failure positions, decorrelated ensembles, uncertainty-aware. Could fixing the blind spots alone be large?" },
]

const diverged = await parallel(LENSES.map(L => () =>
  agent(PRE + "\n\n=== " + L.p + " ===\nReturn your idea list as structured output.",
    { label: 'diverge:' + L.key, phase: 'Diverge', schema: IDEA_SCHEMA })
))

const pool = diverged.filter(Boolean).flatMap(d => (d.ideas || []).map(i => ({ ...i, lens: d.lens })))
log('Generated ' + pool.length + ' raw ideas across ' + diverged.filter(Boolean).length + ' lenses')

const digest = pool.map((i, n) =>
  '#' + (n + 1) + ' [' + i.lens + '] ' + i.name + ' (wild:' + i.wildness + ') -- ' + i.one_line +
  '\n   MECH: ' + i.mechanism + '\n   HUGE: ' + i.why_huge
).join('\n')

phase('Hunt')

const NOM_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['diamonds'],
  properties: {
    diamonds: { type: 'array', items: {
      type: 'object', additionalProperties: false,
      required: ['name', 'why_diamond', 'steelman', 'ceiling', 'key_uncertainty'],
      properties: {
        name: { type: 'string' }, why_diamond: { type: 'string' },
        steelman: { type: 'string' }, ceiling: { type: 'string' }, key_uncertainty: { type: 'string' },
      },
    } },
  },
}

const HUNT_ANGLES = [
  { key: 'max-ceiling', p: "Nominate the 3-5 ideas with the BIGGEST possible ceiling -- ones that IF they worked would be a stupidly-large revolution -- IGNORING feasibility. Steelman each hard." },
  { key: 'real-mechanism', p: "Nominate the 3-5 ideas that are BOTH genuinely revolutionary AND have the most plausible REAL buildable mechanism (not hand-waving). The intersection of bold-and-real." },
  { key: 'uniquely-stillwater', p: "Nominate the 3-5 ideas that exploit something STILLWATER's belief-lattice can do that lc0/Stockfish STRUCTURALLY cannot -- where our weird substrate is the unfair advantage. These could SURPASS, not just match." },
  { key: 'ahead-of-time', p: "You are a hunter from 2032 looking back. Nominate the 3-5 ideas that are ahead of their time -- a future chess intelligence is obviously built on them but they sound premature today. What is the pool sleeping on?" },
  { key: 'combinations', p: "You believe the diamond is a COMBINATION. Nominate the 3-5 best PAIRS/TRIOS that together form something far larger than either alone. Describe each fused system as a single diamond." },
]

const nominations = await parallel(HUNT_ANGLES.map(H => () =>
  agent(PRE + "\n\n=== YOUR ROLE AS DIAMOND HUNTER ===\n" + H.p + "\n\n=== THE FULL IDEA POOL (" + pool.length + " ideas) ===\n" + digest,
    { label: 'hunt:' + H.key, phase: 'Hunt', schema: NOM_SCHEMA })
))

const CRIT_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['gaps'],
  properties: { gaps: { type: 'array', items: {
    type: 'object', additionalProperties: false,
    required: ['missing_angle', 'proposed_idea', 'why_it_matters'],
    properties: { missing_angle: { type: 'string' }, proposed_idea: { type: 'string' }, why_it_matters: { type: 'string' } },
  } } },
}

const critic = await agent(PRE + "\n\n=== YOUR ROLE: COMPLETENESS CRITIC ===\nFind what is MISSING -- angles of attack on the best possible chess network that NO idea in the pool covers, or that are under-explored. Name gaps concretely; for each, propose the missing idea. The diamond may be in the gap.\n\n=== THE FULL POOL ===\n" + digest,
  { label: 'hunt:completeness', phase: 'Hunt', schema: CRIT_SCHEMA })

phase('Shortlist')

const allNoms = nominations.filter(Boolean).flatMap(n => n.diamonds || [])
const critGaps = (critic && critic.gaps) || []
const nomDigest = allNoms.map((d, n) => 'NOM#' + (n + 1) + ' ' + d.name + ': ' + d.why_diamond + ' | steelman: ' + d.steelman + ' | ceiling: ' + d.ceiling + ' | risk: ' + d.key_uncertainty).join('\n')
const gapDigest = critGaps.map((g, n) => 'GAP#' + (n + 1) + ' ' + g.missing_angle + ': ' + g.proposed_idea + ' (' + g.why_it_matters + ')').join('\n')

const SHORT_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['shortlist'],
  properties: {
    shortlist: { type: 'array', items: {
      type: 'object', additionalProperties: false,
      required: ['name', 'consolidated', 'why_top', 'support'],
      properties: {
        name: { type: 'string' }, consolidated: { type: 'string' },
        why_top: { type: 'string' }, support: { type: 'string' },
      },
    } },
  },
}

const shortlist = await agent(PRE + "\n\n=== YOUR ROLE: SHORTLIST SYNTHESIZER ===\nMultiple hunters nominated ideas from a large pool, and a critic named gaps. DEDUPE and MERGE the nominations (many are the same idea in different words), fold in any gap that is genuinely diamond-grade, and produce a ranked SHORTLIST of the 6 STRONGEST diamond candidates most worth deep verification. For each write a consolidated description capturing the best version (merge the strongest framings). Rank by revolution-potential, breaking ties toward 'STILLWATER can do this and lc0 cannot'.\n\n=== HUNTER NOMINATIONS (" + allNoms.length + ") ===\n" + nomDigest + "\n\n=== COMPLETENESS-CRITIC GAPS ===\n" + gapDigest,
  { label: 'shortlist', phase: 'Shortlist', schema: SHORT_SCHEMA })

phase('Verify')

const VERIFY_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['name', 'is_real_diamond', 'magnitude', 'buildable_path', 'hardest_blocker', 'local_feasibility', 'honest_odds', 'verdict'],
  properties: {
    name: { type: 'string' },
    is_real_diamond: { type: 'boolean' },
    magnitude: { type: 'string', enum: ['incremental', 'large', 'stupidly-large'] },
    buildable_path: { type: 'string' },
    hardest_blocker: { type: 'string' },
    local_feasibility: { type: 'string' },
    honest_odds: { type: 'string' },
    verdict: { type: 'string', enum: ['pursue-now', 'prototype-cheaply', 'park-needs-more', 'fools-gold'] },
  },
}

const sl = ((shortlist && shortlist.shortlist) || []).slice(0, 6)
const verified = await parallel(sl.map(d => () =>
  agent(PRE + "\n\n=== YOUR ROLE: DIAMOND VERIFICATION (adversarial but fair) ===\nDeeply pressure-test this single candidate. Is it a REAL diamond (genuine, buildable, stupidly-large) or fool's gold? Be brutally honest about magnitude AND path. Separate crazy-idea-worth-chasing from crazy. Give the CHEAPEST experiment that would reveal whether the diamond is real, the hardest blocker, what is feasible on a single RTX 5070 + public data vs what needs cloud, and HONEST odds of a stupidly-large payoff. Do NOT reflexively kill bold ideas (the project's bias has been over-killing) but do NOT pass fantasy.\n\n=== THE CANDIDATE ===\nNAME: " + d.name + "\nCONSOLIDATED: " + d.consolidated + "\nWHY TOP: " + d.why_top,
    { label: 'verify:' + (d.name || 'cand').slice(0, 22), phase: 'Verify', schema: VERIFY_SCHEMA })
))

return {
  pool_size: pool.length,
  shortlist: sl,
  verified: verified.filter(Boolean),
  gaps: critGaps,
}
