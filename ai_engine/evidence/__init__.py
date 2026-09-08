"""
IBVAP Evidence Module
====================
Captures forensic snapshot evidence on high-priority security alerts.
"""
from .recorder import EvidenceRecorder, get_evidence_recorder

__all__ = ["EvidenceRecorder", "get_evidence_recorder"]
