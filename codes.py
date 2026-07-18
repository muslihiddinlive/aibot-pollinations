import secrets
import string

ALPHABET = string.ascii_uppercase + string.digits


def generate_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(16))


def redeem(store_data: dict, code: str, user_id: int) -> tuple[bool, str]:
    """
    Kodni tekshiradi va bir martalik ishlatadi.
    Qaytaradi: (muvaffaqiyatli_mi, xabar)
    """
    code = code.strip().upper()
    entry = store_data["codes"].get(code)
    if not entry:
        return False, "❌ Bunday kod topilmadi."
    if entry["used"]:
        return False, "❌ Bu kod allaqachon ishlatilgan."

    entry["used"] = True
    entry["used_by"] = user_id
    return True, f"✅ Kod qabul qilindi! +{entry['limit_add']} ta limit, {entry['days']} kunga."
