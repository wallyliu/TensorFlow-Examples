"""Shape-to-route: everything the service needs, and nothing the lab notebooks do.

Before this package existed, 71 modules sat flat in one directory and the
product was indistinguishable from the experiments that produced it. The
server's own dependency closure made the point: importing `wander` from a file
called poc15_wiggle.py dragged in a dinosaur-damage stimulus generator, because
that module imported one at the top level for an experiment it also happened to
contain.

  routeshape.network     download and cache a street network
  routeshape.placement   put a shape on the map; index the streets; pick centres
  routeshape.search      scan placements coarsely, then fit one properly
  routeshape.matching    the Viterbi map-match that turns anchors into a route
  routeshape.feasibility what a distance buys: n_min, width, detour, the floor
  routeshape.recognition how likely a person is to name the shape (POC 29)
  routeshape.street_scale how far apart the streets are, per place (POC 26)
  routeshape.metrics     shape distance, alignment angle
  routeshape.wander      how much longer the route is than the outline
  routeshape.export      GPX
  routeshape.describe    a description -> an outline, checked before it is used
  routeshape.shapes      the shape library and the outlines in it
  routeshape.region      the tiled regional map cache

The experiments that established every constant here live in experiments/, and
nothing in this package imports them.
"""
