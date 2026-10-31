"""INT-inspired UDP probes; timestamps and sequence numbers are in-band payload."""
import argparse
import csv
import json
import os
import socket
import struct
import time
import select
import random

HEADER = struct.Struct("!Id")  # sequence, sender monotonic timestamp


def receive(path, duration):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        csv.writer(f).writerow(["t", "class", "sequence", "delay_ms", "jitter_ms", "lost_packets"])
    sockets = {}
    for name, port in (("voip", 5101), ("video", 5102), ("bulk", 5103)):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("0.0.0.0", port))
        s.settimeout(0.2)
        sockets[s] = name
    state = {name: {"last": None, "count": 0, "lost": 0, "delay": None,
                    "jitter": 0.0} for name in sockets.values()}
    started = time.monotonic()
    while time.monotonic() - started < duration:
        ready, _, _ = select.select(list(sockets), [], [], 0.2)
        for s in ready:
            name = sockets[s]
            data, _ = s.recvfrom(256)
            if len(data) < HEADER.size:
                continue
            seq, sent = HEADER.unpack_from(data)
            now = time.monotonic()
            delay = max(0.0, (now - sent) * 1000.0)
            row = state[name]
            if row["last"] is not None and seq > row["last"] + 1:
                row["lost"] += seq - row["last"] - 1
            if row["delay"] is not None:
                row["jitter"] += (abs(delay - row["delay"]) - row["jitter"]) / 16.0
            row["delay"] = delay
            row["last"] = seq
            row["count"] += 1
            with open(path, "a", newline="") as f:
                csv.writer(f).writerow([now, name, seq, delay, row["jitter"], row["lost"]])
    for s in sockets:
        s.close()


def send(host, port, rate, duration, seed=0):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    interval = 1.0 / rate
    time.sleep(random.Random(seed).uniform(0.0, interval))
    end = time.monotonic() + duration
    seq = 0
    while time.monotonic() < end:
        sent = time.monotonic()
        sock.sendto(HEADER.pack(seq, sent) + b"qos-probe", (host, port))
        seq += 1
        time.sleep(max(0.0, interval - (time.monotonic() - sent)))
    sock.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("role", choices=("send", "receive"))
    p.add_argument("--host", default="10.0.0.10")
    p.add_argument("--port", type=int, default=5101)
    p.add_argument("--rate", type=float, default=10)
    p.add_argument("--duration", type=float, default=60)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--output", default="results/probes.csv")
    a = p.parse_args()
    receive(a.output, a.duration) if a.role == "receive" else send(a.host, a.port, a.rate, a.duration, a.seed)
