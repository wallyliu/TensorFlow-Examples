"""Tests for the route generator.

    python -m unittest discover -s tests -t .        # everything
    python -m unittest tests.test_matching -v        # one module

Standard library `unittest`, no pytest, because the whole suite has to run on a
fresh checkout with nothing installed that the product does not already need.

NOTHING HERE TOUCHES THE NETWORK. `tests/gridfixture.py` builds a Manhattan
grid in memory, which is both faster and stricter than a downloaded city: on a
regular grid the shortest path between two junctions is exactly the Manhattan
distance, so a test can assert an arithmetic answer rather than whatever the
code returned last time.
"""
