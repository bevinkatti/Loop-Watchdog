param(
  [string]$BaseUrl = "http://127.0.0.1:8787",
  [string]$SessionId = "real-user-test:agent:main"
)

$ErrorActionPreference = "Stop"

function Post-Json {
  param(
    [string]$Uri,
    [object]$Body,
    [hashtable]$Headers = @{}
  )

  return Invoke-RestMethod `
    -Uri $Uri `
    -Method Post `
    -ContentType "application/json" `
    -Headers $Headers `
    -Body ($Body | ConvertTo-Json -Depth 8)
}

Write-Host "Testing Loop Watchdog against $BaseUrl with session $SessionId" -ForegroundColor Cyan

$events = @(
  @{
    session_id = $SessionId
    kind = "file_edit"
    summary = "Retry parser patch"
    files = @("src/parser.py", "tests/test_parser.py")
  },
  @{
    session_id = $SessionId
    kind = "test_failure"
    summary = "test_parse_user still fails with NoneType"
    files = @("src/parser.py", "tests/test_parser.py")
    metadata = @{
      error = "AssertionError: expected name, got NoneType"
    }
  },
  @{
    session_id = $SessionId
    kind = "file_edit"
    summary = "Retry parser patch again"
    files = @("src/parser.py", "tests/test_parser.py")
  },
  @{
    session_id = $SessionId
    kind = "test_failure"
    summary = "test_parse_user still fails with NoneType"
    files = @("src/parser.py", "tests/test_parser.py")
    metadata = @{
      error = "AssertionError: expected name, got NoneType"
    }
  }
)

foreach ($event in $events) {
  $result = Post-Json -Uri "$BaseUrl/v1/watchdog/events" -Body $event
  Write-Host ("Event accepted: {0}" -f $event.kind) -ForegroundColor DarkGray
}

$requestHeaders = @{
  "X-Loop-Session" = $SessionId
}

$requestBody = @{
  messages = @(
    @{
      role = "user"
      content = "Fix parser test failure"
    }
  )
}

try {
  $response = Invoke-WebRequest `
    -Uri "$BaseUrl/v1/chat/completions" `
    -Method Post `
    -ContentType "application/json" `
    -Headers $requestHeaders `
    -Body ($requestBody | ConvertTo-Json -Depth 8)

  Write-Host "Unexpected result: request was forwarded instead of paused." -ForegroundColor Yellow
  Write-Host $response.Content
}
catch {
  $statusCode = [int]$_.Exception.Response.StatusCode
  $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
  $body = $reader.ReadToEnd()

  Write-Host ("Model call returned HTTP {0}" -f $statusCode) -ForegroundColor Cyan
  Write-Host $body

  if ($statusCode -eq 409) {
    Write-Host "Success: Loop Watchdog paused the session before another model call could spend credits." -ForegroundColor Green
  } else {
    Write-Host "Watchdog did not return the expected pause response." -ForegroundColor Yellow
  }
}

$snapshot = Invoke-RestMethod -Uri "$BaseUrl/v1/watchdog/dashboard" -Method Get
Write-Host ""
Write-Host "Dashboard snapshot:" -ForegroundColor Cyan
$snapshot | ConvertTo-Json -Depth 8
