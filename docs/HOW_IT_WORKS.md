# How It Works (Plain Language)

If you know what AWS services are but want to understand what this solution actually *does* — this is for you.

---

## The Problem

You have documents going into OpenSearch (think of it as a search engine/database). Some of those documents contain sensitive data — names, social security numbers, credit card numbers, phone numbers, addresses. This solution automatically finds that sensitive data and replaces it with labels like `[NAME]` or `[SSN]` before it ever gets stored. So your search index never contains raw PII.

---

## Mode 1: EC2 (The Always-On Worker)

Think of this as a dedicated computer sitting in your AWS account that you can log into anytime.

**How it works:**
- An EC2 instance runs 24/7 in a private network
- You log in (via SSM — no keys needed) and run Python scripts
- You tell it "scan everything that hasn't been scanned yet" and it goes through your documents one by one
- It calls Comprehend ("hey, does this doc have PII?"), gets the answer, redacts it, and puts the clean version in OpenSearch

**When to use it:**
- You're demoing the solution to a customer
- You're developing/testing
- You want manual control over when scans run

**Downside:** You're paying ~$15/month for that EC2 instance whether it's doing anything or not.

---

## Mode 2: Serverless (The Auto-Pilot)

Think of this as a worker that only exists when there's work to do, then disappears.

**How it works:**
- A Lambda function (tiny piece of code that runs on demand) is wired up to two triggers:
  - **Timer (EventBridge):** Every 5 minutes it wakes up, checks "are there unscanned docs in OpenSearch?", processes them, goes back to sleep
  - **S3 upload:** A new document lands in an S3 bucket → Lambda fires automatically → scans it → indexes the clean version to OpenSearch
- You can also call it directly from your own application code ("here's a document, scan it for me")

**When to use it:**
- Production workloads
- You don't know how many documents you'll get (could be 10 today, 10,000 tomorrow)
- You want zero cost when nothing is happening

**Upside:** You pay literally fractions of a penny per document processed. When nothing's happening, you pay $0 for compute.

---

## Mode 3: Batch (The Bulk Processor)

Think of this as hiring a crew to process a warehouse full of documents overnight.

**How it works:**
- You have 50,000 documents already sitting in OpenSearch that were never scanned
- The script exports them to S3 as a big file
- It kicks off a Comprehend "batch job" — Comprehend processes the entire file in the background (no rate limits, no throttling)
- When it's done (5-15 minutes later), the script reads the results and updates all 50,000 documents in OpenSearch with their PII metadata

**When to use it:**
- You just adopted this solution and have a backlog of existing documents
- You're migrating data from another system
- You have a massive one-time load (100K+ docs)

**Upside:** Comprehend charges 50% less for batch jobs vs. real-time API calls. No throttling. Set it and forget it.

---

## The Secret Sauce (All Modes)

Regardless of which mode you pick, every document goes through the same two-step detection:

1. **Cheap check first** — "Hey Comprehend, does this document contain ANY PII at all?" (costs $0.000025)
   - If NO → mark it clean, done. You just saved money.
   - If YES → proceed to step 2

2. **Full scan** — "OK Comprehend, tell me exactly WHERE the PII is and WHAT type it is" (costs $0.0001)
   - Gets back: "characters 12-22 are a NAME, characters 30-41 are an SSN"
   - Replaces those spans with `[NAME]`, `[SSN]`
   - Indexes the redacted document

This means if 70% of your documents are clean (no PII), you never pay the expensive price for those 70%. That's where the **97% cost savings** comes from compared to just calling the expensive API on everything.

---

## Quick Cost Comparison

| Approach | Cost for 10,000 docs/month |
|----------|---------------------------|
| Do nothing (compliance risk) | $0 + potential fines |
| Manual human review | $5,000+ |
| This solution (serverless) | ~$0.65 |
| This solution (batch) | ~$0.38 |

---

## One-Line Summary

> Documents go in dirty, come out clean — automatically, cheaply, and without ever storing raw PII.
