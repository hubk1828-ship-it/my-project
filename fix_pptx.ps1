$ErrorActionPreference = "Continue"
$tempDir = "$env:USERPROFILE\Desktop\pptx_repair_temp"
$outputFile = "$env:USERPROFILE\Desktop\REPAIRED_V3.pptx"

# Clean previous repair artifacts
if (Test-Path "$tempDir\_rels") { Remove-Item "$tempDir\_rels" -Recurse -Force }
if (Test-Path "$tempDir\ppt\_rels") { Remove-Item "$tempDir\ppt\_rels" -Recurse -Force }
if (Test-Path "$tempDir\ppt\slides\_rels") { Remove-Item "$tempDir\ppt\slides\_rels" -Recurse -Force }
if (Test-Path "$tempDir\ppt\slideLayouts\_rels") { Remove-Item "$tempDir\ppt\slideLayouts\_rels" -Recurse -Force }
if (Test-Path "$tempDir\ppt\slideMasters\_rels") { Remove-Item "$tempDir\ppt\slideMasters\_rels" -Recurse -Force }
if (Test-Path "$tempDir\ppt\notesMasters\_rels") { Remove-Item "$tempDir\ppt\notesMasters\_rels" -Recurse -Force }
if (Test-Path "$tempDir\ppt\notesSlides\_rels") { Remove-Item "$tempDir\ppt\notesSlides\_rels" -Recurse -Force }
if (Test-Path "$tempDir\[Content_Types].xml") { Remove-Item "$tempDir\[Content_Types].xml" -Force }

# Counts
$slideCount = @(Get-ChildItem "$tempDir\ppt\slides" -Filter "slide*.xml").Count
$layoutCount = @(Get-ChildItem "$tempDir\ppt\slideLayouts" -Filter "slideLayout*.xml").Count
$masterCount = @(Get-ChildItem "$tempDir\ppt\slideMasters" -Filter "slideMaster*.xml").Count
$notesMasterCount = @(Get-ChildItem "$tempDir\ppt\notesMasters" -Filter "notesMaster*.xml" -EA SilentlyContinue).Count
$notesSlideCount = @(Get-ChildItem "$tempDir\ppt\notesSlides" -Filter "notesSlide*.xml" -EA SilentlyContinue).Count
$themeCount = @(Get-ChildItem "$tempDir\ppt\theme" -Filter "theme*.xml").Count
Write-Host "Slides:$slideCount Layouts:$layoutCount Masters:$masterCount Themes:$themeCount NotesMasters:$notesMasterCount NotesSlides:$notesSlideCount"

# Helper to write UTF8 no BOM
function WriteFile($path, $text) {
    [System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding $false))
}

# 1. Root _rels/.rels
New-Item "$tempDir\_rels" -ItemType Directory -Force | Out-Null
WriteFile "$tempDir\_rels\.rels" '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>'

# 2. ppt/_rels/presentation.xml.rels
New-Item "$tempDir\ppt\_rels" -ItemType Directory -Force | Out-Null
$sb = [System.Text.StringBuilder]::new()
[void]$sb.AppendLine('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
[void]$sb.AppendLine('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">')
$rid = 1

# Read presentation.xml to get sldMasterId and sldId entries with their existing rId refs
$presXml = Get-Content "$tempDir\ppt\presentation.xml" -Raw -Encoding UTF8

# Map: collect existing rId assignments from presentation.xml
$masterRefs = [regex]::Matches($presXml, 'sldMasterId[^/]*r:id="(rId\d+)"')
$slideRefs = [regex]::Matches($presXml, 'sldId\s[^/]*r:id="(rId\d+)"')
$notesMasterRef = [regex]::Match($presXml, 'notesMasterIdLst.*?r:id="(rId\d+)"')

# Build a map of what rId -> what target, matching the presentation.xml references
$presRIdMap = @{}

foreach ($m in $masterRefs) {
    $presRIdMap[$m.Groups[1].Value] = "slideMaster"
}
foreach ($m in $slideRefs) {
    $presRIdMap[$m.Groups[1].Value] = "slide"
}

# Get all unique rIds from presentation.xml
$allPresRIds = [regex]::Matches($presXml, 'r:id="(rId(\d+))"') | ForEach-Object { [int]$_.Groups[2].Value } | Sort-Object -Unique
$maxPresRId = ($allPresRIds | Measure-Object -Maximum).Maximum

# Build rels matching original rId assignments
# Masters
$masterIdx = 0
foreach ($m in $masterRefs) {
    $masterIdx++
    $rIdVal = $m.Groups[1].Value
    [void]$sb.AppendLine("  <Relationship Id=`"$rIdVal`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster`" Target=`"slideMasters/slideMaster$masterIdx.xml`"/>")
}

# Slides
$slideIdx = 0
foreach ($m in $slideRefs) {
    $slideIdx++
    $rIdVal = $m.Groups[1].Value
    [void]$sb.AppendLine("  <Relationship Id=`"$rIdVal`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide`" Target=`"slides/slide$slideIdx.xml`"/>")
}

# Notes master
if ($notesMasterRef.Success) {
    $rIdVal = $notesMasterRef.Groups[1].Value
    [void]$sb.AppendLine("  <Relationship Id=`"$rIdVal`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesMaster`" Target=`"notesMasters/notesMaster1.xml`"/>")
}

# presProps, viewProps, tableStyles, theme - assign new rIds after max
$nextRId = $maxPresRId + 1
[void]$sb.AppendLine("  <Relationship Id=`"rId$nextRId`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/presProps`" Target=`"presProps.xml`"/>"); $nextRId++
[void]$sb.AppendLine("  <Relationship Id=`"rId$nextRId`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/viewProps`" Target=`"viewProps.xml`"/>"); $nextRId++
[void]$sb.AppendLine("  <Relationship Id=`"rId$nextRId`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/tableStyles`" Target=`"tableStyles.xml`"/>"); $nextRId++
for ($i = 1; $i -le $themeCount; $i++) {
    [void]$sb.AppendLine("  <Relationship Id=`"rId$nextRId`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme`" Target=`"theme/theme$i.xml`"/>"); $nextRId++
}
[void]$sb.AppendLine('</Relationships>')
WriteFile "$tempDir\ppt\_rels\presentation.xml.rels" $sb.ToString()
Write-Host "Created presentation.xml.rels"

# 3. Slide rels - parse each slide to find image/media references
# Key insight: rId1 = slideLayout, remaining rIds = images in order
New-Item "$tempDir\ppt\slides\_rels" -ItemType Directory -Force | Out-Null

# Build a lookup of all media files
$mediaFiles = @(Get-ChildItem "$tempDir\ppt\media" -EA SilentlyContinue | Sort-Object { 
    $num = $_.BaseName -replace '[^0-9]',''
    if ($num) { [int]$num } else { 0 }
})

# For each slide, analyze which rIds it uses and what they reference
# Convention in PPTX: rId1 = slideLayout, rId2+ = images/media in order of appearance
# Images are typically assigned sequentially per slide

# We need a global image counter since each slide references different images
# The file list shows images are ordered: image1..image124
# We need to figure out which images go to which slide

# Strategy: Parse each slide XML for a:blip r:embed references and count them
# Then assign images sequentially across slides

# First pass: count how many image refs each slide has
$slideImageCounts = @()
$slideRIdDetails = @()
for ($i = 1; $i -le $slideCount; $i++) {
    $content = Get-Content "$tempDir\ppt\slides\slide$i.xml" -Raw -Encoding UTF8
    
    # Get all r:embed references (images)
    $embeds = [regex]::Matches($content, 'r:embed="(rId(\d+))"')
    $embedRIds = @()
    foreach ($e in $embeds) { $embedRIds += [int]$e.Groups[2].Value }
    $embedRIds = $embedRIds | Sort-Object -Unique
    
    # Get all r:link references (hyperlinks, usually external)  
    $links = [regex]::Matches($content, 'r:link="(rId(\d+))"')
    $linkRIds = @()
    foreach ($l in $links) { $linkRIds += [int]$l.Groups[2].Value }
    $linkRIds = $linkRIds | Sort-Object -Unique
    
    # rId1 is always slideLayout, so image rIds start from rId2
    $imageRIds = $embedRIds | Where-Object { $_ -ge 2 }
    
    $slideImageCounts += @{ SlideNum=$i; ImageRIds=$imageRIds; LinkRIds=$linkRIds; EmbedRIds=$embedRIds }
}

# Now assign images globally - images appear to be numbered globally across the presentation
# image1-image16 might be for slide1, etc.
# The safest assumption: each slide's rId2 maps to its first image, rId3 to second, etc.
# And images are assigned in order across slides

$globalImageIdx = 1  # Start from image1

for ($i = 0; $i -lt $slideCount; $i++) {
    $slideNum = $i + 1
    $info = $slideImageCounts[$i]
    $imageRIds = $info.ImageRIds
    $content = Get-Content "$tempDir\ppt\slides\slide$slideNum.xml" -Raw -Encoding UTF8
    
    $sSb = [System.Text.StringBuilder]::new()
    [void]$sSb.AppendLine('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
    [void]$sSb.AppendLine('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">')
    
    # rId1 = slideLayout
    $layoutNum = 2  # Most slides use layout 2 (content)
    if ($slideNum -eq 1) { $layoutNum = 1 }  # First slide uses title layout
    if ($layoutNum -gt $layoutCount) { $layoutNum = 1 }
    [void]$sSb.AppendLine("  <Relationship Id=`"rId1`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout`" Target=`"../slideLayouts/slideLayout$layoutNum.xml`"/>")
    
    # Map each image rId to a media file
    $localImageIdx = $globalImageIdx
    foreach ($rIdNum in ($imageRIds | Sort-Object)) {
        if ($localImageIdx -le $mediaFiles.Count) {
            $mediaFile = $mediaFiles[$localImageIdx - 1]
            [void]$sSb.AppendLine("  <Relationship Id=`"rId$rIdNum`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/image`" Target=`"../media/$($mediaFile.Name)`"/>")
            $localImageIdx++
        }
    }
    $globalImageIdx = $localImageIdx
    
    # Check for notesSlide reference
    if (Test-Path "$tempDir\ppt\notesSlides\notesSlide$slideNum.xml") {
        $maxRId = 2
        if ($imageRIds.Count -gt 0) { $maxRId = ($imageRIds | Measure-Object -Maximum).Maximum + 1 }
        # Find the actual rId used for notes in the slide
        $notesRIdMatch = [regex]::Match($content, 'notesSlide.*?r:id="(rId(\d+))"')
        if (-not $notesRIdMatch.Success) {
            [void]$sSb.AppendLine("  <Relationship Id=`"rId$maxRId`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide`" Target=`"../notesSlides/notesSlide$slideNum.xml`"/>")
        }
    }
    
    [void]$sSb.AppendLine('</Relationships>')
    WriteFile "$tempDir\ppt\slides\_rels\slide$slideNum.xml.rels" $sSb.ToString()
}
Write-Host "Created $slideCount slide rels (assigned $($globalImageIdx-1) images)"

# 4. SlideLayout rels
New-Item "$tempDir\ppt\slideLayouts\_rels" -ItemType Directory -Force | Out-Null
for ($i = 1; $i -le $layoutCount; $i++) {
    # Each layout also has image references - check
    $lContent = Get-Content "$tempDir\ppt\slideLayouts\slideLayout$i.xml" -Raw -Encoding UTF8
    $lSb = [System.Text.StringBuilder]::new()
    [void]$lSb.AppendLine('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
    [void]$lSb.AppendLine('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">')
    [void]$lSb.AppendLine("  <Relationship Id=`"rId1`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster`" Target=`"../slideMasters/slideMaster1.xml`"/>")
    [void]$lSb.AppendLine('</Relationships>')
    WriteFile "$tempDir\ppt\slideLayouts\_rels\slideLayout$i.xml.rels" $lSb.ToString()
}
Write-Host "Created $layoutCount layout rels"

# 5. SlideMaster rels  
New-Item "$tempDir\ppt\slideMasters\_rels" -ItemType Directory -Force | Out-Null
# Parse slideMaster to find its rId references
$masterContent = Get-Content "$tempDir\ppt\slideMasters\slideMaster1.xml" -Raw -Encoding UTF8
$masterAllRIds = [regex]::Matches($masterContent, 'r:id="rId(\d+)"') | ForEach-Object { [int]$_.Groups[1].Value } | Sort-Object -Unique

$mSb = [System.Text.StringBuilder]::new()
[void]$mSb.AppendLine('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
[void]$mSb.AppendLine('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">')
# rId1..rId11 = slideLayouts (we have 11 layouts)
for ($j = 1; $j -le $layoutCount; $j++) {
    [void]$mSb.AppendLine("  <Relationship Id=`"rId$j`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout`" Target=`"../slideLayouts/slideLayout$j.xml`"/>")
}
# Next rId = theme
$themeRId = $layoutCount + 1
[void]$mSb.AppendLine("  <Relationship Id=`"rId$themeRId`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme`" Target=`"../theme/theme1.xml`"/>")
[void]$mSb.AppendLine('</Relationships>')
WriteFile "$tempDir\ppt\slideMasters\_rels\slideMaster1.xml.rels" $mSb.ToString()
Write-Host "Created slideMaster rels"

# 6. NotesMaster rels
if ($notesMasterCount -gt 0) {
    New-Item "$tempDir\ppt\notesMasters\_rels" -ItemType Directory -Force | Out-Null
    $themeT = if (Test-Path "$tempDir\ppt\theme\theme2.xml") { "theme2.xml" } else { "theme1.xml" }
    WriteFile "$tempDir\ppt\notesMasters\_rels\notesMaster1.xml.rels" "<?xml version=`"1.0`" encoding=`"UTF-8`" standalone=`"yes`"?><Relationships xmlns=`"http://schemas.openxmlformats.org/package/2006/relationships`"><Relationship Id=`"rId1`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme`" Target=`"../theme/$themeT`"/></Relationships>"
}

# 7. NotesSlide rels
if ($notesSlideCount -gt 0) {
    New-Item "$tempDir\ppt\notesSlides\_rels" -ItemType Directory -Force | Out-Null
    for ($i = 1; $i -le $notesSlideCount; $i++) {
        # Find which slide this notes slide refers to
        $nsContent = Get-Content "$tempDir\ppt\notesSlides\notesSlide$i.xml" -Raw -Encoding UTF8
        WriteFile "$tempDir\ppt\notesSlides\_rels\notesSlide$i.xml.rels" "<?xml version=`"1.0`" encoding=`"UTF-8`" standalone=`"yes`"?><Relationships xmlns=`"http://schemas.openxmlformats.org/package/2006/relationships`"><Relationship Id=`"rId1`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesMaster`" Target=`"../notesMasters/notesMaster1.xml`"/><Relationship Id=`"rId2`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide`" Target=`"../slides/slide$i.xml`"/></Relationships>"
    }
}

# 8. [Content_Types].xml
$ctSb = [System.Text.StringBuilder]::new()
[void]$ctSb.AppendLine('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
[void]$ctSb.AppendLine('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">')
[void]$ctSb.AppendLine('<Default Extension="xml" ContentType="application/xml"/>')
[void]$ctSb.AppendLine('<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>')
[void]$ctSb.AppendLine('<Default Extension="png" ContentType="image/png"/>')
[void]$ctSb.AppendLine('<Default Extension="jpeg" ContentType="image/jpeg"/>')
[void]$ctSb.AppendLine('<Default Extension="jpg" ContentType="image/jpeg"/>')
[void]$ctSb.AppendLine('<Default Extension="svg" ContentType="image/svg+xml"/>')
[void]$ctSb.AppendLine('<Default Extension="gif" ContentType="image/gif"/>')
[void]$ctSb.AppendLine('<Default Extension="emf" ContentType="image/x-emf"/>')
[void]$ctSb.AppendLine('<Default Extension="fntdata" ContentType="application/x-fontdata"/>')

# Detect extra extensions from media
$addedExts = @('xml','rels','png','jpeg','jpg','svg','gif','emf','fntdata')
foreach ($mf in $mediaFiles) {
    $ext = $mf.Extension.TrimStart('.').ToLower()
    if ($ext -and $ext -notin $addedExts) {
        $addedExts += $ext
        $ct = switch($ext) { 'mp4'{'video/mp4'} 'wdp'{'image/vnd.ms-photo'} 'bmp'{'image/bmp'} 'tiff'{'image/tiff'} default{'application/octet-stream'} }
        [void]$ctSb.AppendLine("<Default Extension=`"$ext`" ContentType=`"$ct`"/>")
    }
}

[void]$ctSb.AppendLine('<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>')
[void]$ctSb.AppendLine('<Override PartName="/ppt/presProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presProps+xml"/>')
[void]$ctSb.AppendLine('<Override PartName="/ppt/viewProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml"/>')
[void]$ctSb.AppendLine('<Override PartName="/ppt/tableStyles.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml"/>')
for ($i=1;$i-le $themeCount;$i++) { [void]$ctSb.AppendLine("<Override PartName=`"/ppt/theme/theme$i.xml`" ContentType=`"application/vnd.openxmlformats-officedocument.theme+xml`"/>") }
for ($i=1;$i-le $masterCount;$i++) { [void]$ctSb.AppendLine("<Override PartName=`"/ppt/slideMasters/slideMaster$i.xml`" ContentType=`"application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml`"/>") }
for ($i=1;$i-le $layoutCount;$i++) { [void]$ctSb.AppendLine("<Override PartName=`"/ppt/slideLayouts/slideLayout$i.xml`" ContentType=`"application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml`"/>") }
for ($i=1;$i-le $slideCount;$i++) { [void]$ctSb.AppendLine("<Override PartName=`"/ppt/slides/slide$i.xml`" ContentType=`"application/vnd.openxmlformats-officedocument.presentationml.slide+xml`"/>") }
if ($notesMasterCount -gt 0) { [void]$ctSb.AppendLine('<Override PartName="/ppt/notesMasters/notesMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesMaster+xml"/>') }
for ($i=1;$i-le $notesSlideCount;$i++) { [void]$ctSb.AppendLine("<Override PartName=`"/ppt/notesSlides/notesSlide$i.xml`" ContentType=`"application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml`"/>") }
[void]$ctSb.AppendLine('</Types>')
WriteFile "$tempDir\[Content_Types].xml" $ctSb.ToString()
Write-Host "Created [Content_Types].xml"

# 9. Fix image124.png if corrupted
$img124 = "$tempDir\ppt\media\image124.png"
if (Test-Path $img124) {
    $imgBytes = [System.IO.File]::ReadAllBytes($img124)
    if ($imgBytes.Length -lt 8 -or $imgBytes[0] -ne 0x89 -or $imgBytes[1] -ne 0x50) {
        Write-Host "image124.png is corrupted, replacing with placeholder"
        $pngBytes = [byte[]](0x89,0x50,0x4E,0x47,0x0D,0x0A,0x1A,0x0A,0x00,0x00,0x00,0x0D,0x49,0x48,0x44,0x52,0x00,0x00,0x00,0x01,0x00,0x00,0x00,0x01,0x08,0x06,0x00,0x00,0x00,0x1F,0x15,0xC4,0x89,0x00,0x00,0x00,0x0A,0x49,0x44,0x41,0x54,0x78,0x9C,0x62,0x00,0x00,0x00,0x02,0x00,0x01,0xE5,0x27,0xDE,0xFC,0x00,0x00,0x00,0x00,0x49,0x45,0x4E,0x44,0xAE,0x42,0x60,0x82)
        [System.IO.File]::WriteAllBytes($img124, $pngBytes)
    }
}

# 10. Pack
Write-Host "Packing PPTX..."
if (Test-Path $outputFile) { Remove-Item $outputFile -Force }
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($tempDir, $outputFile, [System.IO.Compression.CompressionLevel]::Optimal, $false)
Write-Host "DONE! Saved: $outputFile ($([math]::Round((Get-Item $outputFile).Length/1MB,2)) MB)"
Write-Host "Open REPAIRED_V3.pptx from Desktop. Click Repair if prompted."
