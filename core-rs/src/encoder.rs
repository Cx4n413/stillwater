//! Lc0 INPUT_CLASSICAL_112_PLANE encoding, ported bit-for-bit from the
//! Python oracle (stillwater/oracle.py), which itself was verified
//! move-by-move against lc0 v0.32.1.
//!
//! Planes (after the side-to-move flip):
//!   0..103   8 history steps x 13 planes, newest first. Per step: our
//!            P,N,B,R,Q,K, their P,N,B,R,Q,K, repetition (all-ones if that
//!            position occurred before within its 50-move window).
//!   104..107 we O-O-O / we O-O / they O-O-O / they O-O
//!   108      all ones if black to move
//!   109      halfmove clock (raw count, constant plane)
//!   110      zeros, 111 ones
//! Black to move: every square mask is rank-mirrored (swap_bytes).

use shakmaty::{Chess, Color, Position, Role};

/// Absolute (white/black) piece bitboards for one historical position.
#[derive(Clone, Copy)]
pub struct Frame {
    pub by_color_role: [[u64; 6]; 2], // [white,black][P,N,B,R,Q,K]
}

impl Frame {
    pub fn of(pos: &Chess) -> Frame {
        let b = pos.board();
        let mut f = Frame { by_color_role: [[0; 6]; 2] };
        for (ci, color) in [Color::White, Color::Black].iter().enumerate() {
            for (ri, role) in [Role::Pawn, Role::Knight, Role::Bishop,
                               Role::Rook, Role::Queen, Role::King]
                .iter().enumerate()
            {
                f.by_color_role[ci][ri] =
                    (b.by_color(*color) & b.by_role(*role)).0;
            }
        }
        f
    }
}

/// Everything the encoder needs about one leaf, captured during descent.
pub struct EncodeJob {
    /// history newest-first: frames[0] is the leaf position itself
    pub frames: Vec<Frame>,        // up to 8
    pub reps: Vec<bool>,           // aligned with frames
    pub stm_black: bool,
    pub castling: [bool; 4],       // us OOO, us OO, them OOO, them OO
    pub halfmove: u32,
    pub fill_history: bool,        // ran out of real history before 8 frames
    pub started_from_startpos: bool,
    pub ep_square: Option<u8>,     // for lc0's pre-history un-move fixup
    pub oldest_black_to_move: bool, // side to move at the OLDEST frame: the
                                    // un-move direction depends on it, not on
                                    // the leaf's side (they differ when the
                                    // available history depth is odd)
}

#[inline]
fn put_mask(out: &mut [f32], plane: usize, mask: u64) {
    let base = plane * 64;
    let mut m = mask;
    while m != 0 {
        let sq = m.trailing_zeros() as usize;
        out[base + sq] = 1.0;
        m &= m - 1;
    }
}

#[inline]
fn fill_plane(out: &mut [f32], plane: usize, value: f32) {
    let base = plane * 64;
    for v in &mut out[base..base + 64] {
        *v = value;
    }
}

/// Encode one job into out[112*64], the caller's slice for this board.
pub fn encode(job: &EncodeJob, out: &mut [f32]) {
    debug_assert_eq!(out.len(), 112 * 64);
    let stm = if job.stm_black { 1 } else { 0 };
    let them = 1 - stm;
    let flip = job.stm_black;

    let n_frames = job.frames.len().min(8);
    // resolve the fill frame (oldest known, with ep un-move fixup)
    let mut fill: Option<[[u64; 6]; 2]> = None;
    if n_frames < 8 && job.fill_history && !job.started_from_startpos {
        let mut f = job.frames[n_frames - 1].by_color_role;
        if let Some(ep) = job.ep_square {
            // The side NOT to move at the OLDEST frame just double-pushed in
            // lc0's synthesized pre-history; un-make it. Direction comes from
            // the oldest frame's turn (mirrors oracle.py, where `b` has been
            // popped back to the root before reading b.turn).
            let (mover, cur, orig) = if !job.oldest_black_to_move {
                (1usize, ep as i32 - 8, ep as i32 + 8) // black pushed
            } else {
                (0usize, ep as i32 + 8, ep as i32 - 8) // white pushed
            };
            if (0..64).contains(&cur) && (0..64).contains(&orig) {
                f[mover][0] = (f[mover][0] & !(1u64 << cur)) | (1u64 << orig);
            }
        }
        fill = Some(f);
    }

    for i in 0..8 {
        let base = 13 * i;
        let (frame, rep) = if i < n_frames {
            (job.frames[i].by_color_role, job.reps[i])
        } else if let Some(f) = fill {
            (f, job.reps[n_frames - 1])
        } else {
            continue; // startpos fill: zeros
        };
        for r in 0..6 {
            let mut us = frame[stm][r];
            let mut th = frame[them][r];
            if flip {
                us = us.swap_bytes();
                th = th.swap_bytes();
            }
            put_mask(out, base + r, us);
            put_mask(out, base + 6 + r, th);
        }
        if rep {
            fill_plane(out, base + 12, 1.0);
        }
    }

    for (k, on) in job.castling.iter().enumerate() {
        if *on {
            fill_plane(out, 104 + k, 1.0);
        }
    }
    if job.stm_black {
        fill_plane(out, 108, 1.0);
    }
    fill_plane(out, 109, job.halfmove as f32);
    // 110 zeros (already), 111 ones
    fill_plane(out, 111, 1.0);
}
