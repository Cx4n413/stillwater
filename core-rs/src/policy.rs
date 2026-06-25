//! Lc0 policy head index (1858 entries), ported from the Python generator
//! and byte-identical to lczero-training's policy_index.py.
//!
//! Layout: for every from-square (a1..h8), all queen-ray and knight
//! destinations sorted by destination square index; then the 66 q/r/b
//! underpromotions. Knight promotions use the bare from-to entry. Castling
//! is indexed king-takes-rook (e1h1). Black to move: squares are rank-
//! flipped (sq ^ 56) before lookup.

use rustc_hash::FxHashMap;

/// promo class: 0 = none/knight, 1 = queen, 2 = rook, 3 = bishop
pub type MoveKey = (u8, u8, u8);

pub struct PolicyMap {
    map: FxHashMap<MoveKey, u16>,
}

impl PolicyMap {
    pub fn new() -> Self {
        let mut entries: Vec<MoveKey> = Vec::with_capacity(1858);
        for fsq in 0u8..64 {
            let fr = (fsq / 8) as i32;
            let ff = (fsq % 8) as i32;
            let mut dests: Vec<u8> = Vec::new();
            for (dr, df) in [
                (0i32, 1i32), (0, -1), (1, 0), (-1, 0),
                (1, 1), (1, -1), (-1, 1), (-1, -1),
            ] {
                let (mut r, mut f) = (fr + dr, ff + df);
                while (0..8).contains(&r) && (0..8).contains(&f) {
                    dests.push((r * 8 + f) as u8);
                    r += dr;
                    f += df;
                }
            }
            for (dr, df) in [
                (1i32, 2i32), (2, 1), (2, -1), (1, -2),
                (-1, -2), (-2, -1), (-2, 1), (-1, 2),
            ] {
                let (r, f) = (fr + dr, ff + df);
                if (0..8).contains(&r) && (0..8).contains(&f) {
                    dests.push((r * 8 + f) as u8);
                }
            }
            dests.sort_unstable();
            dests.dedup();
            for t in dests {
                entries.push((fsq, t, 0));
            }
        }
        for ff in 0u8..8 {
            for tf in [ff as i32 - 1, ff as i32, ff as i32 + 1] {
                if (0..8).contains(&tf) {
                    for promo in [1u8, 2, 3] {
                        // from file ff rank 7 (index 6*8..) -> rank 8
                        entries.push((48 + ff, 56 + tf as u8, promo));
                    }
                }
            }
        }
        assert_eq!(entries.len(), 1858);
        let mut map = FxHashMap::default();
        for (i, e) in entries.iter().enumerate() {
            map.insert(*e, i as u16);
        }
        PolicyMap { map }
    }

    /// Look up a move already expressed in the white-to-move frame with
    /// castling as king-takes-rook and knight promotions stripped.
    #[inline]
    pub fn index(&self, from: u8, to: u8, promo: u8) -> Option<u16> {
        self.map.get(&(from, to, promo)).copied()
    }
}
