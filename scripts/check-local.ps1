$ErrorActionPreference = "Stop"

$checks = @(
    @{ Name = "Python"; Command = { python --version } },
    @{ Name = "Node.js"; Command = { node --version } },
    @{ Name = "npm"; Command = { npm.cmd --version } }
)

Write-Host "Checking local prerequisites..."

foreach ($check in $checks) {
    try {
        $result = & $check.Command 2>$null
        Write-Host ("[OK] {0}: {1}" -f $check.Name, $result)
    }
    catch {
        Write-Host ("[MISSING] {0}" -f $check.Name)
    }
}
