"""同工况比较：python -m motorlab.experiments --output outputs/comparison。"""
import argparse
import csv
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "motorlab-matplotlib"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .simulation import Simulation


def compare(config=None, output="outputs/comparison"):
    folder = Path(output)
    folder.mkdir(parents=True, exist_ok=True)
    results = {}
    fig, axes = plt.subplots(4, 1, figsize=(11, 11), sharex=True)
    for mode in ("fixed", "adaptive", "oracle"):
        sim = Simulation({**(config or {}), "mode": mode})
        while not sim.done:
            sim.step(500)
        results[mode] = {"config": sim.config, "metrics": sim.metrics()}
        with (folder / f"{mode}.csv").open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=list(sim.snapshot()))
            writer.writeheader()
            writer.writerows(sim.history)
        time = [r["time"] for r in sim.history]
        for ax, key in zip(axes, ("rr_est", "speed_error_rpm", "flux_angle_error_deg", "current_magnitude")):
            ax.plot(time, [r[key] for r in sim.history], label=mode, linewidth=1.1)
        print(f"{mode}: {json.dumps(sim.metrics(), ensure_ascii=False)}", flush=True)
    axes[0].plot(time, [r["rr_true"] for r in sim.history], "k--", label="true Rr (evaluation)")
    for ax, label in zip(axes, ("Estimated Rr / ohm", "Speed error / rpm", "Flux angle error / deg", "Current magnitude / A")):
        ax.set_ylabel(label)
        ax.grid(alpha=.25)
        ax.legend(loc="upper right")
    axes[-1].set_xlabel("Simulation time / s")
    fig.suptitle("Identical configuration and noise seed; ideal averaged inverter")
    fig.tight_layout()
    fig.savefig(folder / "comparison.png", dpi=140)
    plt.close(fig)
    (folder / "summary.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="比较固定参数、在线补偿与真实参数参考")
    parser.add_argument("--output", default="outputs/comparison")
    args = parser.parse_args()
    compare(output=args.output)
