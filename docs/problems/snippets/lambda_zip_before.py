# Before q01: vendored the import packages as folders, without their dist-info metadata.
# @learn:before-lambda-zip
for mod in ("pg8000", "scramp", "asn1crypto", "dateutil", "six"):
    spec = importlib.util.find_spec(mod)
    origin = Path(spec.origin)
    if origin.name == "__init__.py":
        for f in sorted(origin.parent.rglob("*.py")):
            put(f, f"{mod}/{f.relative_to(origin.parent)}")
    else:
        put(origin, origin.name)
# @learn:end before-lambda-zip
