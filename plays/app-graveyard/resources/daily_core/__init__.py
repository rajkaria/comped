"""Six read-only Plays over the files your own machine already keeps.

Every scanner in `scan/` answers one question about local state, degrades a source it cannot
read to a labelled unknown instead of failing the run, and prints one JSON object as its last
line. Nothing here opens a socket; nothing here writes outside the caller's out_dir.
"""
__version__ = "0.1.0"
