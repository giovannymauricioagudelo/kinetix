# INSIGHT v2.0 — ReportingAgent (Agent 4)
**Status:** ✅ LIVE | **Endpoints:** 8 | **Base URL:** `/api/v1/insight`

## Overview
ReportingAgent generates, schedules, exports and analyzes business reports across multiple formats.

---

## Endpoints

### 1️⃣ GET `/info`
**Metadata and capabilities**
```json
{
  "id": "insight",
  "name": "ReportingAgent v2.0",
  "endpoints": 8,
  "status": "active",
  "formats": ["PDF", "Excel", "JSON", "CSV"]
}
```

### 2️⃣ POST `/generate-report`
**Generate a report with filters and format**
- `report_type` (string): `sales`, `inventory`, `financial`, `custom`
- `data_source` (string): Database or API endpoint
- `filters` (optional, string): JSON filter expression

**Response:**
```json
{
  "status": "success",
  "report_id": "rpt_sales_123",
  "format": "PDF",
  "size_kb": 1024
}
```

**Example:**
```powershell
$uri = "http://127.0.0.1:8000/api/v1/insight/generate-report?" +
       "report_type=sales&data_source=mssql_kinetix&filters=%7B%22year%22:%222026%22%7D"
Invoke-WebRequest -Uri $uri -Method POST
```

### 3️⃣ POST `/schedule-report`
**Schedule recurring report delivery**
- `report_id` (string): Generated report ID
- `frequency` (string): `daily`, `weekly`, `monthly`, `quarterly`
- `recipients` (optional, string): Email addresses (comma-separated)

**Response:**
```json
{
  "status": "success",
  "schedule_id": "sch_rpt_sales_123",
  "frequency": "weekly",
  "next_run": "2026-09-29T08:00:00Z"
}
```

### 4️⃣ GET `/reports`
**List all generated reports with filters**
- `report_type` (optional, string): Filter by type
- `status` (string): `all`, `active`, `archived`
- `limit` (integer, default=50): Max results

**Response:**
```json
{
  "status": "success",
  "total": 12,
  "reports": [
    {
      "report_id": "rpt_sales_001",
      "type": "sales",
      "created": "2026-09-28T10:00:00Z",
      "size_kb": 2048,
      "format": "PDF"
    }
  ]
}
```

### 5️⃣ POST `/export-data`
**Export raw data in multiple formats**
- `query` (string): SQL or filter expression
- `format` (string): `json`, `csv`, `excel`, `parquet`
- `compression` (string): `none`, `gzip`, `zip`

**Response:**
```json
{
  "status": "success",
  "export_id": "exp_123",
  "format": "csv",
  "rows": 5000,
  "size_mb": 2.5,
  "download_url": "/downloads/exp_123.csv.gz"
}
```

### 6️⃣ GET `/dashboards`
**List available dashboards**
- `owner` (optional, string): Filter by creator
- `status` (string): `active`, `inactive`, `archived`

**Response:**
```json
{
  "status": "success",
  "total": 8,
  "dashboards": [
    {
      "dashboard_id": "dash_001",
      "name": "Sales Overview",
      "owner": "admin",
      "widgets": 12,
      "last_updated": "2026-09-28T09:30:00Z"
    }
  ]
}
```

### 7️⃣ POST `/custom-query`
**Execute custom SQL query with timeout**
- `sql` (string): SQL SELECT query (min 10 chars)
- `timeout_seconds` (integer): 5-300 seconds

**Response:**
```json
{
  "status": "success",
  "query_id": "qry_123",
  "rows_returned": 150,
  "execution_time_ms": 234.5,
  "columns": ["id", "name", "amount"]
}
```

### 8️⃣ GET `/analytics`
**Performance analytics for reporting system**
- `period` (string): `7d`, `30d`, `90d`
- `metric` (optional, string): Specific metric to retrieve

**Response:**
```json
{
  "status": "success",
  "period": "7d",
  "reports_generated": 42,
  "avg_generation_time_ms": 312.5,
  "total_size_gb": 8.2,
  "most_used_format": "PDF",
  "cost_per_report": 0.25
}
```

---

## Security Rules
✅ SQL injection protection (timeout limits, query length validation)  
✅ Format validation (only: json, csv, excel, parquet)  
✅ Compression validation  
✅ Frequency validation for scheduling  

---

## Error Handling
- Invalid `report_type` → `{"status": "error"}`
- Invalid `frequency` → `{"status": "error"}`
- Timeout exceeded → 300 second limit enforced
- Query too short → Minimum 10 characters required
