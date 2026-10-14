"""URH step gate: decides whether a step's artifact is done.

Public API::

    from urh_gate import Gate, load_contract
    verdict = Gate(load_contract("path/to/contract.py")).evaluate("/path/to/workspace")
    verdict.status   # "pass" | "fail" | "park"
"""

from .contract import Contract, Example, FunctionSpec, Property, Ref, load_contract
from .gate import FAIL, GATE_VERSION, PARK, PASS, Gate, Verdict

__all__ = [
    "Contract",
    "Example",
    "FunctionSpec",
    "Property",
    "Ref",
    "load_contract",
    "Gate",
    "Verdict",
    "PASS",
    "FAIL",
    "PARK",
    "GATE_VERSION",
]
