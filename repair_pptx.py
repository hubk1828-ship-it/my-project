"""PPTX Repair Script - Rebuilds corrupted PPTX from extracted files"""
import os
import zipfile
import glob
import re
from pathlib import Path
from lxml import etree

DESKTOP = os.path.join(os.environ['USERPROFILE'], 'Desktop')
TEMP_DIR = os.path.join(DESKTOP, 'pptx_repair_temp')
OUTPUT = os.path.join(DESKTOP, 'REPAIRED_PYTHON.pptx')

# OPC/OOXML namespaces
NS = {
    'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main', 
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'rel': 'http://schemas.openxmlformats.org/package/2006/relationships',
    'ct': 'http://schemas.openxmlformats.org/package/2006/content-types',
}

REL_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'
REL_TYPE_BASE = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
CT_NS = 'http://schemas.openxmlformats.org/package/2006/content-types'

def count_files(pattern):
    return len(glob.glob(os.path.join(TEMP_DIR, pattern)))

def read_xml(path):
    with open(path, 'rb') as f:
        return etree.parse(f)

def write_xml(path, root):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tree = etree.ElementTree(root)
    tree.write(path, xml_declaration=True, encoding='UTF-8', standalone=True)

def make_rels_element():
    return etree.Element('Relationships', xmlns=REL_NS)

def add_rel(parent, rid, rel_type, target):
    etree.SubElement(parent, 'Relationship', Id=rid, Type=rel_type, Target=target)

# --- Analyze ---
slide_count = count_files('ppt/slides/slide*.xml')
layout_count = count_files('ppt/slideLayouts/slideLayout*.xml')
master_count = count_files('ppt/slideMasters/slideMaster*.xml')
theme_count = count_files('ppt/theme/theme*.xml')
notes_master_count = count_files('ppt/notesMasters/notesMaster*.xml')
notes_slide_count = count_files('ppt/notesSlides/notesSlide*.xml')
media_files = sorted(glob.glob(os.path.join(TEMP_DIR, 'ppt/media/*')),
                     key=lambda x: int(re.search(r'(\d+)', os.path.basename(x)).group(1)) if re.search(r'(\d+)', os.path.basename(x)) else 0)

print(f"Slides:{slide_count} Layouts:{layout_count} Masters:{master_count} Themes:{theme_count}")
print(f"NotesMasters:{notes_master_count} NotesSlides:{notes_slide_count} Media:{len(media_files)}")

# --- Parse presentation.xml to get rId mappings ---
pres_tree = read_xml(os.path.join(TEMP_DIR, 'ppt/presentation.xml'))
pres_root = pres_tree.getroot()

# Get slide master rId references
master_refs = pres_root.findall('.//p:sldMasterId', NS)
slide_refs = pres_root.findall('.//p:sldId', NS)

print(f"\nPresentation references: {len(master_refs)} masters, {len(slide_refs)} slides")

# Collect all rIds used in presentation.xml
pres_rids = set()
for el in master_refs + slide_refs:
    rid = el.get('{%s}id' % NS['r'])
    if rid:
        pres_rids.add(rid)
        
# Also check for notesMaster reference
notes_master_els = pres_root.findall('.//p:notesMasterIdLst/p:notesMasterId', NS)
for el in notes_master_els:
    rid = el.get('{%s}id' % NS['r'])
    if rid:
        pres_rids.add(rid)

max_rid = max(int(r.replace('rId','')) for r in pres_rids) if pres_rids else 0

# --- 1. Create _rels/.rels ---
print("\n1. Creating _rels/.rels")
root_rels = make_rels_element()
add_rel(root_rels, 'rId1', f'{REL_TYPE_BASE}/officeDocument', 'ppt/presentation.xml')
rels_dir = os.path.join(TEMP_DIR, '_rels')
os.makedirs(rels_dir, exist_ok=True)
write_xml(os.path.join(rels_dir, '.rels'), root_rels)

# --- 2. Create ppt/_rels/presentation.xml.rels ---
print("2. Creating ppt/_rels/presentation.xml.rels")
pres_rels = make_rels_element()

# Add masters with their original rIds
for idx, el in enumerate(master_refs, 1):
    rid = el.get('{%s}id' % NS['r'])
    add_rel(pres_rels, rid, f'{REL_TYPE_BASE}/slideMaster', f'slideMasters/slideMaster{idx}.xml')

# Add slides with their original rIds  
for idx, el in enumerate(slide_refs, 1):
    rid = el.get('{%s}id' % NS['r'])
    add_rel(pres_rels, rid, f'{REL_TYPE_BASE}/slide', f'slides/slide{idx}.xml')

# Add notes master
for el in notes_master_els:
    rid = el.get('{%s}id' % NS['r'])
    add_rel(pres_rels, rid, f'{REL_TYPE_BASE}/notesMaster', 'notesMasters/notesMaster1.xml')

# Add extra rels
next_rid = max_rid + 1
add_rel(pres_rels, f'rId{next_rid}', f'{REL_TYPE_BASE}/presProps', 'presProps.xml'); next_rid += 1
add_rel(pres_rels, f'rId{next_rid}', f'{REL_TYPE_BASE}/viewProps', 'viewProps.xml'); next_rid += 1
add_rel(pres_rels, f'rId{next_rid}', f'{REL_TYPE_BASE}/tableStyles', 'tableStyles.xml'); next_rid += 1
for i in range(1, theme_count + 1):
    add_rel(pres_rels, f'rId{next_rid}', f'{REL_TYPE_BASE}/theme', f'theme/theme{i}.xml'); next_rid += 1

ppt_rels_dir = os.path.join(TEMP_DIR, 'ppt/_rels')
os.makedirs(ppt_rels_dir, exist_ok=True)
write_xml(os.path.join(ppt_rels_dir, 'presentation.xml.rels'), pres_rels)

# --- 3. Create slide rels with proper media mapping ---
print("3. Creating slide relationships with media mapping")
slides_rels_dir = os.path.join(TEMP_DIR, 'ppt/slides/_rels')
os.makedirs(slides_rels_dir, exist_ok=True)

global_img_idx = 0  # Index into media_files

for slide_num in range(1, slide_count + 1):
    slide_path = os.path.join(TEMP_DIR, f'ppt/slides/slide{slide_num}.xml')
    slide_tree = read_xml(slide_path)
    slide_root = slide_tree.getroot()
    
    slide_rels = make_rels_element()
    
    # rId1 = slideLayout
    layout_num = 1 if slide_num == 1 else 2
    if layout_num > layout_count:
        layout_num = 1
    add_rel(slide_rels, 'rId1', f'{REL_TYPE_BASE}/slideLayout', f'../slideLayouts/slideLayout{layout_num}.xml')
    
    # Find all r:embed and r:link references (excluding rId1 which is layout)
    all_rids = set()
    embed_rids = set()
    link_rids = set()
    
    for el in slide_root.iter():
        for attr_name, attr_val in el.attrib.items():
            if attr_name == '{%s}embed' % NS['r']:
                rid_num = int(attr_val.replace('rId', ''))
                if rid_num > 1:
                    embed_rids.add(rid_num)
                    all_rids.add(rid_num)
            elif attr_name == '{%s}link' % NS['r']:
                rid_num = int(attr_val.replace('rId', ''))
                link_rids.add(rid_num)
                all_rids.add(rid_num)
    
    # Assign media files to embed rIds in order
    for rid_num in sorted(embed_rids):
        if global_img_idx < len(media_files):
            media_name = os.path.basename(media_files[global_img_idx])
            ext = os.path.splitext(media_name)[1].lower()
            
            # Determine relationship type
            if ext in ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.emf', '.wmf', '.tiff', '.wdp'):
                rel_type = f'{REL_TYPE_BASE}/image'
            elif ext == '.svg':
                rel_type = f'{REL_TYPE_BASE}/image'
            elif ext in ('.mp4', '.avi', '.wmv'):
                rel_type = f'{REL_TYPE_BASE}/video'
            elif ext in ('.mp3', '.wav'):
                rel_type = f'{REL_TYPE_BASE}/audio'
            else:
                rel_type = f'{REL_TYPE_BASE}/image'
            
            add_rel(slide_rels, f'rId{rid_num}', rel_type, f'../media/{media_name}')
            global_img_idx += 1
    
    # Add link rIds as external hyperlinks (empty target)
    for rid_num in sorted(link_rids):
        if rid_num not in embed_rids:
            add_rel(slide_rels, f'rId{rid_num}', f'{REL_TYPE_BASE}/hyperlink', '')
    
    # Check for notes slide
    notes_path = os.path.join(TEMP_DIR, f'ppt/notesSlides/notesSlide{slide_num}.xml')
    if os.path.exists(notes_path):
        max_used = max(all_rids) if all_rids else 1
        notes_rid = max_used + 1
        add_rel(slide_rels, f'rId{notes_rid}', f'{REL_TYPE_BASE}/notesSlide', f'../notesSlides/notesSlide{slide_num}.xml')
    
    write_xml(os.path.join(slides_rels_dir, f'slide{slide_num}.xml.rels'), slide_rels)

print(f"   Mapped {global_img_idx}/{len(media_files)} media files across {slide_count} slides")

# --- 4. SlideLayout rels ---
print("4. Creating slideLayout relationships")
layout_rels_dir = os.path.join(TEMP_DIR, 'ppt/slideLayouts/_rels')
os.makedirs(layout_rels_dir, exist_ok=True)
for i in range(1, layout_count + 1):
    lr = make_rels_element()
    add_rel(lr, 'rId1', f'{REL_TYPE_BASE}/slideMaster', '../slideMasters/slideMaster1.xml')
    write_xml(os.path.join(layout_rels_dir, f'slideLayout{i}.xml.rels'), lr)

# --- 5. SlideMaster rels ---
print("5. Creating slideMaster relationships")
master_rels_dir = os.path.join(TEMP_DIR, 'ppt/slideMasters/_rels')
os.makedirs(master_rels_dir, exist_ok=True)
mr = make_rels_element()
for j in range(1, layout_count + 1):
    add_rel(mr, f'rId{j}', f'{REL_TYPE_BASE}/slideLayout', f'../slideLayouts/slideLayout{j}.xml')
add_rel(mr, f'rId{layout_count + 1}', f'{REL_TYPE_BASE}/theme', '../theme/theme1.xml')
write_xml(os.path.join(master_rels_dir, 'slideMaster1.xml.rels'), mr)

# --- 6. NotesMaster rels ---
if notes_master_count > 0:
    print("6. Creating notesMaster relationships")
    nm_rels_dir = os.path.join(TEMP_DIR, 'ppt/notesMasters/_rels')
    os.makedirs(nm_rels_dir, exist_ok=True)
    nmr = make_rels_element()
    theme_target = 'theme2.xml' if os.path.exists(os.path.join(TEMP_DIR, 'ppt/theme/theme2.xml')) else 'theme1.xml'
    add_rel(nmr, 'rId1', f'{REL_TYPE_BASE}/theme', f'../theme/{theme_target}')
    write_xml(os.path.join(nm_rels_dir, 'notesMaster1.xml.rels'), nmr)

# --- 7. NotesSlide rels ---
if notes_slide_count > 0:
    print("7. Creating notesSlide relationships")
    ns_rels_dir = os.path.join(TEMP_DIR, 'ppt/notesSlides/_rels')
    os.makedirs(ns_rels_dir, exist_ok=True)
    for i in range(1, notes_slide_count + 1):
        nsr = make_rels_element()
        add_rel(nsr, 'rId1', f'{REL_TYPE_BASE}/notesMaster', '../notesMasters/notesMaster1.xml')
        add_rel(nsr, 'rId2', f'{REL_TYPE_BASE}/slide', f'../slides/slide{i}.xml')
        write_xml(os.path.join(ns_rels_dir, f'notesSlide{i}.xml.rels'), nsr)

# --- 8. [Content_Types].xml ---
print("8. Creating [Content_Types].xml")
types_root = etree.Element('Types', xmlns=CT_NS)

# Default extensions
defaults = {
    'xml': 'application/xml',
    'rels': 'application/vnd.openxmlformats-package.relationships+xml',
    'png': 'image/png', 'jpeg': 'image/jpeg', 'jpg': 'image/jpeg',
    'svg': 'image/svg+xml', 'gif': 'image/gif', 'emf': 'image/x-emf',
    'fntdata': 'application/x-fontdata',
}

# Add media-specific extensions
for mf in media_files:
    ext = os.path.splitext(mf)[1].lstrip('.').lower()
    if ext not in defaults:
        ct_map = {'mp4':'video/mp4', 'wdp':'image/vnd.ms-photo', 'bmp':'image/bmp', 'wmf':'image/x-wmf'}
        defaults[ext] = ct_map.get(ext, 'application/octet-stream')

for ext, ct in defaults.items():
    etree.SubElement(types_root, 'Default', Extension=ext, ContentType=ct)

# Overrides
overrides = {
    '/ppt/presentation.xml': 'application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml',
    '/ppt/presProps.xml': 'application/vnd.openxmlformats-officedocument.presentationml.presProps+xml',
    '/ppt/viewProps.xml': 'application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml',
    '/ppt/tableStyles.xml': 'application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml',
}

for i in range(1, theme_count + 1):
    overrides[f'/ppt/theme/theme{i}.xml'] = 'application/vnd.openxmlformats-officedocument.theme+xml'
for i in range(1, master_count + 1):
    overrides[f'/ppt/slideMasters/slideMaster{i}.xml'] = 'application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml'
for i in range(1, layout_count + 1):
    overrides[f'/ppt/slideLayouts/slideLayout{i}.xml'] = 'application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml'
for i in range(1, slide_count + 1):
    overrides[f'/ppt/slides/slide{i}.xml'] = 'application/vnd.openxmlformats-officedocument.presentationml.slide+xml'
if notes_master_count > 0:
    overrides['/ppt/notesMasters/notesMaster1.xml'] = 'application/vnd.openxmlformats-officedocument.presentationml.notesMaster+xml'
for i in range(1, notes_slide_count + 1):
    overrides[f'/ppt/notesSlides/notesSlide{i}.xml'] = 'application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml'

for part_name, ct in overrides.items():
    etree.SubElement(types_root, 'Override', PartName=part_name, ContentType=ct)

ct_path = os.path.join(TEMP_DIR, '[Content_Types].xml')
write_xml(ct_path, types_root)

# --- 9. Build the PPTX ZIP ---
print("9. Building PPTX...")
if os.path.exists(OUTPUT):
    os.remove(OUTPUT)

with zipfile.ZipFile(OUTPUT, 'w', zipfile.ZIP_DEFLATED) as zf:
    # Walk all files in temp dir
    for root_dir, dirs, files in os.walk(TEMP_DIR):
        for fname in files:
            full_path = os.path.join(root_dir, fname)
            arcname = os.path.relpath(full_path, TEMP_DIR).replace('\\', '/')
            
            # [Content_Types].xml should be stored (no compression) per OPC
            if arcname == '[Content_Types].xml':
                zf.write(full_path, arcname, compress_type=zipfile.ZIP_STORED)
            else:
                zf.write(full_path, arcname)

size_mb = os.path.getsize(OUTPUT) / (1024*1024)
print(f"\n{'='*45}")
print(f"  REPAIR COMPLETE!")
print(f"{'='*45}")
print(f"File: {OUTPUT}")
print(f"Size: {size_mb:.2f} MB")
print(f"Open REPAIRED_PYTHON.pptx from Desktop")
print(f"Click 'Repair' if PowerPoint prompts you")
