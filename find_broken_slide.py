"""Find which slide breaks PowerPoint"""
from pptx import Presentation
import os, subprocess
from lxml import etree

desktop = os.path.join(os.environ['USERPROFILE'], 'Desktop')
test_dir = os.path.join(desktop, 'pptx_test')
os.makedirs(test_dir, exist_ok=True)
source = os.path.join(desktop, 'REPAIRED_PYTHON.pptx')

def test_pptx(filepath):
    ps = f'try {{ $ppt = New-Object -ComObject PowerPoint.Application; $p = $ppt.Presentations.Open("{filepath}", $true, $false, $false); Write-Output "OK"; $p.Close(); $ppt.Quit(); [System.Runtime.InteropServices.Marshal]::ReleaseComObject($ppt) | Out-Null }} catch {{ Write-Output "FAIL"; try {{ $ppt.Quit() }} catch {{}} }}'
    r = subprocess.run(['powershell','-Command',ps], capture_output=True, text=True, timeout=30)
    return 'OK' in r.stdout

def make_subset(keep_indices, outpath):
    prs = Presentation(source)
    pres_elem = prs.part._element  # The CT_Presentation XML element
    nsmap = {'p': 'http://schemas.openxmlformats.org/presentationml/2006/main'}
    sldIdLst = pres_elem.find('.//p:sldIdLst', nsmap)
    all_sldIds = list(sldIdLst)
    keep_set = set(keep_indices)
    for idx, el in enumerate(all_sldIds):
        if idx not in keep_set:
            sldIdLst.remove(el)
    prs.save(outpath)

# Phase 1: Test ranges of 10
print("=== Phase 1: Testing ranges ===")
failing_ranges = []
for start in range(0, 63, 10):
    end = min(start + 10, 63)
    indices = list(range(start, end))
    name = f"s{start+1}-{end}"
    outpath = os.path.join(test_dir, f'{name}.pptx')
    make_subset(indices, outpath)
    ok = test_pptx(outpath)
    print(f"  {name}: {'OK' if ok else 'FAIL'}")
    if not ok:
        failing_ranges.append((start, end))

if not failing_ranges:
    print("All ranges OK individually! Issue might be file size or combo.")
    # Try first half
    outpath = os.path.join(test_dir, 'first_half.pptx')
    make_subset(list(range(0, 32)), outpath)
    ok = test_pptx(outpath)
    print(f"  First half (1-32): {'OK' if ok else 'FAIL'}")
    
    outpath = os.path.join(test_dir, 'second_half.pptx')
    make_subset(list(range(32, 63)), outpath)
    ok = test_pptx(outpath)
    print(f"  Second half (33-63): {'OK' if ok else 'FAIL'}")
else:
    # Phase 2: Narrow down within failing ranges
    print(f"\n=== Phase 2: Narrowing down in {failing_ranges} ===")
    for start, end in failing_ranges:
        for i in range(start, end):
            outpath = os.path.join(test_dir, f'single_{i+1}.pptx')
            make_subset([i], outpath)
            ok = test_pptx(outpath)
            if not ok:
                print(f"  Slide {i+1}: FAIL <-- BROKEN!")
            else:
                print(f"  Slide {i+1}: OK")

print("\nDone!")
