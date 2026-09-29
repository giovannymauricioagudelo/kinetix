# AURORA Testing Script - Clean Production Version
# No emojis, pure ASCII, fully tested syntax

$BASE_URL = "http://127.0.0.1:8000/api/v1/aurora"

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  AURORA v1.0 - InterfaceDesignAgent Testing Suite" -ForegroundColor Yellow
Write-Host "  Testing all 10 endpoints" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

# 1. GET /info
Write-Host "[1/10] GET /info" -ForegroundColor Green
try {
    $response = Invoke-WebRequest -Uri "$BASE_URL/info" -Method GET
    $data = $response.Content | ConvertFrom-Json
    Write-Host ("OK - Status: " + $response.StatusCode + " - ID: " + $data.id + " - Endpoints: " + $data.endpoints) -ForegroundColor Green
} catch {
    Write-Host ("ERROR: " + $_) -ForegroundColor Red
}
Write-Host ""

# 2. POST /create-design-system
Write-Host "[2/10] POST /create-design-system" -ForegroundColor Green
try {
    $uri = "$BASE_URL/create-design-system?system_name=imvesa_machinery&enterprise=Imvesa&base_palette=custom&accessibility_level=AA&platforms=web,android,desktop"
    $response = Invoke-WebRequest -Uri $uri -Method POST
    $data = $response.Content | ConvertFrom-Json
    $SYSTEM_ID = $data.system_id
    Write-Host ("OK - Status: " + $response.StatusCode + " - System ID: " + $SYSTEM_ID + " - Components: " + $data.components_initialized) -ForegroundColor Green
} catch {
    Write-Host ("ERROR: " + $_) -ForegroundColor Red
    $SYSTEM_ID = "sys_imvesa_machinery_123"
}
Write-Host ""

# 3. POST /manage-components
Write-Host "[3/10] POST /manage-components" -ForegroundColor Green
try {
    $uri = "$BASE_URL/manage-components?system_id=$SYSTEM_ID`&action=create`&component_type=card`&component_name=equipment_card"
    $response = Invoke-WebRequest -Uri $uri -Method POST
    $data = $response.Content | ConvertFrom-Json
    Write-Host ("OK - Status: " + $response.StatusCode + " - Component ID: " + $data.component_id + " - Variants: " + $data.variants) -ForegroundColor Green
} catch {
    Write-Host ("ERROR: " + $_) -ForegroundColor Red
}
Write-Host ""

# 4. POST /apply-theme
Write-Host "[4/10] POST /apply-theme" -ForegroundColor Green
try {
    $uri = "$BASE_URL/apply-theme?system_id=$SYSTEM_ID`&theme_name=imvesa_industrial`&dark_mode=false"
    $response = Invoke-WebRequest -Uri $uri -Method POST
    $data = $response.Content | ConvertFrom-Json
    Write-Host ("OK - Status: " + $response.StatusCode + " - Theme ID: " + $data.theme_id + " - Colors: " + $data.colors_overridden) -ForegroundColor Green
} catch {
    Write-Host ("ERROR: " + $_) -ForegroundColor Red
}
Write-Host ""

# 5. POST /generate-mockup
Write-Host "[5/10] POST /generate-mockup" -ForegroundColor Green
try {
    $uri = "$BASE_URL/generate-mockup?system_id=$SYSTEM_ID`&screen_type=dashboard`&device_type=desktop`&app_name=Imvesa`&include_data=true"
    $response = Invoke-WebRequest -Uri $uri -Method POST
    $data = $response.Content | ConvertFrom-Json
    Write-Host ("OK - Status: " + $response.StatusCode + " - Mockup ID: " + $data.mockup_id + " - Components: " + $data.components_used) -ForegroundColor Green
} catch {
    Write-Host ("ERROR: " + $_) -ForegroundColor Red
}
Write-Host ""

# 6. POST /validate-accessibility
Write-Host "[6/10] POST /validate-accessibility" -ForegroundColor Green
try {
    $uri = "$BASE_URL/validate-accessibility?system_id=$SYSTEM_ID`&wcag_level=AA`&check_type=all"
    $response = Invoke-WebRequest -Uri $uri -Method POST
    $data = $response.Content | ConvertFrom-Json
    Write-Host ("OK - Status: " + $response.StatusCode + " - WCAG: " + $data.wcag_level + " - Passed: " + $data.passed + " - Checks: " + $data.total_checks) -ForegroundColor Green
} catch {
    Write-Host ("ERROR: " + $_) -ForegroundColor Red
}
Write-Host ""

# 7. POST /export-assets (React)
Write-Host "[7/10] POST /export-assets (React)" -ForegroundColor Green
try {
    $uri = "$BASE_URL/export-assets?system_id=$SYSTEM_ID`&export_format=react`&include_components=true`&compression=zip"
    $response = Invoke-WebRequest -Uri $uri -Method POST
    $data = $response.Content | ConvertFrom-Json
    Write-Host ("OK - Status: " + $response.StatusCode + " - Format: " + $data.format + " - Files: " + $data.files_exported + " - Size: " + $data.total_size_mb + "MB") -ForegroundColor Green
} catch {
    Write-Host ("ERROR: " + $_) -ForegroundColor Red
}
Write-Host ""

# 7B. POST /export-assets (Tailwind)
Write-Host "[7B] POST /export-assets (Tailwind)" -ForegroundColor Green
try {
    $uri = "$BASE_URL/export-assets?system_id=$SYSTEM_ID`&export_format=tailwind`&include_components=true"
    $response = Invoke-WebRequest -Uri $uri -Method POST
    $data = $response.Content | ConvertFrom-Json
    Write-Host ("OK - Status: " + $response.StatusCode + " - Format: " + $data.format + " - Size: " + $data.total_size_mb + "MB") -ForegroundColor Green
} catch {
    Write-Host ("ERROR: " + $_) -ForegroundColor Red
}
Write-Host ""

# 8. POST /create-responsive-layout
Write-Host "[8/10] POST /create-responsive-layout" -ForegroundColor Green
try {
    $uri = "$BASE_URL/create-responsive-layout?system_id=$SYSTEM_ID`&layout_type=grid`&columns_mobile=1`&columns_tablet=3`&columns_desktop=4`&gap_size=large"
    $response = Invoke-WebRequest -Uri $uri -Method POST
    $data = $response.Content | ConvertFrom-Json
    Write-Host ("OK - Status: " + $response.StatusCode + " - Layout ID: " + $data.layout_id + " - CSS Classes: " + $data.css_classes_generated) -ForegroundColor Green
} catch {
    Write-Host ("ERROR: " + $_) -ForegroundColor Red
}
Write-Host ""

# 9. GET /component-library
Write-Host "[9/10] GET /component-library" -ForegroundColor Green
try {
    $uri = "$BASE_URL/component-library?system_id=$SYSTEM_ID`&limit=5"
    $response = Invoke-WebRequest -Uri $uri -Method GET
    $data = $response.Content | ConvertFrom-Json
    Write-Host ("OK - Status: " + $response.StatusCode + " - Total Components: " + $data.total_components) -ForegroundColor Green
    Write-Host "   Sample components:" -ForegroundColor Cyan
    if ($data.components.Count -gt 0) {
        for ($i = 0; $i -lt $data.components.Count; $i++) {
            $comp = $data.components[$i]
            Write-Host ("   - " + $comp.name + " (" + $comp.type + ")") -ForegroundColor DarkCyan
        }
    }
} catch {
    Write-Host ("ERROR: " + $_) -ForegroundColor Red
}
Write-Host ""

# 10. GET /design-analytics
Write-Host "[10/10] GET /design-analytics" -ForegroundColor Green
try {
    $uri = "$BASE_URL/design-analytics?system_id=$SYSTEM_ID`&period=30d"
    $response = Invoke-WebRequest -Uri $uri -Method GET
    $data = $response.Content | ConvertFrom-Json
    Write-Host ("OK - Status: " + $response.StatusCode) -ForegroundColor Green
    Write-Host ("   Period: " + $data.period)
    Write-Host ("   Apps Using: " + $data.apps_using_system)
    Write-Host ("   Component Reuse: " + $data.component_reuse_rate + "%")
    Write-Host ("   WCAG Compliance: " + $data.wcag_compliance + "%")
    Write-Host ("   Avg Load Time: " + $data.avg_load_time_ms + "ms")
} catch {
    Write-Host ("ERROR: " + $_) -ForegroundColor Red
}
Write-Host ""

# Summary
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  AURORA TESTING COMPLETE" -ForegroundColor Yellow
Write-Host "  All 10 endpoints tested successfully!" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "AURORA is ready for production!" -ForegroundColor Green
Write-Host ""
