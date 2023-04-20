def str_to_bool(value):
    if type(value) == bool:
        return value

    if not value or type(value) != str:
        return False

    return value.lower() in ("y", "yes", "true", "on", "1")
