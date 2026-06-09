#!/usr/bin/env python3
"""Ingest city guide data into ChromaDB for RAG retrieval."""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.rag import ingest_city_guide, ingest_guidebook


def main():
    data_dir = "data"
    if not os.path.isdir(data_dir):
        print(f"Error: Data directory '{data_dir}' not found")
        sys.exit(1)

    cities = [d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d))]
    print(f"Found {len(cities)} cities: {', '.join(sorted(cities))}")
    print()

    total_chunks = 0
    for city in sorted(cities):
        guide_path = os.path.join(data_dir, city, "city_guide.json")
        guidebook_path = os.path.join(data_dir, city, "guidebook.json")

        n1 = ingest_city_guide(city, guide_path)
        n2 = ingest_guidebook(city, guidebook_path)

        total = n1 + n2
        total_chunks += total
        status = "✓" if total > 0 else "○"
        print(f"  {status} {city:15s} | guide: {n1:3d} | guidebook: {n2:3d} | total: {total:3d}")

    print(f"\nDone: {total_chunks} total chunks ingested into ChromaDB")


if __name__ == "__main__":
    main()
