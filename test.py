import subprocess
result = subprocess.run(['powershell', '-command', 'Get-PhysicalDisk | Select-Object FriendlyName, MediaType, Size'], capture_output=True, text=True)
print(result.stdout)