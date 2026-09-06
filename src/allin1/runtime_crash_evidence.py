"""Read-only, bounded Windows event query for one observed process identity."""
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess

from allin1.processes import run_hidden
from allin1.release_paths import strict_json

# Windows PowerShell 5.1 supports these FilterHashtable keys. Named-data query
# keys require newer PowerShell, so exact process fields are filtered below.
# https://learn.microsoft.com/powershell/scripting/samples/creating-get-winevent-queries-with-filterhashtable
SCRIPT=r"""$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
[Console]::InputEncoding=[Text.UTF8Encoding]::new($false)
try {
  Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Diagnostics\Microsoft.PowerShell.Diagnostics.psd1') -ErrorAction Stop
  $requestedProcess=[Console]::In.ReadToEnd() | ConvertFrom-Json
  $started=[DateTimeOffset]::Parse($requestedProcess.started_at,[Globalization.CultureInfo]::InvariantCulture)
  $expectedTicks=$started.UtcDateTime.ToFileTimeUtc()
  try { $items=@(Get-WinEvent -FilterHashtable @{LogName='Application';ProviderName='Application Error';Id=1000;Level=2;StartTime=$started.UtcDateTime;EndTime=[DateTime]::UtcNow} -MaxEvents 33 -ErrorAction Stop) }
  catch {
    if ($_.FullyQualifiedErrorId -like 'NoMatchingEventsFound*') { $items=@() } else { throw }
  }
  $events=@();$truncated=$items.Count -gt 32
  foreach ($item in ($items | Select-Object -First 32)) {
    $raw=$item.ToXml()
    if ($raw.Length -gt 32768) { $truncated=$true; continue }
    $xml=[xml]$raw;$fields=@{};$duplicate=$false
    foreach ($data in $xml.Event.EventData.Data) {
      if ($fields.ContainsKey([string]$data.Name)) { $duplicate=$true;break }
      $fields[[string]$data.Name]=[string]$data.'#text'
    }
    if ($duplicate -or -not $fields.ContainsKey('ProcessId') -or -not $fields.ContainsKey('ProcessCreationTime') -or -not $fields.ContainsKey('AppPath')) { continue }
    try {
      $processText=$fields.ProcessId;$creationText=$fields.ProcessCreationTime
      $eventProcess=if ($processText.StartsWith('0x')) { [Convert]::ToUInt64($processText.Substring(2),16) } else { [Convert]::ToUInt64($processText,10) }
      $creation=if ($creationText.StartsWith('0x')) { [Convert]::ToUInt64($creationText.Substring(2),16) } else { [Convert]::ToUInt64($creationText,10) }
      if ($eventProcess -eq [UInt64]$requestedProcess.pid -and $creation -eq $expectedTicks -and [string]::Equals($fields.AppPath,$requestedProcess.executable_path,[StringComparison]::OrdinalIgnoreCase)) {
        $events+=$raw
        if ($events.Count -ge 4) { $truncated=$true;break }
      }
    } catch { continue }
  }
  $status=if ($events.Count) { 'observed' } else { 'no_matching_event' }
  @{status=$status;events=@($events);query_truncated=$truncated;queried_events=$items.Count} | ConvertTo-Json -Compress -Depth 4
} catch { @{status='unavailable';reason='Windows Application Error events could not be queried';error_type=$_.Exception.GetType().Name;error_line=$_.InvocationInfo.ScriptLineNumber;events=@()} | ConvertTo-Json -Compress }
"""


def collect(process):
    if not isinstance(process,dict) or type(process.get("pid")) is not int or not 0<process["pid"]<2**32 or not isinstance(process.get("executable_path"),str):
        raise ValueError("Crash lookup requires an observed process identity")
    started=datetime.fromisoformat(process["started_at"].replace("Z","+00:00"))
    if started.tzinfo is None: raise ValueError("Process creation time needs a timezone")
    if os.name!="nt": return {"status":"unavailable","reason":"Windows event logging is required","events":[]}
    windows=Path(os.environ.get("SystemRoot",r"C:\Windows"))
    shell=windows/"System32/WindowsPowerShell/v1.0/powershell.exe"
    if (windows/"Sysnative/WindowsPowerShell/v1.0/powershell.exe").is_file(): shell=windows/"Sysnative/WindowsPowerShell/v1.0/powershell.exe"
    try:
        # Paths and timestamps are JSON stdin data, never interpolated shell code.
        value={key:process[key] for key in ("pid","started_at","executable_path")}
        completed=run_hidden([str(shell),"-NoProfile","-NonInteractive","-Command",SCRIPT],input=json.dumps(value),capture_output=True,text=True,encoding="utf-8",timeout=10)
        if completed.returncode or len(completed.stdout)>192*1024: raise ValueError("Crash query exceeded output bounds")
        result=strict_json(completed.stdout)
        if not isinstance(result,dict) or result.get("status") not in {"observed","no_matching_event","unavailable"} or not isinstance(result.get("events"),list) or len(result["events"])>4 or any(not isinstance(event,str) or len(event)>32768 for event in result["events"]):
            raise ValueError("Malformed crash query result")
        return result
    except (OSError,ValueError,subprocess.SubprocessError):
        return {"status":"unavailable","reason":"Crash observer unavailable or bounded query failed","events":[]}
