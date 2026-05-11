$OutputFile = "PROJECT_CONTEXT.md"

# Reset file
"" | Out-File $OutputFile

function Add-Section {
    param (
        [string]$Title,
        [string]$Content
    )

    Add-Content $OutputFile "`n# $Title`n"
    Add-Content $OutputFile $Content
}

# ============================================
# BASIC PROJECT INFO
# ============================================

Add-Section "Project Structure" (
    tree /F
)

# ============================================
# FIND ALL IMPORTANT FILES
# ============================================

$extensions = @(
    "*.cs",
    "*.csproj",
    "*.sln",
    "*.json",
    "*.config",
    "*.tsx",
    "*.ts",
    "*.js",
    "*.jsx",
    "*.sql",
    "*.yml",
    "*.yaml",
    "*.dockerfile",
    "Dockerfile"
)

foreach ($ext in $extensions) {

    Get-ChildItem -Recurse -Include $ext -ErrorAction SilentlyContinue |
    ForEach-Object {

        Add-Content $OutputFile "`n====================================================="
        Add-Content $OutputFile "FILE: $($_.FullName)"
        Add-Content $OutputFile "====================================================="

        try {
            Get-Content $_.FullName -ErrorAction Stop |
            Add-Content $OutputFile
        }
        catch {
            Add-Content $OutputFile "Could not read file."
        }
    }
}

# ============================================
# NUGET PACKAGES
# ============================================

$csprojFiles = Get-ChildItem -Recurse -Filter *.csproj

foreach ($proj in $csprojFiles) {

    Add-Content $OutputFile "`n# NUGET PACKAGES: $($proj.Name)"

    Select-String -Path $proj.FullName -Pattern "PackageReference" |
    ForEach-Object {
        Add-Content $OutputFile $_.Line
    }
}

# ============================================
# APP SETTINGS
# ============================================

$appsettings = Get-ChildItem -Recurse -Include "appsettings*.json"

foreach ($app in $appsettings) {

    Add-Content $OutputFile "`n# APP SETTINGS: $($app.Name)"

    Get-Content $app.FullName |
    Add-Content $OutputFile
}

# ============================================
# API ENDPOINTS
# ============================================

$controllers = Get-ChildItem -Recurse -Include "*Controller.cs"

foreach ($controller in $controllers) {

    Add-Content $OutputFile "`n# CONTROLLER: $($controller.Name)"

    Select-String -Path $controller.FullName -Pattern "\[HttpGet|\[HttpPost|\[HttpPut|\[HttpDelete|\[Route" |
    ForEach-Object {
        Add-Content $OutputFile $_.Line
    }
}

# ============================================
# REACT PACKAGE.JSON
# ============================================

$packageJson = Get-ChildItem -Recurse -Filter package.json

foreach ($pkg in $packageJson) {

    Add-Content $OutputFile "`n# PACKAGE JSON"

    Get-Content $pkg.FullName |
    Add-Content $OutputFile
}

Write-Host "PROJECT_CONTEXT.md generated successfully!"