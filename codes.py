import secrets
import string

ALPHABET = string.ascii_uppercase + string.digits


def generate_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(16))


def redeem(store_data: dict, code: str, user_id: int) -> tuple[bool, str, dict | None]:
    """
    Kodni tekshiradi va bir martalik ishlatadi (faqat validatsiya - effektni
    chaqiruvchi tomon store.grant_permanent/grant_limit orqali qo'llaydi).
    Qaytaradi: (muvaffaqiyatli_mi, xabar, kod_yozuvi)
    """
    code = code.strip().upper()
    entry = store_data["codes"].get(code)
    if not entry:
        return False, "❌ Bunday kod topilmadi.", None
    if entry["used"]:
        return False, "❌ Bu kod allaqachon ishlatilgan.", None

    entry["used"] = True
    entry["used_by"] = user_id

    if entry.get("type") == "daily":
        msg = f"✅ Kod qabul qilindi! +{entry['amount']} ta kunlik limit, {entry['days']} kunga."
    else:
        msg = f"✅ Kod qabul qilindi! +{entry['amount']} ta limit doimiy qo'shildi."
    return True, msg, entry
