# PPTX Repair Script
$ErrorActionPreference = "Stop"

$tempDir = "$env:USERPROFILE\Desktop\pptx_repair_temp"
$src = (Get-ChildItem "$env:USERPROFILE\Desktop" -Filter "*.pptx")[0]
$outputFile = "$env:USERPROFILE\Desktop\REPAIRED_FILE.pptx"

Write-Host "Source file: $($src.Name)"
Write-Host "Output file: $outputFile"

# Count components
$slideCount = (Get-ChildItem "$tempDir\ppt\slides" -Filter "slide*.xml").Count
$layoutCount = (Get-ChildItem "$tempDir\ppt\slideLayouts" -Filter "slideLayout*.xml").Count
$masterCount = (Get-ChildItem "$tempDir\ppt\slideMasters" -Filter "slideMaster*.xml").Count
$notesMasterCount = @(Get-ChildItem "$tempDir\ppt\notesMasters" -Filter "notesMaster*.xml" -ErrorAction SilentlyContinue).Count
$notesSlideCount = @(Get-ChildItem "$tempDir\ppt\notesSlides" -Filter "notesSlide*.xml" -ErrorAction SilentlyContinue).Count
$themeCount = (Get-ChildItem "$tempDir\ppt\theme" -Filter "theme*.xml").Count
$fontCount = @(Get-ChildItem "$tempDir\ppt\fonts" -ErrorAction SilentlyContinue).Count
$mediaFiles = @(Get-ChildItem "$tempDir\ppt\media" -ErrorAction SilentlyContinue)

Write-Host "Slides: $slideCount, Layouts: $layoutCount, Masters: $masterCount"
Write-Host "Notes Masters: $notesMasterCount, Notes Slides: $notesSlideCount"
Write-Host "Themes: $themeCount, Fonts: $fontCount, Media: $($mediaFiles.Count)"

# Step 1: Create _rels\.rels
Write-Host "Creating root _rels..."
$relsDir = "$tempDir\_rels"
New-Item -ItemType Directory -Path $relsDir -Force | Out-Null

$rootRelsXml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/></Relationships>'
[System.IO.File]::WriteAllText("$relsDir\.rels", $rootRelsXml, (New-Object System.Text.UTF8Encoding $false))

# Step 2: Create ppt\_rels\presentation.xml.rels
Write-Host "Creating presentation.xml.rels..."
$pptRelsDir = "$tempDir\ppt\_rels"
New-Item -ItemType Directory -Path $pptRelsDir -Force | Out-Null

$sb = New-Object System.Text.StringBuilder
[void]$sb.AppendLine('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
[void]$sb.AppendLine('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">')

$rId = 1
# Slide masters
for ($i = 1; $i -le $masterCount; $i++) {
    [void]$sb.AppendLine("  <Relationship Id=`"rId$rId`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster`" Target=`"slideMasters/slideMaster$i.xml`"/>")
    $rId++
}
# Slides
$slideRIdStart = $rId
for ($i = 1; $i -le $slideCount; $i++) {
    [void]$sb.AppendLine("  <Relationship Id=`"rId$rId`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide`" Target=`"slides/slide$i.xml`"/>")
    $rId++
}
# Notes master
if ($notesMasterCount -gt 0) {
    [void]$sb.AppendLine("  <Relationship Id=`"rId$rId`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesMaster`" Target=`"notesMasters/notesMaster1.xml`"/>")
    $rId++
}
# presProps, viewProps, tableStyles
[void]$sb.AppendLine("  <Relationship Id=`"rId$rId`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/presProps`" Target=`"presProps.xml`"/>")
$rId++
[void]$sb.AppendLine("  <Relationship Id=`"rId$rId`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/viewProps`" Target=`"viewProps.xml`"/>")
$rId++
[void]$sb.AppendLine("  <Relationship Id=`"rId$rId`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/tableStyles`" Target=`"tableStyles.xml`"/>")
$rId++
# Themes
for ($i = 1; $i -le $themeCount; $i++) {
    [void]$sb.AppendLine("  <Relationship Id=`"rId$rId`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme`" Target=`"theme/theme$i.xml`"/>")
    $rId++
}
[void]$sb.AppendLine('</Relationships>')
[System.IO.File]::WriteAllText("$pptRelsDir\presentation.xml.rels", $sb.ToString(), (New-Object System.Text.UTF8Encoding $false))

# Step 3: Update presentation.xml rId references
Write-Host "Updating presentation.xml rIds..."
$presContent = [System.IO.File]::ReadAllText("$tempDir\ppt\presentation.xml", [System.Text.Encoding]::UTF8)

# Replace sldMasterId rIds (masters start at rId1)
$masterIdx = 1
$presContent = [regex]::Replace($presContent, '(<p:sldMasterId[^/]*?r:id=")rId\d+(")', {
    param($m)
    $result = $m.Groups[1].Value + "rId$script:masterIdx" + $m.Groups[2].Value
    $script:masterIdx++
    return $result
})

# Replace sldId rIds (slides start at slideRIdStart)
$slideIdx = $slideRIdStart
$presContent = [regex]::Replace($presContent, '(<p:sldId\s[^/]*?r:id=")rId\d+(")', {
    param($m)
    $result = $m.Groups[1].Value + "rId$script:slideIdx" + $m.Groups[2].Value
    $script:slideIdx++
    return $result
})

[System.IO.File]::WriteAllText("$tempDir\ppt\presentation.xml", $presContent, (New-Object System.Text.UTF8Encoding $false))

# Step 4: Create slide _rels (with media references from slide XML)
Write-Host "Creating slide relationships..."
$slideRelsDir = "$tempDir\ppt\slides\_rels"
New-Item -ItemType Directory -Path $slideRelsDir -Force | Out-Null

for ($i = 1; $i -le $slideCount; $i++) {
    $slideFile = "$tempDir\ppt\slides\slide$i.xml"
    $slideContent = [System.IO.File]::ReadAllText($slideFile, [System.Text.Encoding]::UTF8)
    
    $slideSb = New-Object System.Text.StringBuilder
    [void]$slideSb.AppendLine('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
    [void]$slideSb.AppendLine('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">')
    
    # slideLayout reference as rId1
    if ($i -eq 1) { $layoutNum = 1 } else { $layoutNum = 2 }
    if ($layoutNum -gt $layoutCount) { $layoutNum = 1 }
    [void]$slideSb.AppendLine("  <Relationship Id=`"rId1`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout`" Target=`"../slideLayouts/slideLayout$layoutNum.xml`"/>")
    
    # Find all r:embed references and map them to media
    $embedMatches = [regex]::Matches($slideContent, 'r:embed="(rId(\d+))"')
    $addedRIds = @{}
    foreach ($em in $embedMatches) {
        $rid = $em.Groups[1].Value
        $ridNum = [int]$em.Groups[2].Value
        if ($rid -eq "rId1" -or $addedRIds.ContainsKey($rid)) { continue }
        $addedRIds[$rid] = $true
        
        # Try to find corresponding image file
        $imgFile = $null
        foreach ($mf in $mediaFiles) {
            $mfBase = [System.IO.Path]::GetFileNameWithoutExtension($mf.Name)
            $mfNum = $mfBase -replace '[^0-9]', ''
            if ($mfNum -ne '' -and [int]$mfNum -eq $ridNum) {
                $imgFile = $mf
                break
            }
        }
        if ($imgFile) {
            [void]$slideSb.AppendLine("  <Relationship Id=`"$rid`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/image`" Target=`"../media/$($imgFile.Name)`"/>")
        }
    }
    
    # Notes slide reference
    if (Test-Path "$tempDir\ppt\notesSlides\notesSlide$i.xml") {
        $notesRidNum = 2
        while ($addedRIds.ContainsKey("rId$notesRidNum")) { $notesRidNum++ }
        [void]$slideSb.AppendLine("  <Relationship Id=`"rId$notesRidNum`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide`" Target=`"../notesSlides/notesSlide$i.xml`"/>")
    }
    
    [void]$slideSb.AppendLine('</Relationships>')
    [System.IO.File]::WriteAllText("$slideRelsDir\slide$i.xml.rels", $slideSb.ToString(), (New-Object System.Text.UTF8Encoding $false))
}
Write-Host "Created $slideCount slide rels"

# Step 5: Create slideLayout _rels
Write-Host "Creating slideLayout relationships..."
$layoutRelsDir = "$tempDir\ppt\slideLayouts\_rels"
New-Item -ItemType Directory -Path $layoutRelsDir -Force | Out-Null

for ($i = 1; $i -le $layoutCount; $i++) {
    $layoutRels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>'
    [System.IO.File]::WriteAllText("$layoutRelsDir\slideLayout$i.xml.rels", $layoutRels, (New-Object System.Text.UTF8Encoding $false))
}

# Step 6: Create slideMaster _rels
Write-Host "Creating slideMaster relationships..."
$masterRelsDir = "$tempDir\ppt\slideMasters\_rels"
New-Item -ItemType Directory -Path $masterRelsDir -Force | Out-Null

for ($i = 1; $i -le $masterCount; $i++) {
    $mSb = New-Object System.Text.StringBuilder
    [void]$mSb.AppendLine('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
    [void]$mSb.AppendLine('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">')
    $mRid = 1
    for ($j = 1; $j -le $layoutCount; $j++) {
        [void]$mSb.AppendLine("  <Relationship Id=`"rId$mRid`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout`" Target=`"../slideLayouts/slideLayout$j.xml`"/>")
        $mRid++
    }
    [void]$mSb.AppendLine("  <Relationship Id=`"rId$mRid`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme`" Target=`"../theme/theme$i.xml`"/>")
    [void]$mSb.AppendLine('</Relationships>')
    [System.IO.File]::WriteAllText("$masterRelsDir\slideMaster$i.xml.rels", $mSb.ToString(), (New-Object System.Text.UTF8Encoding $false))
}

# Step 7: Notes master rels
if ($notesMasterCount -gt 0) {
    Write-Host "Creating notesMaster relationships..."
    $notesMasterRelsDir = "$tempDir\ppt\notesMasters\_rels"
    New-Item -ItemType Directory -Path $notesMasterRelsDir -Force | Out-Null
    $themeTarget = if (Test-Path "$tempDir\ppt\theme\theme2.xml") { "theme2.xml" } else { "theme1.xml" }
    $nmRels = "<?xml version=`"1.0`" encoding=`"UTF-8`" standalone=`"yes`"?><Relationships xmlns=`"http://schemas.openxmlformats.org/package/2006/relationships`"><Relationship Id=`"rId1`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme`" Target=`"../theme/$themeTarget`"/></Relationships>"
    [System.IO.File]::WriteAllText("$notesMasterRelsDir\notesMaster1.xml.rels", $nmRels, (New-Object System.Text.UTF8Encoding $false))
}

# Step 8: Notes slide rels
if ($notesSlideCount -gt 0) {
    Write-Host "Creating notesSlide relationships..."
    $notesSlideRelsDir = "$tempDir\ppt\notesSlides\_rels"
    New-Item -ItemType Directory -Path $notesSlideRelsDir -Force | Out-Null
    for ($i = 1; $i -le $notesSlideCount; $i++) {
        $nsRels = "<?xml version=`"1.0`" encoding=`"UTF-8`" standalone=`"yes`"?><Relationships xmlns=`"http://schemas.openxmlformats.org/package/2006/relationships`"><Relationship Id=`"rId1`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesMaster`" Target=`"../notesMasters/notesMaster1.xml`"/><Relationship Id=`"rId2`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide`" Target=`"../slides/slide$i.xml`"/></Relationships>"
        [System.IO.File]::WriteAllText("$notesSlideRelsDir\notesSlide$i.xml.rels", $nsRels, (New-Object System.Text.UTF8Encoding $false))
    }
}

# Step 9: Create [Content_Types].xml
Write-Host "Creating [Content_Types].xml..."
$ctSb = New-Object System.Text.StringBuilder
[void]$ctSb.AppendLine('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
[void]$ctSb.AppendLine('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">')
[void]$ctSb.AppendLine('  <Default Extension="xml" ContentType="application/xml"/>')
[void]$ctSb.AppendLine('  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>')
[void]$ctSb.AppendLine('  <Default Extension="png" ContentType="image/png"/>')
[void]$ctSb.AppendLine('  <Default Extension="jpg" ContentType="image/jpeg"/>')
[void]$ctSb.AppendLine('  <Default Extension="jpeg" ContentType="image/jpeg"/>')
[void]$ctSb.AppendLine('  <Default Extension="gif" ContentType="image/gif"/>')
[void]$ctSb.AppendLine('  <Default Extension="emf" ContentType="image/x-emf"/>')
[void]$ctSb.AppendLine('  <Default Extension="wmf" ContentType="image/x-wmf"/>')
[void]$ctSb.AppendLine('  <Default Extension="fntdata" ContentType="application/x-fontdata"/>')

# Extra media extensions
$addedExts = @('png','jpg','jpeg','gif','emf','wmf','fntdata','xml','rels')
foreach ($mf in $mediaFiles) {
    $ext = $mf.Extension.TrimStart('.').ToLower()
    if ($ext -notin $addedExts) {
        $addedExts += $ext
        $ct = switch ($ext) {
            'mp4' { 'video/mp4' }
            'mp3' { 'audio/mpeg' }
            'wav' { 'audio/wav' }
            'wdp' { 'image/vnd.ms-photo' }
            'tiff' { 'image/tiff' }
            'bmp' { 'image/bmp' }
            'svg' { 'image/svg+xml' }
            default { 'application/octet-stream' }
        }
        [void]$ctSb.AppendLine("  <Default Extension=`"$ext`" ContentType=`"$ct`"/>")
    }
}

# Font extensions
if ($fontCount -gt 0) {
    foreach ($ff in (Get-ChildItem "$tempDir\ppt\fonts" -ErrorAction SilentlyContinue)) {
        $ext = $ff.Extension.TrimStart('.').ToLower()
        if ($ext -notin $addedExts -and $ext -ne '') {
            $addedExts += $ext
            [void]$ctSb.AppendLine("  <Default Extension=`"$ext`" ContentType=`"application/octet-stream`"/>")
        }
    }
}

# Overrides
[void]$ctSb.AppendLine('  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>')
[void]$ctSb.AppendLine('  <Override PartName="/ppt/presProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presProps+xml"/>')
[void]$ctSb.AppendLine('  <Override PartName="/ppt/viewProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml"/>')
[void]$ctSb.AppendLine('  <Override PartName="/ppt/tableStyles.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml"/>')

for ($i = 1; $i -le $themeCount; $i++) {
    [void]$ctSb.AppendLine("  <Override PartName=`"/ppt/theme/theme$i.xml`" ContentType=`"application/vnd.openxmlformats-officedocument.theme+xml`"/>")
}
for ($i = 1; $i -le $masterCount; $i++) {
    [void]$ctSb.AppendLine("  <Override PartName=`"/ppt/slideMasters/slideMaster$i.xml`" ContentType=`"application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml`"/>")
}
for ($i = 1; $i -le $layoutCount; $i++) {
    [void]$ctSb.AppendLine("  <Override PartName=`"/ppt/slideLayouts/slideLayout$i.xml`" ContentType=`"application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml`"/>")
}
for ($i = 1; $i -le $slideCount; $i++) {
    [void]$ctSb.AppendLine("  <Override PartName=`"/ppt/slides/slide$i.xml`" ContentType=`"application/vnd.openxmlformats-officedocument.presentationml.slide+xml`"/>")
}
if ($notesMasterCount -gt 0) {
    [void]$ctSb.AppendLine('  <Override PartName="/ppt/notesMasters/notesMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesMaster+xml"/>')
}
for ($i = 1; $i -le $notesSlideCount; $i++) {
    [void]$ctSb.AppendLine("  <Override PartName=`"/ppt/notesSlides/notesSlide$i.xml`" ContentType=`"application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml`"/>")
}
[void]$ctSb.AppendLine('</Types>')
[System.IO.File]::WriteAllText("$tempDir\[Content_Types].xml", $ctSb.ToString(), (New-Object System.Text.UTF8Encoding $false))

# Step 10: Fix broken image124.png
Write-Host "Fixing broken image..."
$brokenImage = "$tempDir\ppt\media\image124.png"
if (-not (Test-Path $brokenImage) -or (Get-Item $brokenImage).Length -eq 0) {
    # Create 1x1 transparent PNG placeholder
    $pngBytes = [byte[]](0x89,0x50,0x4E,0x47,0x0D,0x0A,0x1A,0x0A,0x00,0x00,0x00,0x0D,0x49,0x48,0x44,0x52,0x00,0x00,0x00,0x01,0x00,0x00,0x00,0x01,0x08,0x06,0x00,0x00,0x00,0x1F,0x15,0xC4,0x89,0x00,0x00,0x00,0x0A,0x49,0x44,0x41,0x54,0x78,0x9C,0x62,0x00,0x00,0x00,0x02,0x00,0x01,0xE5,0x27,0xDE,0xFC,0x00,0x00,0x00,0x00,0x49,0x45,0x4E,0x44,0xAE,0x42,0x60,0x82)
    [System.IO.File]::WriteAllBytes($brokenImage, $pngBytes)
    Write-Host "Replaced broken/missing image124.png with placeholder"
} else {
    Write-Host "image124.png exists ($((Get-Item $brokenImage).Length) bytes)"
}

# Step 11: Create the repaired PPTX file
Write-Host "Packing repaired PPTX..."
if (Test-Path $outputFile) { Remove-Item $outputFile -Force }
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($tempDir, $outputFile, [System.IO.Compression.CompressionLevel]::Optimal, $false)

$newSize = (Get-Item $outputFile).Length
Write-Host ""
Write-Host "========================================="
Write-Host "  REPAIR COMPLETE!"
Write-Host "========================================="
Write-Host "Saved to: $outputFile"
Write-Host "Size: $([math]::Round($newSize / 1MB, 2)) MB"
Write-Host ""
Write-Host "Please open REPAIRED_FILE.pptx from your Desktop."
Write-Host "If PowerPoint asks to repair, click 'Repair'."
