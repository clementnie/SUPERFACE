#!/usr/bin/env python3
"""Append pinned wide punctuation while preserving every accepted Han ID/pixel.
Regenerates all font artifacts and notices together. Source ZIP stays outside repo.
"""
import argparse,csv,json,hashlib,unicodedata
from pathlib import Path
import generate_superface_font as g
p=argparse.ArgumentParser();p.add_argument('--archive',type=Path,required=True);a=p.parse_args()
r=g.ROOT;out=g.ASSETS
old=(out/g.MAP_NAME).read_bytes(); old_image=(out/g.FLASH_NAME).read_bytes()
old_rows=[(int(x['unicode'][2:],16),int(x['glyph_id'],16)) for x in csv.DictReader(old.decode().splitlines())]
han=sorted((c,i) for c,i in old_rows if 0x4e00<=c<=0x9fff)
assert len(han)==6727 and [i for _,i in han]==list(range(0x8000,0x9a47))
# Width-two punctuation fits the established two-cell wire/rendering contract.
requested_extra=(out/'required_punctuation.txt').read_bytes()
extra=[int(line[2:],16) for line in requested_extra.decode('ascii').splitlines()]
assert requested_extra==''.join(f'U+{c:06X}\n' for c in extra).encode() and extra==sorted(set(extra))
assert all(unicodedata.east_asian_width(chr(c)) in 'WF' for c in extra)
bitmap,notices=g.load_source(a.archive)
glyphs=g.read_bdf(bitmap,[c for c,_ in han]+extra)
missing=[c for c in extra if c not in glyphs]
assert not missing, [f'U+{c:04X}' for c in missing]
points=[c for c,_ in han]+extra
ids={c:0x8000+i for i,c in enumerate(points)}
rows=[(c,c) for c in range(0x20,0x7f)]+list(ids.items())
mapping=('unicode,glyph_id\n'+''.join(f'U+{c:06X},0x{i:04X}\n' for c,i in sorted(rows))).encode()
payload=g.pack_sram(points,glyphs)
assert payload[:6727*32]==old_image[64:64+6727*32], 'Verified Han artwork changed'
assert all(ids[c]==i for c,i in han), 'Verified Han IDs changed'
g.SAMPLES='你好世界，。！？；：（）【】《》％＋＝＠'
outputs={g.MAP_NAME:mapping,g.MIF_NAME:g.build_mif(payload),g.FLASH_NAME:g.build_flash(payload,len(points),g.mapping_id(mapping)),g.MISSING_NAME:(out/g.MISSING_NAME).read_bytes(),**notices}
outputs[g.SHEET_NAME]=g.build_sheet(g.decode_mif(outputs[g.MIF_NAME]),ids)
meta=json.loads(g.make_manifest(points,(out/g.REPERTOIRE_NAME).read_bytes(),[1]*36,outputs,g.mapping_id(mapping),payload))
meta['repertoire']['supported'].update(han_total=6727,level_2=2972)
meta['repertoire']['policy']='Verified 6727 Han IDs unchanged; append pinned width-two punctuation/full-width symbols'
meta['repertoire']['extension']={'input':'required_punctuation.txt','input_sha256':hashlib.sha256(requested_extra).hexdigest(),'count':len(extra),'unicode':[f'U+{c:06X}' for c in extra],'first_id':'0x9A47','han_ids_preserved':True,'han_payload_prefix_sha256':hashlib.sha256(payload[:6727*32]).hexdigest()}
for name,data in {**outputs,g.MANIFEST_NAME:(json.dumps(meta,indent=2,sort_keys=True)+'\n').encode()}.items():
 f=out/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(data)
(out/'required_punctuation.txt').write_text(''.join(f'U+{c:06X}\n' for c in extra))
print(f'PASS {len(extra)} appended glyphs; total {len(points)}; all6727 Han IDs and bitmap bytes unchanged; image {len(outputs[g.FLASH_NAME])} bytes; mapping {g.mapping_id(mapping).hex()}')

# Update schematic guards along with the protocol provider; no silent stale bounds.
import re
for filename,old_label,new_label,old_value,new_value in [
    ('Glyph_Class.bdf','K16_9A46','K16_9ABB',39494,39611),
    ('Terminal_Display.bdf','K15_1A47','K15_1ABC',6727,6844)]:
    path=r/'lab8_restored'/filename
    text=path.read_text().replace(old_label,new_label).replace(f'"{old_value}"',f'"{new_value}"')
    path.write_text(text)
