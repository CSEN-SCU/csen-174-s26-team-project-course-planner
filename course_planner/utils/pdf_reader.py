import base64


def pdf_to_base64(pdf_bytes: bytes) -> str:
    """将 PDF 字节编码为 Claude document 所需的 base64 字符串。"""
    return base64.standard_b64encode(pdf_bytes).decode("utf-8")
