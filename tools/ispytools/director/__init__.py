"""Minimal Macromedia Director file reader (RIFX / XFIR, protected and Afterburner).

Supports what the I Spy pipeline needs:
  * container + memory map (imap/mmap) and Afterburner (Fver/Fcdr/ABMP/FGEI/ILS)
  * KEY* resource ownership, CAS* slot table, CASt member records
  * bitmaps (BITD + CLUT), text (STXT), sounds (snd ), scripts (Lscr/Lnam names + string literals)
  * cast list (MCsL), frame labels (VWLB), score sprites (VWSC)
"""

from .file import DirectorFile  # noqa: F401
