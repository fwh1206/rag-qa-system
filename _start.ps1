$root = Get-Location
$py = Join-Path $root 'venv\Scripts\python.exe'
$port = $env:RAG_PORT
if (-not $port) { $port = "8000" }
$out = Join-Path $root "logs\server-$port.out.log"
$err = Join-Path $root "logs\server-$port.err.log"
$p = Start-Process -FilePath $py -ArgumentList '-m','uvicorn','main:app','--host','127.0.0.1','--port',$port -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
"started pid $($p.Id)"
Start-Sleep -Seconds 6
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -TimeoutSec 8
    "health $($health.status)"
} catch {
    $_.Exception.Message
}
