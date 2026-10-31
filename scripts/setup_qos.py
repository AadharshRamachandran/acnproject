"""Apply configured HTB queues to a discovered OVS port and print queue UUIDs."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from manager.actuator import setup_qos
from manager.config import load_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("interface", help="OVS port name (normally s1-ethN)")
    args = parser.parse_args()
    try:
        print(json.dumps(setup_qos(args.interface, load_config()), indent=2))
    except FileNotFoundError as exc:
        parser.error(f"required OVS executable missing: {exc}")
    except Exception as exc:
        parser.error(f"could not configure HTB queues on {args.interface}: {exc}")


if __name__ == "__main__":
    main()
