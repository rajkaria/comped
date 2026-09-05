"""Which architectures an application actually ships, read from its Mach-O header.

An Intel-only app on Apple silicon runs under translation, and nothing in the Finder says so.
The answer is sixteen bytes into the executable: a fat binary lists its slices, and a thin one
names one CPU type. Reading it needs no tools and no code execution.
"""
import struct

FAT_MAGIC, FAT_CIGAM = 0xCAFEBABE, 0xBEBAFECA
FAT_MAGIC_64, FAT_CIGAM_64 = 0xCAFEBABF, 0xBFBAFECA
MH_MAGIC, MH_CIGAM = 0xFEEDFACE, 0xCEFAEDFE
MH_MAGIC_64, MH_CIGAM_64 = 0xFEEDFACF, 0xCFFAEDFE

CPU_X86, CPU_X86_64, CPU_ARM, CPU_ARM64 = 7, 7 | 0x01000000, 12, 12 | 0x01000000
NAMES = {CPU_X86: "i386", CPU_X86_64: "x86_64", CPU_ARM: "arm", CPU_ARM64: "arm64"}


def architectures(head: bytes) -> list:
    """Sorted architecture names, or [] when the bytes are not a Mach-O image."""
    if len(head) < 8:
        return []
    magic = struct.unpack_from(">I", head, 0)[0]
    if magic in (FAT_MAGIC, FAT_MAGIC_64, FAT_CIGAM, FAT_CIGAM_64):
        order = ">" if magic in (FAT_MAGIC, FAT_MAGIC_64) else "<"
        wide = magic in (FAT_MAGIC_64, FAT_CIGAM_64)
        count = struct.unpack_from(order + "I", head, 4)[0]
        if count > 32:
            return []
        step, out = (32 if wide else 20), []
        for i in range(count):
            off = 8 + i * step
            if off + 4 > len(head):
                break
            out.append(NAMES.get(struct.unpack_from(order + "I", head, off)[0] & 0xFFFFFFFF, "other"))
        return sorted(set(out))
    # A thin image names its own byte order in the magic: FEEDFACF is big-endian on disk,
    # CFFAEDFE the same header written little-endian. The CPU type follows in that same order.
    if magic in (MH_MAGIC, MH_MAGIC_64):
        order = ">"
    elif magic in (MH_CIGAM, MH_CIGAM_64):
        order = "<"
    else:
        return []
    if len(head) < 8:
        return []
    return [NAMES.get(struct.unpack_from(order + "I", head, 4)[0] & 0xFFFFFFFF, "other")]
