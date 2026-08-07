r"""Dialect extensions: optional notation, one rule table each.

An extension is a mapping from node type to lowering rule, plus the
names its lowerings emit into generated Python.  The core lowers the
Sage language; everything past that is an extension a session opts into.
Each stays Sage-free, so the notation is testable without a Sage
installation; the matching module under :mod:`sageparse.preparser`
registers it into a live session.

:mod:`sageparse.extensions.research` is the catch-all for non-standard
notation migrated upstream out of research use.
"""
