"""Sergio's shortcuts, wired like the fruit fly brain.

The adult fly connectome (FlyWire, Nature, October 2024: about 140 000 neurons,
more than 50 million synapses, over 8 000 cell types; and the hemibrain and male
central nervous system maps Google built with Janelia) shows a small brain that
is fast because each region has one job and the paths between them are short:

* eyes and antennae preprocess what comes in;
* the lateral horn answers innately, with hard-wired paths;
* the mushroom body learns associations, with sparse Kenyon-cell codes and
  dopamine neurons that reward or punish;
* the central complex keeps a heading and chooses where to go;
* descending neurons turn the choice into movement;
* the giant fiber is the escape reflex, the shortest path in the brain;
* a rich club of hub neurons ties the regions together.

:mod:`.regions` maps each region to the part of Sergio that does that job;
:mod:`.memory` is the mushroom body that learns the owner's shortcuts.
"""

from openjarvis.connectome.memory import MushroomBody, get_memory, kenyon_code
from openjarvis.connectome.regions import REGIONS, brain_map

__all__ = ["REGIONS", "MushroomBody", "brain_map", "get_memory", "kenyon_code"]
