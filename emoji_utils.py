import re
from aiogram.types import MessageEntity

_PATTERN = re.compile(r"\{(\w+)\}")
_PLACEHOLDER = "🙂"


def _utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def build_emoji_entities(template: str, emoji_map: dict) -> tuple[str, list[MessageEntity]]:
    """
    Matn ichidagi {key} belgilarni emoji_map dagi custom_emoji_id bilan almashtirib,
    Telegram uchun to'g'ri MessageEntity(custom_emoji) ro'yxatini quradi.
    Offset/length UTF-16 birliklarida hisoblanadi (Telegram talabi).
    Kalit topilmasa, {key} o'zgarishsiz qoladi.
    """
    result = ""
    entities: list[MessageEntity] = []
    last_end = 0
    for m in _PATTERN.finditer(template):
        result += template[last_end:m.start()]
        key = m.group(1)
        emoji_id = emoji_map.get(key)
        if emoji_id:
            offset = _utf16_len(result)
            result += _PLACEHOLDER
            entities.append(MessageEntity(
                type="custom_emoji",
                offset=offset,
                length=_utf16_len(_PLACEHOLDER),
                custom_emoji_id=emoji_id,
            ))
        else:
            result += m.group(0)
        last_end = m.end()
    result += template[last_end:]
    return result, entities
