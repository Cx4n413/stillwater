"""Bounded BT4 graph probe: find the SHARED embedding (the tensor that is an
ancestor of all three heads -- policy/wdl/mlh -- and closest to them). That
tensor is what we expose as a new ONNX output to feed a frozen-backbone value
head. onnx.load only (no onnxruntime session -> avoids the slow CPU inference
load while the gauntlet uses the CPU)."""
import onnx

P = r"C:\Users\nonna\Downloads\ExperimentalChessEngine\nets\BT4-1024x15x32h-policytune.onnx"
m = onnx.load(P)
g = m.graph
producers = {}
for n in g.node:
    for o in n.output:
        producers[o] = n
# topological index of each tensor (by node order)
topo = {}
for idx, n in enumerate(g.node):
    for o in n.output:
        topo[o] = idx

outs = [o.name for o in g.output]
print("OUTPUTS:", outs)


def ancestors(start, cap=5000):
    seen = set()
    stack = [start]
    while stack:
        t = stack.pop()
        if t in seen:
            continue
        seen.add(t)
        n = producers.get(t)
        if n:
            for inp in n.input:
                if inp not in seen:
                    stack.append(inp)
    return seen


anc = {o: ancestors(o) for o in outs}
common = set.intersection(*anc.values())
# the shared embedding = the common ancestor with the HIGHEST topo index (latest,
# i.e. closest to where the heads diverge) that is an actual produced tensor.
cand = [(topo.get(t, -1), t) for t in common if t in topo]
cand.sort(reverse=True)
print("=== top shared-ancestor tensors (closest to the heads = the embedding) ===")
for ti, t in cand[:8]:
    n = producers.get(t)
    print(f"  topo={ti}  tensor='{t}'  produced_by={n.op_type} '{n.name}'")

# Show the wdl head's back-chain from /output/wdl down to the shared embedding
emb = cand[0][1] if cand else None
print(f"=== wdl head main-path back-chain (stop at shared embedding '{emb}') ===")
seen = set()
cur = '/output/wdl'
for _ in range(40):
    if cur in seen:
        break
    seen.add(cur)
    n = producers.get(cur)
    if not n:
        print(f"  [graph-input/init] {cur}")
        break
    # find the main (non-initializer, produced) input
    nexts = [i for i in n.input if i in producers]
    print(f"  {n.op_type:14s} '{n.name}'  out={cur}  in={list(n.input)}")
    if cur == emb or not nexts:
        break
    cur = nexts[0]
print("DONE")
