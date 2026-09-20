$ErrorActionPreference = 'SilentlyContinue'
$stop = 'C:\Users\xiaopeng\AppData\Local\Temp\solomeal-stress-0918\sampler.stop'
$out  = 'C:\Users\xiaopeng\AppData\Local\Temp\solomeal-stress-0918\sampler.csv'
'stamp,pid,name,cpu_ms' | Out-File -FilePath $out -Encoding ascii
$prev = @{}
while (-not (Test-Path $stop)) {
  $now = Get-Date
  $snap = @{}
  foreach ($p in Get-Process) {
    if ($null -eq $p.CPU) { continue }
    $snap[$p.Id] = @{ name = $p.ProcessName; cpu = $p.CPU * 1000 }
  }
  $delta = @()
  foreach ($id in $snap.Keys) {
    if ($prev.ContainsKey($id)) {
      $d = $snap[$id].cpu - $prev[$id].cpu
      if ($d -gt 0) { $delta += [pscustomobject]@{ pid = $id; name = $snap[$id].name; cpu_ms = [math]::Round($d) } }
    }
  }
  foreach ($row in ($delta | Sort-Object cpu_ms -Descending | Select-Object -First 8)) {
    '{0:HH:mm:ss},{1},{2},{3}' -f $now, $row.pid, $row.name, $row.cpu_ms | Out-File -FilePath $out -Append -Encoding ascii
  }
  $prev = $snap
  Start-Sleep -Milliseconds 1500
}
'sampler finished' | Out-File -FilePath $out -Append -Encoding ascii
