"""Isolated, bounded detection attempt. No callback or background executor."""
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

from .app import decode_image
from .contract import validate, validate_result
from .detector import detect
from .runtime import initialize


def run(body):
    validate("request", body)
    if body["assignmentMethod"] == "llm" and not os.getenv("OPENAI_API_KEY"):
        return {"protocolVersion": 2, "drawingId": body["drawingId"], "runId": body["runId"],
                "status": "failed", "error": {"code": "assignment_method_unavailable",
                "message": "The requested assignment method is unavailable", "retryable": False}}
    try:
        svg = decode_image(body["image"], int(os.getenv("MAX_SVG_BYTES", "67108864")))
        result = detect(svg, body)
        validate_result(result, body)
        return result
    except Exception:
        logging.exception("detection failed runId=%s", body["runId"])
        return {"protocolVersion": 2, "drawingId": body["drawingId"], "runId": body["runId"],
                "status": "failed", "error": {"code": "detection_failed",
                "message": "Input could not be processed into a valid detection result", "retryable": False}}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Place all nested engine scratch files under the parent's directory so a
    # timeout doesn't leave RAM-backed /tmp files behind on a warm instance.
    os.environ["TMPDIR"] = str(Path(sys.argv[1]).parent)
    tempfile.tempdir = None
    initialize()
    body = json.loads(Path(sys.argv[1]).read_bytes())
    Path(sys.argv[2]).write_text(json.dumps(run(body), ensure_ascii=False, allow_nan=False))
