//! Proof bursts: the missing belief-to-proof promotion operator.
//!
//! When the lattice believes a position is nearly decided (|value| > 0.92)
//! but has no theorem, a bounded mate search tries to PROMOTE the belief to
//! a proof. Sound by construction: it only claims "side to move mates in n"
//! when an attacking line exists in which EVERY legal defender reply is
//! covered; attacker moves are restricted to checks (incomplete — quiet
//! mating moves are the search's job — but never wrong). A success enters
//! the lattice as a variance-zero pin and propagates rootward, ending court
//! deliberation and converting won positions with certainty.

use shakmaty::{Chess, Move, Position};

/// Does the side to move force mate within `plies` (odd: 1, 3, 5...)?
/// Decrements `budget` per node; returns false on exhaustion (never lies).
pub fn mate_in(pos: &Chess, plies: u32, budget: &mut i64) -> bool {
    *budget -= 1;
    if *budget <= 0 || plies == 0 {
        return false;
    }
    let legal = pos.legal_moves();
    for m in &legal {
        if !is_check_move(pos, m) {
            continue; // attackers play checks only: sound, incomplete
        }
        let mut p2 = pos.clone();
        p2.play_unchecked(m);
        if p2.is_checkmate() {
            return true;
        }
        if plies < 3 {
            continue;
        }
        if p2.is_stalemate() || p2.is_insufficient_material() {
            continue; // this check lets the defender off — try another
        }
        // every defender reply must be mated within plies-2
        let replies = p2.legal_moves();
        let mut all_mated = !replies.is_empty();
        for r in &replies {
            let mut p3 = p2.clone();
            p3.play_unchecked(r);
            if !mate_in(&p3, plies - 2, budget) {
                all_mated = false;
                break;
            }
            if *budget <= 0 {
                return false;
            }
        }
        if all_mated {
            return true;
        }
    }
    false
}

#[inline]
fn is_check_move(pos: &Chess, m: &Move) -> bool {
    let mut p2 = pos.clone();
    p2.play_unchecked(m);
    p2.is_check()
}

/// Iterative-deepening wrapper: shortest checking mate within `max_plies`,
/// or None. Total node budget shared across depths.
pub fn find_mate(pos: &Chess, max_plies: u32, budget: i64) -> Option<u32> {
    let mut left = budget;
    let mut d = 1;
    while d <= max_plies {
        if mate_in(pos, d, &mut left) {
            return Some(d);
        }
        if left <= 0 {
            return None;
        }
        d += 2;
    }
    None
}
