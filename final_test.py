import httpx
import json

print("Generating itinerary for: 带父母去长沙3天，想去岳麓山和橘子洲")
print()

resp = httpx.post(
    "http://localhost:8090/agent/plan-sync",
    json={"message": "带父母去长沙3天，想去岳麓山和橘子洲，住岳麓区"},
    timeout=120
)
data = resp.json()

print(f"Status: {data.get('status')}")
print(f"Source: {data.get('source')}")

itin = data.get("itinerary")
if itin:
    print()
    print("=" * 50)
    print("  AI Generated Itinerary (Hotel + Route Fixed)")
    print("=" * 50)
    city = itin["city"]
    days = itin["days"]
    print(f"City: {city}")
    print(f"Days: {len(days)}")
    hotel = itin.get("hotel")
    if hotel:
        hname = hotel.get("name", "?")
        harea = hotel.get("area", "?")
        print(f"Hotel: {hname} ({harea})")
    else:
        print("Hotel: None")
    print()

    for day in days:
        day_num = day["day"]
        print(f"--- Day {day_num} ---")
        for stop in day.get("stops", []):
            sm = stop.get("start_minutes", 0)
            h = sm // 60
            m = sm % 60
            slot = stop.get("slot", "?")
            pname = stop.get("poi_name", "?")
            print(f"  [{h:02d}:{m:02d}] {slot} - {pname}")
            reason = stop.get("reason")
            if reason:
                print(f"           {reason}")
        print()

    summary = itin.get("summary")
    if summary:
        print("=== Summary ===")
        print(summary)
else:
    print("No itinerary generated")
    print(json.dumps(data, ensure_ascii=False, indent=2)[:1000])
