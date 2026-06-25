"""#1 signal check: can a net trained on the SEARCH's policy predict the search's
move better than BT4's raw policy (73.3% baseline)? Decisive go/no-go for whether
the search's move-improvement is learnable on this corpus. Run in swtrain_venv.
"""
import numpy as np, os, time, torch, torch.nn as nn

REPO = r"C:\Users\nonna\Downloads\ExperimentalChessEngine"
d = np.load(os.path.join(REPO, "harvest", "signal_dataset.npz"))
boards = torch.from_numpy(d["boards"].astype(np.float32))
spol = torch.from_numpy(d["spol"].astype(np.float32))
mask = torch.from_numpy(np.unpackbits(d["mask"], axis=1)[:, :4096].astype(np.float32))
sval = torch.from_numpy(d["sval"].astype(np.float32))
sbest = torch.from_numpy(d["sbest"].astype(np.int64))
bbest = torch.from_numpy(d["bbest"].astype(np.int64))
bval = torch.from_numpy(d["bval"].astype(np.float32))
N = len(boards)
g = torch.Generator().manual_seed(0x57111A7E)
idx = torch.randperm(N, generator=g)
cut = int(N * 0.85)
tr, va = idx[:cut], idx[cut:]
dev = "cuda"
print(f"{N} positions, {len(tr)} train / {len(va)} val | device {torch.cuda.get_device_name(0)}", flush=True)


class Net(nn.Module):
    def __init__(self, ch=96):
        super().__init__()
        self.body = nn.Sequential(
            nn.Conv2d(18, ch, 3, padding=1), nn.ReLU(),
            nn.Conv2d(ch, ch, 3, padding=1), nn.ReLU(),
            nn.Conv2d(ch, ch, 3, padding=1), nn.ReLU(),
            nn.Conv2d(ch, ch, 3, padding=1), nn.ReLU())
        self.pol = nn.Linear(ch * 64, 4096)
        self.val = nn.Sequential(nn.Linear(ch * 64, 128), nn.ReLU(),
                                 nn.Linear(128, 1), nn.Tanh())

    def forward(self, x):
        h = self.body(x).flatten(1)
        return self.pol(h), self.val(h).squeeze(1)


net = Net().to(dev)
opt = torch.optim.Adam(net.parameters(), 1e-3, weight_decay=1e-4)
va_x = boards[va].to(dev); va_m = mask[va].to(dev)
bacc = (bbest[va] == sbest[va]).float().mean().item()
bvmae = (bval[va] - sval[va]).abs().mean().item()
dis = (sbest[va] != bbest[va])
B = 256
best_nacc = 0
for epoch in range(40):
    net.train()
    perm = tr[torch.randperm(len(tr), generator=g)]
    for s in range(0, len(perm), B):
        bi = perm[s:s + B]
        xb = boards[bi].to(dev); pb = spol[bi].to(dev); mb = mask[bi].to(dev); vb = sval[bi].to(dev)
        pl, vl = net(xb)
        pl = pl.masked_fill(mb == 0, -1e9)
        loss = -(pb * torch.log_softmax(pl, 1)).sum(1).mean() + ((vl - vb) ** 2).mean()
        opt.zero_grad(); loss.backward(); opt.step()
    net.eval()
    with torch.no_grad():
        pl, vl = net(va_x)
        pl = pl.masked_fill(va_m == 0, -1e9)
        nb = pl.argmax(1).cpu()
        nacc = (nb == sbest[va]).float().mean().item()
        nacc_dis = (nb[dis] == sbest[va][dis]).float().mean().item()
        vmae = (vl.cpu() - sval[va]).abs().mean().item()
    best_nacc = max(best_nacc, nacc)
    if epoch % 4 == 0 or epoch == 39:
        print(f"ep{epoch:2d}: net_top1_vs_search {nacc:.3f} (BT4 {bacc:.3f}) | "
              f"net_on_disagree {nacc_dis:.3f} | val_MAE net {vmae:.4f} (BT4 {bvmae:.4f})", flush=True)
print(f"\nBEST net_top1_vs_search {best_nacc:.3f}  vs  BT4 {bacc:.3f}")
print("SIGNAL VERDICT:", "LEARNABLE -- net beats BT4 at predicting the search move"
      if best_nacc > bacc + 0.01 else
      "WEAK/NONE -- net cannot beat BT4's prior on this corpus (data-bound or unlearnable)")
