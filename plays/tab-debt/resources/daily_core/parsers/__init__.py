"""Format readers. Each one takes bytes and returns plain data, or raises nothing the caller minds.

Every reader here is defensive by construction: a file written by a browser version this code has
never seen must degrade to "could not read that", never to a wrong number and never to a crash.
"""
