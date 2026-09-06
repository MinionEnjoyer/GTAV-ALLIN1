"""Read-only Windows process metadata; no injection, memory patch or elevation."""
import os
import subprocess
from pathlib import Path

from allin1.processes import run_hidden
from allin1.release_paths import strict_json


def probe(pid):
    if type(pid) is not int or not 0 < pid < 2**32:
        raise ValueError("Choose a valid process ID")
    if os.name != "nt":
        return {"status":"unavailable","reason":"Windows process metadata is required"}
    # Get-Process Path/MainModule can be unavailable across bitness or access
    # boundaries. Never turn that into a process-exit or module-load claim.
    # https://learn.microsoft.com/powershell/module/microsoft.powershell.management/get-process
    script = """$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$observedProcess=Get-Process -Id __PID__ -ErrorAction SilentlyContinue
if ($null -eq $observedProcess) { @{status='absent'} | ConvertTo-Json -Compress; exit }
try {
  $started=$observedProcess.StartTime.ToUniversalTime().ToString('o')
  $exe=$observedProcess.Path
  if ([string]::IsNullOrWhiteSpace($exe)) { throw 'Executable identity unavailable' }
  $modules=@(); $moduleStatus='observed'; $truncated=$false
  try { $allModules=@($observedProcess.Modules); $truncated=$allModules.Count -gt 512; $modules=@($allModules | Select-Object -First 512 | ForEach-Object { $_.FileName }) }
  catch { $moduleStatus='unavailable' }
  @{status='observed';pid=$observedProcess.Id;started_at=$started;executable_path=$exe;modules=$modules;modules_status=$moduleStatus;modules_truncated=$truncated} | ConvertTo-Json -Compress -Depth 4
} catch { @{status='unavailable';reason='Process identity could not be read'} | ConvertTo-Json -Compress }
""".replace("__PID__",str(pid))
    windows = Path(os.environ.get("SystemRoot",r"C:\Windows"))
    shell = windows/"System32/WindowsPowerShell/v1.0/powershell.exe"
    if (windows/"Sysnative/WindowsPowerShell/v1.0/powershell.exe").is_file():
        shell = windows/"Sysnative/WindowsPowerShell/v1.0/powershell.exe"
    try:
        result = run_hidden([str(shell),"-NoProfile","-NonInteractive","-Command",script],capture_output=True,text=True,encoding="utf-8",timeout=10)
        if result.returncode or len(result.stdout)>512*1024:
            return {"status":"unavailable","reason":"Process observer failed or exceeded its bound"}
        value = strict_json(result.stdout)
        if not isinstance(value,dict) or value.get("status") not in {"observed","absent","unavailable"}:
            raise ValueError("Invalid process evidence")
        return value
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        return {"status":"unavailable","reason":type(exc).__name__}
