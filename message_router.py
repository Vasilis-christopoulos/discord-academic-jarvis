def is_module_allowed(module: str, context: dict) -> bool:
    channel_type = context.get("type")
    if module == "rag":
        return channel_type in ("rag", "rag-calendar")
    if module == "calendar":
        return channel_type in ("calendar", "rag-calendar")
    if module == "fallback":
        # Fallback is always allowed
        return True
    return False
