"""Phase-0 feasibility probe for #90: can we freeze BT4's backbone and expose the
pre-value-head embedding (for graph surgery), so a new value head can be trained
on it? Prints I/O, checks the onnx lib, and traces the value head back to its
embedding input."""
import sys

P = r"C:\Users\nonna\Downloads\ExperimentalChessEngine\nets\BT4-1024x15x32h-policytune.onnx"

import onnxruntime as ort
sess = ort.InferenceSession(P, providers=['CPUExecutionProvider'])
print("=== ONNX INPUTS ===")
for i in sess.get_inputs():
    print(f"  {i.name}  shape={i.shape}  type={i.type}")
print("=== ONNX OUTPUTS ===")
for o in sess.get_outputs():
    print(f"  {o.name}  shape={o.shape}  type={o.type}")

try:
    import onnx
    print("=== onnx lib AVAILABLE", onnx.__version__, "===")
    m = onnx.load(P)
    g = m.graph
    print("graph nodes:", len(g.node))
    producers = {}
    for n in g.node:
        for outp in n.output:
            producers[outp] = n
    outnames = [o.name for o in g.output]
    print("graph outputs:", outnames)
    for on in outnames:
        n = producers.get(on)
        if n:
            print(f"  {on} <- {n.op_type} '{n.name}' inputs={list(n.input)}")

    def trace(name, depth=0, maxd=10):
        pad = "  " * depth
        n = producers.get(name)
        if not n:
            print(f"{pad}[graph-input/initializer] {name}")
            return
        print(f"{pad}{n.op_type} '{n.name}' <- {list(n.input)}")
        for inp in n.input:
            # follow only tensor inputs (skip weight initializers heuristically)
            if inp in producers:
                trace(inp, depth + 1, maxd)
    # trace the value/wdl head back toward the shared embedding
    target = None
    for on in outnames:
        lo = on.lower()
        if 'value' in lo or 'wdl' in lo or 'win' in lo:
            target = on; break
    if target is None and outnames:
        target = outnames[0]
    print(f"=== TRACE value head from '{target}' (looking for the shared embedding / pooling) ===")
    trace(target, maxd=12)
except Exception as e:
    print("=== onnx lib NOT available:", repr(e))
