"""#90 step 4: train the max-backup-native value head.

A small MLP on BT4's value features (/value/reshape, 8192-d) outputs a scalar
value (child stm). The loss is the ANTI-GRAVEYARD core:
  (1) RANKING-KL: per parent, the softmax over siblings of the predicted
      root-perspective value (= -head_value(child)) matches the softmax over the
      deep SETTLED values. This distills the search's move ORDERING (free depth),
      NOT the magnitude (the magnitude self-distill was -26 Elo).
  (2) MAGNITUDE LEASH: head_value stays near BT4's native value, so the co-tuned
      search constants are not detuned.
  (3) PROOF ANCHOR: on proven children, pull hard to the proven (variance-0) value.

Deploy keeps BT4's native draw mass D and only re-derives W/L from the new value,
so D never drifts. Saves the head weights (npz) for the two-stage oracle.

    swtrain_venv/python tools/train_value_head.py
"""
from __future__ import annotations
import os
import sys
import time

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTDIR = os.path.join(REPO, "games", "rankfeat")
HEAD_OUT = os.path.join(REPO, "nets", "value_head_v1.npz")

import torch
import torch.nn as nn
import torch.nn.functional as F

DEV = "cuda" if torch.cuda.is_available() else "cpu"

# ---- hyperparameters (first pass; tune if the val ranking improves) ----
HID = int(os.environ.get("VH_HID", "256"))
TEMP = float(os.environ.get("VH_TEMP", "0.30"))      # ranking softmax temperature
LAM_MAG = float(os.environ.get("VH_LAM_MAG", "0.1"))  # magnitude leash (anti-detune)
LAM_PROOF = 2.0      # proof hard-anchor weight
EPOCHS = 12
GROUPS_PER_BATCH = 512
LR = 1e-3
VAL_FRAC = 0.04


class Head(nn.Module):
    def __init__(self, d_in, hid):
        super().__init__()
        self.l1 = nn.Linear(d_in, hid)
        self.l2 = nn.Linear(hid, 1)

    def forward(self, x):
        return torch.tanh(self.l2(F.mish(self.l1(x)))).squeeze(-1)


def group_spans(gid):
    # gid is contiguous non-decreasing -> spans of equal gid
    change = np.nonzero(np.diff(gid))[0] + 1
    starts = np.concatenate([[0], change])
    ends = np.concatenate([change, [len(gid)]])
    return np.stack([starts, ends], 1)   # [G,2]


def main():
    meta = np.load(os.path.join(OUTDIR, "meta.npz"))
    N = int(meta["N"]); D = int(meta["dfeat"])
    targets = meta["targets"].astype(np.float32)      # root-persp settled value
    proof = meta["proof"].astype(np.float32)
    baseval = meta["baseval"].astype(np.float32)      # BT4 native child value
    feats = np.memmap(os.path.join(OUTDIR, "feats.f16"), dtype=np.float16,
                      mode="r", shape=(N, D))
    spans = group_spans(meta["gid"])
    G = len(spans)
    print(f"N={N} D={D} groups={G} device={DEV}")

    rng = np.random.default_rng(0)
    perm = rng.permutation(G)
    nval = int(G * VAL_FRAC)
    val_g, tr_g = perm[:nval], perm[nval:]

    head = Head(D, HID).to(DEV)
    opt = torch.optim.Adam(head.parameters(), lr=LR)

    def run_batch(gidxs, train):
        # gather children of these groups
        rows = []
        seg = []          # group id within batch, per child
        for s, (gi) in enumerate(gidxs):
            a, b = spans[gi]
            rows.append(np.arange(a, b))
            seg.append(np.full(b - a, s, np.int64))
        rows = np.concatenate(rows); seg = np.concatenate(seg)
        x = torch.from_numpy(np.ascontiguousarray(feats[rows]).astype(np.float32)).to(DEV)
        tgt = torch.from_numpy(targets[rows]).to(DEV)         # root persp
        base = torch.from_numpy(baseval[rows]).to(DEV)        # child stm (BT4)
        pf = torch.from_numpy(proof[rows]).to(DEV)
        segt = torch.from_numpy(seg).to(DEV)
        nseg = len(gidxs)

        v = head(x)                       # child-stm value
        rootv = -v                        # root-perspective value of the move

        # segment softmax-KL: target dist vs pred dist, per group
        def seg_logsoftmax(s):
            # s: [M] scores; segt groups -> log-softmax within each segment
            m = torch.full((nseg,), -1e9, device=DEV).index_reduce_(
                0, segt, s.detach(), "amax", include_self=True)
            s2 = s - m[segt]
            e = torch.exp(s2)
            denom = torch.zeros(nseg, device=DEV).index_add_(0, segt, e)
            return s2 - torch.log(denom[segt] + 1e-9)

        logp = seg_logsoftmax(rootv / TEMP)
        with torch.no_grad():
            logq = seg_logsoftmax(tgt / TEMP)
        q = torch.exp(logq)
        # KL(q||p) = sum q*(logq-logp); average per group then per batch
        kl_per = q * (logq - logp)
        kl = torch.zeros(nseg, device=DEV).index_add_(0, segt, kl_per).mean()

        mag = F.mse_loss(v, base)                       # leash to BT4 magnitude
        pmask = pf > 0.5
        proof_l = (F.mse_loss(rootv[pmask], tgt[pmask])
                   if pmask.any() else torch.zeros((), device=DEV))
        loss = kl + LAM_MAG * mag + LAM_PROOF * proof_l
        if train:
            opt.zero_grad(); loss.backward(); opt.step()
        # ranking acc: does argmax(pred root value) match argmax(target) per group?
        with torch.no_grad():
            def seg_argmax(s):
                best = torch.full((nseg,), -1e9, device=DEV)
                idx = torch.full((nseg,), -1, device=DEV, dtype=torch.long)
                order = torch.arange(len(s), device=DEV)
                for gg in range(nseg):
                    msk = segt == gg
                    if msk.any():
                        sub = s[msk]; oi = order[msk]
                        idx[gg] = oi[torch.argmax(sub)]
                return idx
            top1 = (seg_argmax(rootv) == seg_argmax(tgt)).float().mean().item()
        return loss.item(), kl.item(), mag.item(), float(proof_l), top1

    print("training...")
    best_vacc = -1.0
    best_state = None
    for ep in range(EPOCHS):
        head.train()
        rng.shuffle(tr_g)
        t0 = time.time(); accs = []
        for i in range(0, len(tr_g), GROUPS_PER_BATCH):
            gb = tr_g[i:i + GROUPS_PER_BATCH]
            l, kl, mag, pl, acc = run_batch(gb, True)
            accs.append(acc)
        # val
        head.eval()
        vacc = []
        with torch.no_grad():
            for i in range(0, len(val_g), GROUPS_PER_BATCH):
                gb = val_g[i:i + GROUPS_PER_BATCH]
                _, _, _, _, acc = run_batch(gb, False)
                vacc.append(acc)
        print(f"ep{ep:2d} loss={l:.4f} kl={kl:.4f} mag={mag:.4f} proof={pl:.4f} "
              f"train_top1={np.mean(accs):.3f} val_top1={np.mean(vacc):.3f} "
              f"({time.time()-t0:.0f}s)", flush=True)
        vm = float(np.mean(vacc))
        if vm > best_vacc:
            best_vacc = vm
            best_state = {k: v.detach().cpu().clone() for k, v in head.state_dict().items()}

    # baseline: how often does BT4's NATIVE value already match the settled argmax?
    head.eval()
    base_acc = []
    with torch.no_grad():
        for i in range(0, len(val_g), GROUPS_PER_BATCH):
            gb = val_g[i:i + GROUPS_PER_BATCH]
            rows = []; seg = []
            for s, gi in enumerate(gb):
                a, b = spans[gi]; rows.append(np.arange(a, b)); seg.append(np.full(b-a, s, np.int64))
            rows = np.concatenate(rows); seg = np.concatenate(seg)
            tgt = targets[rows]; bv = -baseval[rows]   # root persp of BT4 native
            segn = seg
            import collections
            byg = collections.defaultdict(list)
            for k, gg in enumerate(segn):
                byg[gg].append(k)
            ok = 0; tot = 0
            for gg, ks in byg.items():
                ks = np.array(ks)
                if np.argmax(bv[ks]) == np.argmax(tgt[ks]):
                    ok += 1
                tot += 1
            base_acc.append(ok / max(tot, 1))
    print(f"BASELINE BT4-native val_top1 vs settled = {np.mean(base_acc):.3f}")

    if best_state is not None:
        head.load_state_dict(best_state)
    print(f"BEST val_top1 = {best_vacc:.3f}  (BT4-native was 0.507; >0.507 = re-rank gain)")
    w = {k: v.detach().cpu().numpy() for k, v in head.state_dict().items()}
    np.savez(HEAD_OUT, l1_w=w["l1.weight"], l1_b=w["l1.bias"],
             l2_w=w["l2.weight"], l2_b=w["l2.bias"],
             d_in=np.int64(D), hid=np.int64(HID))
    print(f"SAVED head -> {HEAD_OUT}")


if __name__ == "__main__":
    main()
