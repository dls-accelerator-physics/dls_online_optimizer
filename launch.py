'''
DLS-OnlineOptimiser: A flexible online optimisation package for use on the Diamond machine.
Version 2  2017-07-04
@authors: David Obee, James Rogers, Greg Henderson and Gareth Bird

IMPORTANT KEY:
        ARs: Algorithm results (objectives)
        APs: Algorithm parameters
        MRs: Machine results (objectives)
        MPs: Machine parameters

'''
from __future__ import division
import pkg_resources
pkg_resources.require('cothread')
pkg_resources.require('matplotlib')
pkg_resources.require('numpy')
pkg_resources.require('scipy')

import sys
import matplotlib
matplotlib.use("TkAgg")

from dlsoo import config, gui


OPTIMISERS = {
    'Multi-Objective Particle Swarm Optimiser (MOPSO)': 'mopso',
    'Multi-Objective Simulated Annealing (MOSA)': 'mosa',
    'Multi-Objective Non-dominated Sorting Genetic Algorithm (NSGA-II)': 'nsga2',
    'Single-Objective Robust Conjugate Direction Search (RCDS)': 'rcds'
    }


if __name__ == '__main__':
    print 'Welcome to DLS Online Optimiser'
    parameters = config.Parameters()
    if '-m' in sys.argv:
        parameters.useMachine = True
    elif '-s' in sys.argv:
        parameters.useMachine = False
    gui.start(OPTIMISERS, parameters)

