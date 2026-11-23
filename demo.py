"""Run the GreenSense three-model concept demonstration from PowerShell."""
import argparse
import math
from urllib.error import URLError

from advisor import advise
from models import harvest_signal, market_signal, storage_signal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-days", type=int, choices=[1, 4, 8, 12], default=8)
    parser.add_argument("--shipped-kg", type=float, default=0, help="Simulated outgoing stock in kg")
    args = parser.parse_args()
    if not math.isfinite(args.shipped_kg) or args.shipped_kg < 0:
        parser.error("Outbound stock must be a finite, non-negative weight.")
    try:
        storage = storage_signal(args.storage_days, args.shipped_kg)
    except ValueError as exc:
        parser.error(str(exc))
    harvest = harvest_signal()
    market = market_signal()
    print("GREENSENSE   |   Tomato greenhouse decision support\n")
    print("1. PRE-HARVEST   |   AGC2 harvest records")
    print(f"   Next recorded harvest event: {harvest['predicted_kg']:.2f} kg predicted "
          f"for the {harvest['area_m2']} m2 compartment.\n")
    print("2. STORAGE       |   Simulated stock ledger + tomato quality experiment")
    print(f"   Opening {storage['opening_kg']:.2f} + received {storage['inbound_kg']:.2f}"
          f" - shipped {storage['outbound_kg']:.2f} = {storage['available_kg']:.2f} kg available.")
    print(f"   At storage day {args.storage_days}, predicted firmness is "
          f"{storage['predicted_firmness']:.2f} kgf/cm2.\n")
    print("3. MARKET        |   FreshRetailNet retail sales proxy")
    print(f"   Next-day sales index {market['predicted_sales_index']:.3f}; "
          f"previous three-day mean {market['previous_3day_mean']:.3f}.\n")
    print("4. GROWER BRIEF  |   Local Qwen summary and suggested action", flush=True)
    try:
        result = advise(harvest, storage, market)
    except (OSError, URLError, RuntimeError, ValueError, KeyError, IndexError) as exc:
        parser.exit(1, f"Adviser unavailable: {exc}\n")
    print("   " + result["summary"] + "\n   Suggested action: " + result["advice"])
    print("\nReplay check (single examples):")
    print(f"   Observed harvest {harvest['observed_kg']:.2f} kg | "
          f"Held-out firmness {storage['held_out_firmness']:.2f} kgf/cm2 | "
          f"Observed sales index {market['observed_sales_index']:.3f}")


if __name__ == "__main__":
    main()
