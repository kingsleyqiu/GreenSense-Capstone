"""Demonstrate tomato planting and allocation decisions using public evidence."""
import argparse
from urllib.error import URLError

from advisor import advise
from models import harvest_signal, market_signal, storage_signal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-days", type=int, choices=[1, 4, 8, 12], default=8)
    parser.add_argument("--treatment", choices=[f"T{i}" for i in range(1, 7)], default="T1")
    args = parser.parse_args()
    market = market_signal()
    harvest = harvest_signal()
    storage = storage_signal(args.storage_days, args.treatment)

    print(f"1. PLANTING OUTLOOK | Ontario greenhouse tomatoes, {market['year']} (tonnes/year)")
    for key, label in [("estimated_consumption_kg", "Estimated fresh consumption"),
                       ("exports_kg", "International exports"), ("marketed_kg", "Marketed production")]:
        score = market["targets"][key]
        print(f"   {label}: {score['tonnes']:,} t ({score['method']}). "
              f"2023-25 mean absolute error: {score['test_mae_t']:,} t.")
        print(f"     Test comparison: MLP {score['mlp_mae_t']:,} t | previous year {score['baseline_mae_t']:,} t.")
    print("   Consumption is a supply-balance estimate. Provincial flows do not measure unfilled orders.")
    print(f"\n2. NEXT PICK | Public AGC2 compartment AICU ({harvest['area_m2']} m2)")
    print(f"   Replay for {harvest['event']}: predicted {harvest['predicted_kg']:.2f} kg, "
          f"recorded {harvest['observed_kg']:.2f} kg.")
    print(f"   Last {harvest['checks']} picks: mean absolute error {harvest['mae_kg']:.2f} kg "
          f"(previous three-pick average {harvest['baseline_mae_kg']:.2f} kg).")
    print(f"\n3. STORED FRUIT | Public experiment, {args.treatment}, day {args.storage_days}")
    print(f"   Predicted firmness {storage['predicted_firmness']:.2f} kgf/cm2, "
          f"measured replicate {storage['held_out_firmness']:.2f} kgf/cm2.")
    print(f"   {storage['checks']} held-out measurements: mean absolute error {storage['mae']:.2f} kgf/cm2 "
          f"(same-condition average {storage['baseline_mae']:.2f}).")
    print("\n4. FARM DECISION | Public data only")
    print("   Planting area, available stock, confirmed outlets, unused kilograms and financial loss: unknown.")
    print("   To size a crop: establish a reachable sales volume and marketable yield per unit area.")
    print("   To track waste: record each batch's sold, processed, own-use and discarded quantities.")
    print("\n5. GROWER BRIEF | Local Qwen", flush=True)
    try:
        brief = advise(harvest, storage, market)
    except (OSError, URLError, RuntimeError, ValueError, KeyError, IndexError) as exc:
        parser.exit(1, f"Adviser unavailable: {exc}\n")
    print(f"   {brief['summary']}\n   Suggested action: {brief['advice']}")


if __name__ == "__main__":
    main()
