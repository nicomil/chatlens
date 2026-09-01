"""One module per experiment: raw export in, canonical tables out.

An adapter is the only place that may know an experiment's column names, its
group size, its treatments or its payoff rule. Everything downstream works
from the canonical tables alone, which is what lets the same analysis run on a
different experiment.

``otree_coalition`` is the reference implementation, written for the
three-player coalition-formation experiment the project grew out of.
"""
