//! Position keys, bit-compatible with the Python engine.
//!
//! key = polyglot zobrist  XOR  R50_SALTS[min(halfmove_clock >> 4, 7)]
//!       XOR (REP_SALT if the node is a repetition/claim-salted state)
//!
//! The salt constants were generated once by Python's Random(0x57111A7E)
//! and are frozen here verbatim so ledgers and proofs transfer between the
//! Python and Rust engines.

use shakmaty::fen::Fen;
use shakmaty::uci::UciMove;
use shakmaty::zobrist::{Zobrist64, ZobristHash};
use shakmaty::{CastlingMode, Chess, EnPassantMode, Position};

pub const R50_SALTS: [u64; 8] = [
    0x0000000000000000,
    0xd05249d8d79ccd3c,
    0x61b583b611931723,
    0x35426493c4d0f8ef,
    0xde2613a3ed4c3cbf,
    0x3828f61e98242612,
    0x1bc03637d4d5c482,
    0x53cf50ce8c1e15a3,
];
pub const REP_SALT: u64 = 0xf479fe444bfc61c8;

#[inline]
pub fn zobrist(pos: &Chess) -> u64 {
    pos.zobrist_hash::<Zobrist64>(EnPassantMode::Legal).0
}

#[inline]
pub fn position_key(pos: &Chess, halfmove_clock: u32, rep: bool) -> u64 {
    position_key_c(pos, halfmove_clock, rep, false)
}

/// Like `position_key_c` but with an explicit `finer` override (rank-2 B,
/// R_FINER50): when `coarse` is set, `finer` KEEPS the real 16-ply buckets
/// for clock < 64 instead of collapsing the whole sub-64 plateau to one
/// bucket. `finer` has no effect when `coarse` is false. `position_key_c`
/// forwards `finer = false`, so legacy callers are byte-identical.
#[inline]
pub fn position_key_cf(pos: &Chess, halfmove_clock: u32, rep: bool,
                       coarse: bool, finer: bool) -> u64 {
    let bucket = if coarse && halfmove_clock < 64 && !finer {
        0
    } else {
        std::cmp::min((halfmove_clock >> 4) as usize, 7)
    };
    let mut k = zobrist(pos) ^ R50_SALTS[bucket];
    if rep {
        k ^= REP_SALT;
    }
    k
}

/// `coarse`: one bucket below clock 64 (R_COARSER50). The fine 16-ply
/// buckets re-keyed the whole lattice six times across a 100-ply grind —
/// periodic amnesia in exactly the games lc0 ground us down in. Values
/// only genuinely depend on the clock near the 50-move horizon, so fine
/// buckets are kept for clock >= 64; claim/terminal RULES read the true
/// clock everywhere and are unaffected. NOTE: a different key scheme —
/// ledgers must not transfer across modes (fingerprint guard in python).
#[inline]
pub fn position_key_c(pos: &Chess, halfmove_clock: u32, rep: bool,
                      coarse: bool) -> u64 {
    // legacy entry point: finer = false preserves byte-identical keys.
    position_key_cf(pos, halfmove_clock, rep, coarse, false)
}

/// Replay a game and return the final position's key (for cross-checks).
pub fn position_key_from_fen(fen: &str, moves: &[String], rep: bool) -> Result<u64, String> {
    let setup: Fen = fen.parse().map_err(|e| format!("bad fen: {e}"))?;
    let mut pos: Chess = setup
        .into_position(CastlingMode::Standard)
        .map_err(|e| format!("illegal position: {e}"))?;
    let mut halfmove = pos.halfmoves();
    for u in moves {
        let uci: UciMove = u.parse().map_err(|e| format!("bad uci {u}: {e}"))?;
        let m = uci
            .to_move(&pos)
            .map_err(|e| format!("illegal move {u}: {e}"))?;
        halfmove = if m.is_zeroing() { 0 } else { halfmove + 1 };
        pos.play_unchecked(&m);
    }
    Ok(position_key(&pos, halfmove, rep))
}
