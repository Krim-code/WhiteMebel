import base64, hmac, hashlib

def verify_cp_signature(raw_body: bytes, signature_from_header: str, secret: str) -> bool:
    if not signature_from_header:
        return False
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")
    # сравнение без тайминга нам ок
    return expected == signature_from_header
