#!/usr/bin/env python3
"""
UE Traffic Generator — measures end-to-end request latency.

Usage:
  # Sequential: 1 UE, 10 requests one by one
  python3 ue_traffic_gen.py --url http://<ksvc-url>/predict --image test_0_cat.png --mode sequential

  # Concurrent burst: 1 UE, N images at same time
  python3 ue_traffic_gen.py --url http://<ksvc-url>/predict --images test_0_cat.png test_1_ship.png ... --mode concurrent

  # Ramp: auto test N=5,10,15 concurrent
  python3 ue_traffic_gen.py --url http://<ksvc-url>/predict --image test_0_cat.png --mode ramp
"""

import asyncio
import aiohttp
import argparse
import csv
import time
import statistics
import os
from datetime import datetime, timezone


# ── helpers ──────────────────────────────────────────────────────────────────

def now_ms():
    return time.perf_counter() * 1000


def utc_iso():
    return datetime.now(timezone.utc).isoformat()


def print_summary(label, latencies_ms):
    s = sorted(latencies_ms)
    n = len(s)
    print(f"\n{'─'*50}")
    print(f"  {label}")
    print(f"{'─'*50}")
    print(f"  Requests : {n}")
    print(f"  Min      : {min(s):.1f} ms")
    print(f"  Avg      : {statistics.mean(s):.1f} ms")
    print(f"  Median   : {statistics.median(s):.1f} ms")
    print(f"  p95      : {s[int(n*0.95)]:.1f} ms")
    print(f"  p99      : {s[min(int(n*0.99), n-1)]:.1f} ms")
    print(f"  Max      : {max(s):.1f} ms")
    if n > 1:
        print(f"  Stdev    : {statistics.stdev(s):.1f} ms")
    print(f"{'─'*50}")


# ── single request ────────────────────────────────────────────────────────────

async def send_request(session, url, image_path, req_id, ue_id=0):
    """Send one POST /predict and return timing + result."""
    t_send = now_ms()
    t_send_iso = utc_iso()
    status = 0
    prediction = ""
    confidence = 0.0
    error = ""

    try:
        with open(image_path, "rb") as f:
            data = aiohttp.FormData()
            data.add_field("file", f,
                           filename=os.path.basename(image_path),
                           content_type="image/png")
            async with session.post(url, data=data) as resp:
                status = resp.status
                if status == 200:
                    body = await resp.json()
                    prediction = body.get("prediction", "")
                    confidence = body.get("confidence", 0.0)
                else:
                    error = await resp.text()
    except Exception as e:
        error = str(e)

    t_recv = now_ms()
    latency = t_recv - t_send

    return {
        "ue_id":       ue_id,
        "req_id":      req_id,
        "image":       os.path.basename(image_path),
        "t_send_iso":  t_send_iso,
        "latency_ms":  round(latency, 2),
        "status":      status,
        "prediction":  prediction,
        "confidence":  round(confidence, 4),
        "error":       error,
    }


# ── modes ─────────────────────────────────────────────────────────────────────

async def mode_sequential(url, image_path, n=10, delay_s=0.0):
    """1 UE, N requests one after another."""
    print(f"\n[Sequential] {n} requests → {url}")
    rows = []
    async with aiohttp.ClientSession() as session:
        for i in range(n):
            row = await send_request(session, url, image_path, req_id=i)
            rows.append(row)
            status_icon = "✓" if row["status"] == 200 else "✗"
            print(f"  [{i+1:02d}] {status_icon} {row['latency_ms']:7.1f} ms  "
                  f"→ {row['prediction']} ({row['confidence']:.2%})")
            if delay_s > 0:
                await asyncio.sleep(delay_s)

    print_summary("Sequential Results", [r["latency_ms"] for r in rows])
    return rows


async def mode_concurrent_burst(url, image_paths, ue_id=0):
    """1 UE, send len(image_paths) requests simultaneously."""
    n = len(image_paths)
    print(f"\n[Concurrent] {n} simultaneous requests → {url}")

    t_batch_start = now_ms()
    async with aiohttp.ClientSession() as session:
        tasks = [
            send_request(session, url, img, req_id=i, ue_id=ue_id)
            for i, img in enumerate(image_paths)
        ]
        rows = await asyncio.gather(*tasks)
    t_batch_end = now_ms()

    rows = list(rows)
    for r in rows:
        status_icon = "✓" if r["status"] == 200 else "✗"
        print(f"  [req {r['req_id']:02d}] {status_icon} {r['latency_ms']:7.1f} ms  "
              f"→ {r['prediction']} ({r['confidence']:.2%})")

    total_ms = t_batch_end - t_batch_start
    print(f"\n  Batch wall-clock: {total_ms:.1f} ms  ({n} req in parallel)")
    print_summary(f"Concurrent N={n} Results", [r["latency_ms"] for r in rows])

    for r in rows:
        r["batch_n"] = n
        r["batch_wall_ms"] = round(total_ms, 2)

    return rows


async def mode_ramp(url, image_path, levels=None):
    """Ramp up concurrent requests: N = 5, 10, 15 (reuses same image)."""
    if levels is None:
        levels = [5, 10, 15]

    all_rows = []
    for n in levels:
        images = [image_path] * n
        rows = await mode_concurrent_burst(url, images, ue_id=0)
        all_rows.extend(rows)
        print(f"\n  ⏳ Cooling down 5s before next ramp level...")
        await asyncio.sleep(5)

    return all_rows


# ── CSV export ────────────────────────────────────────────────────────────────

def save_csv(rows, path):
    if not rows:
        return
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n  Results saved → {path}")


# ── main ──────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="UE traffic generator for CIFAR-10 FaaS")
    parser.add_argument("--url",    required=True, help="Full predict URL, e.g. http://host/predict")
    parser.add_argument("--image",  default=None,  help="Single image path (sequential / ramp modes)")
    parser.add_argument("--images", nargs="+",     help="Multiple image paths (concurrent mode)")
    parser.add_argument("--mode",   default="sequential",
                        choices=["sequential", "concurrent", "ramp"],
                        help="Test mode")
    parser.add_argument("--n",      type=int, default=10, help="Number of sequential requests")
    parser.add_argument("--delay",  type=float, default=0.0, help="Delay between sequential requests (s)")
    parser.add_argument("--out",    default=None, help="Output CSV path (auto-generated if omitted)")
    args = parser.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if args.mode == "sequential":
        if not args.image:
            parser.error("--image required for sequential mode")
        rows = await mode_sequential(args.url, args.image, n=args.n, delay_s=args.delay)
        out = args.out or f"ue_sequential_{ts}.csv"

    elif args.mode == "concurrent":
        images = args.images or ([args.image] * 5 if args.image else None)
        if not images:
            parser.error("--images or --image required for concurrent mode")
        rows = await mode_concurrent_burst(args.url, images)
        out = args.out or f"ue_concurrent_n{len(images)}_{ts}.csv"

    elif args.mode == "ramp":
        if not args.image:
            parser.error("--image required for ramp mode")
        rows = await mode_ramp(args.url, args.image)
        out = args.out or f"ue_ramp_{ts}.csv"

    save_csv(rows, out)


if __name__ == "__main__":
    asyncio.run(main())
