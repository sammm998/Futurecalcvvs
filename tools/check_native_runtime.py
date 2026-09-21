"""Fail installation early when the full detector's local runtime is missing."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from vvs_engine.source_rules.native_detection import load_runtime


def main():
    load_runtime()
    import onnxruntime
    import pytesseract
    model=ROOT/'models/pipestudio-labels.onnx'
    if not model.is_file():raise RuntimeError('PipeStudios detektionsmodell saknas: '+str(model))
    try:
        version=str(pytesseract.get_tesseract_version()).splitlines()[0]
    except pytesseract.TesseractNotFoundError:
        sys.exit('Tesseract saknas. Installera Tesseract och kör setup-local.sh igen. På macOS med Homebrew: brew install tesseract')
    print('Detektorns beroenden tillgängliga: ONNX Runtime '+onnxruntime.__version__+', Tesseract '+version)
if __name__=='__main__':main()
