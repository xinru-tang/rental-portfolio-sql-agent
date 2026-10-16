-- ============================================================================
-- Apartment Portfolio Database — Relational Schema
-- Source: "Apartment Portfolio Database Design Report" (Group 2, ISBA course,
-- Santa Clara University). This DDL implements the 14-table 3NF schema from
-- that report's Section 3.2 exactly as designed (EER model: 11 core entities
-- + 2 subtypes + 14 relationships). Built for SQLite.
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- MANAGER (strong entity)
-- ---------------------------------------------------------------------------
CREATE TABLE MANAGER (
    ManagerID     INTEGER PRIMARY KEY,
    ManagerName   TEXT NOT NULL,
    ManagerPhone  TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- PROPERTY (strong entity)
-- ---------------------------------------------------------------------------
CREATE TABLE PROPERTY (
    PropertyID    INTEGER PRIMARY KEY,
    PropertyName  TEXT NOT NULL,
    Street        TEXT NOT NULL,
    City          TEXT NOT NULL,
    State         TEXT NOT NULL,
    PostalCode    TEXT NOT NULL,
    YearBuilt     INTEGER NOT NULL,
    ManagerID     INTEGER NOT NULL,
    FOREIGN KEY (ManagerID) REFERENCES MANAGER(ManagerID)
);

-- ---------------------------------------------------------------------------
-- UNIT (weak entity — identified by PROPERTY)
-- ---------------------------------------------------------------------------
CREATE TABLE UNIT (
    PropertyID        INTEGER NOT NULL,
    UnitNumber        TEXT NOT NULL,
    Bedrooms          INTEGER NOT NULL,
    Bathrooms         REAL NOT NULL,
    Floor             INTEGER NOT NULL,
    SquareFeet        INTEGER NOT NULL,
    BaseRentAmt       NUMERIC(10,2) NOT NULL,
    OperationalStatus TEXT NOT NULL CHECK (OperationalStatus IN ('Active','Offline')),
    PRIMARY KEY (PropertyID, UnitNumber),
    FOREIGN KEY (PropertyID) REFERENCES PROPERTY(PropertyID)
);

-- ---------------------------------------------------------------------------
-- TENANT (strong entity)
-- ---------------------------------------------------------------------------
CREATE TABLE TENANT (
    TenantID      INTEGER PRIMARY KEY,
    FirstName     TEXT NOT NULL,
    LastName      TEXT NOT NULL,
    Email         TEXT NOT NULL,
    Phone         TEXT NOT NULL,
    DateOfBirth   TEXT NOT NULL,
    Employer      TEXT,
    AnnualIncome  NUMERIC(10,2)
);

-- ---------------------------------------------------------------------------
-- LEASE (associative entity — resolves TENANT-to-UNIT M:N, self-referencing
-- renewal chain via PriorLeaseID)
-- ---------------------------------------------------------------------------
CREATE TABLE LEASE (
    LeaseID       INTEGER PRIMARY KEY,
    TenantID      INTEGER NOT NULL,
    PropertyID    INTEGER NOT NULL,
    UnitNumber    TEXT NOT NULL,
    PriorLeaseID  INTEGER,
    StartDate     TEXT NOT NULL,
    EndDate       TEXT NOT NULL,
    LeaseStatus   TEXT NOT NULL CHECK (LeaseStatus IN ('Active','Expired','Terminated')),
    MonthlyRent   NUMERIC(10,2) NOT NULL,
    DepositAmt    NUMERIC(10,2) NOT NULL,
    FOREIGN KEY (TenantID) REFERENCES TENANT(TenantID),
    FOREIGN KEY (PropertyID, UnitNumber) REFERENCES UNIT(PropertyID, UnitNumber),
    FOREIGN KEY (PriorLeaseID) REFERENCES LEASE(LeaseID)
);

-- ---------------------------------------------------------------------------
-- PAYMENT (weak entity — identified by LEASE)
-- ---------------------------------------------------------------------------
CREATE TABLE PAYMENT (
    LeaseID        INTEGER NOT NULL,
    PaymentNumber  INTEGER NOT NULL,
    PaymentDate    TEXT NOT NULL,
    AmountPaid     NUMERIC(10,2) NOT NULL,
    PaymentMethod  TEXT NOT NULL CHECK (PaymentMethod IN ('ACH','Card','Check','Cash')),
    PeriodCovered  TEXT NOT NULL,
    LateFeeAmt     NUMERIC(10,2) NOT NULL DEFAULT 0,
    PRIMARY KEY (LeaseID, PaymentNumber),
    FOREIGN KEY (LeaseID) REFERENCES LEASE(LeaseID)
);

-- ---------------------------------------------------------------------------
-- PARKING_SPOT (strong entity)
-- ---------------------------------------------------------------------------
CREATE TABLE PARKING_SPOT (
    SpotID       INTEGER PRIMARY KEY,
    PropertyID   INTEGER NOT NULL,
    SpotLabel    TEXT NOT NULL,
    SpotType     TEXT NOT NULL CHECK (SpotType IN ('Standard','Covered','EV','Accessible')),
    MonthlyFee   NUMERIC(8,2) NOT NULL,
    FOREIGN KEY (PropertyID) REFERENCES PROPERTY(PropertyID)
);

-- ---------------------------------------------------------------------------
-- PARKING_ASSIGNMENT (associative entity — resolves TENANT-to-PARKING_SPOT M:N)
-- ---------------------------------------------------------------------------
CREATE TABLE PARKING_ASSIGNMENT (
    AssignmentID     INTEGER PRIMARY KEY,
    TenantID         INTEGER NOT NULL,
    SpotID           INTEGER NOT NULL,
    StartDate        TEXT NOT NULL,
    EndDate          TEXT,
    AssignmentStatus TEXT NOT NULL CHECK (AssignmentStatus IN ('Active','Ended')),
    FOREIGN KEY (TenantID) REFERENCES TENANT(TenantID),
    FOREIGN KEY (SpotID) REFERENCES PARKING_SPOT(SpotID)
);

-- ---------------------------------------------------------------------------
-- TECHNICIAN (supertype) / IN_HOUSE_TECH, CONTRACTOR_TECH (subtypes, total-disjoint)
-- ---------------------------------------------------------------------------
CREATE TABLE TECHNICIAN (
    TechnicianID    INTEGER PRIMARY KEY,
    TechnicianName  TEXT NOT NULL,
    Phone           TEXT NOT NULL,
    EngagementDate  TEXT NOT NULL,
    TechType        TEXT NOT NULL CHECK (TechType IN ('H','C'))  -- H = in-house, C = contractor
);

CREATE TABLE IN_HOUSE_TECH (
    TechnicianID   INTEGER PRIMARY KEY,
    EmployeeNumber TEXT NOT NULL,
    Department     TEXT NOT NULL,
    HourlyWage     NUMERIC(8,2) NOT NULL,
    FOREIGN KEY (TechnicianID) REFERENCES TECHNICIAN(TechnicianID)
);

CREATE TABLE CONTRACTOR_TECH (
    TechnicianID   INTEGER PRIMARY KEY,
    CompanyName    TEXT NOT NULL,
    ContractNumber TEXT NOT NULL,
    BillingRate    NUMERIC(8,2) NOT NULL,
    InsuranceExpiry TEXT NOT NULL,
    FOREIGN KEY (TechnicianID) REFERENCES TECHNICIAN(TechnicianID)
);

CREATE TABLE TECHNICIAN_SKILL (
    TechnicianID  INTEGER NOT NULL,
    Skill         TEXT NOT NULL,
    PRIMARY KEY (TechnicianID, Skill),
    FOREIGN KEY (TechnicianID) REFERENCES TECHNICIAN(TechnicianID)
);

-- ---------------------------------------------------------------------------
-- MAINTENANCE_REQUEST (strong entity)
-- ---------------------------------------------------------------------------
CREATE TABLE MAINTENANCE_REQUEST (
    RequestID         INTEGER PRIMARY KEY,
    PropertyID        INTEGER NOT NULL,
    UnitNumber        TEXT NOT NULL,
    TechnicianID       INTEGER,
    ReportedByTenantID INTEGER,
    ReportedDate       TEXT NOT NULL,
    CompletedDate      TEXT,
    Category           TEXT NOT NULL,
    Priority            TEXT NOT NULL CHECK (Priority IN ('Low','Medium','High','Emergency')),
    RequestStatus       TEXT NOT NULL CHECK (RequestStatus IN ('Open','Assigned','Completed')),
    Description          TEXT,
    LaborHours           NUMERIC(6,2),
    PartsCost             NUMERIC(8,2),
    FOREIGN KEY (PropertyID, UnitNumber) REFERENCES UNIT(PropertyID, UnitNumber),
    FOREIGN KEY (TechnicianID) REFERENCES TECHNICIAN(TechnicianID),
    FOREIGN KEY (ReportedByTenantID) REFERENCES TENANT(TenantID)
);

-- ---------------------------------------------------------------------------
-- INSPECTION (strong entity)
-- ---------------------------------------------------------------------------
CREATE TABLE INSPECTION (
    InspectionID     INTEGER PRIMARY KEY,
    PropertyID       INTEGER NOT NULL,
    UnitNumber       TEXT NOT NULL,
    InspectorTechID  INTEGER,
    ScheduledDate    TEXT NOT NULL,
    CompletedDate    TEXT,
    InspectionType   TEXT NOT NULL CHECK (InspectionType IN ('Move-In','Move-Out','Routine','Complaint')),
    ResultRating     INTEGER CHECK (ResultRating BETWEEN 1 AND 5),
    Notes            TEXT,
    FOREIGN KEY (PropertyID, UnitNumber) REFERENCES UNIT(PropertyID, UnitNumber),
    FOREIGN KEY (InspectorTechID) REFERENCES TECHNICIAN(TechnicianID)
);
