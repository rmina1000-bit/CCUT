# Silero VAD runtime

This directory is the local runtime location for the Silero VAD ONNX model.
The model is provisioned per machine and is not committed.

- File: `silero_vad.onnx`
- SHA256: `1A153A22F4509E292A94E67D6F9B85E8DEB25B4988682B7E174C65279D8788E3`
- Source: local isolated LAB-3 environment,
  `D:\CCUT_EXTERNAL_DATA\lab3\silero_venv\Lib\site-packages\silero_vad\data\silero_vad.onnx`
- Runtime: existing `onnxruntime==1.24.1`

If the model is absent or its hash differs, the sensor reports
`MODEL_MISSING` and the analysis pipeline continues without Silero evidence.
