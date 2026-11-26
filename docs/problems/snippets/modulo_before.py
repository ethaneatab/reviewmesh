# Before q08: owner = hash % N. Correct until N changes.
# @learn:before-modulo
def owner(key: str, workers: list[str]) -> str:
    workers = sorted(workers)
    return workers[h64(key) % len(workers)]
# @learn:end before-modulo
