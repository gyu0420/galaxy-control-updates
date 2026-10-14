Option Explicit
Dim fso, shell, temp, stream, result
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
temp = fso.BuildPath(shell.ExpandEnvironmentStrings("%TEMP%"), fso.GetTempName & ".ps1")
Set stream = fso.CreateTextFile(temp, True, True)
stream.WriteLine "param([string]$Package)"
stream.WriteLine "$ErrorActionPreference = 'Stop'"
stream.WriteLine "try {"
stream.WriteLine "    $base = Join-Path $env:LOCALAPPDATA 'GRP'"
stream.WriteLine "    $dest = Join-Path $base 'GalaxyControl_v8_40'"
stream.WriteLine "    $marker = Join-Path $dest '.extracted'"
stream.WriteLine "    if (!(Test-Path -LiteralPath $marker)) {"
stream.WriteLine "        New-Item -ItemType Directory -Path $dest -Force | Out-Null"
stream.WriteLine "        $lines = [IO.File]::ReadAllLines($Package)"
stream.WriteLine "        $encoded = ($lines | Where-Object { $_.StartsWith(""'PAYLOAD "") } | ForEach-Object { $_.Substring(9) }) -join ''"
stream.WriteLine "        $zip = Join-Path $base ([Guid]::NewGuid().ToString() + '.zip')"
stream.WriteLine "        [IO.File]::WriteAllBytes($zip, [Convert]::FromBase64String($encoded))"
stream.WriteLine "        Expand-Archive -LiteralPath $zip -DestinationPath $dest -Force"
stream.WriteLine "        Remove-Item -LiteralPath $zip -Force"
stream.WriteLine "        Set-Content -LiteralPath $marker -Value '8.40' -Encoding ASCII"
stream.WriteLine "    }"
stream.WriteLine "    $launcher = Join-Path $dest '갤럭시 관제소 실행.vbs'"
stream.WriteLine "    if (!(Test-Path -LiteralPath $launcher)) { throw 'Missing launcher file' }"
stream.WriteLine "    $shortcutScript = Join-Path $dest 'internal\CreateShortcut.ps1'"
stream.WriteLine "    & $shortcutScript"
stream.WriteLine "    Start-Process -FilePath 'wscript.exe' -ArgumentList ('""' + $launcher + '""') -WorkingDirectory $dest"
stream.WriteLine "} catch {"
stream.WriteLine "    Add-Type -AssemblyName System.Windows.Forms"
stream.WriteLine "    [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Galaxy Control') | Out-Null"
stream.WriteLine "    exit 1"
stream.WriteLine "}"
stream.Close
result = shell.Run("powershell.exe -NoProfile -ExecutionPolicy Bypass -File " & Chr(34) & temp & Chr(34) & " -Package " & Chr(34) & WScript.ScriptFullName & Chr(34), 0, True)
If fso.FileExists(temp) Then fso.DeleteFile temp, True
WScript.Quit result
