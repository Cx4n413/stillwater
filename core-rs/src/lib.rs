use numpy::{IntoPyArray, PyArray1, PyArray2, PyReadonlyArray1, PyReadonlyArray2};
use pyo3::prelude::*;

mod encoder;
mod engine;
mod keys;
mod policy;
mod prover;

#[pyfunction]
fn position_key_of(fen: &str, moves: Vec<String>, rep: bool) -> PyResult<u64> {
    keys::position_key_from_fen(fen, &moves, rep)
        .map_err(pyo3::exceptions::PyValueError::new_err)
}

#[pyclass]
struct Core {
    inner: engine::Core,
}

#[pymethods]
impl Core {
    #[new]
    #[pyo3(signature = (syzygy_path=None, strict_draws=false,
                        max_nodes=2_500_000, palimpsest_on=true, tb_max_men=5))]
    fn new(syzygy_path: Option<String>, strict_draws: bool, max_nodes: usize,
           palimpsest_on: bool, tb_max_men: u32) -> Core {
        Core {
            inner: engine::Core::new(syzygy_path, strict_draws, max_nodes,
                                     palimpsest_on, tb_max_men),
        }
    }

    fn set_position(&mut self, fen: &str, moves: Vec<String>) -> PyResult<()> {
        self.inner
            .set_position(fen, &moves)
            .map_err(pyo3::exceptions::PyValueError::new_err)
    }

    #[pyo3(signature = (rho, lens_on, draw_contempt=0.0, root_q0=0.0))]
    fn set_search(&mut self, rho: f64, lens_on: bool,
                  draw_contempt: f64, root_q0: f64) {
        self.inner.set_search(rho, lens_on, draw_contempt, root_q0);
    }

    fn set_features(&mut self, bursts: bool, thompson: bool) {
        self.inner.set_features(bursts, thompson);
    }

    fn set_refine(&mut self, mask: u32) {
        self.inner.set_refine(mask);
    }

    #[pyo3(signature = (lcb_k, fpu_red, ml_thresh, cpuct_init=1.745,
                        cpuct_factor=3.894, c_var=0.35, vloss_w=0.85))]
    fn set_tunables(&mut self, lcb_k: f64, fpu_red: f64, ml_thresh: f64,
                    cpuct_init: f64, cpuct_factor: f64, c_var: f64,
                    vloss_w: f64) {
        self.inner.set_tunables(lcb_k, fpu_red, ml_thresh, cpuct_init,
                                cpuct_factor, c_var, vloss_w);
    }

    fn set_honest_k(&mut self, k: f64) {
        self.inner.set_honest_k(k);
    }

    fn set_voi(&mut self, on: bool) {
        self.inner.set_voi(on);
    }

    fn set_confback(&mut self, w: f64, cap: f64) {
        self.inner.set_confback(w, cap);
    }

    fn graph_stats(&self) -> (usize, usize, usize, usize, usize) {
        self.inner.graph_stats()
    }

    fn prove_burst(&mut self, py: Python<'_>, budget: i64) -> usize {
        py.allow_threads(|| self.inner.prove_burst(budget))
    }

    fn proofs_minted(&self) -> u64 {
        self.inner.proofs_minted
    }

    #[pyo3(signature = (beta=None))]
    fn set_corrector(&mut self, beta: Option<[f64; 8]>) {
        self.inner.set_corrector(beta);
    }

    fn reset_flight(&mut self) {
        self.inner.reset_flight();
    }

    /// Select up to `want` leaves; returns (planes [n,112,8,8] f32, n).
    fn select_batch<'py>(
        &mut self, py: Python<'py>, want: usize,
    ) -> (Bound<'py, PyArray2<f32>>, usize) {
        let (buf, n) = py.allow_threads(|| {
            let n = self.inner.select_batch(want);
            (self.inner.encode_pending(), n)
        });
        let arr = numpy::ndarray::Array2::from_shape_vec((n, 112 * 64), buf)
            .expect("shape");
        (arr.into_pyarray(py), n)
    }

    /// FENs of the pending leaves (mock-oracle and debugging path).
    fn pending_fens(&self) -> Vec<String> {
        use shakmaty::{fen::Fen, EnPassantMode, Position};
        self.inner
            .pending
            .iter()
            .map(|l| {
                Fen::from_position(l.pos.clone(), EnPassantMode::Legal)
                    .to_string()
            })
            .collect()
    }

    fn integrate(
        &mut self, py: Python<'_>, policy: PyReadonlyArray2<f32>,
        wdl: PyReadonlyArray2<f32>, mlh: Option<PyReadonlyArray1<f32>>,
    ) -> usize {
        let p = policy.as_slice().expect("policy contiguous");
        let w = wdl.as_slice().expect("wdl contiguous");
        let m = mlh.as_ref().map(|a| a.as_slice().expect("mlh contiguous"));
        py.allow_threads(|| self.inner.integrate(p, w, m))
    }

    fn settle(&mut self, py: Python<'_>, max_ops: usize) -> usize {
        py.allow_threads(|| self.inner.settle(max_ops))
    }

    fn root_key(&self) -> u64 {
        self.inner.root_key
    }

    /// ((value, w, d, l, variance, raw_value, raw_mlh, mlh),
    ///  (proof, proof_dist, evals, claim_floor, exists, has_moves,
    ///   path_cond))
    /// path_cond (rank-2 / Fix C): true when the root's settled belief is
    /// PATH-CONDITIONAL -- it rests on a repetition/claim cycle the search
    /// walked assuming the opponent cooperates (including a StrictDraws n=3
    /// hard terminal, which is rep-salted and path_cond). Python (Fix A) uses
    /// it to delay short-circuiting deliberation on a draw proof the opponent
    /// can decline, WITHOUT delaying unconditional draws (insufficient
    /// material / 50-move / stalemate, which are NOT path_cond). Additive 7th
    /// element: positional consumers (flags[0..5]) are unaffected.
    fn root_info(&self)
        -> ((f64, f64, f64, f64, f64, f64, f64, f64),
            (bool, u32, u32, bool, bool, bool, bool))
    {
        match self.inner.nodes.get(&self.inner.root_key) {
            None => ((0., 0., 0., 0., 0., 0., 60., 60.),
                     (false, 0, 0, false, false, false, false)),
            Some(n) => (
                (n.value, n.wdl[0], n.wdl[1], n.wdl[2], n.variance,
                 n.raw_value, n.raw_mlh, n.mlh),
                (n.proof, n.proof_dist, n.evals, n.claim_floor, true,
                 !n.moves.is_empty(), n.path_cond),
            ),
        }
    }

    /// Per evaluated root child: (uci, value, v_them, variance, evals,
    /// proof, proof_dist, mlh, w, d, l, claim_floor) — child's own stm view.
    fn root_children(&self)
        -> Vec<(String, f64, f64, f64, u32, bool, u32, f64, f64, f64, f64,
                bool)>
    {
        self.inner.children_of(self.inner.root_key)
    }

    fn root_edge_visits(&self) -> Vec<u32> {
        self.inner.root_edge_visits_aligned()
    }

    fn node_children(&self, key: u64)
        -> Vec<(String, f64, f64, f64, u32, bool, u32, f64, f64, f64, f64,
                bool)>
    {
        self.inner.children_of(key)
    }

    /// (uci, prior, expanded) for every root move (court phantom-arm data).
    fn root_moves(&self) -> Vec<(String, f32, bool)> {
        self.inner.root_moves_with_priors()
    }

    fn node_count(&self) -> usize {
        self.inner.nodes.len()
    }

    #[pyo3(signature = (keep_lessons=false))]
    fn clear(&mut self, keep_lessons: bool) {
        self.inner.clear(keep_lessons);
    }

    fn stats(&self) -> (u64, u64, u64, u64) {
        (self.inner.backups, self.inner.terminals_found, self.inner.tb_hits,
         self.inner.lessons_count)
    }

    /// (proven, cycle, terminal, batch-dup) selection-miss counters.
    fn miss_stats(&self) -> (u64, u64, u64, u64) {
        (self.inner.miss_proven, self.inner.miss_cycle,
         self.inner.miss_terminal, self.inner.miss_dup)
    }

    fn export_proofs<'py>(
        &self, py: Python<'py>, max_dist: u32,
    ) -> (Bound<'py, PyArray1<u64>>, Bound<'py, PyArray1<f32>>,
          Bound<'py, PyArray1<u16>>, Bound<'py, PyArray1<f32>>,
          Bound<'py, PyArray1<u8>>)
    {
        let (k, v, d, m, t) = self.inner.export_proofs(max_dist);
        (k.into_pyarray(py), v.into_pyarray(py), d.into_pyarray(py),
         m.into_pyarray(py), t.into_pyarray(py))
    }

    fn seed_proofs(
        &mut self, keys: PyReadonlyArray1<u64>, vals: PyReadonlyArray1<f32>,
        dists: PyReadonlyArray1<u16>, mlhs: PyReadonlyArray1<f32>,
        turns: PyReadonlyArray1<u8>,
    ) -> usize {
        self.inner.seed_proofs(
            keys.as_slice().expect("keys"),
            vals.as_slice().expect("vals"),
            dists.as_slice().expect("dists"),
            mlhs.as_slice().expect("mlhs"),
            turns.as_slice().expect("turns"),
        )
    }

    fn tb_open(&self) -> bool {
        self.inner.tb.is_some()
    }
}

/// Debug: lc0 policy index of every legal move in a FEN (cross-check vs
/// the Python LUT).
#[pyfunction]
fn policy_indices(fen: &str) -> PyResult<Vec<(String, i32)>> {
    use shakmaty::{fen::Fen, CastlingMode, Color, Position};
    let setup: Fen = fen
        .parse()
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("{e}")))?;
    let pos: shakmaty::Chess = setup
        .into_position(CastlingMode::Standard)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("{e}")))?;
    let core = engine::Core::new(None, false, 1000, false, 5);
    let flip = pos.turn() == Color::Black;
    Ok(pos
        .legal_moves()
        .iter()
        .map(|m| {
            (
                m.to_uci(CastlingMode::Standard).to_string(),
                core.policy_index_pub(m, flip).map(|x| x as i32).unwrap_or(-1),
            )
        })
        .collect())
}

#[pymodule]
fn stillwater_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(position_key_of, m)?)?;
    m.add_function(wrap_pyfunction!(policy_indices, m)?)?;
    m.add_class::<Core>()?;
    Ok(())
}
