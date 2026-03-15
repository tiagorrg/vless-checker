#!/usr/bin/env python3
import requests
import socket
import time
import json
import os
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

BLACK_URL = "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/BLACK_VLESS_RUS.txt"
WHITE_URL = "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/WHITE-CIDR-RU-checked.txt"

MAX_WORKERS = 20
TEST_TIMEOUT = 5
MAX_LATENCY_MS = 2000

COUNTRIES = {
    "estonia":     ["estonia"],
    "finland":     ["finland"],
    "germany":     ["germany"],
    "sweden":      ["sweden"],
    "netherlands": ["netherlands"],
}


def fetch_keys(url):
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    lines = resp.text.strip().splitlines()
    return [line.strip() for line in lines if line.strip().startswith("vless://")]


def filter_keys(keys, mode):
    if mode in COUNTRIES:
        keywords = COUNTRIES[mode]
        return [k for k in keys if any(kw in k.lower() for kw in keywords)]
    if mode == "white":
        return [k for k in keys if "russia" not in k.lower()]
    if mode == "russia":
        return [k for k in keys if "russia" in k.lower()]
    return keys


def parse_host_port(key):
    try:
        without_scheme = key[len("vless://"):]
        at_idx = without_scheme.rfind("@")
        after_at = without_scheme[at_idx + 1:]
        host_port = after_at.split("?")[0].split("#")[0]
        if ":" in host_port:
            host, port = host_port.rsplit(":", 1)
            return host.strip("[]"), int(port)
    except Exception:
        pass
    return None, None


def test_key(key):
    host, port = parse_host_port(key)
    if not host:
        return None
    start = time.time()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TEST_TIMEOUT)
        result = sock.connect_ex((host, port))
        sock.close()
        elapsed = round((time.time() - start) * 1000, 1)
        if result == 0 and elapsed <= MAX_LATENCY_MS:
            return {"key": key, "host": host, "port": port, "latency_ms": elapsed}
    except Exception:
        pass
    return None


def check_mode(keys):
    working = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(test_key, key): key for key in keys}
        for future in as_completed(futures):
            result = future.result()
            if result:
                working.append(result)

    working.sort(key=lambda x: x["latency_ms"])

    return {
        "best": working[0]["key"] if working else None,
        "top5": working[:5],
        "total_working": len(working),
        "total": len(keys),
    }


def main():
    print("Загружаем BLACK ключи...")
    black_keys = fetch_keys(BLACK_URL)
    print(f"Загружено {len(black_keys)} BLACK ключей")

    print("Загружаем WHITE ключи...")
    white_keys = fetch_keys(WHITE_URL)
    print(f"Загружено {len(white_keys)} WHITE ключей")

    results = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }

    for country in COUNTRIES:
        filtered = filter_keys(black_keys, country)
        print(f"[{country}] {len(filtered)} ключей, проверяем...")
        results[country] = check_mode(filtered)
        print(f"[{country}] Рабочих: {results[country]['total_working']}/{results[country]['total']}")

    for mode in ("white", "russia"):
        filtered = filter_keys(white_keys, mode)
        print(f"[{mode}] {len(filtered)} ключей, проверяем...")
        results[mode] = check_mode(filtered)
        print(f"[{mode}] Рабочих: {results[mode]['total_working']}/{results[mode]['total']}")

    os.makedirs("docs", exist_ok=True)
    with open("docs/keys.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("Сохранено в docs/keys.json")


if __name__ == "__main__":
    main()
