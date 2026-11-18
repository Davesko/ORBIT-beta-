"""The strongest installed local writer model (gemma4:26b writes natural, funnier text than the 9B), if there is one."""
WRITERS = ('gemma4:26b',)


def writer_model():
    try:
        from studio import local_api
        names = {m.get('name') for m in (local_api('ollama', 'api/tags', None, timeout=5) or {}).get('models', [])}
    except Exception:
        return None
    return next((m for m in WRITERS if m in names), None)
