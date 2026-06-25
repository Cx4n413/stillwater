//! The STILLWATER core: position-keyed belief lattice, prioritized
//! dirty-queue settling, and the best-first broker — a faithful port of
//! stillwater/{lattice,search}.py with every hard-won semantic intact:
//! proof certificates + 50-move envelopes, claim floors (threefold/50-move
//! are CLAIMS, not terminals), path-conditioning taint, the Mirror
//! (opponent-conditional values), the Lens (liveliness, rho-gated), and the
//! in-game palimpsest corrections.

use rustc_hash::{FxHashMap, FxHashSet};
use shakmaty::fen::Fen;
use shakmaty::uci::UciMove;
use shakmaty::{CastlingMode, CastlingSide, Chess, Color, Move, Position, Role,
               Square};
use shakmaty_syzygy::Tablebase;
use std::cmp::Ordering;
use std::collections::BinaryHeap;

use crate::encoder::{encode, EncodeJob, Frame};
use crate::keys::{position_key_c, position_key_cf, zobrist};
use crate::policy::PolicyMap;
use crate::prover::find_mate;
use std::sync::atomic::{AtomicU64, Ordering as AtomicOrdering};

pub const GAMMA: f64 = 0.997;
pub const SETTLE_EPS: f64 = 0.004;
pub const FPU_PENALTY: f64 = 0.10;
pub const C_PUCT: f64 = 1.7;
pub const C_VAR: f64 = 0.35;
pub const VLOSS: f64 = 0.85;
pub const MLH_W: f64 = 0.12;
pub const MLH_SCALE: f64 = 80.0;
pub const RHO_GATE: f64 = 0.90;
pub const LENS_W: f64 = 0.10;
pub const LENS_FLOOR: f64 = -0.05;

// ---- the Refine package: lc0-informed search refinements, bit-gated.
// Mask 0 reproduces the legacy engine exactly; UCI Refine=true sets all
// bits; STILLWATER_REFINE_MASK isolates single bits for attribution runs.
pub const R_TEMP: u32 = 1; //     policy softmax temperature 1.359
pub const R_CPUCT: u32 = 2; //    cpuct log-growth schedule
pub const R_FPU: u32 = 4; //      lc0 FPU: settled anchor, visited-mass decay
pub const R_MLH: u32 = 8; //      gated absolute MLH utility (not x1.12)
pub const R_LCB: u32 = 16; //     LCB argmax backup (winner's-curse fix)
pub const R_GAMMA: u32 = 32; //   no discount across zeroing edges
pub const R_UFLIGHT: u32 = 64; // in-flight in U denominator; Q stays honest
pub const R_TWOFOLD: u32 = 128; // twofold-in-tree draw pins
pub const R_NOFLOOR: u32 = 256; // backup aggregates EXPANDED children only:
                                // the q0 raw-eval floor (optimism precisely
                                // when a position deteriorates — the parity-
                                // match drift mode) competes only while a
                                // node has NO expanded child at all
                                // (0x200 is the python-side robust pick)
pub const R_MEANBACK: u32 = 1024; // value = evidence-weighted mean of
                                  // expanded children (lc0 backup), sticky
                                  // proof wins override; selection/proofs
                                  // still see per-child minimax values.
                                  // REJECTED on evidence: WAC 97->56 — the
                                  // mean dilutes forced lines in a lattice.
pub const R_COARSER50: u32 = 2048; // one r50 key bucket below clock 64:
                                   // lattice survives long maneuvering
                                   // instead of amnesia every 16 plies
pub const R_REPFORCE: u32 = 4096; // forcibility gate (rank-2 B, SAFE SUBSET):
                                  // de-force ONLY the WINNING side's twofold
                                  // pin / claim floor-DOWN (f<0) -- the
                                  // Ra8/route-away over-claim direction. The
                                  // LOSING/EQUAL side's floor-UP (f>=0,
                                  // perpetual-check saving draw) stays
                                  // UNCONDITIONAL: the is_check proxy is
                                  // evaluated at the post-move node, which is
                                  // the WRONG node for the saver, so the f>=0
                                  // gate is HELD until a cycle-aware check
                                  // detector exists. NO-OP at draw_contempt=0
                                  // (f==0). Default off = legacy.
pub const R_FINER50: u32 = 8192;  // keep real 16-ply r50 buckets even when
                                  // R_COARSER50 is set (do NOT collapse the
                                  // whole clk<64 plateau to one belief).
                                  // DIFFERENT key scheme: ledger_scheme folds
                                  // in 0x2000 (engine_rs.py) so it never
                                  // aliases a plain-COARSER50 ledger.
pub const R_VISITREAD: u32 = 16384; // structure lever (0x4000): maintain a CLEAN
                                  // per-root-edge VISIT count (root_edge_visits),
                                  // incremented once per integrated fresh leaf on
                                  // the root edge it descended through -- the
                                  // lc0-style visit distribution, free of the
                                  // transposition pooling that contaminates the
                                  // node eval count. STAGE 1: only maintains the
                                  // counter + exposes it (readout UNCHANGED); the
                                  // visit-readout is gated separately in Python.
                                  // Default off = zero work, bit-identical.
                                  // Default off = legacy/COARSER50 behavior.
pub const POLICY_TEMP: f32 = 1.359;
pub const CPUCT_INIT: f64 = 1.745;
pub const CPUCT_BASE: f64 = 38739.0;
pub const CPUCT_FACTOR: f64 = 3.894;
pub const FPU_REDUCTION: f64 = 0.33;
pub const LCB_K: f64 = 0.5;
// Draw-contempt deadband (value units): no contempt until our settled root
// value is genuinely won. DEAD=0.55 ~= +116cp (bottom of the measured won
// band); SAT=0.70 ~= +193cp (full ramp). Equal/edge positions (v <= ~0.50,
// <= +99cp) get ZERO contempt — the over-press (Lens-regression) guard.
pub const DRAW_DEAD: f64 = 0.55;
pub const DRAW_SAT: f64 = 0.70;
pub const ML_CAP: f64 = 0.0345;
pub const ML_SLOPE: f64 = 0.0027;
pub const ML_THRESH: f64 = 0.8;
pub const ML_SCALED: f64 = 1.6521;
pub const ML_QUAD: f64 = -0.6521;

/// lc0's GetMUtility: an absolute, capped moves-left bonus that only acts
/// once a position is decisive (|q| past the threshold) — prefer shorter
/// games when winning, longer when losing. q is the mover-view child value.
#[inline]
pub fn m_utility(q: f64, child_m: f64, parent_m: f64, thresh: f64) -> f64 {
    let base = (ML_SLOPE * (child_m - parent_m)).clamp(-ML_CAP, ML_CAP)
        * if q > 0.0 { -1.0 } else { 1.0 };
    let qa = ((q.abs() - thresh) / (1.0 - thresh)).max(0.0);
    base * (ML_SCALED * qa + ML_QUAD * qa * qa)
}
const LESSON_EVIDENCE: u32 = 32;
const PRIOR_VAR: f64 = 0.02 * 0.02 * 25.0;
const OBS_VAR: f64 = 0.18 * 0.18;
const MAX_CORRECTION: f64 = 0.12;
const MIN_EVIDENCE: u32 = 3;

// ---- belief-driven selection: epistemic uncertainty + value-of-information ----
/// Prior epistemic uncertainty of a fresh leaf — its value rests on one net
/// glance, so it is maximally reducible by search. Search contracts it to 0.
const EPI0: f64 = 1.0;
/// Per-level epistemic contraction in the max-backup: the uncertainty a node
/// inherits from its winning child is damped by this factor (each resolved ply
/// of search below the node shrinks what remains to learn about its value).
const EPI_DECAY: f64 = 0.75;
/// Value-closeness scale (value units, ~"is this sibling a live contender?")
/// for the argmax-ambiguity term in propagation and the closeness kernel in
/// VOI: how near a sibling's value must sit to the best to be decision-relevant.
const VOI_TAU: f64 = 0.10;
/// Floor on the combined-epistemic denominator in the VOI closeness kernel.
const VOI_EPS: f64 = 1e-6;

/// Gated draw value, side-relative (free fn so it can be called while a node
/// is mutably borrowed from self.nodes — takes only Copy scalar fields).
/// Returns 0 unless draw_contempt>0 AND |root_q0| past the deadband. Negative
/// for the winning side (decline the draw), positive for the losing side.
#[inline]
fn draw_value(draw_contempt: f64, root_q0: f64, root_turn_white: bool,
              turn_white: bool) -> f64 {
    if draw_contempt <= 0.0 {
        return 0.0;
    }
    let q = root_q0.clamp(-0.999, 0.999);
    let mag = ((q.abs() - DRAW_DEAD) / (DRAW_SAT - DRAW_DEAD)).clamp(0.0, 1.0);
    let shaped = mag * q.signum();                 // signed ramp, 0 in deadband
    let draw_val_root = -draw_contempt * shaped;   // < 0 for the winning side
    if turn_white == root_turn_white {
        draw_val_root
    } else {
        -draw_val_root
    }
}

#[inline]
pub fn eff_value(v: f64, mlh: f64) -> f64 {
    v * (1.0 + MLH_W * (1.0 - mlh / MLH_SCALE).max(0.0))
}

#[inline]
fn wdl_variance(w: f64, _d: f64, l: f64) -> f64 {
    let v = w - l;
    ((w + l) - v * v).max(0.0)
}

#[inline]
fn sq(s: Square) -> u8 {
    u32::from(s) as u8
}

pub struct Node {
    pub wdl: [f64; 3],
    pub value: f64,
    pub variance: f64,
    /// Epistemic (reducible-by-search) uncertainty in this node's value, kept
    /// DISTINCT from `variance` (the aleatoric / intrinsic-sharpness component
    /// = wdl_variance, which search cannot remove). A fresh leaf carries EPI0
    /// (its value rests on the net's single glance); search drives it to 0 as
    /// the subtree below settles. Propagated up the graph in backup() and read
    /// by the VOI selection rule. Only maintained when voi_on (else stale/EPI0,
    /// and never read — the default PUCT path is bit-identical without it).
    pub epistemic: f64,
    pub raw_value: f64,
    pub raw_wdl: [f64; 3],
    pub raw_mlh: f64,
    pub mlh: f64,
    pub v_them: f64,
    pub evals: u32,
    pub moves: Vec<Move>,
    pub priors: Vec<f32>,
    pub child_keys: Vec<Option<u64>>,
    pub parents: Vec<u64>,
    pub terminal: Option<f64>,
    pub claim_floor: bool,
    pub path_cond: bool,
    pub proof: bool,
    pub proof_dist: u32,
    pub turn_white: bool,
    pub observed: bool,
    pub ctx: u64,
}

impl Node {
    fn fresh(wdl: [f64; 3], raw_value: f64, moves: Vec<Move>, priors: Vec<f32>,
             ctx: u64, mlh: f64, turn_white: bool) -> Node {
        let n_moves = moves.len();
        Node {
            wdl,
            value: raw_value,
            variance: wdl_variance(wdl[0], wdl[1], wdl[2]),
            epistemic: EPI0,
            raw_value,
            raw_wdl: wdl,
            raw_mlh: mlh,
            mlh,
            v_them: raw_value,
            evals: 1,
            moves,
            priors,
            child_keys: vec![None; n_moves],
            parents: Vec::new(),
            terminal: None,
            claim_floor: false,
            path_cond: false,
            proof: false,
            proof_dist: 0,
            turn_white,
            observed: false,
            ctx,
        }
    }

    fn terminal_node(result: f64, turn_white: bool) -> Node {
        let wdl = if result < 0.0 { [0.0, 0.0, 1.0] } else { [0.0, 1.0, 0.0] };
        let mut n = Node::fresh(wdl, result, Vec::new(), Vec::new(), 0, 0.0,
                                turn_white);
        n.value = result;
        n.v_them = result;
        n.variance = 0.0;
        n.epistemic = 0.0; // proven: nothing left for search to reduce
        n.terminal = Some(result);
        n.proof = true;
        n.proof_dist = 0;
        n.evals = 0;
        n
    }

    fn pinned(value: f64, dist: u32, mlh: f64, turn_white: bool) -> Node {
        let wdl = if value > 0.5 {
            [1.0, 0.0, 0.0]
        } else if value < -0.5 {
            [0.0, 0.0, 1.0]
        } else {
            [0.0, 1.0, 0.0]
        };
        let mut n = Node::fresh(wdl, value, Vec::new(), Vec::new(), 0,
                                mlh.max(0.0), turn_white);
        n.value = value;
        n.v_them = value;
        n.variance = 0.0;
        n.epistemic = 0.0; // proven (mate/TB): epistemically certain
        n.terminal = Some(value);
        n.proof = true;
        n.proof_dist = dist;
        n.evals = 0;
        n
    }
}

struct Dirty {
    priority: f64,
    seq: u64,
    key: u64,
}
impl PartialEq for Dirty {
    fn eq(&self, o: &Self) -> bool {
        self.seq == o.seq
    }
}
impl Eq for Dirty {}
impl PartialOrd for Dirty {
    fn partial_cmp(&self, o: &Self) -> Option<Ordering> {
        Some(self.cmp(o))
    }
}
impl Ord for Dirty {
    fn cmp(&self, o: &Self) -> Ordering {
        // max-heap: higher priority first, then older seq first
        self.priority
            .total_cmp(&o.priority)
            .then(o.seq.cmp(&self.seq))
    }
}

pub struct PendingLeaf {
    pub key: u64,
    pub parent_key: u64, // 0 = the root itself (no link)
    pub move_idx: usize,
    pub path: Vec<u64>,
    pub edge_path: Vec<(u64, u32)>, // in-flight vloss along the WHOLE route
    pub pos: Chess,
    pub job: EncodeJob,
    pub claim: bool,
    pub halfmove: u32,
}

pub struct Core {
    pub nodes: FxHashMap<u64, Node>,
    pub max_nodes: usize,
    heap: BinaryHeap<Dirty>,
    seq: u64,
    pub backups: u64,
    pub terminals_found: u64,
    pub tb_hits: u64,
    vloss: FxHashMap<(u64, u32), u32>,
    pub policy: PolicyMap,
    pub tb: Option<Tablebase<Chess>>,
    pub tb_max_men: u32,
    pub strict_draws: bool,
    pub palimpsest_on: bool,
    pub miss_proven: u64,
    pub miss_cycle: u64,
    pub miss_terminal: u64,
    pub miss_dup: u64,
    lessons: FxHashMap<u64, (u32, f64)>,
    pub lessons_count: u64,
    // per-search settings
    pub rho: f64,
    pub lens_on: bool,
    // Gated draw contempt: a rules-draw/claim node is worth a small NEGATIVE
    // value for the side to move when our settled root assessment is winning
    // (so we decline draws and play on), 0 when equal, small POSITIVE when
    // losing (so we still take saving draws). draw_contempt=0 == legacy.
    pub draw_contempt: f64,
    pub root_q0: f64,
    pub bursts_on: bool,
    pub thompson_on: bool,
    pub voi_on: bool,      // value-of-information selection: replace PUCT descent
                           // with VOI = epistemic(c) * closeness(v_c, v_best),
                           // concentrating evals on the moves whose resolution
                           // most reduces the node's decision uncertainty. Needs
                           // the epistemic field maintained in backup(). OFF ==
                           // legacy PUCT (the default path stays bit-identical).
    pub refine: u32,
    pub lcb_k: f64,   // backup LCB strength (R_LCB); runtime-tunable
    pub fpu_red: f64, // FPU reduction (R_FPU); runtime-tunable
    pub ml_thresh: f64, // MLH gate (R_MLH); lc0's 0.8 assumes mean-backup
                        // Q saturation — at max-backup our won-position
                        // values sit lower and the urgency never fired
                        // (the +3.56-peak draws); runtime-tunable
    pub cpuct_init: f64,   // PUCT exploration (R_CPUCT base); tunable
    pub cpuct_factor: f64, // PUCT log-growth rate; tunable
    pub c_var: f64,        // variance exploration bonus weight; tunable
    pub vloss_w: f64,      // virtual-loss weight (legacy branch); tunable
    pub honest_k: f64,     // honest-max winner's-curse backup correction:
                           // the adopted max is debiased by honest_k*sqrt(2 ln N)
                           // /sqrt(1+evals) -- grows with fanout N (the term the
                           // per-child LCB lacks), decays with evidence (so it
                           // still converges to exact minimax). 0.0 == OFF/legacy.
    pub confback_w: f64,   // confidence-weighted backup (0.0 == OFF, byte-identical):
                           // blend the adopted max toward the children-mean by
                           // w = confback_w/sqrt(1+best_evals), capped at confback_cap.
                           // Discounts an UNCERTAIN extreme -- the over-estimated
                           // worst-case opponent reply that tanks a good move (32%
                           // search_structure over-pessimism) and the over-optimistic
                           // thin best move -- while a SETTLED extreme (a real, deep
                           // refutation) is trusted, so it is NOT deaf like R_MEANBACK.
    pub confback_cap: f64,
    rng: AtomicU64,
    burst_cands: Vec<(u64, Chess)>,
    pub proofs_minted: u64,
    pub corrector: Option<[f64; 8]>,
    // game context (set_position)
    pub root_key: u64,
    pub root_pos: Option<Chess>,
    pub root_turn_white: bool,
    pub root_halfmove: u32,
    hist_keys: Vec<u64>,    // zobrist of every game position incl. root
    hist_clocks: Vec<u32>,
    hist_frames: Vec<Frame>,
    started_from_startpos: bool,
    fen_ep: Option<u8>,     // game-root FEN's legal ep square (lc0 fixup)
    fen_black_to_move: bool,
    pub pending: Vec<PendingLeaf>,
    // Structure lever (R_VISITREAD): clean per-root-MOVE-index visit count for
    // the current search. Lives OUTSIDE the Node graph so transposition pooling
    // (which inflates child Node.evals via multiple parents) cannot contaminate
    // it. Re-zeroed per-SEARCH (root_visit_epoch != root_key) in select_batch,
    // lazily sized to the live root's move list.
    pub root_edge_visits: Vec<u32>,
    root_visit_epoch: u64,
}

const STARTPOS: &str =
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

impl Core {
    pub fn new(syzygy_path: Option<String>, strict_draws: bool,
               max_nodes: usize, palimpsest_on: bool, tb_max_men: u32)
               -> Core {
        let tb = syzygy_path.and_then(|p| {
            let mut t: Tablebase<Chess> = Tablebase::new();
            match t.add_directory(&p) {
                Ok(n) if n > 0 => Some(t),
                _ => None,
            }
        });
        Core {
            nodes: FxHashMap::default(),
            max_nodes,
            heap: BinaryHeap::new(),
            seq: 0,
            backups: 0,
            terminals_found: 0,
            tb_hits: 0,
            vloss: FxHashMap::default(),
            policy: PolicyMap::new(),
            tb,
            tb_max_men,
            strict_draws,
            palimpsest_on,
            miss_proven: 0,
            miss_cycle: 0,
            miss_terminal: 0,
            miss_dup: 0,
            lessons: FxHashMap::default(),
            lessons_count: 0,
            rho: 1.0,
            lens_on: true,
            draw_contempt: 0.0,
            root_q0: 0.0,
            bursts_on: false,
            thompson_on: false,
            voi_on: false,
            refine: 0,
            lcb_k: LCB_K,
            fpu_red: FPU_REDUCTION,
            ml_thresh: ML_THRESH,
            cpuct_init: CPUCT_INIT,
            cpuct_factor: CPUCT_FACTOR,
            c_var: C_VAR,
            vloss_w: VLOSS,
            honest_k: 0.0,
            confback_w: 0.0,
            confback_cap: 0.0,
            rng: AtomicU64::new(0x5717_1A7E_D00D_F00Du64),
            burst_cands: Vec::new(),
            proofs_minted: 0,
            corrector: None,
            root_key: 0,
            root_pos: None,
            root_turn_white: true,
            root_halfmove: 0,
            hist_keys: Vec::new(),
            hist_clocks: Vec::new(),
            hist_frames: Vec::new(),
            started_from_startpos: true,
            fen_ep: None,
            fen_black_to_move: false,
            pending: Vec::new(),
            root_edge_visits: Vec::new(),
            root_visit_epoch: u64::MAX,
        }
    }

    // ------------------------------------------------------------ position

    pub fn set_position(&mut self, fen: &str, moves: &[String])
                        -> Result<(), String> {
        let setup: Fen = fen.parse().map_err(|e| format!("bad fen: {e}"))?;
        let mut pos: Chess = setup
            .into_position(CastlingMode::Standard)
            .map_err(|e| format!("illegal position: {e}"))?;
        self.started_from_startpos = fen == STARTPOS
            || fen.starts_with("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -");
        self.fen_ep = pos
            .ep_square(shakmaty::EnPassantMode::Always)
            .map(|s| u32::from(s) as u8);
        self.fen_black_to_move = pos.turn() == Color::Black;
        let mut clock = pos.halfmoves();
        self.hist_keys.clear();
        self.hist_clocks.clear();
        self.hist_frames.clear();
        self.hist_keys.push(zobrist(&pos));
        self.hist_clocks.push(clock);
        self.hist_frames.push(Frame::of(&pos));
        for u in moves {
            let uci: UciMove = u.parse().map_err(|e| format!("bad uci {u}: {e}"))?;
            let m = uci
                .to_move(&pos)
                .map_err(|e| format!("illegal move {u}: {e}"))?;
            clock = if m.is_zeroing() { 0 } else { clock + 1 };
            pos.play_unchecked(&m);
            self.hist_keys.push(zobrist(&pos));
            self.hist_clocks.push(clock);
            self.hist_frames.push(Frame::of(&pos));
        }
        self.root_key = position_key_cf(&pos, clock, false,
                                        self.r(R_COARSER50), self.r(R_FINER50));
        self.root_turn_white = pos.turn() == Color::White;
        self.root_halfmove = clock;
        self.root_pos = Some(pos);
        Ok(())
    }

    pub fn set_search(&mut self, rho: f64, lens_on: bool,
                      draw_contempt: f64, root_q0: f64) {
        self.rho = rho;
        self.lens_on = lens_on;
        self.draw_contempt = draw_contempt;
        self.root_q0 = root_q0;
    }

    /// Side-relative value of a rules-draw / claim node, gated by our own
    /// settled root assessment. Returns 0 unless we are genuinely winning
    /// (|root_q0| past DEAD) AND draw_contempt > 0. Negative for the winning
    /// side (decline the draw, play on), positive for the losing side (take
    /// the saving draw). `turn_white` is the node's side to move.
    #[inline]
    fn d_for(&self, turn_white: bool) -> f64 {
        draw_value(self.draw_contempt, self.root_q0, self.root_turn_white,
                   turn_white)
    }

    pub fn set_features(&mut self, bursts: bool, thompson: bool) {
        self.bursts_on = bursts;
        self.thompson_on = thompson;
    }

    pub fn set_refine(&mut self, mask: u32) {
        self.refine = mask;
    }

    #[allow(clippy::too_many_arguments)]
    pub fn set_tunables(&mut self, lcb_k: f64, fpu_red: f64, ml_thresh: f64,
                        cpuct_init: f64, cpuct_factor: f64, c_var: f64,
                        vloss_w: f64) {
        self.lcb_k = lcb_k;
        self.fpu_red = fpu_red;
        self.ml_thresh = ml_thresh;
        self.cpuct_init = cpuct_init;
        self.cpuct_factor = cpuct_factor;
        self.c_var = c_var;
        self.vloss_w = vloss_w;
    }

    pub fn set_honest_k(&mut self, k: f64) {
        self.honest_k = k;
    }

    pub fn set_voi(&mut self, on: bool) {
        self.voi_on = on;
    }

    pub fn set_confback(&mut self, w: f64, cap: f64) {
        self.confback_w = w;
        self.confback_cap = cap;
    }

    /// Transposition-graph structure (read-only): (nodes, parent_edges,
    /// multi_parent_nodes, max_parents, parented_nodes). Parent backrefs are
    /// recorded for nodes that have been linked into the relaxation graph, so
    /// `parented_nodes` (not the full node count, which includes glanced-but-
    /// not-yet-linked leaves) is the honest denominator. Among parented nodes a
    /// pure search TREE has exactly one parent each (multi == 0); every parent
    /// beyond the first is a position reached by a DIFFERENT move order -- a
    /// transposition the lattice evaluates ONCE where a tree recomputes it per
    /// path. (edges - parented_nodes) is that surplus reuse (>=0 in a graph,
    /// ==0 in a tree); multi_parent_nodes / parented_nodes is the graph share.
    pub fn graph_stats(&self) -> (usize, usize, usize, usize, usize) {
        let mut edges = 0usize;
        let mut multi = 0usize;
        let mut maxp = 0usize;
        let mut parented = 0usize;
        for n in self.nodes.values() {
            let p = n.parents.len();
            edges += p;
            if p >= 1 {
                parented += 1;
            }
            if p > 1 {
                multi += 1;
            }
            if p > maxp {
                maxp = p;
            }
        }
        (self.nodes.len(), edges, multi, maxp, parented)
    }

    #[inline]
    fn r(&self, bit: u32) -> bool {
        self.refine & bit != 0
    }

    /// Forcibility gate for a repetition/claim draw floor (rank-2 B, SAFE
    /// SUBSET). `f` is the side-relative draw value for the cycle's mover:
    ///   f <  0 == this mover is WINNING -> the floor-DOWN routes AWAY from
    ///             the rep (the Ra8 / opponent-declines over-claim). Under
    ///             R_REPFORCE we DE-FORCE this pin: a non-compellable draw the
    ///             winner relies on is NOT pinned; it falls through to a
    ///             normal evaluated leaf and re-validates after the opponent
    ///             deviates.  (Deliberation-level companion: Fix A + path_cond.)
    ///   f >= 0 == this mover is LOSING/EQUAL -> the floor-UP is the
    ///             perpetual-check / saving-draw resource. This MUST stay
    ///             UNCONDITIONAL: the only sound forcing proxy available here
    ///             is pos.is_check(), but `pos` is the node AFTER the
    ///             completing move (the OPPONENT is to move), which is the
    ///             WRONG node for the saver (the saver's own decision node is
    ///             a ply earlier and is NOT in check). Gating f>=0 on
    ///             is_check would SUPPRESS the saving draw -> regression of
    ///             claim-draw history #2. HELD until forcing detection is
    ///             cycle-aware (any check by the forcing side anywhere in the
    ///             repeated window). So f>=0 always returns true here.
    /// Bit OFF -> true unconditionally (legacy). NO-OP at draw_contempt=0
    /// because draw_value returns 0 for all sides (f<0 never fires).
    #[inline]
    fn rep_floor_ok(&self, f: f64) -> bool {
        if !self.r(R_REPFORCE) {
            return true; // legacy: unconditional floor
        }
        // SAFE SUBSET: only de-force the WINNING side's route-away pin.
        // The losing/equal side's saving floor is never touched.
        f >= 0.0
    }

    pub fn set_corrector(&mut self, beta: Option<[f64; 8]>) {
        self.corrector = beta;
    }

    /// Learned oracle correction (Distillery-trained ridge model). Features
    /// MUST stay in lockstep with tools/build_dataset.py::features_of.
    fn corrector_delta(&self, pos: &Chess, raw_v: f64, raw_mlh: f64) -> f64 {
        let beta = match &self.corrector {
            Some(b) => b,
            None => return 0.0,
        };
        let b = pos.board();
        let val = |r: Role| -> f64 {
            match r {
                Role::Pawn => 1.0, Role::Knight => 3.0, Role::Bishop => 3.0,
                Role::Rook => 5.0, Role::Queen => 9.0, _ => 0.0,
            }
        };
        let (us, them) = (pos.turn(), !pos.turn());
        let mut mat_us = 0.0;
        let mut mat_them = 0.0;
        for r in [Role::Pawn, Role::Knight, Role::Bishop, Role::Rook, Role::Queen] {
            mat_us += val(r) * (b.by_color(us) & b.by_role(r)).count() as f64;
            mat_them += val(r) * (b.by_color(them) & b.by_role(r)).count() as f64;
        }
        let pawns = b.by_role(Role::Pawn).count() as f64;
        let pieces = b.occupied().count() as f64;
        let f = [
            1.0,
            raw_v,
            raw_v * raw_v.abs(),
            raw_mlh.min(160.0) / 80.0,
            (mat_us + mat_them) / 78.0,
            (mat_us - mat_them) / 9.0,
            pawns / 16.0,
            pieces / 32.0,
        ];
        let delta: f64 = f.iter().zip(beta.iter()).map(|(x, w)| x * w).sum();
        delta.clamp(-0.15, 0.15)
    }

    // xorshift64* — deterministic, cheap, good enough for posterior sampling
    #[inline]
    fn rand_u64(&self) -> u64 {
        let mut x = self.rng.load(AtomicOrdering::Relaxed);
        x ^= x >> 12;
        x ^= x << 25;
        x ^= x >> 27;
        self.rng.store(x, AtomicOrdering::Relaxed);
        x.wrapping_mul(0x2545_F491_4F6C_DD1D)
    }

    #[inline]
    fn rand_normal(&self) -> f64 {
        // Box-Muller from two uniform draws
        let u1 = (self.rand_u64() >> 11) as f64 / (1u64 << 53) as f64;
        let u2 = (self.rand_u64() >> 11) as f64 / (1u64 << 53) as f64;
        (-2.0 * (u1.max(1e-12)).ln()).sqrt()
            * (2.0 * std::f64::consts::PI * u2).cos()
    }

    // ---------------------------------------------------------- palimpsest

    fn context_of(pos: &Chess) -> u64 {
        use std::hash::{Hash, Hasher};
        let b = pos.board();
        let mut h = rustc_hash::FxHasher::default();
        (b.by_color(Color::White) & b.by_role(Role::Pawn)).0.hash(&mut h);
        (b.by_color(Color::Black) & b.by_role(Role::Pawn)).0.hash(&mut h);
        for color in [Color::White, Color::Black] {
            for role in [Role::Knight, Role::Bishop, Role::Rook, Role::Queen] {
                ((b.by_color(color) & b.by_role(role)).0.count_ones() as u8)
                    .hash(&mut h);
            }
        }
        (pos.turn() == Color::White).hash(&mut h);
        h.finish()
    }

    fn correction(&self, ctx: u64) -> f64 {
        if !self.palimpsest_on {
            return 0.0;
        }
        match self.lessons.get(&ctx) {
            Some((n, total)) if *n >= MIN_EVIDENCE => {
                let post = (total / OBS_VAR)
                    / (1.0 / PRIOR_VAR + (*n as f64) / OBS_VAR);
                post.clamp(-MAX_CORRECTION, MAX_CORRECTION)
            }
            _ => 0.0,
        }
    }

    fn observe(&mut self, ctx: u64, lesson: f64) {
        if !self.palimpsest_on || ctx == 0 {
            return;
        }
        let cell = self.lessons.entry(ctx).or_insert((0, 0.0));
        cell.0 += 1;
        cell.1 += lesson;
        self.lessons_count += 1;
    }

    // ------------------------------------------------------------- settling

    pub fn mark_dirty(&mut self, key: u64, priority: f64) {
        self.seq += 1;
        self.heap.push(Dirty { priority, seq: self.seq, key });
    }

    pub fn backup(&mut self, key: u64) -> f64 {
        // phase 1: read everything immutably
        let (best, mirror_out, deltas);
        {
            let node = match self.nodes.get(&key) {
                Some(n) => n,
                None => return 0.0,
            };
            if node.proof || node.moves.is_empty() {
                return 0.0;
            }
            let rho = self.rho;
            let mirror = rho < RHO_GATE;
            let opp_node = mirror && (node.turn_white != self.root_turn_white);
            let lens = self.lens_on && rho < RHO_GATE
                && node.turn_white == self.root_turn_white;

            let mut best_q: Option<f64> = None;
            let mut best_sel = f64::NEG_INFINITY;
            let mut best_child: Option<&Node> = None;
            let mut best_proof = false;
            let mut best_evals = 0u32;
            let mut n_expanded = 0usize;
            let mut any_unexpanded = false;
            let mut all_proven = true;
            let mut any_path_cond = false;
            let mut vis_mass = 0.0f64;
            let mut wsum = 0.0f64; // R_MEANBACK accumulators
            let mut wtot = 0.0f64;
            let mut them_q: Vec<f64> = Vec::new();
            let mut them_p: Vec<f64> = Vec::new();
            // Epistemic propagation (only when voi_on; zero cost otherwise).
            // voi_children holds (q, epistemic) per expanded child so the
            // argmax-ambiguity term can be formed once best_q is known.
            let voi = self.voi_on;
            let mut voi_children: Vec<(f64, f64)> = Vec::new();
            let mut best_epi = EPI0;
            let mut best_voi_idx = usize::MAX;

            for (idx, ck) in node.child_keys.iter().enumerate() {
                let child = ck.and_then(|k| self.nodes.get(&k));
                match child {
                    None => {
                        any_unexpanded = true;
                        all_proven = false;
                        if mirror {
                            them_q.push(node.raw_value);
                            them_p.push(node.priors[idx] as f64);
                        }
                    }
                    Some(c) => {
                        if !c.proof {
                            all_proven = false;
                        }
                        if c.path_cond {
                            any_path_cond = true;
                        }
                        vis_mass += node.priors[idx] as f64;
                        n_expanded += 1;
                        let g = if self.r(R_GAMMA)
                            && node.moves[idx].is_zeroing()
                        {
                            1.0
                        } else {
                            GAMMA
                        };
                        let q = -g * c.value;
                        let mut qe = if self.r(R_MLH) {
                            q + m_utility(q, c.mlh, node.mlh, self.ml_thresh)
                        } else {
                            -g * eff_value(c.value, c.mlh)
                        };
                        if lens && qe > LENS_FLOOR {
                            qe += LENS_W * c.wdl[2];
                        }
                        // LCB argmax (winner's-curse fix): a child backed by
                        // one optimistic eval no longer outranks a settled
                        // line — the max is taken over evidence-discounted
                        // values, while the VALUE adopted stays the plain q
                        // of whichever child wins. COUNT-based penalty: the
                        // wdl-variance form was a measured no-op (variance
                        // tracks position sharpness, not estimate error —
                        // ~0.002 in decided positions). k/sqrt(1+n) is the
                        // epistemic proxy; converges to exact minimax.
                        let sel = if self.r(R_LCB) {
                            qe - self.lcb_k / (1.0 + c.evals as f64).sqrt()
                        } else {
                            qe
                        };
                        if voi {
                            voi_children.push((q, c.epistemic));
                        }
                        if best_q.is_none() || sel > best_sel {
                            best_q = Some(q);
                            best_sel = sel;
                            best_child = Some(c);
                            best_proof = c.proof;
                            best_evals = c.evals;
                            if voi {
                                best_epi = c.epistemic;
                                best_voi_idx = voi_children.len() - 1;
                            }
                        }
                        if self.r(R_MEANBACK) || self.confback_w > 0.0 {
                            let w = 1.0 + c.evals as f64;
                            wsum += w * q;
                            wtot += w;
                        }
                        if mirror {
                            them_q.push(-g * c.v_them);
                            them_p.push(node.priors[idx] as f64);
                        }
                    }
                }
            }
            // R_NOFLOOR: once ANY child is expanded, the node's value comes
            // from the search, not the net's first glance. The raw-eval
            // floor was systematic optimism exactly when positions slip
            // (the parity-match drift mode: SW read -0.3 in SF -1.5
            // positions for dozens of plies). Selection FPU still routes
            // descents to unvisited siblings; only the VALUE stops hiding.
            if any_unexpanded
                && !(self.r(R_NOFLOOR) && best_q.is_some())
                && !(self.r(R_MEANBACK) && wtot > 0.0)
            {
                // Optimism about unexplored moves — under R_FPU it decays
                // with the policy mass already examined, so a refuted node
                // cannot hide behind its raw eval until the entire move
                // list has been expanded (the "bad news waits" flaw).
                let q0 = if self.r(R_FPU) {
                    node.raw_value - self.fpu_red * vis_mass.sqrt()
                } else {
                    node.raw_value
                };
                let mut q0e = if self.r(R_MLH) {
                    q0
                } else {
                    eff_value(q0, node.raw_mlh)
                };
                if lens && q0e > LENS_FLOOR {
                    q0e += LENS_W * node.raw_wdl[0];
                }
                if best_q.is_none() || q0e > best_sel {
                    best_q = Some(q0);
                    best_child = None;
                    if voi {
                        // an unexplored move now leads: its value rests on the
                        // net's glance alone -> full prior epistemic, no sibling
                        // is the "winning child" to inherit a contracted std.
                        best_epi = EPI0;
                        best_voi_idx = usize::MAX;
                    }
                }
            }

            // Epistemic = (winning line's residual uncertainty, contracted one
            // ply) + (argmax ambiguity: how much a sibling we are unsure about
            // could overturn the decision). The aleatoric `variance` is set
            // separately below from the winning child's wdl_variance.
            let epi_new = if voi {
                let bq_v = best_q.unwrap_or(node.raw_value);
                let denom = 2.0 * VOI_TAU * VOI_TAU;
                let mut amb = 0.0;
                for (i, &(cq, ce)) in voi_children.iter().enumerate() {
                    if i == best_voi_idx {
                        continue; // the winner's std is the inherited term
                    }
                    let gap = bq_v - cq;
                    amb += (-(gap * gap) / denom).exp() * ce;
                }
                // Unexplored policy mass sitting near the best value is live
                // decision uncertainty too — a move we have not looked at yet
                // might be best. Weight EPI0 by that mass and its closeness.
                let unexp = (1.0 - vis_mass).max(0.0);
                if unexp > 1e-6 {
                    let q0 = node.raw_value - self.fpu_red * vis_mass.sqrt();
                    let gap = bq_v - q0;
                    amb += unexp * EPI0 * (-(gap * gap) / denom).exp();
                }
                Some(EPI_DECAY * best_epi + amb)
            } else {
                None
            };

            let bc = best_child.map(|c| {
                (c.wdl, c.variance, c.mlh, c.proof, c.proof_dist, c.path_cond)
            });
            // R_MEANBACK: evidence-weighted mean of expanded children — the
            // lc0 backup. Sticky proofs: a proven best child (or a fully
            // proven node) keeps exact minimax so theorems are never diluted
            // by the running mean.
            let mean_q = if self.r(R_MEANBACK) && wtot > 0.0 && !best_proof
                && !all_proven
            {
                Some(wsum / wtot)
            } else {
                None
            };
            // children-mean for the confidence-weighted backup blend (phase 2);
            // available whenever confback (or R_MEANBACK) accumulated wsum/wtot.
            let conf_mean = if wtot > 0.0 { Some(wsum / wtot) } else { None };
            let v_them_new = if mirror && !them_q.is_empty() {
                if opp_node {
                    let qbest = them_q.iter().cloned().fold(f64::MIN, f64::max);
                    let tot: f64 = them_p.iter().sum::<f64>().max(1e-12);
                    let blend: f64 = them_q
                        .iter()
                        .zip(&them_p)
                        .map(|(q, p)| q * p)
                        .sum::<f64>()
                        / tot;
                    Some(rho * qbest + (1.0 - rho) * blend)
                } else {
                    Some(them_q.iter().cloned().fold(f64::MIN, f64::max))
                }
            } else {
                None
            };
            best = (best_q, bc, all_proven, any_path_cond, mean_q,
                    n_expanded, best_evals, best_proof, epi_new, conf_mean);
            mirror_out = v_them_new;
            deltas = ();
        }
        let _ = deltas;

        // phase 2: write
        let (best_q, bc, all_proven, any_path_cond, mean_q,
             n_expanded, best_evals, best_proof, epi_new, conf_mean) = best;
        let honest_k = self.honest_k;
        let confback_w = self.confback_w;
        let confback_cap = self.confback_cap;
        let node = self.nodes.get_mut(&key).unwrap();
        let old = node.value;
        let bq = best_q.unwrap_or(node.raw_value);
        let mut v = mean_q.unwrap_or(bq);
        // Honest-max winner's-curse correction (gated honest_k>0): the adopted
        // max over n_expanded noisy children is biased high by ~sqrt(2 ln N)
        // standard errors; subtract that, scaled by the winner's epistemic std
        // (~1/sqrt(1+evals)) so it decays to exact minimax as evidence grows.
        // Skipped for proven nodes (kept exact) and the unexpanded-floor case.
        if honest_k > 0.0 && mean_q.is_none() && bc.is_some()
            && !best_proof && !all_proven && n_expanded >= 2
        {
            v -= honest_k * (2.0 * (n_expanded as f64).ln()).sqrt()
                / (1.0 + best_evals as f64).sqrt();
        }
        // Confidence-weighted backup (gated confback_w>0): blend the adopted max
        // toward the children-mean by the WINNING child's uncertainty (thin
        // evidence -> lean to mean; settled -> full max). Un-tanks an over-
        // estimated worst-case opponent reply (the 32% over-pessimism) and
        // debiases an over-optimistic thin best move, while a SETTLED extreme
        // (a real, deep refutation) is trusted -> NOT deaf like R_MEANBACK.
        let _ = conf_mean;
        if confback_w > 0.0 && mean_q.is_none() && bc.is_some()
            && !best_proof && !all_proven && n_expanded >= 2
        {
            let mut w = confback_w / (1.0 + best_evals as f64).sqrt();
            if confback_cap > 0.0 {
                w = w.min(confback_cap);
            }
            // Anchor toward the net's OWN glance (raw_value), not the children-
            // mean: raw_value is SELECTIVE -- it endorses a move BT4 likes (un-
            // tanks a good move the backup over-pessimized BELOW the net) and
            // keeps a genuinely bad move bad (the net agrees with the backup
            // there). Confidence-gated: floors only thin/uncertain bad-news,
            // releases on settled evidence -> the signal-gated version of the
            // failed blanket q0-floor (deaf-to-bad-news) regression.
            v = (1.0 - w) * v + w * node.raw_value;
        }
        node.value = v;
        if let Some(e) = epi_new {
            node.epistemic = e;
        }
        match bc {
            Some((cwdl, cvar, cmlh, cproof, cdist, cpc)) => {
                node.wdl = [cwdl[2], cwdl[1], cwdl[0]];
                node.variance = cvar;
                node.mlh = cmlh + 1.0;
                if (cproof && bq > 0.5) || all_proven {
                    node.proof = true;
                    node.variance = 0.0;
                    node.epistemic = 0.0; // proven this backup: certainty
                    node.proof_dist = cdist + 1;
                    if all_proven {
                        node.path_cond = node.path_cond || any_path_cond;
                    } else {
                        node.path_cond = node.path_cond || cpc;
                    }
                }
            }
            None => {
                node.wdl = node.raw_wdl;
                node.variance =
                    wdl_variance(node.raw_wdl[0], node.raw_wdl[1], node.raw_wdl[2]);
                node.mlh = node.raw_mlh;
            }
        }
        node.v_them = mirror_out.unwrap_or(node.value);
        if node.claim_floor {
            // Two-sided claim floor with gated contempt. f = the draw value
            // for this node's mover: >0 when the mover is LOSING (perpetual /
            // saving draw stays attractive — floor UP), <0 when the mover is
            // WINNING (the rep is strictly worse than any real won line, so
            // the search routes away from it and plays on). f==0 == legacy.
            // Free fn (not self.d_for) so the self.draw_contempt/root_* field
            // reads are disjoint from the &mut self.nodes borrow held by node.
            let f = draw_value(self.draw_contempt, self.root_q0,
                               self.root_turn_white, node.turn_white);
            // rank-2 B SAFE SUBSET: de-force ONLY the WINNING side's floor-DOWN
            // (f<0, route away from the rep). The losing/equal floor-UP (f>=0,
            // perpetual-check saving draw) stays UNCONDITIONAL. Inlined as a
            // disjoint `self.refine` read (NOT self.rep_floor_ok) so it does
            // not alias the &mut self.nodes borrow held by `node` -- same
            // reason draw_value above is a free fn. Bit OFF / contempt=0 ->
            // unconditional (legacy / NO-OP).
            let rep_floor_ok = (self.refine & R_REPFORCE == 0) || f >= 0.0;
            if rep_floor_ok && node.value < f {
                node.value = f;
                if f >= 0.0 {
                    // saving-draw / equal: collapse loss mass into draw mass
                    let (w, d, l) = (node.wdl[0], node.wdl[1], node.wdl[2]);
                    node.wdl = [w, d + l, 0.0];
                } // f < 0: keep wdl coherent with the (negative) value — do
                  // NOT rewrite it to a pure draw.
                if node.v_them < f {
                    node.v_them = f;
                }
                if node.proof {
                    node.proof_dist = 0;
                }
            }
        }
        self.backups += 1;
        (node.value - old).abs()
    }

    pub fn settle(&mut self, max_ops: usize) -> usize {
        let mut done = 0;
        while done < max_ops {
            let d = match self.heap.pop() {
                Some(d) => d,
                None => break,
            };
            if !self.nodes.contains_key(&d.key) {
                continue;
            }
            let delta = self.backup(d.key);
            done += 1;
            if delta > SETTLE_EPS {
                let parents: Vec<u64> =
                    self.nodes.get(&d.key).map(|n| n.parents.clone())
                        .unwrap_or_default();
                for pk in parents {
                    self.mark_dirty(pk, delta);
                }
            }
        }
        done
    }

    // -------------------------------------------------------------- broker

    fn score_moves(&self, node: &Node, key: u64) -> (i64, Option<u64>) {
        // Root Thompson sampling: at the root, descend the move whose value
        // SAMPLE from its posterior is best, instead of PUCT's deterministic
        // optimism. This is approximate best-arm identification — evals flow
        // in proportion to the probability a move is actually best, which is
        // the question the court is deciding.
        if self.thompson_on && key == self.root_key {
            const TAU2: f64 = 0.0009;
            let mut best_s = f64::NEG_INFINITY;
            let mut best_i: i64 = -1;
            let mut best_child: Option<u64> = None;
            for (i, ck) in node.child_keys.iter().enumerate() {
                let (mean, std, child_key) = match ck
                    .and_then(|k| self.nodes.get(&k).map(|c| (k, c)))
                {
                    None => (
                        node.raw_value - FPU_PENALTY
                            + 0.4 * node.priors[i] as f64,
                        0.30,
                        None,
                    ),
                    Some((k, c)) => {
                        if c.proof {
                            continue;
                        }
                        (
                            -GAMMA * eff_value(c.value, c.mlh),
                            (c.variance / (1.0 + c.evals as f64) + TAU2)
                                .sqrt(),
                            Some(k),
                        )
                    }
                };
                let damp = 6.0f64;
                let s = mean + std * self.rand_normal()
                    - self.vloss_w
                        * (*self.vloss.get(&(key, i as u32)).unwrap_or(&0)
                            as f64)
                        / damp;
                if s > best_s {
                    best_s = s;
                    best_i = i as i64;
                    best_child = child_key;
                }
            }
            return (best_i, best_child);
        }
        // Value-of-information descent (gated voi_on): pick the child whose
        // resolution most reduces THIS node's decision uncertainty, rather than
        // PUCT's policy*sqrt(N)/(1+n) optimism. VOI(c) = epistemic(c) *
        // closeness(c), closeness = exp(-(v_best-v_c)^2 / 2*VOI_TAU^2) -- a
        // FIXED decision-relevance scale (NOT the combined epistemic: scaling
        // the kernel by the children's own uncertainty made it blind to value
        // gaps while everything was fresh, so the search degenerated to breadth-
        // first expansion of confidently-losing moves -- the v1 failure the
        // characterization caught). With a fixed TAU a hung piece (gap ~1.0)
        // gets closeness ~exp(-50)~0 and is abandoned; only moves whose value
        // sits within ~TAU of the best stay live, and among those the MOST
        // epistemically-uncertain one is resolved first. Unexpanded children
        // take the node's current value as an optimistic prior (a move we have
        // not looked at might match the best) and EPI0, scaled by the policy
        // prior so BT4 still orders the first looks. In-flight count damps the
        // score so a batch spreads across contenders. This is the search rule
        // the belief-lattice thesis implies: selection driven by what resolves
        // the decision, not borrowed from MCTS.
        if self.voi_on {
            let denom = 2.0 * VOI_TAU * VOI_TAU + VOI_EPS;
            // pass 1: the node's currently-best believed value
            let mut v_best = f64::NEG_INFINITY;
            for (i, ck) in node.child_keys.iter().enumerate() {
                let v_c = match ck.and_then(|k| self.nodes.get(&k).map(|c| (k, c)))
                {
                    None => node.value,
                    Some((_, c)) => {
                        if c.proof {
                            continue;
                        }
                        let g = if node.moves[i].is_zeroing() { 1.0 } else { GAMMA };
                        -g * eff_value(c.value, c.mlh)
                    }
                };
                if v_c > v_best {
                    v_best = v_c;
                }
            }
            if v_best == f64::NEG_INFINITY {
                v_best = node.value; // all children proven: nothing to select
            }
            // pass 2: VOI score per child
            let mut best_s = f64::NEG_INFINITY;
            let mut best_i: i64 = -1;
            let mut best_child: Option<u64> = None;
            for (i, ck) in node.child_keys.iter().enumerate() {
                let inflight =
                    *self.vloss.get(&(key, i as u32)).unwrap_or(&0) as f64;
                let (v_c, se_c, child_key, prior_w) = match ck
                    .and_then(|k| self.nodes.get(&k).map(|c| (k, c)))
                {
                    None => (node.value, EPI0, None, node.priors[i] as f64),
                    Some((k, c)) => {
                        if c.proof {
                            continue;
                        }
                        let g = if node.moves[i].is_zeroing() { 1.0 } else { GAMMA };
                        (-g * eff_value(c.value, c.mlh), c.epistemic, Some(k), 1.0)
                    }
                };
                let gap = v_best - v_c;
                let closeness = (-(gap * gap) / denom).exp();
                let s = prior_w * se_c * closeness / (1.0 + inflight);
                if s > best_s {
                    best_s = s;
                    best_i = i as i64;
                    best_child = child_key;
                }
            }
            return (best_i, best_child);
        }
        let sqrt_n = ((node.evals + 1) as f64).sqrt();
        let cpuct = if self.r(R_CPUCT) {
            // lc0's log-growth schedule: more exploration as evidence piles
            // up at a node (1.745 at N=0, ~2.6 at N=10k). init/factor tunable.
            self.cpuct_init
                + self.cpuct_factor
                    * ((node.evals as f64 + CPUCT_BASE) / CPUCT_BASE).ln()
        } else {
            C_PUCT
        };
        // lc0 FPU: unvisited children anchor on the parent's SETTLED value,
        // reduced by sqrt of the policy mass already examined — the more of
        // the move list has been tried, the less promising the leftovers.
        let fpu_q = if self.r(R_FPU) {
            let vis_mass: f64 = node
                .child_keys
                .iter()
                .enumerate()
                .filter(|(_, ck)| {
                    ck.map_or(false, |k| self.nodes.contains_key(&k))
                })
                .map(|(i, _)| node.priors[i] as f64)
                .sum();
            node.value - self.fpu_red * vis_mass.sqrt()
        } else {
            node.raw_value - FPU_PENALTY
        };
        let mut best_s = f64::NEG_INFINITY;
        let mut best_i: i64 = -1;
        let mut best_child: Option<u64> = None;
        for (i, ck) in node.child_keys.iter().enumerate() {
            let inflight =
                *self.vloss.get(&(key, i as u32)).unwrap_or(&0) as f64;
            let (q, u, child_key, child_evals) = match ck
                .and_then(|k| self.nodes.get(&k).map(|c| (k, c)))
            {
                None => (
                    fpu_q,
                    if self.r(R_UFLIGHT) {
                        cpuct * node.priors[i] as f64 * sqrt_n
                            / (1.0 + inflight)
                    } else {
                        cpuct * node.priors[i] as f64 * sqrt_n
                    },
                    None,
                    0u32,
                ),
                Some((k, c)) => {
                    if c.proof {
                        continue; // nothing left to learn there
                    }
                    let g = if self.r(R_GAMMA) && node.moves[i].is_zeroing() {
                        1.0 // progress edges carry value undamped; cycles
                            // can only pass through non-zeroing moves, so
                            // the contraction that damps them is intact
                    } else {
                        GAMMA
                    };
                    let q = if self.r(R_MLH) {
                        let qp = -g * c.value;
                        qp + m_utility(qp, c.mlh, node.mlh, self.ml_thresh)
                    } else {
                        -g * eff_value(c.value, c.mlh)
                    };
                    let n_eff = if self.r(R_UFLIGHT) {
                        c.evals as f64 + inflight
                    } else {
                        c.evals as f64
                    };
                    (
                        q,
                        cpuct * node.priors[i] as f64 * sqrt_n
                            / (1.0 + n_eff)
                            + self.c_var
                                * (c.variance / (1.0 + c.evals as f64)).sqrt(),
                        Some(k),
                        c.evals,
                    )
                }
            };
            // Legacy in-flight loss: a Q penalty scaled by evidence (a flat
            // penalty spread the search near-uniform; uncapped damping
            // deadlocked tiny endgames — see the vloss saga). Under
            // R_UFLIGHT the in-flight count lives in the U denominator
            // instead (the lc0 way) and Q stays honest.
            let q = if self.r(R_UFLIGHT) {
                q
            } else {
                let damp = (1.0 + child_evals as f64).sqrt();
                q - self.vloss_w * inflight / damp
            };
            let s = q + u;
            if s > best_s {
                best_s = s;
                best_i = i as i64;
                best_child = child_key;
            }
        }
        (best_i, best_child)
    }

    fn is_repetition(
        &self, current: u64, clock: u32,
        path_keys: &[u64], n: u32,
    ) -> bool {
        // count occurrences of `current` within the reversible window,
        // scanning the descent path first, then the game history. skip(1)
        // applies ONLY to the path (its last entry IS the current position);
        // the game history's last entry is the ROOT — a genuine prior
        // occurrence. Skipping it made the engine blind to repetitions that
        // include the root: it walked into a claimable threefold while +3
        // on lichess and the losing opponent claimed the draw.
        let mut count = 1u32;
        let mut steps = 0u32;
        for k in path_keys.iter().rev().skip(1) {
            steps += 1;
            if steps > clock {
                return count >= n;
            }
            if *k == current {
                count += 1;
                if count >= n {
                    return true;
                }
            }
        }
        for k in self.hist_keys.iter().rev() {
            steps += 1;
            if steps > clock {
                break;
            }
            if *k == current {
                count += 1;
                if count >= n {
                    return true;
                }
            }
        }
        count >= n
    }

    /// Exact result for the side to move, or None. Mirrors _terminal_value.
    fn terminal_value(
        &self, pos: &Chess, clock: u32, zkey: u64, path_keys: &[u64],
    ) -> Option<f64> {
        if pos.legal_moves().is_empty() {
            return Some(if pos.is_check() { -1.0 } else { 0.0 });
        }
        if pos.is_insufficient_material() {
            return Some(0.0);
        }
        if clock >= 150 {
            return Some(0.0);
        }
        if clock >= 8 && self.is_repetition(zkey, clock, path_keys, 5) {
            return Some(0.0);
        }
        if self.strict_draws {
            if clock >= 100 {
                return Some(0.0);
            }
            if clock >= 8 && self.is_repetition(zkey, clock, path_keys, 3) {
                return Some(0.0);
            }
        }
        None
    }

    fn claimable(&self, clock: u32, zkey: u64, path_keys: &[u64]) -> bool {
        clock >= 100
            || (clock >= 8 && self.is_repetition(zkey, clock, path_keys, 3))
    }

    fn probe_tb(&self, pos: &Chess, clock: u32) -> Option<(f64, u32, f64)> {
        let tb = self.tb.as_ref()?;
        if pos.board().occupied().count() as u32 > self.tb_max_men
            || pos.castles().any()
        {
            return None;
        }
        let wdl = tb.probe_wdl(pos).ok()?;
        use shakmaty_syzygy::AmbiguousWdl;
        let decisive = match wdl {
            AmbiguousWdl::Win => Some(1.0),
            AmbiguousWdl::Loss => Some(-1.0),
            // draws, cursed/blessed, and rounding-ambiguous results all
            // collapse to a clock-safe draw: never a false decisive proof
            _ => None,
        };
        match decisive {
            None => Some((0.0, 0, 1.0)),
            Some(sign) => {
                let dtz = match tb.probe_dtz(pos) {
                    Ok(d) => d.ignore_rounding(),
                    Err(_) => return Some((0.0, 0, 1.0)), // WDL-only: be safe
                };
                let need = i32::from(dtz).unsigned_abs();
                let headroom = 100u32.saturating_sub(clock);
                if need > headroom {
                    Some((0.0, 0, 1.0)) // the 50-move rule draws it first
                } else {
                    Some((sign, need, need as f64))
                }
            }
        }
    }

    /// Build the encoder job for the current descent state.
    fn encode_job(
        &self, pos: &Chess, clock: u32,
        path_frames: &[Frame], path_keys: &[u64], path_clocks: &[u32],
    ) -> EncodeJob {
        // unified newest-first view over descent + game history
        let total_frames = path_frames.len() + self.hist_frames.len();
        let take = total_frames.min(8);
        let mut frames: Vec<Frame> = Vec::with_capacity(take);
        let mut keys: Vec<u64> = Vec::with_capacity(take);
        let mut clocks: Vec<u32> = Vec::with_capacity(take);
        let get = |i: usize| -> (Frame, u64, u32) {
            // i = 0 is the leaf (last descent entry); walk backwards
            if i < path_frames.len() {
                let j = path_frames.len() - 1 - i;
                (path_frames[j], path_keys[j], path_clocks[j])
            } else {
                let j = self.hist_frames.len() - 1 - (i - path_frames.len());
                (self.hist_frames[j], self.hist_keys[j], self.hist_clocks[j])
            }
        };
        for i in 0..take {
            let (f, k, c) = get(i);
            frames.push(f);
            keys.push(k);
            clocks.push(c);
        }
        // repetition flags: frame i repeats if its key occurs earlier within
        // its 50-move window. CAPPED at 8 plies back from the leaf — the
        // validated Python engine hands the oracle board.copy(stack=8), so
        // its rep plane never sees repeats further back. The compiled core
        // must feed the net IDENTICAL features or it plays a different
        // (unvalidated) game: scanning the full history here produced
        // phantom repetition flags in long maneuvering sequences and
        // measurably weaker play. (Claim/terminal detection still uses the
        // full history — that is rules, this is net input.)
        let mut reps = vec![false; take];
        for i in 0..take {
            let limit = (clocks[i] as usize)
                .min(total_frames - 1 - i)
                .min(8usize.saturating_sub(i));
            for j in 1..=limit {
                let (_, kj, _) = get(i + j);
                if kj == keys[i] {
                    reps[i] = true;
                    break;
                }
            }
        }
        let stm_black = pos.turn() == Color::Black;
        let castling = [
            pos.castles().has(pos.turn(), CastlingSide::QueenSide),
            pos.castles().has(pos.turn(), CastlingSide::KingSide),
            pos.castles().has(!pos.turn(), CastlingSide::QueenSide),
            pos.castles().has(!pos.turn(), CastlingSide::KingSide),
        ];
        // oldest available position (for ep fixup): only matters when the
        // whole game fits in <8 frames
        let oldest_is_root = take == total_frames;
        // The oldest frame in a root-reaching window IS the game-root FEN's
        // position: its ep square and side-to-move drive lc0's pre-history
        // un-move fixup (only consulted when history is shorter than 8 plies).
        let ep = if oldest_is_root { self.fen_ep } else { None };
        EncodeJob {
            frames,
            reps,
            stm_black,
            castling,
            halfmove: clock,
            fill_history: oldest_is_root,
            started_from_startpos: self.started_from_startpos,
            ep_square: ep,
            oldest_black_to_move: self.fen_black_to_move,
        }
    }

    pub fn reset_flight(&mut self) {
        self.vloss.clear();
        // NOTE: reset_flight is a per-BATCH hook (called after every integrate
        // to clear vloss residue), NOT per-search -- so root_edge_visits is
        // re-zeroed per-SEARCH by the root-key epoch in select_batch, not here.
    }

    /// Descend up to `want` times, queueing fresh leaves for evaluation.
    /// Returns the number of leaves pending (including the root special).
    pub fn select_batch(&mut self, want: usize) -> usize {
        self.pending.clear();
        let root_pos = match &self.root_pos {
            Some(p) => p.clone(),
            None => return 0,
        };
        // Root missing or move-less (a seeded ledger pin — proof or not, the
        // root must offer real moves): evaluate the root itself fresh.
        let need_root = match self.nodes.get(&self.root_key) {
            None => true,
            Some(n) => n.moves.is_empty(),
        };
        if need_root {
            let job = self.encode_job(&root_pos, self.root_halfmove, &[], &[], &[]);
            self.pending.push(PendingLeaf {
                key: self.root_key,
                parent_key: 0,
                move_idx: 0,
                path: Vec::new(),
                edge_path: Vec::new(),
                pos: root_pos,
                job,
                claim: false,
                halfmove: self.root_halfmove,
            });
            return 1;
        }

        // Structure lever: per-SEARCH re-zero of the clean per-root-edge visit
        // counter. reset_flight is per-BATCH (clears vloss after each integrate)
        // so it CANNOT own this reset; instead re-zero when the root identity
        // changed (new search / new ply) or the move count differs. Within one
        // search (same root_key) it then accumulates across all select_batch
        // calls. Gated; zero work when off.
        if self.r(R_VISITREAD) {
            let nm = self.nodes.get(&self.root_key)
                .map(|n| n.moves.len()).unwrap_or(0);
            if self.root_visit_epoch != self.root_key
                || self.root_edge_visits.len() != nm
            {
                self.root_edge_visits = vec![0; nm];
                self.root_visit_epoch = self.root_key;
            }
        }

        let mut out_keys: FxHashSet<u64> = FxHashSet::default();
        let mut misses = 0usize;
        let max_misses = want * 2 + 8;
        while self.pending.len() < want && misses < max_misses {
            {
                let root = self.nodes.get(&self.root_key).unwrap();
                if root.proof || root.moves.is_empty() {
                    break;
                }
            }
            let mut pos = root_pos.clone();
            let mut clock = self.root_halfmove;
            let mut node_key = self.root_key;
            let mut path: Vec<u64> = vec![self.root_key];
            let mut seen: FxHashSet<u64> = FxHashSet::default();
            seen.insert(self.root_key);
            let mut path_zkeys: Vec<u64> = Vec::new();
            let mut path_clocks: Vec<u32> = Vec::new();
            let mut path_frames: Vec<Frame> = Vec::new();
            let mut edge_path: Vec<(u64, u32)> = Vec::new();

            let mut retries = 0u32;
            'descent: loop {
                let (i, child_key) = {
                    let node = self.nodes.get(&node_key).unwrap();
                    self.score_moves(node, node_key)
                };
                if i < 0 {
                    // every move proven: node will settle to a proof itself
                    self.mark_dirty(node_key, 1.0);
                    misses += 1;
                    self.miss_proven += 1;
                    break 'descent;
                }
                let mv = {
                    let node = self.nodes.get(&node_key).unwrap();
                    node.moves[i as usize].clone()
                };
                let saved_pos = pos.clone();
                let saved_clock = clock;
                clock = if mv.is_zeroing() { 0 } else { clock + 1 };
                pos.play_unchecked(&mv);
                let zkey = zobrist(&pos);
                path_zkeys.push(zkey);
                path_clocks.push(clock);
                path_frames.push(Frame::of(&pos));
                edge_path.push((node_key, i as u32));

                if let Some(ck) = child_key {
                    if seen.contains(&ck) || path.len() > 128 {
                        self.mark_dirty(node_key, 0.5);
                        misses += 1;
                        self.miss_cycle += 1;
                        break 'descent;
                    }
                    // Proof-burst candidate: a saturated belief with no
                    // theorem, position in hand right here on the descent.
                    if self.bursts_on && self.burst_cands.len() < 32 {
                        if let Some(c) = self.nodes.get(&ck) {
                            if c.value > 0.92 && !c.proof && !c.moves.is_empty()
                                && !self.burst_cands.iter().any(|(k, _)| *k == ck)
                            {
                                self.burst_cands.push((ck, pos.clone()));
                            }
                        }
                    }
                    node_key = ck;
                    path.push(ck);
                    seen.insert(ck);
                    continue 'descent;
                }

                // Unevaluated edge: terminal, claim, transposition, or leaf.
                let tv = self.terminal_value(&pos, clock, zkey, &path_zkeys);
                // R_TWOFOLD (lc0's two-fold-draws rule, RESTRICTED to the
                // descent path): a repetition loop the search itself walked
                // is pinned as an in-tree draw — going around a cycle gains
                // nothing, and the pin collapses it in one step instead of
                // letting gamma-contraction grind it down over thousands of
                // backups. Repeats against GAME history are deliberately
                // excluded: those are claim-world positions (the opponent
                // may decline at the board — the Ra8 lesson) and stay with
                // the n=3 claim machinery. The pin lives on the rep-salted
                // key (transposition-safe) and is path_cond, so it can
                // never leak into the proof ledger.
                let twofold_in_path = self.r(R_TWOFOLD)
                    && clock >= 4
                    && path_zkeys
                        .iter()
                        .rev()
                        .skip(1) // last entry IS the current position
                        .take(clock as usize)
                        .any(|k| *k == zkey);
                // rank-2 B SAFE SUBSET: only PIN the in-path twofold when the
                // floor is allowed. d_for(pos.turn) is the mover-relative draw
                // value; rep_floor_ok de-forces ONLY the WINNING side's pin
                // (f<0). When refused, fall through: the edge is left unpinned
                // and handled by the normal claim/terminal/leaf machinery,
                // re-validated after the opponent's actual reply. NOTE the
                // unpinned cycle re-enters gamma-contraction (GAMMA=0.997)
                // plus the seen-set / path.len()>128 guards -- it still damps
                // to a draw and cannot loop (validate node counts).
                let twofold_pin = twofold_in_path
                    && self.rep_floor_ok(self.d_for(pos.turn() == Color::White));
                if tv.is_none() && twofold_pin {
                    let key = position_key_cf(&pos, clock, true,
                                              self.r(R_COARSER50),
                                              self.r(R_FINER50));
                    if !self.nodes.contains_key(&key) {
                        let mut term = Node::terminal_node(
                            0.0, pos.turn() == Color::White);
                        term.path_cond = true;
                        // gated contempt: a winning side values this in-tree
                        // draw as < 0 and routes away from the rep loop.
                        let f = self.d_for(term.turn_white);
                        term.value = f;
                        term.v_them = f;
                        self.nodes.insert(key, term);
                        self.terminals_found += 1;
                    }
                    let n = self.nodes.get_mut(&key).unwrap();
                    if !n.parents.contains(&node_key) {
                        n.parents.push(node_key);
                    }
                    if let Some(p) = self.nodes.get_mut(&node_key) {
                        p.child_keys[i as usize] = Some(key);
                    }
                    self.mark_dirty(node_key, 1.0);
                    misses += 1;
                    self.miss_terminal += 1;
                    break 'descent;
                }
                let claim = tv.is_none() && !self.strict_draws
                    && self.claimable(clock, zkey, &path_zkeys);
                let rep = claim
                    || (tv == Some(0.0)
                        && !pos.legal_moves().is_empty()
                        && !pos.is_insufficient_material());
                let key = position_key_cf(&pos, clock, rep,
                                          self.r(R_COARSER50), self.r(R_FINER50));

                if let Some(t) = tv {
                    if !self.nodes.contains_key(&key) {
                        let mut term =
                            Node::terminal_node(t, pos.turn() == Color::White);
                        if rep {
                            term.path_cond = true;
                        }
                        // gated contempt on a DRAW terminal only (t==0.0);
                        // mate/stalemate (t==+-1.0) keep their exact value.
                        if t == 0.0 {
                            let f = self.d_for(term.turn_white);
                            term.value = f;
                            term.v_them = f;
                        }
                        self.nodes.insert(key, term);
                        self.terminals_found += 1;
                    }
                    let n = self.nodes.get_mut(&key).unwrap();
                    if !n.parents.contains(&node_key) {
                        n.parents.push(node_key);
                    }
                    if let Some(p) = self.nodes.get_mut(&node_key) {
                        p.child_keys[i as usize] = Some(key);
                    }
                    self.mark_dirty(node_key, 1.0);
                    misses += 1;
                    self.miss_terminal += 1;
                    break 'descent;
                }
                if self.nodes.contains_key(&key) {
                    // transposition: link and keep descending through it
                    {
                        let n = self.nodes.get_mut(&key).unwrap();
                        if !n.parents.contains(&node_key) {
                            n.parents.push(node_key);
                        }
                    }
                    if let Some(p) = self.nodes.get_mut(&node_key) {
                        p.child_keys[i as usize] = Some(key);
                    }
                    self.mark_dirty(node_key, 0.5);
                    if seen.contains(&key) || path.len() > 128 {
                        misses += 1;
                        break 'descent;
                    }
                    node_key = key;
                    path.push(key);
                    seen.insert(key);
                    continue 'descent;
                }
                // tablebase: a proof oracle (skip claimable positions)
                if !claim {
                    if let Some((tbv, dist, mlh)) = self.probe_tb(&pos, clock) {
                        let tnode = Node::pinned(
                            tbv, dist, mlh, pos.turn() == Color::White);
                        self.nodes.insert(key, tnode);
                        self.tb_hits += 1;
                        let n = self.nodes.get_mut(&key).unwrap();
                        if !n.parents.contains(&node_key) {
                            n.parents.push(node_key);
                        }
                        if let Some(p) = self.nodes.get_mut(&node_key) {
                            p.child_keys[i as usize] = Some(key);
                        }
                        self.mark_dirty(node_key, 1.0);
                        misses += 1;
                        break 'descent;
                    }
                }
                if out_keys.contains(&key) {
                    // This leaf is already in the batch via another path.
                    // Don't waste the whole descent (the Python engine did,
                    // capping batches at ~34 leaves and starving the GPU):
                    // penalize the edge, roll back one step, and pick the
                    // next-best move at the same node.
                    *self.vloss.entry((node_key, i as u32)).or_insert(0) += 1;
                    self.miss_dup += 1;
                    retries += 1;
                    if retries > 8 {
                        // Saturated descent: just give up this attempt. Do
                        // NOT plant path-wide vloss here — unlike a leaf's
                        // in-flight loss (released by integrate), nothing
                        // would ever remove it, and the phantom penalties
                        // accumulate on exactly the engine's best lines,
                        // pushing the search off its principal variation as
                        // the move progresses.
                        misses += 1;
                        break 'descent;
                    }
                    pos = saved_pos;
                    clock = saved_clock;
                    path_zkeys.pop();
                    path_clocks.pop();
                    path_frames.pop();
                    edge_path.pop();
                    continue 'descent;
                }
                // fresh leaf: in-flight loss along the WHOLE route so the
                // next descent forks as early as it profitably can
                let job = self.encode_job(
                    &pos, clock, &path_frames, &path_zkeys, &path_clocks);
                for (k, ix) in &edge_path {
                    *self.vloss.entry((*k, *ix)).or_insert(0) += 1;
                }
                out_keys.insert(key);
                self.pending.push(PendingLeaf {
                    key,
                    parent_key: node_key,
                    move_idx: i as usize,
                    path: path.clone(),
                    edge_path,
                    pos: pos.clone(),
                    job,
                    claim,
                    halfmove: clock,
                });
                break 'descent;
            }
        }
        self.pending.len()
    }

    /// Encode all pending leaves into a flat [n, 112*64] f32 buffer.
    pub fn encode_pending(&self) -> Vec<f32> {
        let n = self.pending.len();
        let mut out = vec![0f32; n * 112 * 64];
        for (i, leaf) in self.pending.iter().enumerate() {
            encode(&leaf.job, &mut out[i * 112 * 64..(i + 1) * 112 * 64]);
        }
        out
    }

    pub fn policy_index_pub(&self, m: &Move, flip: bool) -> Option<u16> {
        self.policy_index(m, flip)
    }

    /// Map a shakmaty move to its lc0 policy index for the given side.
    fn policy_index(&self, m: &Move, flip: bool) -> Option<u16> {
        let (mut from, mut to, promo) = match m {
            Move::Castle { king, rook } => (sq(*king), sq(*rook), 0u8),
            _ => {
                let from = sq(m.from()?);
                let to = sq(m.to());
                let promo = match m.promotion() {
                    Some(Role::Queen) => 1u8,
                    Some(Role::Rook) => 2,
                    Some(Role::Bishop) => 3,
                    _ => 0, // none or knight (bare move string)
                };
                (from, to, promo)
            }
        };
        if flip {
            from ^= 56;
            to ^= 56;
        }
        self.policy.index(from, to, promo)
    }

    /// Fold one GPU batch into the lattice. Returns evals integrated.
    pub fn integrate(
        &mut self, policy: &[f32], wdl: &[f32], mlh: Option<&[f32]>,
    ) -> usize {
        let n = self.pending.len();
        let pending = std::mem::take(&mut self.pending);
        for (bi, leaf) in pending.iter().enumerate() {
            // --- decode wdl (already probabilities, renormalize) ---
            let (mut w, mut d, mut l) = (
                wdl[bi * 3] as f64,
                wdl[bi * 3 + 1] as f64,
                wdl[bi * 3 + 2] as f64,
            );
            let s = w + d + l;
            if s > 0.0 {
                w /= s;
                d /= s;
                l /= s;
            }
            let mlh_v = mlh.map(|m| (m[bi] as f64).max(0.0)).unwrap_or(60.0);

            // The root special (parent_key 0) must REPLACE whatever sits at
            // its key: a ledger-seeded moves-less proof pin cannot serve as
            // a root, and the fresh evaluation supersedes it.
            if leaf.parent_key == 0 || !self.nodes.contains_key(&leaf.key) {
                // --- decode policy over legal moves ---
                let legal = leaf.pos.legal_moves();
                let flip = leaf.pos.turn() == Color::Black;
                let logits: Vec<f32> = legal
                    .iter()
                    .map(|m| {
                        self.policy_index(m, flip)
                            .map(|ix| policy[bi * 1858 + ix as usize])
                            .unwrap_or(-80.0)
                    })
                    .collect();
                let mx = logits.iter().cloned().fold(f32::MIN, f32::max);
                // R_TEMP: BT4's match-play behavior was tuned around lc0's
                // policy-softmax-temp 1.359 — flattened priors. Temp 1.0
                // over-concentrates the search on the net's first choice.
                let tmp = if self.r(R_TEMP) { POLICY_TEMP } else { 1.0 };
                let mut priors: Vec<f32> =
                    logits.iter().map(|x| ((x - mx) / tmp).exp()).collect();
                let psum: f32 = priors.iter().sum::<f32>().max(1e-12);
                for p in &mut priors {
                    *p /= psum;
                }
                let ctx = Self::context_of(&leaf.pos);
                let base_v = ((w - l) + self.correction(ctx)).clamp(-0.999, 0.999);
                let raw_v = (base_v
                    + self.corrector_delta(&leaf.pos, base_v, mlh_v))
                    .clamp(-0.999, 0.999);
                let mut node = Node::fresh(
                    [w, d, l],
                    raw_v,
                    legal.to_vec(),
                    priors,
                    ctx,
                    mlh_v,
                    leaf.pos.turn() == Color::White,
                );
                if leaf.claim {
                    node.claim_floor = true;
                    node.path_cond = true;
                    let f = self.d_for(node.turn_white);
                    // rank-2 B SAFE SUBSET: de-force ONLY the WINNING side's
                    // floor-DOWN (f<0). The losing/equal floor-UP (f>=0) is
                    // UNCONDITIONAL (rep_floor_ok true for f>=0). The
                    // forcing_rep Node field + is_check forcing proxy are HELD
                    // (the is_check proxy is at the wrong node for the saver).
                    if self.rep_floor_ok(f) && node.value < f {
                        node.value = f;
                        if f >= 0.0 {
                            node.wdl = [w, d + l, 0.0];
                        }
                        if node.v_them < f {
                            node.v_them = f;
                        }
                    }
                }
                self.nodes.insert(leaf.key, node);
            }
            if leaf.parent_key != 0 {
                {
                    let nd = self.nodes.get_mut(&leaf.key).unwrap();
                    if !nd.parents.contains(&leaf.parent_key) {
                        nd.parents.push(leaf.parent_key);
                    }
                }
                if let Some(p) = self.nodes.get_mut(&leaf.parent_key) {
                    p.child_keys[leaf.move_idx] = Some(leaf.key);
                }
                self.mark_dirty(leaf.parent_key, 1.0);
            }
            // release the in-flight loss along the whole route
            for (k, ix) in &leaf.edge_path {
                if let Some(v) = self.vloss.get_mut(&(*k, *ix)) {
                    if *v > 1 {
                        *v -= 1;
                    } else {
                        self.vloss.remove(&(*k, *ix));
                    }
                }
            }
            // Structure lever: credit this integrated fresh leaf to the ROOT
            // edge it descended through (edge_path[0] is the root edge by
            // construction -- the descent seeds path=[root_key] and pushes the
            // first edge at the root). The clean per-root-edge analog of
            // node.evals; terminal/TB/cycle/dup descents produce no PendingLeaf
            // and are correctly not counted. Gated; zero work when off.
            if self.r(R_VISITREAD) {
                if let Some(&(k0, i0)) = leaf.edge_path.first() {
                    if k0 == self.root_key {
                        if let Some(c) = self.root_edge_visits.get_mut(i0 as usize) {
                            *c += 1;
                        }
                    }
                }
            }
            // evidence accounting + palimpsest lessons along the path
            for k in &leaf.path {
                let lesson = {
                    match self.nodes.get_mut(k) {
                        None => None,
                        Some(pn) => {
                            pn.evals += 1;
                            if pn.evals == LESSON_EVIDENCE && !pn.observed
                                && pn.ctx != 0
                            {
                                pn.observed = true;
                                Some((pn.ctx, pn.value - pn.raw_value))
                            } else {
                                None
                            }
                        }
                    }
                };
                if let Some((ctx, les)) = lesson {
                    self.observe(ctx, les);
                }
            }
        }
        self.settle(20000);
        n
    }

    // ------------------------------------------------------------- queries

    pub fn children_of(&self, key: u64)
        -> Vec<(String, f64, f64, f64, u32, bool, u32, f64, f64, f64, f64, bool)>
    {
        let mut out = Vec::new();
        if let Some(node) = self.nodes.get(&key) {
            for (i, ck) in node.child_keys.iter().enumerate() {
                if let Some(c) = ck.and_then(|k| self.nodes.get(&k)) {
                    out.push((
                        node.moves[i].to_uci(CastlingMode::Standard).to_string(),
                        c.value,
                        c.v_them,
                        c.variance,
                        c.evals,
                        c.proof,
                        c.proof_dist,
                        c.mlh,
                        c.wdl[0],
                        c.wdl[1],
                        c.wdl[2],
                        c.claim_floor,
                    ));
                }
            }
        }
        out
    }

    /// READ-ONLY introspection for the SMAB premise gate: walk the principal
    /// variation starting at the root move `root_move_uci` (the best-child
    /// chain, descending the max-q child each ply) up to `max_depth` plies, and
    /// return per ply (best_q, second_q, n_expanded) where q = -g*child.value is
    /// EXACTLY the quantity backup ranks on (same zeroing/GAMMA convention).
    /// second_q is NaN when fewer than 2 children are expanded. Does not mutate
    /// anything; the lattice and its behavior are untouched.
    pub fn pv_child_gaps(&self, root_move_uci: &str, max_depth: usize)
        -> Vec<(f64, f64, i64)>
    {
        let mut out = Vec::new();
        let root = match self.nodes.get(&self.root_key) {
            Some(n) => n,
            None => return out,
        };
        let mut key = None;
        for (i, m) in root.moves.iter().enumerate() {
            if m.to_uci(CastlingMode::Standard).to_string() == root_move_uci {
                key = root.child_keys[i];
                break;
            }
        }
        let mut key = match key {
            Some(k) => k,
            None => return out,
        };
        for _ in 0..max_depth {
            let node = match self.nodes.get(&key) {
                Some(n) => n,
                None => break,
            };
            if node.proof || node.moves.is_empty() {
                break;
            }
            let mut qs: Vec<(f64, u64)> = Vec::new();
            for (idx, ck) in node.child_keys.iter().enumerate() {
                if let Some(c) = ck.and_then(|k| self.nodes.get(&k)) {
                    let g = if self.r(R_GAMMA) && node.moves[idx].is_zeroing() {
                        1.0
                    } else {
                        GAMMA
                    };
                    qs.push((-g * c.value, ck.unwrap()));
                }
            }
            if qs.is_empty() {
                break;
            }
            qs.sort_by(|a, b| b.0.total_cmp(&a.0));
            let best_q = qs[0].0;
            let second_q = if qs.len() >= 2 { qs[1].0 } else { f64::NAN };
            out.push((best_q, second_q, qs.len() as i64));
            key = qs[0].1;
        }
        out
    }

    /// Structure lever: clean per-root-edge visit counts, aligned index-for-
    /// index with children_of(root_key) / root_children() (same expanded-only
    /// filter), so the Python readout can zip vis[i] with scored[i].
    pub fn root_edge_visits_aligned(&self) -> Vec<u32> {
        let mut out = Vec::new();
        if let Some(node) = self.nodes.get(&self.root_key) {
            for (i, ck) in node.child_keys.iter().enumerate() {
                if ck.and_then(|k| self.nodes.get(&k)).is_some() {
                    out.push(self.root_edge_visits.get(i).copied().unwrap_or(0));
                }
            }
        }
        out
    }

    pub fn root_moves_with_priors(&self) -> Vec<(String, f32, bool)> {
        let mut out = Vec::new();
        if let Some(node) = self.nodes.get(&self.root_key) {
            for (i, m) in node.moves.iter().enumerate() {
                out.push((
                    m.to_uci(CastlingMode::Standard).to_string(),
                    node.priors[i],
                    node.child_keys[i].is_some(),
                ));
            }
        }
        out
    }

    pub fn export_proofs(&self, max_dist: u32)
        -> (Vec<u64>, Vec<f32>, Vec<u16>, Vec<f32>, Vec<u8>)
    {
        let mut keys = Vec::new();
        let mut vals = Vec::new();
        let mut dists = Vec::new();
        let mut mlhs = Vec::new();
        let mut turns = Vec::new();
        for (k, n) in &self.nodes {
            if n.proof && n.proof_dist >= 2 && n.proof_dist <= max_dist
                && !n.claim_floor && !n.path_cond
            {
                keys.push(*k);
                vals.push(n.value as f32);
                dists.push(n.proof_dist as u16);
                mlhs.push(n.mlh as f32);
                turns.push(n.turn_white as u8);
            }
        }
        (keys, vals, dists, mlhs, turns)
    }

    pub fn seed_proofs(
        &mut self, keys: &[u64], vals: &[f32], dists: &[u16], mlhs: &[f32],
        turns: &[u8],
    ) -> usize {
        let mut n = 0;
        for i in 0..keys.len() {
            if !self.nodes.contains_key(&keys[i]) {
                self.nodes.insert(
                    keys[i],
                    Node::pinned(
                        vals[i] as f64,
                        dists[i] as u32,
                        mlhs[i] as f64,
                        turns[i] != 0,
                    ),
                );
                n += 1;
            }
        }
        n
    }

    /// Promote saturated beliefs into theorems: bounded checking-mate search
    /// on candidates snapshotted during descent. Returns proofs minted.
    pub fn prove_burst(&mut self, budget: i64) -> usize {
        if !self.bursts_on || self.burst_cands.is_empty() {
            return 0;
        }
        let cands = std::mem::take(&mut self.burst_cands);
        let per = (budget / cands.len() as i64).max(2000);
        let mut minted = 0;
        for (key, pos) in cands {
            let still_wanted = match self.nodes.get(&key) {
                Some(n) => !n.proof && n.value > 0.9,
                None => false,
            };
            if !still_wanted {
                continue;
            }
            if let Some(plies) = find_mate(&pos, 9, per) {
                let parents = {
                    let n = self.nodes.get_mut(&key).unwrap();
                    n.value = GAMMA.powi(plies as i32);
                    n.wdl = [1.0, 0.0, 0.0];
                    n.variance = 0.0;
                    n.proof = true;
                    n.proof_dist = plies;
                    n.mlh = plies as f64;
                    n.v_them = n.value;
                    n.parents.clone()
                };
                for pk in parents {
                    self.mark_dirty(pk, 1.0);
                }
                minted += 1;
                self.proofs_minted += 1;
            }
        }
        if minted > 0 {
            self.settle(20000);
        }
        minted
    }

    pub fn clear(&mut self, keep_lessons: bool) {
        self.nodes.clear();
        self.heap.clear();
        self.vloss.clear();
        self.pending.clear();
        self.root_edge_visits.clear();
        self.burst_cands.clear();
        if !keep_lessons {
            self.lessons.clear();
        }
    }
}
