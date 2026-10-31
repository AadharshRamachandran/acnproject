"""Fail-fast checks for native Linux and container testbed dependencies."""
import importlib.util
import shutil
import sys


def main():
    commands = ("ovs-vsctl", "ovs-ofctl", "mn", "iperf3", "tc")
    missing = [name for name in commands if shutil.which(name) is None]
    modules = ("mininet", "ryu", "yaml", "sklearn", "numpy", "matplotlib")
    missing_modules = [name for name in modules if importlib.util.find_spec(name) is None]
    if missing or missing_modules:
        print("Missing testbed dependencies:", file=sys.stderr)
        for name in missing:
            print(f"  executable: {name}", file=sys.stderr)
        for name in missing_modules:
            print(f"  Python module: {name}", file=sys.stderr)
        print("Use the supplied Dockerfile or install these packages on a supported Linux host.", file=sys.stderr)
        return 1
    print("Environment checks passed (Linux, OVS, Mininet, iperf3, tc, Python modules).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
