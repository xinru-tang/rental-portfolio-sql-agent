"""
Seed data generator for the Apartment Portfolio Database.

Builds apartment_portfolio.db (SQLite) from schema.sql, then populates it
with realistic synthetic data using Faker. Enforces the three business
rules from the Group 2 design report that plain keys/cardinalities can't:

  BR-1: no two LEASE date ranges overlap for the same UNIT
  BR-2: no two PARKING_ASSIGNMENT date ranges overlap for the same SPOT
  BR-3: PriorLeaseID (when present) references an earlier lease for the
        same tenant + unit, with StartDate after the prior lease's EndDate

Run:  python3 seed_data.py
"""
import sqlite3
import random
from datetime import date, timedelta
from faker import Faker

random.seed(42)
fake = Faker()
Faker.seed(42)

DB_PATH = "apartment_portfolio.db"
N_PROPERTIES = 6
UNITS_PER_PROPERTY = (8, 16)      # random range
N_TENANTS = 70
N_TECHNICIANS = 10
N_MAINTENANCE_REQUESTS = 90
N_INSPECTIONS = 50

STATES_CITIES = [
    ("Santa Clara", "CA"), ("San Jose", "CA"), ("Sunnyvale", "CA"),
    ("Mountain View", "CA"), ("Fremont", "CA"), ("Redwood City", "CA"),
]

SKILLS_POOL = ["Plumbing", "Electrical", "HVAC", "Appliance Repair",
               "Carpentry", "Painting", "Locksmith", "General Maintenance"]

MAINT_CATEGORIES = ["Plumbing", "Electrical", "HVAC", "Appliance",
                     "Pest Control", "Structural", "Other"]


def daterange_overlaps(a_start, a_end, b_start, b_end):
    return a_start <= b_end and b_start <= a_end


def build_schema(conn):
    with open("schema.sql", encoding="utf-8") as f:
        conn.executescript(f.read())


def seed_managers_properties_units(conn):
    cur = conn.cursor()
    manager_ids = []
    for i in range(1, 5):
        name = fake.name()
        phone = fake.phone_number()
        cur.execute("INSERT INTO MANAGER (ManagerID, ManagerName, ManagerPhone) VALUES (?,?,?)",
                    (i, name, phone))
        manager_ids.append(i)

    property_ids = []
    units = []  # (PropertyID, UnitNumber)
    for pid in range(1, N_PROPERTIES + 1):
        city, state = random.choice(STATES_CITIES)
        name = f"{fake.last_name()} {random.choice(['Apartments','Terrace','Court','Residences','Commons'])}"
        cur.execute("""INSERT INTO PROPERTY
            (PropertyID, PropertyName, Street, City, State, PostalCode, YearBuilt, ManagerID)
            VALUES (?,?,?,?,?,?,?,?)""",
            (pid, name, fake.street_address(), city, state, fake.postcode(),
             random.randint(1985, 2020), random.choice(manager_ids)))
        property_ids.append(pid)

        n_units = random.randint(*UNITS_PER_PROPERTY)
        floors = max(1, n_units // 6)
        for u in range(1, n_units + 1):
            unit_number = f"{random.randint(1, floors)}{str(u).zfill(2)}"
            bedrooms = random.choice([0, 1, 1, 2, 2, 3])
            bathrooms = random.choice([1, 1, 1.5, 2, 2])
            sqft = 450 + bedrooms * 280 + random.randint(-40, 60)
            base_rent = round(1400 + bedrooms * 650 + random.randint(-100, 250), 2)
            status = random.choices(["Active", "Offline"], weights=[95, 5])[0]
            cur.execute("""INSERT INTO UNIT
                (PropertyID, UnitNumber, Bedrooms, Bathrooms, Floor, SquareFeet, BaseRentAmt, OperationalStatus)
                VALUES (?,?,?,?,?,?,?,?)""",
                (pid, unit_number, bedrooms, bathrooms, int(unit_number[0]), sqft, base_rent, status))
            units.append((pid, unit_number, base_rent))
    conn.commit()
    return property_ids, units


def seed_tenants(conn):
    cur = conn.cursor()
    tenant_ids = []
    for tid in range(1, N_TENANTS + 1):
        first, last = fake.first_name(), fake.last_name()
        cur.execute("""INSERT INTO TENANT
            (TenantID, FirstName, LastName, Email, Phone, DateOfBirth, Employer, AnnualIncome)
            VALUES (?,?,?,?,?,?,?,?)""",
            (tid, first, last, f"{first.lower()}.{last.lower()}{tid}@email.com",
             fake.phone_number(), fake.date_of_birth(minimum_age=21, maximum_age=68).isoformat(),
             fake.company(), round(random.uniform(38000, 165000), 2)))
        tenant_ids.append(tid)
    conn.commit()
    return tenant_ids


def seed_leases_and_payments(conn, units, tenant_ids):
    cur = conn.cursor()
    lease_id = 1
    payment_rows = []
    # track occupied date ranges per unit to enforce BR-1
    unit_lease_history = {u: [] for u in [(p, n) for p, n, _ in units]}
    unassigned_tenants = list(tenant_ids)
    random.shuffle(unassigned_tenants)

    today = date(2026, 8, 1)
    for (pid, unit_number, base_rent) in units:
        if not unassigned_tenants or random.random() < 0.12:
            continue  # leave a small share of units vacant

        # decide 1 or 2 sequential leases (renewal chain) for this unit
        n_leases = random.choices([1, 2], weights=[65, 35])[0]
        cursor_start = today - timedelta(days=random.randint(200, 620))
        prior_lease_id = None
        tenant_id = unassigned_tenants.pop() if unassigned_tenants else random.choice(tenant_ids)

        for k in range(n_leases):
            term_months = random.choice([6, 12, 12, 12])
            start = cursor_start
            end = start + timedelta(days=30 * term_months)
            status = "Active" if end >= today and k == n_leases - 1 else \
                     ("Terminated" if random.random() < 0.08 else "Expired")
            rent = round(base_rent * random.uniform(0.98, 1.06), 2)
            deposit = round(rent, 2)

            cur.execute("""INSERT INTO LEASE
                (LeaseID, TenantID, PropertyID, UnitNumber, PriorLeaseID, StartDate, EndDate,
                 LeaseStatus, MonthlyRent, DepositAmt)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (lease_id, tenant_id, pid, unit_number, prior_lease_id,
                 start.isoformat(), end.isoformat(), status, rent, deposit))

            # monthly payments for months that have elapsed
            months_elapsed = min(term_months, max(0, (min(today, end).year - start.year) * 12 +
                                                   (min(today, end).month - start.month)))
            for m in range(months_elapsed):
                pay_date = start + timedelta(days=30 * m + random.randint(0, 4))
                late_fee = round(random.choice([0, 0, 0, 0, 35, 50]), 2)
                payment_rows.append((lease_id, m + 1, pay_date.isoformat(), rent + late_fee,
                                      random.choice(["ACH", "ACH", "Card", "Check"]),
                                      f"{pay_date.strftime('%Y-%m')}", late_fee))

            prior_lease_id = lease_id
            lease_id += 1
            cursor_start = end + timedelta(days=1)
            if k < n_leases - 1 and not unassigned_tenants:
                break

    cur.executemany("""INSERT INTO PAYMENT
        (LeaseID, PaymentNumber, PaymentDate, AmountPaid, PaymentMethod, PeriodCovered, LateFeeAmt)
        VALUES (?,?,?,?,?,?,?)""", payment_rows)
    conn.commit()


def seed_parking(conn, property_ids, tenant_ids):
    cur = conn.cursor()
    spot_id = 1
    spots = []
    for pid in property_ids:
        n_spots = random.randint(6, 14)
        for s in range(n_spots):
            spot_type = random.choices(["Standard", "Covered", "EV", "Accessible"],
                                        weights=[55, 25, 12, 8])[0]
            fee = {"Standard": 0, "Covered": 45, "EV": 65, "Accessible": 0}[spot_type]
            cur.execute("""INSERT INTO PARKING_SPOT (SpotID, PropertyID, SpotLabel, SpotType, MonthlyFee)
                VALUES (?,?,?,?,?)""", (spot_id, pid, f"P{spot_id:03d}", spot_type, fee))
            spots.append(spot_id)
            spot_id += 1
    conn.commit()

    assignment_id = 1
    rows = []
    for spot in spots:
        if random.random() < 0.35:
            continue  # some spots stay unassigned
        n_assignments = random.choices([1, 2], weights=[70, 30])[0]
        cursor_start = date(2026, 8, 1) - timedelta(days=random.randint(150, 500))
        for k in range(n_assignments):
            length = random.randint(60, 220)
            start = cursor_start
            end = start + timedelta(days=length)
            status = "Active" if k == n_assignments - 1 and end >= date(2026, 8, 1) else "Ended"
            rows.append((assignment_id, random.choice(tenant_ids), spot,
                         start.isoformat(), None if status == "Active" else end.isoformat(), status))
            assignment_id += 1
            cursor_start = end + timedelta(days=1)
    cur.executemany("""INSERT INTO PARKING_ASSIGNMENT
        (AssignmentID, TenantID, SpotID, StartDate, EndDate, AssignmentStatus)
        VALUES (?,?,?,?,?,?)""", rows)
    conn.commit()


def seed_technicians(conn):
    cur = conn.cursor()
    tech_ids = []
    for tid in range(1, N_TECHNICIANS + 1):
        tech_type = random.choices(["H", "C"], weights=[55, 45])[0]
        cur.execute("""INSERT INTO TECHNICIAN (TechnicianID, TechnicianName, Phone, EngagementDate, TechType)
            VALUES (?,?,?,?,?)""",
            (tid, fake.name(), fake.phone_number(),
             fake.date_between(start_date="-4y", end_date="-3m").isoformat(), tech_type))
        if tech_type == "H":
            cur.execute("""INSERT INTO IN_HOUSE_TECH (TechnicianID, EmployeeNumber, Department, HourlyWage)
                VALUES (?,?,?,?)""",
                (tid, f"EMP{1000+tid}", random.choice(["Maintenance", "Facilities", "Grounds"]),
                 round(random.uniform(24, 42), 2)))
        else:
            cur.execute("""INSERT INTO CONTRACTOR_TECH
                (TechnicianID, CompanyName, ContractNumber, BillingRate, InsuranceExpiry)
                VALUES (?,?,?,?,?)""",
                (tid, fake.company() + " Services", f"CT-{2000+tid}",
                 round(random.uniform(55, 110), 2),
                 fake.date_between(start_date="+2m", end_date="+18m").isoformat()))
        n_skills = random.randint(1, 3)
        for skill in random.sample(SKILLS_POOL, n_skills):
            cur.execute("INSERT OR IGNORE INTO TECHNICIAN_SKILL (TechnicianID, Skill) VALUES (?,?)",
                        (tid, skill))
        tech_ids.append(tid)
    conn.commit()
    return tech_ids


def seed_maintenance_and_inspections(conn, units, tech_ids, tenant_ids):
    cur = conn.cursor()
    unit_list = [(p, n) for p, n, _ in units]

    for rid in range(1, N_MAINTENANCE_REQUESTS + 1):
        pid, unit_number = random.choice(unit_list)
        reported = fake.date_between(start_date="-9m", end_date="today")
        status = random.choices(["Open", "Assigned", "Completed"], weights=[15, 20, 65])[0]
        tech_id = random.choice(tech_ids) if status != "Open" else None
        completed = None
        if status == "Completed":
            completed = (reported + timedelta(days=random.randint(0, 12))).isoformat()
        reported_by = random.choice(tenant_ids) if random.random() < 0.75 else None
        cur.execute("""INSERT INTO MAINTENANCE_REQUEST
            (RequestID, PropertyID, UnitNumber, TechnicianID, ReportedByTenantID, ReportedDate,
             CompletedDate, Category, Priority, RequestStatus, Description, LaborHours, PartsCost)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (rid, pid, unit_number, tech_id, reported_by, reported.isoformat(), completed,
             random.choice(MAINT_CATEGORIES),
             random.choices(["Low", "Medium", "High", "Emergency"], weights=[30, 40, 22, 8])[0],
             status, fake.sentence(nb_words=8),
             round(random.uniform(0.5, 6), 1) if status == "Completed" else None,
             round(random.uniform(15, 300), 2) if status == "Completed" else None))

    for iid in range(1, N_INSPECTIONS + 1):
        pid, unit_number = random.choice(unit_list)
        scheduled = fake.date_between(start_date="-6m", end_date="+2m")
        is_done = scheduled <= date(2026, 8, 1)
        inspector = random.choice(tech_ids) if is_done or random.random() < 0.5 else None
        completed = (scheduled + timedelta(days=random.randint(0, 3))).isoformat() if is_done else None
        cur.execute("""INSERT INTO INSPECTION
            (InspectionID, PropertyID, UnitNumber, InspectorTechID, ScheduledDate, CompletedDate,
             InspectionType, ResultRating, Notes)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (iid, pid, unit_number, inspector, scheduled.isoformat(), completed,
             random.choice(["Move-In", "Move-Out", "Routine", "Complaint"]),
             random.randint(2, 5) if is_done else None,
             fake.sentence(nb_words=6) if is_done else None))
    conn.commit()


def main():
    import os
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)  # always rebuild fresh so re-running never hits "table already exists"
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    build_schema(conn)

    property_ids, units = seed_managers_properties_units(conn)
    tenant_ids = seed_tenants(conn)
    seed_leases_and_payments(conn, units, tenant_ids)
    seed_parking(conn, property_ids, tenant_ids)
    tech_ids = seed_technicians(conn)
    seed_maintenance_and_inspections(conn, units, tech_ids, tenant_ids)

    # quick sanity report
    cur = conn.cursor()
    for t in ["MANAGER", "PROPERTY", "UNIT", "TENANT", "LEASE", "PAYMENT", "PARKING_SPOT",
              "PARKING_ASSIGNMENT", "TECHNICIAN", "IN_HOUSE_TECH", "CONTRACTOR_TECH",
              "TECHNICIAN_SKILL", "MAINTENANCE_REQUEST", "INSPECTION"]:
        n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"{t:22s} {n:5d} rows")
    conn.close()
    print(f"\nBuilt {DB_PATH}")


if __name__ == "__main__":
    main()
