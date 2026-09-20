"""Audit analytics: computer-assisted audit techniques (CAATs) over a
transaction population, reusing recwise.importer. Currently: Benford's
Law first-digit analysis.
"""

from recwise.analytics.benford import BenfordResult, Conformity, DigitStat, analyze

__all__ = ["BenfordResult", "Conformity", "DigitStat", "analyze"]
