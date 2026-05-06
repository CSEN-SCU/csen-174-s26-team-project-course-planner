import base64


def pdf_to_base64(pdf_bytes: bytes) -> str:
    """Encode PDF bytes as base64 for Claude document APIs."""
    return base64.standard_b64encode(pdf_bytes).decode("utf-8")
