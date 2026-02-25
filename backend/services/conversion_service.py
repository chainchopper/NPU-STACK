"""Conversion service — model format conversion and quantization using real APIs."""

import os
import shutil
import tempfile
from typing import Optional

import numpy as np
import onnx

try:
    import onnxruntime as ort
    HAS_ORT = True
except ImportError:
    ort = None
    HAS_ORT = False

MODEL_STORE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models")
os.makedirs(MODEL_STORE, exist_ok=True)


def validate_onnx(model_path: str) -> dict:
    """Validate an ONNX model and return metadata."""
    model = onnx.load(model_path)
    onnx.checker.check_model(model)

    graph = model.graph
    inputs = []
    for inp in graph.input:
        shape = []
        for dim in inp.type.tensor_type.shape.dim:
            shape.append(dim.dim_value if dim.dim_value > 0 else "dynamic")
        inputs.append({"name": inp.name, "shape": shape})

    outputs = []
    for out in graph.output:
        shape = []
        for dim in out.type.tensor_type.shape.dim:
            shape.append(dim.dim_value if dim.dim_value > 0 else "dynamic")
        outputs.append({"name": out.name, "shape": shape})

    return {
        "opset_version": model.opset_import[0].version if model.opset_import else None,
        "ir_version": model.ir_version,
        "producer": model.producer_name,
        "num_nodes": len(graph.node),
        "inputs": inputs,
        "outputs": outputs,
        "node_types": list(set(n.op_type for n in graph.node)),
    }


def convert_onnx_to_openvino(
    onnx_path: str,
    output_dir: Optional[str] = None,
    model_name: Optional[str] = None,
    compress_to_fp16: bool = True,
) -> dict:
    """
    Convert ONNX model to OpenVINO IR format using OpenVINO tools.
    
    Returns dict with paths to the .xml and .bin files.
    """
    import openvino as ov

    if output_dir is None:
        output_dir = MODEL_STORE
    if model_name is None:
        model_name = os.path.splitext(os.path.basename(onnx_path))[0] + "_openvino"

    # Read ONNX model and convert to OpenVINO
    ov_model = ov.convert_model(onnx_path)

    if compress_to_fp16:
        import openvino.runtime.passes as passes
        pass_manager = passes.Manager()
        pass_manager.register_pass(passes.CompressQuantizeWeights())
        pass_manager.run_passes(ov_model)

    # Save the model
    xml_path = os.path.join(output_dir, f"{model_name}.xml")
    ov.save_model(ov_model, xml_path, compress_to_fp16=compress_to_fp16)
    bin_path = xml_path.replace(".xml", ".bin")

    return {
        "xml_path": xml_path,
        "bin_path": bin_path,
        "xml_size": os.path.getsize(xml_path),
        "bin_size": os.path.getsize(bin_path) if os.path.exists(bin_path) else 0,
        "format": "openvino_ir",
    }


def quantize_onnx_dynamic(
    onnx_path: str,
    output_path: Optional[str] = None,
    weight_type: str = "int8",
) -> dict:
    """
    Apply dynamic quantization to an ONNX model.
    
    Quantizes weights to INT8 while keeping activations in float.
    Best for transformer/RNN models and when calibration data isn't available.
    """
    from onnxruntime.quantization import quantize_dynamic, QuantType

    if output_path is None:
        base = os.path.splitext(onnx_path)[0]
        output_path = f"{base}_quantized_{weight_type}.onnx"

    quant_type = QuantType.QUInt8 if weight_type == "uint8" else QuantType.QInt8

    quantize_dynamic(
        model_input=onnx_path,
        model_output=output_path,
        weight_type=quant_type,
    )

    original_size = os.path.getsize(onnx_path)
    quantized_size = os.path.getsize(output_path)

    return {
        "output_path": output_path,
        "original_size": original_size,
        "quantized_size": quantized_size,
        "compression_ratio": round(original_size / quantized_size, 2),
        "weight_type": weight_type,
        "method": "dynamic",
    }


def quantize_onnx_static(
    onnx_path: str,
    output_path: Optional[str] = None,
    calibration_data: Optional[list] = None,
    num_calibration_samples: int = 100,
) -> dict:
    """
    Apply static quantization to an ONNX model with calibration.
    
    Uses representative data to determine quantization parameters.
    Provides better accuracy than dynamic quantization.
    """
    from onnxruntime.quantization import quantize_static, CalibrationDataReader, QuantType, QuantFormat
    from onnxruntime.quantization.shape_inference import quant_pre_process

    if output_path is None:
        base = os.path.splitext(onnx_path)[0]
        output_path = f"{base}_quantized_static_int8.onnx"

    # Pre-process model for quantization
    preprocessed_path = onnx_path + ".preprocessed.onnx"
    quant_pre_process(onnx_path, preprocessed_path)

    # Create calibration data reader
    class RandomCalibrationReader(CalibrationDataReader):
        def __init__(self, model_path, num_samples):
            session = ort.InferenceSession(model_path)
            self.input_name = session.get_inputs()[0].name
            input_shape = session.get_inputs()[0].shape
            # Replace dynamic dims with reasonable defaults
            self.input_shape = [s if isinstance(s, int) and s > 0 else 1 for s in input_shape]
            self.num_samples = num_samples
            self.current = 0

        def get_next(self):
            if self.current >= self.num_samples:
                return None
            self.current += 1
            return {self.input_name: np.random.randn(*self.input_shape).astype(np.float32)}

    reader = RandomCalibrationReader(preprocessed_path, num_calibration_samples)

    quantize_static(
        model_input=preprocessed_path,
        model_output=output_path,
        calibration_data_reader=reader,
        quant_format=QuantFormat.QDQ,
        per_channel=True,
        weight_type=QuantType.QInt8,
    )

    # Clean up preprocessed file
    if os.path.exists(preprocessed_path):
        os.remove(preprocessed_path)

    original_size = os.path.getsize(onnx_path)
    quantized_size = os.path.getsize(output_path)

    return {
        "output_path": output_path,
        "original_size": original_size,
        "quantized_size": quantized_size,
        "compression_ratio": round(original_size / quantized_size, 2),
        "weight_type": "int8",
        "method": "static_qdq",
        "calibration_samples": num_calibration_samples,
    }


def compress_openvino_nncf(
    model_path: str,
    output_dir: Optional[str] = None,
    mode: str = "int8",
) -> dict:
    """
    Compress an OpenVINO or ONNX model using NNCF (Neural Network Compression Framework).
    
    Supports INT8 weight compression for NPU deployment.
    """
    import openvino as ov
    import nncf

    if output_dir is None:
        output_dir = MODEL_STORE

    core = ov.Core()

    # Load model (supports both ONNX and OpenVINO IR)
    if model_path.endswith(".onnx"):
        ov_model = ov.convert_model(model_path)
    else:
        ov_model = core.read_model(model_path)

    model_name = os.path.splitext(os.path.basename(model_path))[0]

    if mode == "int8":
        compressed = nncf.compress_weights(
            ov_model,
            mode=nncf.CompressWeightsMode.INT8_ASYM,
        )
        suffix = "nncf_int8"
    elif mode == "int4":
        compressed = nncf.compress_weights(
            ov_model,
            mode=nncf.CompressWeightsMode.INT4_ASYM,
            group_size=64,
        )
        suffix = "nncf_int4"
    else:
        raise ValueError(f"Unsupported NNCF mode: {mode}. Supported: int8, int4")

    output_path = os.path.join(output_dir, f"{model_name}_{suffix}.xml")
    ov.save_model(compressed, output_path)

    return {
        "xml_path": output_path,
        "bin_path": output_path.replace(".xml", ".bin"),
        "format": "openvino_ir",
        "compression": suffix,
    }


def get_onnx_model_info(model_path: str) -> dict:
    """Get detailed info about an ONNX model."""
    try:
        info = validate_onnx(model_path)
        info["file_size"] = os.path.getsize(model_path)
        info["valid"] = True
        return info
    except Exception as e:
        return {"valid": False, "error": str(e)}
