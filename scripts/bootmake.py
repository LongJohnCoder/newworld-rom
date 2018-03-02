#!/usr/bin/env python3

from zlib import adler32
from sys import argv
from html import escape as html_escape
import re

def html_escape_forth(f):
    return re.sub(r'[<>]+', lambda m: html_escape(m.group()), f)



# Set constants.

# The COMPATIBLE field at the top of the script
COMPATIBLE = [
    "MacRISC",
    "MacRISC2",
    "MacRISC3",
    "MacRISC4",
]

# Changes to the Forth boot script, all off by default
DELETE_MODEL_CHECK = False
DELETE_CHECKSUM_CHECK = False
G4_FIX = True

# *After* OF has loaded this file, set the "model" property?
SET_MODEL_PROPERTY = ''
SET_MODEL_PROPERTY = 'PowerMac5,1' # Cube

# ...and the "compatible" property? (empty strings not counted)
SET_COMPATIBLE_PROPERTY = [x for x in [
    SET_MODEL_PROPERTY,
    *COMPATIBLE,
    'Power Macintosh',
] if x]

# Adds code to set the AAPL,debug property early in the boot script
DEBUG_PROPERTY = 0
# DEBUG_PROPERTY |= 0x00000001 # Print general informative messages.
# DEBUG_PROPERTY |= 0x00000002 # Print formatted Mac OS tables (except config/universal info).
# DEBUG_PROPERTY |= 0x00000004 # Print formatted config info table.
# DEBUG_PROPERTY |= 0x00000008 # Dump Mac OS tables (except config/universal info).
# DEBUG_PROPERTY |= 0x00000010 # Print node names while copying the device tree.
# DEBUG_PROPERTY |= 0x00000020 # Print property info while copying the device tree.
# DEBUG_PROPERTY |= 0x00000040 # Print interrupt-related info.
# DEBUG_PROPERTY |= 0x00000080 # Print interrupt tree traversal info.
# DEBUG_PROPERTY |= 0x00000100 # Print address resolution info.
# DEBUG_PROPERTY |= 0x00000200 # Print NV-RAM info.
# DEBUG_PROPERTY |= 0x00000400 # Print Mac OS "universal" info.
# DEBUG_PROPERTY |= 0x00000800 # Print "special" node info.
# DEBUG_PROPERTY |= 0x00001000 # Load EtherPrintf utility via parcel for post FCode debugging.
# DEBUG_PROPERTY |= 0x00002000 # Print BOOTP/DHCP/BSDP information.
# DEBUG_PROPERTY |= 0x00004000 # Allocate writable ROM aperture.
# DEBUG_PROPERTY |= 0x00008000 # Mark Toolbox image as non-cacheable.
# DEBUG_PROPERTY |= 0x00010000 # Print parcel info while copying the device tree.
# DEBUG_PROPERTY |= 0x00020000 # Print information on device tree data checksums.
# DEBUG_PROPERTY |= 0x01000000 # Enable the Nanokernel debugger.
# DEBUG_PROPERTY |= 0x02000000 # Display the Nanokernel log during boot.
# DEBUG_PROPERTY |= 0x10000000 # Dont attempt to unhibernate system.
# DEBUG_PROPERTY |= 0x40000000 # Halt after end of FCode (useful if outputting to screen).

# The OF-friendly parts of the file are padded out to 20k with nulls
DATA_OFFSET = 0x5000



# Load the two binary blobs, and save their offsets and sizes.

out_path, elf_path, parcels_path = argv[1:]


tbxi = bytearray(DATA_OFFSET)

for x in ['elf', 'parcels']:
    locals()[x + '_offset'] = len(tbxi)
    with open(locals()[x + '_path'], 'rb') as f:
        data = f.read()
        while len(data) % 4:
            data.extend(b'\x00')
    locals()[x + '_size'] = len(data)

    tbxi.extend(data)

info_size = len(tbxi)



# Assemble the CHRP-BOOT text for Open Firmware to parse.

BOOT_SCRIPT = ''

if DEBUG_PROPERTY: BOOT_SCRIPT += """
\ DEBUG_PROPERTY
dev /
%X encode-int " AAPL,debug" property
device-end
\ END DEBUG_PROPERTY
""" % DEBUG_PROPERTY

if SET_MODEL_PROPERTY: BOOT_SCRIPT += """
\ SET_MODEL_PROPERTY
dev /
" %s" encode-string " model" property
device-end
\ END SET_MODEL_PROPERTY
""" % SET_MODEL_PROPERTY

if SET_COMPATIBLE_PROPERTY:
    BOOT_SCRIPT += "\ SET_COMPATIBLE_PROPERTY\n"
    BOOT_SCRIPT += "dev /\n"
    BOOT_SCRIPT += '" %s" encode-string' % SET_COMPATIBLE_PROPERTY[0]
    for x in SET_COMPATIBLE_PROPERTY[1:]:
        BOOT_SCRIPT += ' " %s" encode-string encode+' % x
    BOOT_SCRIPT += ' " compatible" property\n'
    BOOT_SCRIPT += 'device-end\n'
    BOOT_SCRIPT += '\ END SET_COMPATIBLE_PROPERTY\n'

if G4_FIX: BOOT_SCRIPT += """
\ G4_FIX:
" /cpus/PowerPC,G4@0" find-package if
  " /cpus/PowerPC,G4@0" select-dev
  " cpu-version" active-package get-package-property 0= if
     decode-int
     2swap
     2drop
     80010201 <
     0= if
       80010201 encode-int " cpu-version" property
     then
  then
  device-end
then
\ END G4_FIX
"""

BOOT_SCRIPT += """
here >r
dev /
"""

if DELETE_MODEL_CHECK: BOOT_SCRIPT += """
\ Model check deleted
"""
else: BOOT_SCRIPT += """
" model" active-package get-package-property abort" can't find MODEL"
decode-string 2swap 2drop " iMac,1" $= ?dup 0= if
 " compatible" active-package get-package-property abort" can't find COMPATIBLE"
 false >r
 begin
  dup while
  decode-string here over 2swap bounds ?do
   i c@ dup [char] A [char] Z between if h# 20 xor then c,
   loop
%s
  2drop
  repeat
 2drop r>
  then
r> here - allot
0= abort" this image is not for this platform"
""" % '\n'.join('  2dup " %s" $= r> or >r' % m.lower() for m in COMPATIBLE)

if DELETE_CHECKSUM_CHECK: BOOT_SCRIPT += """
\ Checksum check deleted
"""
else: BOOT_SCRIPT += """
decimal
1 load-base load-size 14 - adler32    load-base load-size + 12 - 12 ['] eval catch if
 2drop ." , bad checksum value" -1
  then
 <> if
 ." , checksum error"
 abort
  then
hex
"""

BOOT_SCRIPT += """
dev /openprom
0 0 " supports-bootinfo" property  device-end

" /chosen" find-package 0= abort" can't find '/chosen'" constant /chosen
" memory" /chosen get-package-property abort" memory??" decode-int constant xmem 2drop
" mmu" /chosen get-package-property abort" mmu??" decode-int constant xmmu 2drop
" AAPL,debug" " /" find-package 0= abort" can't find '/'" get-package-property if
   false
  else
 2drop true
  then
 constant debug?
debug? if cr ." checking for RELEASE-LOAD-AREA" then
" release-load-area" $find 0= if 2drop false then  constant 'release-load-area
debug? if 'release-load-area if ." , found it" else ." , not found" then then
: do-translate " translate" xmmu $call-method ;
: do-map  " map" xmmu $call-method ;
: do-unmap " unmap" xmmu $call-method ;
: claim-mem  " claim" xmem $call-method ;
: release-mem " release" xmem $call-method ;
: claim-virt " claim" xmmu $call-method ;
: release-virt " release" xmmu $call-method ;
1000 constant pagesz
pagesz 1- constant pagesz-1
-1000 constant pagemask
h# {elf_offset:06X} constant elf-offset
h# {elf_size:06X} constant elf-size
elf-size pagesz-1 + pagemask and constant elf-pages
h# {parcels_offset:06X} constant parcels-offset
h# {parcels_size:06X} constant parcels-size
parcels-size pagesz-1 + pagemask and constant parcels-pages
h# {info_size:06X} constant info-size
info-size pagesz-1 + pagemask and constant info-pages
0 value load-base-claim
0 value info-base
'release-load-area if
    load-base to info-base
  else
    load-base info-pages 0 ['] claim-mem catch if 3drop 0 then to load-base-claim
    info-pages 1000 claim-virt to info-base
    load-base info-base info-pages 10 do-map   then
\ allocate room for both images
parcels-pages 400000 claim-mem constant rom-phys parcels-pages 1000 claim-virt constant rom-virt rom-phys rom-virt parcels-pages 10 do-map  
elf-pages 1000 claim-mem constant elf-phys   elf-pages 1000 claim-virt constant elf-virt
elf-phys elf-virt elf-pages 10 do-map    info-base elf-offset + elf-virt elf-size move  debug? if cr ." elf-phys,elf-virt,elf-pages: " elf-phys u. ." , " elf-virt u. ." , " elf-pages u. then
\ copy the compressed image
debug? if cr ." copying compressed ROM image" then
rom-virt parcels-pages 0 fill
info-base parcels-offset + rom-virt parcels-size move
'release-load-area 0= if
    info-base info-pages do-unmap      load-base-claim ?dup if info-pages release-mem then
  then
debug? if cr ." MacOS-ROM phys,virt,size: " rom-phys u. ." , " rom-virt u. ." , " parcels-size u. then
\ create the actual property
debug? if cr ." finding/creating '/rom/macos' package" then
device-end 0 to my-self
" /rom" find-device
" macos" ['] find-device catch if 2drop new-device " macos" device-name finish-device then
" /rom/macos" find-device
debug? if cr ." creating 'AAPL,toolbox-parcels' property" then
rom-virt encode-int parcels-size encode-int encode+ " AAPL,toolbox-parcels" property
device-end
debug? if cr ." copying MacOS.elf to load-base" then
'release-load-area if
    load-base elf-pages + 'release-load-area execute
  else
    load-base elf-pages 0 claim-mem
    load-base dup elf-pages 0 do-map    then
elf-virt load-base elf-size move
elf-virt elf-pages do-unmap      elf-virt elf-pages release-virt
elf-phys elf-pages release-mem
debug? if cr ." init-program" then
init-program
debug? if cr ." .registers" .registers then
debug? if cr ." go" cr then
go
cr ." end of BOOT-SCRIPT"
"""

BOOT_SCRIPT = BOOT_SCRIPT.format(**locals())
BOOT_SCRIPT = html_escape_forth(BOOT_SCRIPT)


BITMAP = """
0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF92FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF4925B7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF92006EDBFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFDB0049B7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFBFBBBFBBBFBBBFBBBFBBBFBBBFBBBFBB252577BFDFDFDFDFDFDFDFDFDFDFDFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFF772F332F2F2F332F2F2F332F2F2F332F2A055757575757575B57575B57575B579BFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFF772F2F2F332F2F2F332F2F2F332F2F2F012E57575B575B57575757575757575777FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFF97132F0F2F132F0F2F132F0F2F0F2F0A0557575B5757575B57575B57575B575797FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFF772F2F330F2F2F2F0F2F0F2F2F332F052A575B5757535357575B57575B57575B97FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFF772F2F2F332F0F2B062F332F132F0A00575757575B25255B5757575B5757575797FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFF772F132F0F332F0B060F2F0F2F2F0529575B575B572525575B575757575B575777FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFF970F2F2F2F0F2F0B262F0F332F0A0053575757575B25255B57575B5757575B5797FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFF772F2F132F2F332F0F2F332F2F0501575B575B5757534F57575B57575B57575797FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFF772F2F2F132F2F2F2F132F2F0F052A575757575B5757575B57575757575B575797FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFF77330F332F0F2F132F2F0F2F2F00535757575B5757575B575757575B57575B5777FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFF972F2F2F2F332F2F132F2F132A00575B575B57575B5757575B5757575B57575797FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFF770F330F330F2F0F2F2F332F05255B575757575B5757575B57575B575757575797FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFF972F2F2F2F332F332F0F2F2F052A575B57575757575B5757575B57575B575B5797FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFF772F0F330F2F0F2F0F332F33052A5757575757575B5757575B575757575B575777FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFF772F2F2F332F332F2F2F0F2F050000000000002E57575B5757575B575757575B97FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFF77332F132F0F2F0F2F0F332F2A0A2A2A2A050053575B5757575B5757575B575797FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFF970F2F2F2F332F332F330F2F0F332F0F330600575757575B5757575B57575B5797FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFF772F332F132F0F2F0F2F2F332F2F332F0F2504575B575B57575753575B57575777FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFF772F2F2F2F0B060A2B0F2F0F332F0F2F33050557575B574F2E2505535757575B97FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFF772F0F330F332F2B0A0606060A0B0B2B0B05052A29250005292E575757575B5797FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFF970F2F2F2F0F2F132F2F0F2B0A0A060606010025292E53575B57575B575B575797FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFF772F330F332F132F2F2F2F2F332F2F2F2F0501575B575757575757575757575777FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFF77332F2F2F2F2F2F132F0F2F0F2F2F0F2F050057575B575B57575B575B57575B97FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFF772F2F2F0F332F132F2F2F332F332F2F332600535B575757575B5757575B575797FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFF970F330F332F0F2F2F132F0F2F0F330F2F0A004F57575B5757575B5757575B5797FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFF9B332F33332F3333332F333333332F33332F002A77777777777777777777777797FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFDBDBDBDBDBDBDBDBDBDBDBDBDBDBFBDB2025B7DBDBDBDBDBDBDBDBDBDBDBDBFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF6E00B7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF006EFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFB7B7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFDBDBFFFFFFFFFFFFFFDBDBFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFBB57539BFFFFFFFFFFFF775377DFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFF92006EFFFFFFFFFF6E2592FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF53B7DBDBBB53DFFFFFDF97DBFBBB33FFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFF2525FFFFFFFFFF2525DBFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF3397DBFFFFFFDF33DBFF57B7FFFFFF97DBFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFF9225B7FFFFFFB76E25DBFFFFFFFFFFFFFFFFFFFFFFFFFFDBB7FFFFFFFF7733B7FFFFFFFFFF9B53FF3397FFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFF92496EFFFFFFB79225DBFFFFB792496EFFFFFFB7926E49FFFFFFFFFFFF2F73FFFFFFFFFFFFDF0FDB5333FFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFDBB7B725FFFFFF929225DBFF9292FFFF00DBFF6EB7FFFF6E92FFFFFFFFFF0F93FFFFFFFFFFFFFF2F979B2F33DFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFDBB7FF00B7FFDBB7B725DBFF25B7FFFF25B7DB49DBFFFFFFB7FFFFFFFFDF0F97FFFFFFFFFFFFFF3373FFBB330F53FFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFDBDBFF6E49FFB7FFFF00DBFFFFFFFFFF00B74949FFFFFFFFFFFFFFFFFFDF2F97FFFFFFFFFFFFFF3373FFFFFF972F33FFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFDBDBFFB725FF92FFFF00DBFFFFFFDB9225B7256EFFFFFFFFFFFFFFFFFFFF2F97FFFFFFFFFFFFFF2F73FFFFFFFFBB2F97FFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFB7DBFFFF006EB7FFFF00B7FFFFB7DBFF25B7256EFFFFFFFFFFFFFFFFFFFF3373FFFFFFFFFFFFDF2F97FFFFFFFFFF7773FFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFB7DBFFFF4925DBFFFF00B7FF6EB7FFFF25B76E49FFFFFFFFFFFFFFFFFFFF9B33FFFFFFFFFFFF5753B7BBFFFFFFFF7773FFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFF92DBFFFFDB49DBFFFF00B7FF25B7FFB700B7FF25DBFFFFFFFFFFFFFFFFFFFF5377FFFFFFFFBB3397DF53FFFFFFFF57B7FFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFDB2549DBFFFFB7FFDB490049DB254992DB2549DB9225DBFF92FFFFFFFFFFFFFFFF5397FFFFBB53B7FBFF3397FFFF77B7DBFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFB792DBFFFFFFFFFFB7B7B7DBB76EB7FFDB92DBFFB76E6EB7FFFFFFFFFFFFFFFFFFB7737797DBFFFFFFFF977397BBDBFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0BFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF0B
0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B0B
"""


BADGES = """
1010
000000000000000000ABFE0000000000
0000000000000000ABFF000000000000
ABABABABABABABABFFABABABABABABAB
AB7F7F7F7F7F7FFF7F2A2A2A2A2A2AAB
AB7F7F7FF17F7FFF542A2AFF2A2A2AAB
AB7F7F7FF17FABFF2A2A2AFF2A2A2AAB
AB7F7F7F7F7FFF7F2A2A2A2A2A2A2AAB
AB7F7F7F7F7FFF542A2A2A2A2A2A2AAB
AB7F7F7F7F7FFFFFFFFF2A2A2A2A2AAB
AB7F7F7F7F7F7F7F7FFF2A2A2A2A2AAB
AB7F7FFFF17F7F7F7FFF2A2AFFFF2AAB
AB7F7F7F7FF1F1F1F1FFFFFF542A2AAB
AB7F7F7F7F7F7F7F7FFF2A2A2A2A2AAB
ABABABABABABABABABFFABABABABABAB
000000000000000000ABFF0000000000
00000000000000000000ABFF00000000
000000000000000000F3FF0000000000
0000000000000000F3FF000000000000
F3F3F3F3F3F3F3F3FFF3F3F3F3F3F3F3
F3AAAAAAAAAAAAFFAA555555555555F3
F3AAAAAAF4AAAAFF7F5555FF555555F3
F3AAAAAAF4AAF3FF555555FF555555F3
F3AAAAAAAAAAFFAA55555555555555F3
F3AAAAAAAAAAFF7F55555555555555F3
F3AAAAAAAAAAFFFFFFFF5555555555F3
F3AAAAAAAAAAAAAAAAFF5555555555F3
F3AAAAFFF4AAAAAAAAFF5555FFFF55F3
F3AAAAAAAAF4F4F4F4FFFFFF7F5555F3
F3AAAAAAAAAAAAAAAAFF5555555555F3
F3F3F3F3F3F3F3F3F3FFF3F3F3F3F3F3
000000000000000000F3FF0000000000
00000000000000000000F3FF00000000
000000000000000000FFFE0000000000
0000000000000000FFFF000000000000
FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
000000000000000000FFFF0000000000
00000000000000000000FFFF00000000
"""


COMPATIBLE_TAG = '\n'.join(COMPATIBLE)

BOOT_INFO = """
<CHRP-BOOT>
<COMPATIBLE>
{COMPATIBLE_TAG}
</COMPATIBLE>
<DESCRIPTION>
MacROM for NewWorld.
</DESCRIPTION>
<ICON SIZE=64,64 COLOR-SPACE=3,3,2 >
<BITMAP>
{BITMAP}
</BITMAP>
</ICON>
<BOOT-SCRIPT>
{BOOT_SCRIPT}
</BOOT-SCRIPT>
<OS-BADGE-ICONS>
{BADGES}
</OS-BADGE-ICONS>
</CHRP-BOOT>
""".format(**locals())


BOOT_INFO = '\n'.join(l for l in BOOT_INFO.split('\n') if l)
BOOT_INFO = BOOT_INFO.replace('\n', '\r')
BOOT_INFO += '\r\x04' # CR, EOT
BOOT_INFO = BOOT_INFO.encode('ascii')

if len(BOOT_INFO) > DATA_OFFSET:
    raise ValueError

# Insert the text
tbxi[:len(BOOT_INFO)] = BOOT_INFO



# Checksum

cksum = adler32(tbxi)
cksum_str = ('\r\\ h# %08X' % cksum).encode('ascii')

tbxi.extend(cksum_str)



# Write out.

with open(out_path, 'wb') as f:
    f.write(tbxi)
