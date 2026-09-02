import httpx, json

resp = httpx.post(
    'http://localhost:8090/agent/plan-sync',
    json={"message": "去长沙3天，想去岳麓山和橘子洲"},
    timeout=120
)
data = resp.json()
print("Status:", data.get("status"))
print("Source:", data.get("source"))

itin = data.get("itinerary")
if itin:
    print()
    print("=" * 50)
    print("  AI Generated Itinerary")
    print("=" * 50)
    city = itin["city"]
    days = itin["days"]
    hotel = itin.get("hotel")
    print(f"City: {city}")
    print(f"Days: {len(days)}")
    if hotel:
        hname = hotel["name"]
        harea = hotel.get("area", "")
        print(f"Hotel: {hname} ({harea})")
    print()
    
    for day in days:
        day_num = day["day"]
        print(f"--- Day {day_num} ---")
        for stop in day.get("stops", []):
            sm = stop["start_minutes"]
            h = sm // 60
            m = sm % 60
            slot = stop["slot"]
            pname = stop["poi_name"]
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
    print("No itinerary")
    print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
