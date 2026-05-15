"""Generate and index 1000 realistic test documents with varied PII patterns."""
import json
import random
import string
from os_client import get_client
from config import OPENSEARCH_INDEX

FIRST = ["James","Mary","Robert","Patricia","John","Jennifer","Michael","Linda","David","Elizabeth","William","Barbara","Richard","Susan","Joseph","Jessica","Thomas","Sarah","Christopher","Karen","Charles","Lisa","Daniel","Nancy","Matthew","Betty","Anthony","Margaret","Mark","Sandra","Donald","Ashley","Steven","Kimberly","Paul","Emily","Andrew","Donna","Joshua","Michelle","Kenneth","Carol","Kevin","Amanda","Brian","Dorothy","George","Melissa","Timothy","Deborah"]
LAST = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Rodriguez","Martinez","Hernandez","Lopez","Gonzalez","Wilson","Anderson","Thomas","Taylor","Moore","Jackson","Martin","Lee","Perez","Thompson","White","Harris","Sanchez","Clark","Ramirez","Lewis","Robinson","Walker","Young","Allen","King","Wright","Scott","Torres","Nguyen","Hill","Flores"]
STREETS = ["Main St","Oak Ave","Elm Dr","Pine Rd","Maple Ln","Cedar Blvd","Birch Way","Walnut Ct","Cherry Pl","Spruce Ter"]
CITIES = ["Seattle WA 98101","New York NY 10001","Chicago IL 60601","Houston TX 77001","Phoenix AZ 85001","Philadelphia PA 19101","San Antonio TX 78201","San Diego CA 92101","Dallas TX 75201","Austin TX 78701"]
DOMAINS = ["gmail.com","yahoo.com","outlook.com","company.org","example.com"]

TEMPLATES_PII = [
    "New account request from {name}. SSN {ssn}. Email: {email}. Phone: {phone}. Address: {addr}.",
    "Wire transfer of ${amt} authorized by {name} on {date}. Destination account {acct} at {bank}.",
    "Customer {name} (DOB {dob}) reported lost card {cc}. Replacement sent to {addr}.",
    "Loan application: {name}, SSN {ssn}, annual income ${amt}. Contact: {phone}, {email}.",
    "Fraud alert: card {cc} used at unauthorized merchant. Cardholder {name}, phone {phone}.",
    "Account {acct} holder {name} requested address change to {addr}. Verified via {email}.",
    "Insurance claim filed by {name}, policy #{pol}. DOB {dob}. Contact {phone}.",
    "Direct deposit setup for {name}, routing {routing}, account {acct}. Effective {date}.",
    "KYC verification: {name}, passport {passport}, address {addr}. Email {email}.",
    "Beneficiary update: {name} added to account {acct}. SSN {ssn}. Phone {phone}.",
]

TEMPLATES_CLEAN = [
    "Quarterly compliance review completed. No findings. Next review scheduled for Q{q}.",
    "System maintenance window confirmed for Saturday 2AM-6AM EST. All teams notified.",
    "New security policy v{ver} published. All staff must acknowledge by end of month.",
    "Budget allocation for infrastructure upgrades approved. Procurement to begin next sprint.",
    "Team standup notes: deployment pipeline green, no blockers, sprint velocity on track.",
    "Vendor contract renewal processed. SLA terms unchanged from previous agreement.",
    "Training module on data handling best practices now available in the learning portal.",
    "Incident postmortem complete. Root cause identified as configuration drift. Remediated.",
    "Architecture review board approved the migration plan. Timeline remains Q{q} delivery.",
    "Office relocation logistics finalized. IT equipment move scheduled for the weekend.",
]

TITLES_PII = ["Account Request","Wire Transfer","Lost Card Report","Loan Application","Fraud Alert","Address Change","Insurance Claim","Direct Deposit","KYC Verification","Beneficiary Update"]
TITLES_CLEAN = ["Compliance Review","System Maintenance","Policy Update","Budget Approval","Standup Notes","Contract Renewal","Training Update","Incident Postmortem","Architecture Review","Office Relocation"]


def rand_name():
    return random.choice(FIRST) + " " + random.choice(LAST)

def rand_ssn():
    return f"{random.randint(100,999)}-{random.randint(10,99)}-{random.randint(1000,9999)}"

def rand_email(name):
    return name.lower().replace(" ", ".") + str(random.randint(1, 99)) + "@" + random.choice(DOMAINS)

def rand_phone():
    return f"({random.randint(200,999)}) {random.randint(200,999)}-{random.randint(1000,9999)}"

def rand_addr():
    return f"{random.randint(100,9999)} {random.choice(STREETS)}, {random.choice(CITIES)}"

def rand_cc():
    return f"{random.randint(4000,4999)}-{random.randint(1000,9999)}-{random.randint(1000,9999)}-{random.randint(1000,9999)}"

def rand_acct():
    return "".join(random.choices(string.digits, k=10))

def rand_date():
    m = random.choice(["January","February","March","April","May","June","July","August","September","October","November","December"])
    return f"{m} {random.randint(1,28)}, {random.randint(1950,2005)}"


def gen_pii_doc():
    name = rand_name()
    tpl = random.choice(TEMPLATES_PII)
    title = TITLES_PII[TEMPLATES_PII.index(tpl)]
    body = tpl.format(
        name=name, ssn=rand_ssn(), email=rand_email(name), phone=rand_phone(),
        addr=rand_addr(), amt=f"{random.randint(1,500)*1000:,}", acct=rand_acct(),
        cc=rand_cc(), date=rand_date(), dob=rand_date(), bank="First National",
        pol=rand_acct()[:8], routing=rand_acct()[:9], passport="X" + rand_acct()[:8],
        q=random.randint(1, 4), ver=f"{random.randint(1,5)}.{random.randint(0,9)}"
    )
    return {"title": title + " #" + rand_acct()[:5], "body": body}


def gen_clean_doc():
    tpl = random.choice(TEMPLATES_CLEAN)
    title = TITLES_CLEAN[TEMPLATES_CLEAN.index(tpl)]
    body = tpl.format(q=random.randint(1, 4), ver=f"{random.randint(1,5)}.{random.randint(0,9)}")
    return {"title": title, "body": body}


def main():
    client = get_client()
    total = 1000
    pii_count = 700

    print(f"Generating {total} documents ({pii_count} with PII, {total - pii_count} clean)...")

    batch = []
    for i in range(total):
        doc = gen_pii_doc() if i < pii_count else gen_clean_doc()
        batch.append(doc)

        if len(batch) == 50:
            body = ""
            for d in batch:
                body += json.dumps({"index": {"_index": OPENSEARCH_INDEX}}) + "\n"
                body += json.dumps(d) + "\n"
            client.bulk(body=body)
            print(f"  Indexed {i+1}/{total}")
            batch = []

    if batch:
        body = ""
        for d in batch:
            body += json.dumps({"index": {"_index": OPENSEARCH_INDEX}}) + "\n"
            body += json.dumps(d) + "\n"
        client.bulk(body=body)
        print(f"  Indexed {total}/{total}")

    print("Done. 1000 documents indexed.")


if __name__ == "__main__":
    main()
