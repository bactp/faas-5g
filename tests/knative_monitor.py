#!/usr/bin/env python3
"""
Knative Pod Lifecycle Monitor — tracks pod scaling and startup breakdown.

Requires: kubectl configured and pointing to your cluster.

Usage:
  # Start monitor (keep running during UE test)
  python3 knative_monitor.py --service cifar10-faas --namespace default

  # With health polling against the service URL
  python3 knative_monitor.py --service cifar10-faas --health-url http://<ksvc-url>/health

  # Auto stop after N seconds
  python3 knative_monitor.py --service cifar10-faas --duration 120
"""

import subprocess
import json
import time
import csv
import argparse
import threading
import requests
from datetime import datetime, timezone
from collections import defaultdict


# ── kubectl helpers ───────────────────────────────────────────────────────────

def kubectl_get_pods(namespace, selector):
    """Return list of pod dicts for the given label selector."""
    try:
        out = subprocess.check_output([
            "kubectl", "get", "pods",
            "-n", namespace,
            "-l", selector,
            "-o", "json",
            "--field-selector", "status.phase!=Failed"
        ], stderr=subprocess.DEVNULL)
        return json.loads(out).get("items", [])
    except Exception:
        return []


def get_knative_selector(service_name, namespace):
    """Get pod label selector for a Knative service."""
    try:
        out = subprocess.check_output([
            "kubectl", "get", "ksvc", service_name,
            "-n", namespace,
            "-o", "jsonpath={.status.latestCreatedRevisionName}"
        ], stderr=subprocess.DEVNULL)
        revision = out.decode().strip()
        return f"serving.knative.dev/revision={revision}"
    except Exception:
        # fallback to service label
        return f"serving.knative.dev/service={service_name}"


def parse_timestamp(ts_str):
    """Parse ISO8601 timestamp → epoch seconds (float)."""
    if not ts_str:
        return None
    try:
        ts_str = ts_str.replace("Z", "+00:00")
        return datetime.fromisoformat(ts_str).timestamp()
    except Exception:
        return None


# ── pod lifecycle extractor ───────────────────────────────────────────────────

def extract_pod_lifecycle(pod):
    """
    Extract all lifecycle timestamps from a pod object.
    Returns dict with keys: created, scheduled, initialized, running, ready
    All values are epoch seconds (float) or None if not yet reached.
    """
    meta   = pod.get("metadata", {})
    status = pod.get("status", {})
    name   = meta.get("name", "unknown")

    # T_created
    t_created = parse_timestamp(meta.get("creationTimestamp"))

    # T_scheduled, T_initialized, T_ready (from conditions)
    t_scheduled   = None
    t_initialized = None
    t_ready       = None
    for cond in status.get("conditions", []):
        ctype  = cond.get("type")
        cstatus = cond.get("status")
        ts     = parse_timestamp(cond.get("lastTransitionTime"))
        if ctype == "PodScheduled"  and cstatus == "True": t_scheduled   = ts
        if ctype == "Initialized"   and cstatus == "True": t_initialized = ts
        if ctype == "Ready"         and cstatus == "True": t_ready       = ts

    # T_running (container actually started)
    t_running = None
    for cs in status.get("containerStatuses", []):
        run_ts = cs.get("state", {}).get("running", {}).get("startedAt")
        if run_ts:
            t_running = parse_timestamp(run_ts)
            break

    phase = status.get("phase", "Unknown")

    return {
        "pod_name":     name,
        "phase":        phase,
        "t_created":    t_created,
        "t_scheduled":  t_scheduled,
        "t_initialized":t_initialized,
        "t_running":    t_running,
        "t_ready":      t_ready,
    }


def compute_deltas(lc):
    """Compute duration breakdowns from lifecycle timestamps."""
    d = {}

    def delta_ms(a, b):
        if a is not None and b is not None:
            return round((b - a) * 1000, 1)
        return None

    d["schedule_lag_ms"]    = delta_ms(lc["t_created"],    lc["t_scheduled"])
    d["init_ms"]            = delta_ms(lc["t_scheduled"],  lc["t_initialized"])
    d["container_start_ms"] = delta_ms(lc["t_initialized"],lc["t_running"])
    d["app_ready_ms"]       = delta_ms(lc["t_running"],    lc["t_ready"])
    d["cold_start_ms"]      = delta_ms(lc["t_created"],    lc["t_ready"])
    return d


# ── health poller ─────────────────────────────────────────────────────────────

class HealthPoller:
    """
    Polls GET /health every 300ms.
    Records the first time it gets HTTP 200 after a period of non-200.
    """
    def __init__(self, url, interval=0.3):
        self.url      = url
        self.interval = interval
        self.events   = []   # list of (epoch_s, status_code)
        self._stop    = threading.Event()

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        prev_ok = None
        while not self._stop.is_set():
            try:
                r = requests.get(self.url, timeout=2)
                code = r.status_code
            except Exception:
                code = 0
            now = time.time()
            if (prev_ok is None) or (code == 200 and prev_ok != 200) or (code != 200 and prev_ok == 200):
                self.events.append((now, code))
                prev_ok = code
            time.sleep(self.interval)

    def first_200_after(self, after_epoch):
        """Return epoch of first HTTP 200 seen after after_epoch."""
        for ts, code in self.events:
            if ts >= after_epoch and code == 200:
                return ts
        return None


# ── main monitor loop ─────────────────────────────────────────────────────────

class KnativeMonitor:
    def __init__(self, service, namespace, health_url=None, poll_interval=0.5):
        self.service       = service
        self.namespace     = namespace
        self.health_url    = health_url
        self.poll_interval = poll_interval
        self.selector      = get_knative_selector(service, namespace)
        self.baseline_pods = set()
        self.tracked       = {}   # pod_name → latest lifecycle dict
        self.new_pods      = []   # list of finalized pod records
        self._stop         = threading.Event()
        self.health_poller = HealthPoller(health_url) if health_url else None
        self.t_start       = None

    def snapshot_baseline(self):
        """Call this BEFORE the load test starts."""
        pods = kubectl_get_pods(self.namespace, self.selector)
        self.baseline_pods = {p["metadata"]["name"] for p in pods}
        self.t_start = time.time()
        print(f"  Baseline: {len(self.baseline_pods)} existing pod(s)")
        print(f"  Selector: {self.selector}")
        if self.health_poller:
            self.health_poller.start()
            print(f"  Health poller: {self.health_url}")

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print(f"  Monitor started (poll every {self.poll_interval}s)...")

    def stop(self):
        self._stop.set()
        if self.health_poller:
            self.health_poller.stop()

    def _run(self):
        while not self._stop.is_set():
            pods = kubectl_get_pods(self.namespace, self.selector)
            for pod in pods:
                name = pod["metadata"]["name"]
                if name in self.baseline_pods:
                    continue   # skip pre-existing pods
                lc = extract_pod_lifecycle(pod)
                self.tracked[name] = lc
                deltas = compute_deltas(lc)
                phase = lc["phase"]
                ready = lc["t_ready"] is not None
                symbol = "✓" if ready else "⏳"
                print(f"\r  {symbol} {name[-24:]:24s} | phase={phase:8s} | "
                      f"cold_start={str(deltas['cold_start_ms'])+'ms':>10s} | "
                      f"pods={len(self.tracked)}   ", end="", flush=True)
            time.sleep(self.poll_interval)

    def finalize(self):
        """Call after test completes — build final records."""
        print()  # newline after \r updates
        records = []
        for name, lc in self.tracked.items():
            deltas  = compute_deltas(lc)
            rec     = {**lc, **deltas}

            # Health endpoint: first 200 after pod was created
            if self.health_poller and lc["t_created"]:
                rec["health_200_epoch"] = self.health_poller.first_200_after(lc["t_created"])
                if rec["health_200_epoch"] and lc["t_created"]:
                    rec["health_ready_ms"] = round((rec["health_200_epoch"] - lc["t_created"]) * 1000, 1)
                else:
                    rec["health_ready_ms"] = None
            else:
                rec["health_200_epoch"] = None
                rec["health_ready_ms"]  = None

            # Convert epoch → ISO strings for readability
            for key in ["t_created", "t_scheduled", "t_initialized", "t_running", "t_ready"]:
                if rec[key]:
                    rec[key + "_iso"] = datetime.fromtimestamp(rec[key], tz=timezone.utc).isoformat()

            records.append(rec)

        records.sort(key=lambda r: r["t_created"] or 0)
        self.new_pods = records
        return records

    def print_summary(self):
        if not self.new_pods:
            print("\n  No new pods were created during the test window.")
            return

        print(f"\n{'═'*70}")
        print(f"  KNATIVE SCALING SUMMARY")
        print(f"{'═'*70}")
        print(f"  New pods created : {len(self.new_pods)}")
        print()

        for i, rec in enumerate(self.new_pods):
            print(f"  Pod #{i+1}: {rec['pod_name']}")
            print(f"    Created     : {rec.get('t_created_iso', 'N/A')}")
            print(f"    Scheduled   : {rec.get('t_scheduled_iso', 'N/A')}   (+{rec['schedule_lag_ms']} ms)")
            print(f"    Initialized : {rec.get('t_initialized_iso', 'N/A')}   (+{rec['init_ms']} ms)")
            print(f"    Running     : {rec.get('t_running_iso', 'N/A')}   (+{rec['container_start_ms']} ms)")
            print(f"    Ready       : {rec.get('t_ready_iso', 'N/A')}   (+{rec['app_ready_ms']} ms)")
            if rec["health_ready_ms"] is not None:
                print(f"    /health 200 : +{rec['health_ready_ms']} ms from creation")
            print(f"    ── Cold start total : {rec['cold_start_ms']} ms ──")
            print()

        # aggregate across all pods
        cold_starts = [r["cold_start_ms"] for r in self.new_pods if r["cold_start_ms"]]
        if cold_starts:
            import statistics
            print(f"  Cold start (all pods): min={min(cold_starts)}ms  "
                  f"avg={statistics.mean(cold_starts):.0f}ms  max={max(cold_starts)}ms")
        print(f"{'═'*70}")


# ── CSV export ────────────────────────────────────────────────────────────────

def save_csv(records, path):
    if not records:
        return
    # flatten: exclude raw epoch fields, keep ISO + delta fields
    exclude = {"t_created","t_scheduled","t_initialized","t_running","t_ready","health_200_epoch"}
    keys = [k for k in records[0].keys() if k not in exclude]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    print(f"\n  Pod lifecycle saved → {path}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Knative pod lifecycle monitor")
    parser.add_argument("--service",    required=True, help="Knative service name, e.g. cifar10-faas")
    parser.add_argument("--namespace",  default="default")
    parser.add_argument("--health-url", default=None,  help="Full URL to /health endpoint for app-ready tracking")
    parser.add_argument("--duration",   type=int, default=0,
                        help="Auto-stop after N seconds (0 = wait for Ctrl+C)")
    parser.add_argument("--out",        default=None)
    args = parser.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = args.out or f"knative_pods_{ts}.csv"

    monitor = KnativeMonitor(
        service=args.service,
        namespace=args.namespace,
        health_url=args.health_url,
    )

    print(f"\n[Knative Monitor] service={args.service} namespace={args.namespace}")
    monitor.snapshot_baseline()
    monitor.start()

    try:
        if args.duration > 0:
            print(f"  Auto-stop in {args.duration}s  (or Ctrl+C)")
            time.sleep(args.duration)
        else:
            print("  Running... press Ctrl+C to stop and export results.")
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass

    print("\n  Stopping monitor...")
    monitor.stop()
    records = monitor.finalize()
    monitor.print_summary()
    save_csv(records, out)


if __name__ == "__main__":
    main()
