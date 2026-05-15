"""Non-interactive version of demo_run.sh - runs the full pipeline."""
import os
os.environ.setdefault("OPENSEARCH_ENDPOINT", "<your-opensearch-endpoint>")

from os_client import get_client
from config import OPENSEARCH_INDEX

client = get_client()

# Step 0: Health check
info = client.info()
print("=== Step 0: Health Check ===")
cluster = info.get("cluster_name", "unknown")
version = info.get("version", {}).get("number", "unknown")
print("Cluster: " + cluster + ", Version: " + version)

# Step 1: Counts before
def cnt(q=None):
    return client.count(index=OPENSEARCH_INDEX, body=(q or {"query": {"match_all": {}}}))["count"]

try:
    total = cnt()
    scanned = cnt({"query": {"exists": {"field": "pii_flag"}}})
    flagged = cnt({"query": {"term": {"pii_flag": True}}})
    print("\n=== Step 1: Counts BEFORE ===")
    print("Total: " + str(total) + "  Scanned: " + str(scanned) + "  Flagged: " + str(flagged))
except Exception as e:
    print("Index may not exist yet: " + str(e))
    total = 0

# Step 2: Add test data
print("\n=== Step 2: Seed Test Data ===")
import add_more_data
add_more_data.seed()

# Step 3: Counts after seed
total = cnt()
scanned = cnt({"query": {"exists": {"field": "pii_flag"}}})
print("\n=== Step 3: Coverage BEFORE scan ===")
print("Scanned: " + str(scanned) + "/" + str(total))

# Step 4: Run PII detection
print("\n=== Step 4: Run Comprehend PII Detection ===")
import detect_pii
detect_pii.scan_unscanned()

# Step 5: Counts after scan
total = cnt()
scanned = cnt({"query": {"exists": {"field": "pii_flag"}}})
flagged = cnt({"query": {"term": {"pii_flag": True}}})
print("\n=== Step 5: Coverage AFTER scan ===")
print("Scanned: " + str(scanned) + "/" + str(total) + "  Flagged: " + str(flagged))

# Step 6: PII type breakdown
print("\n=== Step 6: PII Type Breakdown ===")
resp = client.search(index=OPENSEARCH_INDEX, body={"size": 0, "aggs": {"t": {"terms": {"field": "pii_types", "size": 20}}}})
buckets = resp.get("aggregations", {}).get("t", {}).get("buckets", [])
if not buckets:
    print("No PII types found.")
for b in buckets:
    print("  " + b["key"] + ": " + str(b["doc_count"]))

print("\n=== Done ===")
