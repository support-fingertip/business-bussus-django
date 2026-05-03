import re

def get_prefix(name: str) -> str:
    if not name:
        return "ObjX"

    # Split by underscore and camelCase
    parts = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)', name.replace('_', ' '))

    if not parts:
        parts = [name]

    prefix = ''

    # Build a mixed-case prefix from the first two parts
    for i, part in enumerate(parts):
        if i == 0:
            prefix += part[:2].capitalize()  # e.g., 'Fi' from 'fields'
        elif i == 1 and len(prefix) < 4:
            prefix += part[0].upper()        # e.g., 'P' from 'permissions'
        elif len(prefix) < 5:
            prefix += part[0].lower()        # optional third char
        if len(prefix) >= 5:
            break

    # Ensure at least 3 characters
    while len(prefix) < 3:
        prefix += 'X'

    return prefix
