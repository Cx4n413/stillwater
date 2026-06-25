"""#90 step 1: ONNX surgery. Add the shared encoder embedding /encoder14/ln2 as a
model output so a frozen-backbone value head can be trained on it. Saves
nets/BT4-embed.onnx (same backbone, one extra output). Uses static shape
inference to report the embedding dims (no slow runtime inference here)."""
import onnx
from onnx import helper, TensorProto, shape_inference

SRC = r"C:\Users\nonna\Downloads\ExperimentalChessEngine\nets\BT4-1024x15x32h-policytune.onnx"
DST = r"C:\Users\nonna\Downloads\ExperimentalChessEngine\nets\BT4-embed.onnx"
# /value/reshape = the value head's FLATTENED feature vector (input to its MLP):
#   small + storable, and retraining dense1->dense2 on it IS fine-tuning the value
#   head. /encoder14/ln2 (full per-token encoder embedding) kept as a fallback.
EXPOSE = ["/value/reshape", "/value/embed/mish", "/encoder14/ln2"]

m = onnx.load(SRC)
g = m.graph

try:
    inferred = shape_inference.infer_shapes(m)
    want = set(EXPOSE)
    for vi in inferred.graph.value_info:
        if vi.name in want:
            dims = [(d.dim_value if d.HasField('dim_value') else d.dim_param)
                    for d in vi.type.tensor_type.shape.dim]
            print(f"'{vi.name}' inferred shape: {dims}  elem_type={vi.type.tensor_type.elem_type}")
except Exception as e:
    print("shape inference note:", repr(e))

have = {o.name for o in g.output}
for name in EXPOSE:
    if name not in have:
        g.output.append(helper.make_tensor_value_info(name, TensorProto.FLOAT16, None))

onnx.save(m, DST)        # skip checker: a shape-less added output is fine for ORT
print("SAVED:", DST)
print("model outputs now:", [o.name for o in onnx.load(DST).graph.output])
