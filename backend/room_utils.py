
import unicodedata


def normalize_room(room_name: str) -> str:
    """
    Convert room names to a consistent identifier.

    Examples:
    hall-A -> halla
    Hall A -> halla
    Hall-A -> halla
    """
    text = unicodedata.normalize("NFKC", room_name)
    return "".join(
        char for char in text.casefold()
        if char.isalnum()
    )
