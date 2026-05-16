$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression

$tempDir = "$env:USERPROFILE\Desktop\pptx_repair_temp"
$outputFile = "$env:USERPROFILE\Desktop\REPAIRED_V4.pptx"

if (Test-Path $outputFile) { Remove-Item $outputFile -Force }

# Create ZIP manually with proper PPTX ordering
# [Content_Types].xml MUST be first and stored (not compressed) per OPC spec
$stream = [System.IO.File]::Create($outputFile)
$zip = New-Object System.IO.Compression.ZipArchive($stream, [System.IO.Compression.ZipArchiveMode]::Create)

function AddFileToZip($zip, $entryName, $filePath, $compressionLevel) {
    $entry = $zip.CreateEntry($entryName, $compressionLevel)
    $entryStream = $entry.Open()
    $fileBytes = [System.IO.File]::ReadAllBytes($filePath)
    $entryStream.Write($fileBytes, 0, $fileBytes.Length)
    $entryStream.Close()
}

function AddDirToZip($zip, $dirPath, $basePath, $compressionLevel) {
    foreach ($file in (Get-ChildItem $dirPath -Recurse -File)) {
        $relativePath = $file.FullName.Substring($basePath.Length + 1).Replace('\', '/')
        AddFileToZip $zip $relativePath $file.FullName $compressionLevel
    }
}

Write-Host "Building PPTX with proper structure..."

# 1. [Content_Types].xml FIRST (Stored/NoCompression per OPC spec)
$ctPath = Join-Path $tempDir "[Content_Types].xml"
AddFileToZip $zip "[Content_Types].xml" $ctPath ([System.IO.Compression.CompressionLevel]::NoCompression)
Write-Host "Added [Content_Types].xml (no compression)"

# 2. _rels/.rels
AddFileToZip $zip "_rels/.rels" "$tempDir\_rels\.rels" ([System.IO.Compression.CompressionLevel]::Optimal)

# 3. ppt/_rels/presentation.xml.rels
AddFileToZip $zip "ppt/_rels/presentation.xml.rels" "$tempDir\ppt\_rels\presentation.xml.rels" ([System.IO.Compression.CompressionLevel]::Optimal)

# 4. ppt/presentation.xml
AddFileToZip $zip "ppt/presentation.xml" "$tempDir\ppt\presentation.xml" ([System.IO.Compression.CompressionLevel]::Optimal)

# 5. Themes
foreach ($f in (Get-ChildItem "$tempDir\ppt\theme" -Filter "*.xml")) {
    AddFileToZip $zip "ppt/theme/$($f.Name)" $f.FullName ([System.IO.Compression.CompressionLevel]::Optimal)
}

# 6. SlideMasters + rels
foreach ($f in (Get-ChildItem "$tempDir\ppt\slideMasters" -Filter "*.xml")) {
    AddFileToZip $zip "ppt/slideMasters/$($f.Name)" $f.FullName ([System.IO.Compression.CompressionLevel]::Optimal)
}
foreach ($f in (Get-ChildItem "$tempDir\ppt\slideMasters\_rels" -Filter "*.rels")) {
    AddFileToZip $zip "ppt/slideMasters/_rels/$($f.Name)" $f.FullName ([System.IO.Compression.CompressionLevel]::Optimal)
}

# 7. SlideLayouts + rels
foreach ($f in (Get-ChildItem "$tempDir\ppt\slideLayouts" -Filter "*.xml")) {
    AddFileToZip $zip "ppt/slideLayouts/$($f.Name)" $f.FullName ([System.IO.Compression.CompressionLevel]::Optimal)
}
foreach ($f in (Get-ChildItem "$tempDir\ppt\slideLayouts\_rels" -Filter "*.rels")) {
    AddFileToZip $zip "ppt/slideLayouts/_rels/$($f.Name)" $f.FullName ([System.IO.Compression.CompressionLevel]::Optimal)
}

# 8. Slides + rels
foreach ($f in (Get-ChildItem "$tempDir\ppt\slides" -Filter "*.xml" | Sort-Object { [int]($_.BaseName -replace '[^0-9]','') })) {
    AddFileToZip $zip "ppt/slides/$($f.Name)" $f.FullName ([System.IO.Compression.CompressionLevel]::Optimal)
}
foreach ($f in (Get-ChildItem "$tempDir\ppt\slides\_rels" -Filter "*.rels")) {
    AddFileToZip $zip "ppt/slides/_rels/$($f.Name)" $f.FullName ([System.IO.Compression.CompressionLevel]::Optimal)
}

# 9. NotesMasters + rels
if (Test-Path "$tempDir\ppt\notesMasters") {
    foreach ($f in (Get-ChildItem "$tempDir\ppt\notesMasters" -Filter "*.xml")) {
        AddFileToZip $zip "ppt/notesMasters/$($f.Name)" $f.FullName ([System.IO.Compression.CompressionLevel]::Optimal)
    }
    if (Test-Path "$tempDir\ppt\notesMasters\_rels") {
        foreach ($f in (Get-ChildItem "$tempDir\ppt\notesMasters\_rels" -Filter "*.rels")) {
            AddFileToZip $zip "ppt/notesMasters/_rels/$($f.Name)" $f.FullName ([System.IO.Compression.CompressionLevel]::Optimal)
        }
    }
}

# 10. NotesSlides + rels
if (Test-Path "$tempDir\ppt\notesSlides") {
    foreach ($f in (Get-ChildItem "$tempDir\ppt\notesSlides" -Filter "*.xml")) {
        AddFileToZip $zip "ppt/notesSlides/$($f.Name)" $f.FullName ([System.IO.Compression.CompressionLevel]::Optimal)
    }
    if (Test-Path "$tempDir\ppt\notesSlides\_rels") {
        foreach ($f in (Get-ChildItem "$tempDir\ppt\notesSlides\_rels" -Filter "*.rels")) {
            AddFileToZip $zip "ppt/notesSlides/_rels/$($f.Name)" $f.FullName ([System.IO.Compression.CompressionLevel]::Optimal)
        }
    }
}

# 11. Other ppt XML files
foreach ($xmlName in @('presProps.xml','viewProps.xml','tableStyles.xml')) {
    $xmlPath = "$tempDir\ppt\$xmlName"
    if (Test-Path $xmlPath) {
        AddFileToZip $zip "ppt/$xmlName" $xmlPath ([System.IO.Compression.CompressionLevel]::Optimal)
    }
}

# 12. Fonts
if (Test-Path "$tempDir\ppt\fonts") {
    foreach ($f in (Get-ChildItem "$tempDir\ppt\fonts" -File)) {
        AddFileToZip $zip "ppt/fonts/$($f.Name)" $f.FullName ([System.IO.Compression.CompressionLevel]::Optimal)
    }
}

# 13. Media files (images, etc.)
$mediaCount = 0
if (Test-Path "$tempDir\ppt\media") {
    foreach ($f in (Get-ChildItem "$tempDir\ppt\media" -File)) {
        AddFileToZip $zip "ppt/media/$($f.Name)" $f.FullName ([System.IO.Compression.CompressionLevel]::Optimal)
        $mediaCount++
    }
}

$zip.Dispose()
$stream.Close()

$size = [math]::Round((Get-Item $outputFile).Length / 1MB, 2)
Write-Host "`n==========================================="
Write-Host "  REPAIR V4 COMPLETE!"
Write-Host "==========================================="
Write-Host "File: REPAIRED_V4.pptx"
Write-Host "Size: $size MB"
Write-Host "Media files: $mediaCount"
Write-Host "Try opening REPAIRED_V4.pptx from Desktop"
