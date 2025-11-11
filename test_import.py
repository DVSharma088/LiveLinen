import importlib, traceback

mod = "dispatch.views"
print(f"Testing import of {mod}...")

try:
    importlib.import_module(mod)
    print("✅ OK: dispatch.views imported successfully")
except Exception:
    print("❌ Import failed. Traceback below:\n")
    traceback.print_exc()
