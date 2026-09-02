import sys
sys.stdout.reconfigure(encoding='utf-8')
content = open('tools/clustering.py', 'r', encoding='utf-8').read()

old_rest = '''    # Assign restaurants to clusters based on location
    for cluster in clusters:
        if not cluster.center_lat or not cluster.center_lng:
            cluster.center_lat, cluster.center_lng = _area_center(cluster.attractions)
        
        # Find closest restaurants
        cluster_restaurants = []
        for rest in restaurants:
            rest_lat = rest.get("lat", 0)
            rest_lng = rest.get("lng", 0)
            
            if not rest_lat or not rest_lng:
                continue
            
            dist = _haversine_km(
                cluster.center_lat, cluster.center_lng,
                rest_lat, rest_lng
            )
            
            if dist < 5.0:  # Within 5km
                cluster_restaurants.append((dist, rest))
        
        # Sort by distance and take top 3
        cluster_restaurants.sort(key=lambda x: x[0])
        cluster.restaurants = [r for _, r in cluster_restaurants[:3]]'''

new_rest = '''    # Assign restaurants to clusters with cross-day deduplication
    assigned_restaurant_ids: set[str] = set()

    for cluster in clusters:
        if not cluster.center_lat or not cluster.center_lng:
            cluster.center_lat, cluster.center_lng = _area_center(cluster.attractions)

        # Find closest restaurants not yet assigned to other days
        cluster_restaurants = []
        for rest in restaurants:
            rest_id = rest.get("id", rest.get("name", ""))
            if rest_id in assigned_restaurant_ids:
                continue  # Skip already-assigned restaurant

            rest_lat = rest.get("lat", 0)
            rest_lng = rest.get("lng", 0)
            if not rest_lat or not rest_lng:
                continue

            dist = _haversine_km(
                cluster.center_lat, cluster.center_lng,
                rest_lat, rest_lng,
            )

            if dist < 5.0:  # Within 5km
                # Bonus for score from RestaurantAgent
                agent_score = rest.get("_score", 0)
                # Combine: lower distance = better, higher score = better
                combined = agent_score - dist * 10
                cluster_restaurants.append((combined, dist, rest))

        # Sort by combined score (best first), take top 3
        cluster_restaurants.sort(key=lambda x: x[0], reverse=True)
        cluster.restaurants = [r for _, _, r in cluster_restaurants[:3]]

        # Track assigned restaurant IDs to prevent cross-day duplicates
        for r in cluster.restaurants:
            rid = r.get("id", r.get("name", ""))
            if rid:
                assigned_restaurant_ids.add(rid)'''

if old_rest in content:
    content = content.replace(old_rest, new_rest)
    open('tools/clustering.py', 'w', encoding='utf-8').write(content)
    print("clustering.py updated with cross-day restaurant dedup")
else:
    print("ERROR: pattern not found")
    # Show what's actually there
    import re
    m = re.search(r'# Assign restaurants.*?cluster.restaurants = \[.*?\]', content, re.DOTALL)
    if m:
        print(repr(m.group()[:200]))
