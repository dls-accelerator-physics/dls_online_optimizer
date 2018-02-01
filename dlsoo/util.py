'''
Version 2
2017-07-30

This version of util is used in basic optimisation. The important class to read through are sim_machine_interactor_bulk_base and
dls_machine_interactor_bulk_base. This contains the methods for starting and stopping injection. The measure_results function is
also an important part to understand; this is how the interactor deals with noisy data.

IMPORTANT KEY:
        ARs: Algorithm results (objectives)
        APs: Algorithm parameters
        MRs: Machine results (objectives)
        MPs: Machine parameters

'''

from __future__ import division

import pkg_resources
from audioop import avg
pkg_resources.require('cothread')

import random

import time
import math
import pickle
import types
import model
import kur_model
import ca_abstraction_mapping

from cothread.catools import caget, caput, ca_nothing
from cothread.cadef import CAException
import cothread

#---------------------------------------------------------IMPORTANT FUNCTIONS-----------------------------------------------#

def abstract_caget(pv):
    """
    standard channel access 'get' function using cothread
    """
    if pv in ca_abstraction_mapping.name_to_function_mapping:
        return ca_abstraction_mapping.name_to_function_mapping[pv]()
    else:
        return caget(pv)

#-------------------------------------------------------------------

def abstract_caput(pv, value):
    """
    standard channel access 'set' function using cothread
    """
    caput(pv, value)

#-------------------------------------------------------------------

def set_params(param_vars, settings, set_command):
    """
    change the parameters using set_command. This will usually be abstract_caput
    """

    # Calculate the maximum delay time
    max_delay = 0
    for i in param_vars:
        if i.delay > max_delay:
            max_delay = i.delay

    # Set the parameters
    for i in range(len(param_vars)):
        set_command(param_vars[i].pv, settings[i])

    # Sleep for the appropriate amount of time
    cothread.Sleep(max_delay)

#-------------------------------------------------------------------

def measure_results(measurement_vars, get_command):
    """
    This part (redesigned by @James Rogers) measures the objectives and calculates the mean and standard deviation.
    Outliers are detected (2*sigma away from mean) and discarded. The mean and standard deviation are then returned.

    The get_command is usually abstract_caget (see above).
    """

    average = []
    counts = []
    dev = []
    err = []

    #for each objective
    for i in range(len(measurement_vars)):

        result = int(measurement_vars[i].min_counts) * [0.]
        std = int(measurement_vars[i].min_counts) * [0.]

        for j in range(int(measurement_vars[i].min_counts)):

            value = get_command(measurement_vars[i].pv)
            result[j] = value
            std[j] = value ** 2
            j += 1
            time.sleep(measurement_vars[i].delay)

        mean = sum(result) / measurement_vars[i].min_counts
        standard_deviation = (sum(std) / measurement_vars[i].min_counts) - mean ** 2
        standard_deviation = math.sqrt(standard_deviation)

        #detect and remove any outliers
        anomaly = False
        for j in result:
            if (abs(mean - j)) > 2 * standard_deviation:
                anomaly = True
                index = result.index(j)
                result.remove(j)
                del std[index]

        #recalculate mean if outliers are found
        if anomaly == True:
            mean = sum(result) / len(result)
            standard_deviation = (sum(std) / len(result)) - mean ** 2
            standard_deviation = math.sqrt(standard_deviation)

        stat_err = standard_deviation / math.sqrt(len(result))

        average.append(mean)
        counts.append(len(result))
        dev.append(standard_deviation)
        err.append(stat_err)

    results = []
    for i in range(len(average)):
        results.append(measurement(mean=average[i], counts=counts[i], dev=dev[i], err=err[i]))

    return results

#-------------------------------------------------------------------

def find_group_a_bounds(param_var_min, param_var_max, initial_values, set_relative):
    '''
    This part (not finished) is to find the boundaries required for the algorithm parameters
    such that the machine parameters never go out of their bounds. It currently works for setting
    when you have relative setting, but not yet for absolute setting. This is what I need to
    finish.

    Edit (@James Rogers): The absolute setting method (the part that wasn't finished) is not
                          necessary and the option has been removed from the GUI in main.py,
                          i.e. set_relative is always set as True in main.py if the parameter
                          ranges are defined using bounds (as opposed to changes).
    '''
    min = None
    max = None

    if set_relative:

        for p_min, p_max, init in zip(param_var_min, param_var_max, initial_values):
            amount_above = p_max - init
            amount_below = p_min - init

            if min != None:
                if amount_below > min:
                    min = amount_below
            else:
                min = amount_below

            if max != None:
                if amount_above < max:
                    max = amount_above
            else:
                max = amount_above


    else:

        for p_min, p_max in zip(param_var_min, param_var_max):
            if min != None:
                if p_min > min:
                    min = p_min
            else:
                min = p_min

            if max != None:
                if p_max < max:
                    max = p_max
            else:
                max = p_max


    print (min, max)
    return (min, max)

#-------------------------------------------------------------------------

def save_details_file(object):
    """
    returns a file of useful information used in this file duration an optimisation
    """

    file_return = ""

    file_return += "DLS Machine Interactor Base\n"
    file_return += "===========================\n\n"

    file_return += "Parameter variables:\n"
    file_return += "-------------------\n"
    for i in object.param_vars:
        file_return += "PV name: {0}\n".format(i.pv)
        file_return += "Delay: {0} s\n\n".format(i.delay)

    file_return += "Measurement variables:\n"
    file_return += "---------------------\n"

    collated_measurement_vars = []
    if hasattr(object, "measurement_vars_noinj"):
        collated_measurement_vars = object.measurement_vars_noinj + object.measurement_vars_inj
    else:
        collated_measurement_vars = object.measurement_vars

    for i in collated_measurement_vars:
        file_return += "PV name: {0}\n".format(i.pv)
        file_return += "Minimum counts: {0}\n".format(i.min_counts)
        file_return += "Delay: {0} s\n\n".format(i.delay)

    return file_return

#-----------------------------------------PARAMETER AND OBJECTIVE PYTHON OBJECTS USED IN MAIN.PY------------------------------------#

#these classes are used in the 'add_pv' type functions in many classes in main.py

class dls_param_var:
    def __init__(self, pv, delay):
        self.pv = pv
        self.delay = delay

        self.initial_setting = None


class dls_measurement_var:
    def __init__(self, pv, min_counts, delay):
        self.pv = pv
        self.min_counts = min_counts
        self.delay = delay

###################################################  MAIN INTERACTOR FOR BASIC (MACHINE) #############################################

#Many of the functions within this class are used in main.py and the algorithm files. The most important to understand is get_mr

class dls_machine_interactor_bulk_base:

    def __init__(self, param_var_groups=None, measurement_vars=None, set_relative=None):

        self.param_var_groups = param_var_groups
        self.measurement_vars = measurement_vars

        self.param_vars = []
        for group in self.param_var_groups:
            for param in group:
                self.param_vars.append(param)

        if set_relative == None:
            self.set_relative = []

            for i in self.param_var_groups:
                self.set_relative.append(False)

        # If we need to do relative setting, we need the initial values
        if set_relative != None:
            self.initial_values = self.get_mp()
            self.set_relative = set_relative


        ''' We create a dictionary to store the input ap keys, with the output mp values '''
        self.ap_to_mp_store = {}


    def save_details_file(self):
        return save_details_file(self)

    def get_pv(self, pv):
        return abstract_caget(pv)

    def set_pv(self, pv, value):
        caput(pv, value)

    def ap_to_mp(self, aps):

        mps = []

        mpsindex = 0
        for ngroup, group in enumerate(self.param_var_groups):

            for nparam, param in enumerate(group):

                if self.set_relative[ngroup] == True:
                    mps.append(self.initial_values[mpsindex] + aps[ngroup])

                else:
                    mps.append(aps[ngroup])

                mpsindex += 1

        ''' Store this mapping in the ap_to_mp_store dictionary '''
        self.ap_to_mp_store[tuple(aps)] = tuple(mps)
        #print self.ap_to_mp_store

        return mps

    def mp_to_ap(self, mps):

        aps = []

        mpsindex = 0
        for ngroup, group in enumerate(self.param_var_groups):
            print mpsindex
            if self.set_relative[ngroup]:
                aps.append(mps[mpsindex] - self.initial_values[mpsindex])
            elif not self.set_relative[ngroup]:
                aps.append(mps[mpsindex])

            for nparam, param in enumerate(group):
                mpsindex += 1


        print "mps: {0}".format(mps)
        print "aps: {0}".format(aps)
        print "initial values: {0}".format(self.initial_values)

        return aps


    def mr_to_ar(self, mrs):
        return mrs

    def set_mp(self, mps):
        set_params(self.param_vars, mps, caput)

    def get_mp(self):
        mps = []
        for param in self.param_vars:
            print "THIS IS THE PV!: {0}".format(param.pv)
            print type(param.pv)
            print param.pv.encode('ascii', 'ignore')
            print type(param.pv.encode('ascii', 'ignore'))
            mps.append(abstract_caget(param.pv))

        return mps

    def get_mr(self):
        mrs = measure_results(self.measurement_vars, abstract_caget)
        return mrs

    def set_ap(self, aps):
        mps = self.ap_to_mp(aps)
        self.set_mp(mps)

    def get_ap(self):
        mps = self.get_mp()
        aps = self.mp_to_ap(mps)
        return aps

    def get_ar(self):
        mrs = self.get_mr()
        ars = self.mr_to_ar(mrs)
        return ars

    def find_a_bounds(self, param_var_min, param_var_max):

        min_bounds = []
        max_bounds = []

        mpsindex = 0
        for ngroup, group in enumerate(self.param_var_groups):

            if self.set_relative[ngroup]:
                min = None
                max = None

                for param in group:
                    amount_above = param_var_max[mpsindex] - self.initial_values[mpsindex]
                    amount_below = param_var_min[mpsindex] - self.initial_values[mpsindex]

                    if min != None:
                        if amount_below > min:
                            min = amount_below
                    else:
                        min = amount_below

                    if max != None:
                        if amount_above < max:
                            max = amount_above
                    else:
                        max = amount_above

                    mpsindex += 1

            else:
                min = None
                max = None

                for param in group:
                    if min != None:
                        if param_var_min[mpsindex] > min:
                            min = param_var_min[mpsindex]
                    else:
                        min = param_var_min[mpsindex]

                    if max != None:
                        if param_var_max[mpsindex] < max:
                            max = param_var_max[mpsindex]
                    else:
                        max = param_var_max[mpsindex]

                    mpsindex += 1


            min_bounds.append(min)
            max_bounds.append(max)

        print (min_bounds, max_bounds)
        return (min_bounds, max_bounds)

    def string_ap_to_mp_store(self):
        print self.ap_to_mp_store
        return pickle.dumps(self.ap_to_mp_store)

###################################################  MAIN INTERACTOR FOR BASIC (SIMULATION) #############################################

#Many of the functions within this class are used in main.py and the algorithm files. The most important to understand is get_mr.

class sim_machine_interactor_bulk_base:

    def __init__(self, param_var_groups=None, measurement_vars=None, set_relative=None):

        self.param_var_groups = param_var_groups
        self.measurement_vars = measurement_vars

        self.param_vars = []
        for group in self.param_var_groups:
            for param in group:
                self.param_vars.append(param)

        if set_relative == None:
            self.set_relative = []

            for i in self.param_var_groups:
                self.set_relative.append(False)

        # If we need to do relative setting, we need the initial values
        if set_relative != None:
            self.initial_values = self.get_mp()
            self.set_relative = set_relative


        ''' We create a dictionary to store the input ap keys, with the output mp values '''
        self.ap_to_mp_store = {}


    def save_details_file(self):
        return save_details_file(self)

    def get_pv(self, pv):
        return model.caget(pv)

    def set_pv(self, pv, value):
        model.caput(pv, value)

    def ap_to_mp(self, aps):

        mps = []

        mpsindex = 0
        for ngroup, group in enumerate(self.param_var_groups):

            for nparam, param in enumerate(group):

                if self.set_relative[ngroup] == True:
                    mps.append(self.initial_values[mpsindex] + aps[ngroup])

                else:
                    mps.append(aps[ngroup])

                mpsindex += 1

        ''' Store this mapping in the ap_to_mp_store dictionary '''
        self.ap_to_mp_store[tuple(aps)] = tuple(mps)
        #print self.ap_to_mp_store

        return mps

    def mp_to_ap(self, mps):

        aps = []

        mpsindex = 0
        for ngroup, group in enumerate(self.param_var_groups):
            print mpsindex
            if self.set_relative[ngroup]:
                aps.append(mps[mpsindex] - self.initial_values[mpsindex])
            elif not self.set_relative[ngroup]:
                aps.append(mps[mpsindex])

            for nparam, param in enumerate(group):
                mpsindex += 1


        print "mps: {0}".format(mps)
        print "aps: {0}".format(aps)
        print "initial values: {0}".format(self.initial_values)

        return aps


    def mr_to_ar(self, mrs):
        return mrs

    def set_mp(self, mps):
        set_params(self.param_vars, mps, model.caput)

    def get_mp(self):
        mps = []
        for param in self.param_vars:
            mps.append(model.caget(param.pv))

        return mps

    def get_mr(self):
        mrs = measure_results(self.measurement_vars, model.caget)
        return mrs

    def set_ap(self, aps):
        mps = self.ap_to_mp(aps)
        self.set_mp(mps)

    def get_ap(self):
        mps = self.get_mp()
        aps = self.mp_to_ap(mps)
        return aps

    def get_ar(self):
        mrs = self.get_mr()
        ars = self.mr_to_ar(mrs)
        return ars

    def find_a_bounds(self, param_var_min, param_var_max):

        min_bounds = []
        max_bounds = []

        mpsindex = 0
        for ngroup, group in enumerate(self.param_var_groups):

            if self.set_relative[ngroup]:
                min = None
                max = None

                for param in group:
                    amount_above = param_var_max[mpsindex] - self.initial_values[mpsindex]
                    amount_below = param_var_min[mpsindex] - self.initial_values[mpsindex]

                    if min != None:
                        if amount_below > min:
                            min = amount_below
                    else:
                        min = amount_below

                    if max != None:
                        if amount_above < max:
                            max = amount_above
                    else:
                        max = amount_above

                    mpsindex += 1

            else:
                min = None
                max = None

                for param in group:
                    if min != None:
                        if param_var_min[mpsindex] > min:
                            min = param_var_min[mpsindex]
                    else:
                        min = param_var_min[mpsindex]

                    if max != None:
                        if param_var_max[mpsindex] < max:
                            max = param_var_max[mpsindex]
                    else:
                        max = param_var_max[mpsindex]

                    mpsindex += 1


            min_bounds.append(min)
            max_bounds.append(max)

        print (min_bounds, max_bounds)
        return (min_bounds, max_bounds)

    def string_ap_to_mp_store(self):
        print self.ap_to_mp_store
        return pickle.dumps(self.ap_to_mp_store)

######################################################### END OF USEFUL CLASSES/FUNCTIONS ##########################################

# the remaining classes/functions are not used in injection that often and are not important in understanding how the file works.


class dls_machine_interactor_base:

    def __init__(self, param_vars, measurement_vars):
        self.param_vars = param_vars
        self.measurement_vars = measurement_vars

    def save_details_file(self):
        return save_details_file(self)


    def ap_to_mp(self, aps):
        return aps

    def mr_to_ar(self, mrs):
        return mrs

    def set_mp(self, mps):
        set_params(self.param_vars, mps, caput)

    def get_mp(self):
        mps = []
        for i in self.param_vars:
            print i.pv
            mps.append(abstract_caget(i.pv))

        return mps

    def get_mr(self):
        mrs = measure_results(self.measurement_vars, abstract_caget)
        return mrs

    def set_ap(self, aps):
        mps = self.ap_to_mp(aps)
        self.set_mp(mps)

    def get_ar(self):
        mrs = self.get_mr()
        ars = self.mr_to_ar(mrs)
        return ars

    def set_get_a(self, aps):
        self.set_ap(aps)
        ars = self.get_ar()
        return ars



class sim_machine_interactor_base:

    def __init__(self, param_vars, measurement_vars):
        self.param_vars = param_vars
        self.measurement_vars = measurement_vars

    def save_details_file(self):
        return save_details_file(self)


    def ap_to_mp(self, aps):
        return aps

    def mr_to_ar(self, mrs):
        return mrs

    def set_mp(self, mps):
        set_params(self.param_vars, mps, model.caput)

    def get_mp(self):
        mps = []
        for i in self.param_vars:
            print i.pv
            mps.append(model.caget(i.pv))

        return mps

    def get_mr(self):
        mrs = measure_results(self.measurement_vars, model.caget)
        return mrs

    def set_ap(self, aps):
        mps = self.ap_to_mp(aps)
        self.set_mp(mps)

    def get_ar(self):
        mrs = self.get_mr()
        ars = self.mr_to_ar(mrs)
        return ars

    def set_get_a(self, aps):
        self.set_ap(aps)
        ars = self.get_ar()
        return ars



class dls_machine_interactor_bulk_base_inj_control:

    def __init__(self, param_var_groups=None, measurement_vars_noinj=None, measurement_vars_inj=None, set_relative=None):

        self.param_var_groups = param_var_groups
        self.measurement_vars_noinj = measurement_vars_noinj
        self.measurement_vars_inj = measurement_vars_inj


        self.param_vars = []
        for group in self.param_var_groups:
            for param in group:
                self.param_vars.append(param)

        if set_relative == None:
            self.set_relative = []

            for i in self.param_var_groups:
                self.set_relative.append(False)

        # If we need to do relative setting, we need the initial values
        if set_relative != None:
            self.initial_values = self.get_mp()
            self.set_relative = set_relative


        ''' We create a dictionary to store the input ap keys, with the output mp values '''
        self.ap_to_mp_store = {}


    def save_details_file(self):
        return save_details_file(self)

    def get_pv(self, pv):
        return abstract_caget(pv)

    def set_pv(self, pv, value):
        caput(pv, value)

    def ap_to_mp(self, aps):

        mps = []

        mpsindex = 0
        for ngroup, group in enumerate(self.param_var_groups):

            for nparam, param in enumerate(group):

                if self.set_relative[ngroup] == True:
                    mps.append(self.initial_values[mpsindex] + aps[ngroup])

                else:
                    mps.append(aps[ngroup])

                mpsindex += 1

        ''' Store this mapping in the ap_to_mp_store dictionary '''
        self.ap_to_mp_store[tuple(aps)] = tuple(mps)
        #print self.ap_to_mp_store

        return mps

    def mp_to_ap(self, mps):

        aps = []

        mpsindex = 0
        for ngroup, group in enumerate(self.param_var_groups):
            print mpsindex
            if self.set_relative[ngroup]:
                aps.append(mps[mpsindex] - self.initial_values[mpsindex])
            elif not self.set_relative[ngroup]:
                aps.append(mps[mpsindex])

            for nparam, param in enumerate(group):
                mpsindex += 1


        print "mps: {0}".format(mps)
        print "aps: {0}".format(aps)
        print "initial values: {0}".format(self.initial_values)

        return aps


    def mr_to_ar(self, mrs):
        return mrs

    def set_mp(self, mps):
        set_params(self.param_vars, mps, caput)

    def get_mp(self):
        mps = []
        for param in self.param_vars:
            mps.append(abstract_caget(param.pv))

        return mps

    # This should be the only method we need to modify for injection control
    def get_mr(self):
        #mrs = measure_results(self.measurement_vars, model.abstract_caget)

        average_inj = [0] * len(self.measurement_vars_inj)
        counts_inj = [0] * len(self.measurement_vars_inj)
        dev_inj = [0] * len(self.measurement_vars_inj)

        average_noinj = [0] * len(self.measurement_vars_noinj)
        counts_noinj = [0] * len(self.measurement_vars_noinj)
        dev_noinj = [0] * len(self.measurement_vars_noinj)

        ''' Final ones '''
        #average = [0] * len(measurement_vars)
        #counts = [0] * len(measurement_vars)
        #dev = [0] * len(measurement_vars)

        get_command = abstract_caget

        run = True
        start_time = time.time()

        ''' First measure the injection results '''
        # Begin injecting
        print "Start injection"
        #caput('LI-TI-MTGEN-01:START', 1)
        cothread.Sleep(0.1)
        #caput('LI-TI-MTGEN-01:START', 0)
        cothread.Sleep(1)

        run = True
        start_time = time.time()

        while run:
            # Check whether to make any measurements
            for i in range(len(self.measurement_vars_inj)):
                # If the time since start is > the measurement delay * number of times its been counted, then
                if (time.time() - start_time) > (self.measurement_vars_inj[i].delay * counts_inj[i]):
                    print "Measuring {0}".format(self.measurement_vars_inj[i].pv)
                    value = get_command(self.measurement_vars_inj[i].pv)
                    average_inj[i] += value
                    counts_inj[i] += 1
                    dev_inj[i] += value ** 2

            # Check if finished
            run = False
            for i in range(len(self.measurement_vars_inj)):
                # If the number counted is less than that required, then carry on, else you can stop
                if counts_inj[i] < self.measurement_vars_inj[i].min_counts:
                    run = True

        average_inj = [average_inj[i]/counts_inj[i] for i in range(len(average_inj))]
        dev_inj = [(dev_inj[i]/counts_inj[i]) - average_inj[i]**2 for i in range(len(average_inj))]
        err_inj = [(dev_inj[i])/(math.sqrt(counts_inj[i])) for i in range(len(average_inj))]

        # Return results back to the optimiser
        #return average We would previously just return the number. Now we will return a measurement object
        results_inj = []
        for i in range(len(average_inj)):
            results_inj.append(measurement(mean=average_inj[i], counts=counts_inj[i], dev=dev_inj[i], err=err_inj[i]))

        ''' Now for the non-injection measurements '''
        # Stop injection
        print "Stop injection"
        caput('LI-TI-MTGEN-01:STOP', 1)
        cothread.Sleep(0.1)
        caput('LI-TI-MTGEN-01:STOP', 0)
        cothread.Sleep(1)


        run = True
        start_time = time.time()

        while run:
            # Check whether to make any measurements
            for i in range(len(self.measurement_vars_noinj)):
                # If the time since start is > the measurement delay * number of times its been counted, then
                if (time.time() - start_time) > (self.measurement_vars_noinj[i].delay * counts_noinj[i]):
                    print "Measuring {0}".format(self.measurement_vars_noinj[i].pv)
                    value = get_command(self.measurement_vars_noinj[i].pv)
                    average_noinj[i] += value
                    counts_noinj[i] += 1
                    dev_noinj[i] += value ** 2

            # Check if finished
            run = False
            for i in range(len(self.measurement_vars_noinj)):
                # If the number counted is less than that required, then carry on, else you can stop
                if counts_noinj[i] < self.measurement_vars_noinj[i].min_counts:
                    run = True

        average_noinj = [average_noinj[i]/counts_noinj[i] for i in range(len(average_noinj))]
        dev_noinj = [(dev_noinj[i]/counts_noinj[i]) - average_noinj[i]**2 for i in range(len(average_noinj))]
        err_noinj = [(dev_noinj[i])/(math.sqrt(counts_noinj[i])) for i in range(len(average_noinj))]

        # Return results back to the optimiser
        #return average We would previously just return the number. Now we will return a measurement object
        results_noinj = []
        for i in range(len(average_noinj)):
            results_noinj.append(measurement(mean=average_noinj[i], counts=counts_noinj[i], dev=dev_noinj[i], err=err_noinj[i]))



        ''' Now combine the results into a single list '''

        results = results_noinj + results_inj

        mrs = results

        return mrs

    def set_ap(self, aps):
        mps = self.ap_to_mp(aps)
        self.set_mp(mps)

    def get_ap(self):
        mps = self.get_mp()
        aps = self.mp_to_ap(mps)
        return aps

    def get_ar(self):
        mrs = self.get_mr()
        ars = self.mr_to_ar(mrs)
        return ars

    def find_a_bounds(self, param_var_min, param_var_max):

        min_bounds = []
        max_bounds = []

        mpsindex = 0
        for ngroup, group in enumerate(self.param_var_groups):

            if self.set_relative[ngroup]:
                min = None
                max = None

                for param in group:
                    amount_above = param_var_max[mpsindex] - self.initial_values[mpsindex]
                    amount_below = param_var_min[mpsindex] - self.initial_values[mpsindex]

                    if min != None:
                        if amount_below > min:
                            min = amount_below
                    else:
                        min = amount_below

                    if max != None:
                        if amount_above < max:
                            max = amount_above
                    else:
                        max = amount_above

                    mpsindex += 1

            else:
                min = None
                max = None

                for param in group:
                    if min != None:
                        if param_var_min[mpsindex] > min:
                            min = param_var_min[mpsindex]
                    else:
                        min = param_var_min[mpsindex]

                    if max != None:
                        if param_var_max[mpsindex] < max:
                            max = param_var_max[mpsindex]
                    else:
                        max = param_var_max[mpsindex]

                    mpsindex += 1


            min_bounds.append(min)
            max_bounds.append(max)

        print (min_bounds, max_bounds)
        return (min_bounds, max_bounds)

    def string_ap_to_mp_store(self):
        print self.ap_to_mp_store
        return pickle.dumps(self.ap_to_mp_store)


class sim_machine_interactor_bulk_base_inj_control:

    def __init__(self, param_var_groups=None, measurement_vars_noinj=None, measurement_vars_inj=None, set_relative=None):

        self.param_var_groups = param_var_groups
        self.measurement_vars_noinj = measurement_vars_noinj
        self.measurement_vars_inj = measurement_vars_inj


        self.param_vars = []
        for group in self.param_var_groups:
            for param in group:
                self.param_vars.append(param)

        if set_relative == None:
            self.set_relative = []

            for i in self.param_var_groups:
                self.set_relative.append(False)

        # If we need to do relative setting, we need the initial values
        if set_relative != None:
            self.initial_values = self.get_mp()
            self.set_relative = set_relative


        ''' We create a dictionary to store the input ap keys, with the output mp values '''
        self.ap_to_mp_store = {}


    def save_details_file(self):
        return save_details_file(self)

    def get_pv(self, pv):
        return model.caget(pv)

    def set_pv(self, pv, value):
        model.caput(pv, value)

    def ap_to_mp(self, aps):

        mps = []

        mpsindex = 0
        for ngroup, group in enumerate(self.param_var_groups):

            for nparam, param in enumerate(group):

                if self.set_relative[ngroup] == True:
                    mps.append(self.initial_values[mpsindex] + aps[ngroup])

                else:
                    mps.append(aps[ngroup])

                mpsindex += 1

        ''' Store this mapping in the ap_to_mp_store dictionary '''
        self.ap_to_mp_store[tuple(aps)] = tuple(mps)
        #print self.ap_to_mp_store

        return mps

    def mp_to_ap(self, mps):

        aps = []

        mpsindex = 0
        for ngroup, group in enumerate(self.param_var_groups):
            print mpsindex
            if self.set_relative[ngroup]:
                aps.append(mps[mpsindex] - self.initial_values[mpsindex])
            elif not self.set_relative[ngroup]:
                aps.append(mps[mpsindex])

            for nparam, param in enumerate(group):
                mpsindex += 1


        print "mps: {0}".format(mps)
        print "aps: {0}".format(aps)
        print "initial values: {0}".format(self.initial_values)

        return aps


    def mr_to_ar(self, mrs):
        return mrs

    def set_mp(self, mps):
        set_params(self.param_vars, mps, model.caput)

    def get_mp(self):
        mps = []
        for param in self.param_vars:
            mps.append(model.caget(param.pv))

        return mps

    # This should be the only method we need to modify for injection control
    def get_mr(self):
        #mrs = measure_results(self.measurement_vars, model.caget)

        average_inj = [0] * len(self.measurement_vars_inj)
        counts_inj = [0] * len(self.measurement_vars_inj)
        dev_inj = [0] * len(self.measurement_vars_inj)

        average_noinj = [0] * len(self.measurement_vars_noinj)
        counts_noinj = [0] * len(self.measurement_vars_noinj)
        dev_noinj = [0] * len(self.measurement_vars_noinj)

        ''' Final ones '''
        #average = [0] * len(measurement_vars)
        #counts = [0] * len(measurement_vars)
        #dev = [0] * len(measurement_vars)

        get_command = model.caget

        run = True
        start_time = time.time()

        ''' First measure the injection results '''
        # Begin injecting
        print "Start injection"
        #caput('LI-TI-MTGEN-01:START', 1)
        cothread.Sleep(0.1)
        #caput('LI-TI-MTGEN-01:START', 0)
        cothread.Sleep(1)

        run = True
        start_time = time.time()

        while run:
            # Check whether to make any measurements
            for i in range(len(self.measurement_vars_inj)):
                # If the time since start is > the measurement delay * number of times its been counted, then
                if (time.time() - start_time) > (self.measurement_vars_inj[i].delay * counts_inj[i]):
                    print "Measuring {0}".format(self.measurement_vars_inj[i].pv)
                    value = get_command(self.measurement_vars_inj[i].pv)
                    average_inj[i] += value
                    counts_inj[i] += 1
                    dev_inj[i] += value ** 2

            # Check if finished
            run = False
            for i in range(len(self.measurement_vars_inj)):
                # If the number counted is less than that required, then carry on, else you can stop
                if counts_inj[i] < self.measurement_vars_inj[i].min_counts:
                    run = True

        average_inj = [average_inj[i]/counts_inj[i] for i in range(len(average_inj))]
        dev_inj = [(dev_inj[i]/counts_inj[i]) - average_inj[i]**2 for i in range(len(average_inj))]
        err_inj = [(dev_inj[i])/(math.sqrt(counts_inj[i])) for i in range(len(average_inj))]

        # Return results back to the optimiser
        #return average We would previously just return the number. Now we will return a measurement object
        results_inj = []
        for i in range(len(average_inj)):
            results_inj.append(measurement(mean=average_inj[i], counts=counts_inj[i], dev=dev_inj[i], err=err_inj[i]))

        ''' Now for the non-injection measurements '''
        # Stop injection
        print "Stop injection"
        #caput('LI-TI-MTGEN-01:STOP', 1)
        cothread.Sleep(0.1)
        #caput('LI-TI-MTGEN-01:STOP', 0)
        cothread.Sleep(1)


        run = True
        start_time = time.time()

        while run:
            # Check whether to make any measurements
            for i in range(len(self.measurement_vars_noinj)):
                # If the time since start is > the measurement delay * number of times its been counted, then
                if (time.time() - start_time) > (self.measurement_vars_noinj[i].delay * counts_noinj[i]):
                    print "Measuring {0}".format(self.measurement_vars_noinj[i].pv)
                    value = get_command(self.measurement_vars_noinj[i].pv)
                    average_noinj[i] += value
                    counts_noinj[i] += 1
                    dev_noinj[i] += value ** 2

            # Check if finished
            run = False
            for i in range(len(self.measurement_vars_noinj)):
                # If the number counted is less than that required, then carry on, else you can stop
                if counts_noinj[i] < self.measurement_vars_noinj[i].min_counts:
                    run = True

        average_noinj = [average_noinj[i]/counts_noinj[i] for i in range(len(average_noinj))]
        dev_noinj = [(dev_noinj[i]/counts_noinj[i]) - average_noinj[i]**2 for i in range(len(average_noinj))]
        err_noinj = [(dev_noinj[i])/(math.sqrt(counts_noinj[i])) for i in range(len(average_noinj))]

        # Return results back to the optimiser
        #return average We would previously just return the number. Now we will return a measurement object
        results_noinj = []
        for i in range(len(average_noinj)):
            results_noinj.append(measurement(mean=average_noinj[i], counts=counts_noinj[i], dev=dev_noinj[i], err=err_noinj[i]))



        ''' Now combine the results into a single list '''

        results = results_noinj + results_inj

        mrs = results

        return mrs

    def set_ap(self, aps):
        mps = self.ap_to_mp(aps)
        self.set_mp(mps)

    def get_ap(self):
        mps = self.get_mp()
        aps = self.mp_to_ap(mps)
        return aps

    def get_ar(self):
        mrs = self.get_mr()
        ars = self.mr_to_ar(mrs)
        return ars

    def find_a_bounds(self, param_var_min, param_var_max):

        min_bounds = []
        max_bounds = []

        mpsindex = 0
        for ngroup, group in enumerate(self.param_var_groups):

            if self.set_relative[ngroup]:
                min = None
                max = None

                for param in group:
                    amount_above = param_var_max[mpsindex] - self.initial_values[mpsindex]
                    amount_below = param_var_min[mpsindex] - self.initial_values[mpsindex]

                    if min != None:
                        if amount_below > min:
                            min = amount_below
                    else:
                        min = amount_below

                    if max != None:
                        if amount_above < max:
                            max = amount_above
                    else:
                        max = amount_above

                    mpsindex += 1

            else:
                min = None
                max = None

                for param in group:
                    if min != None:
                        if param_var_min[mpsindex] > min:
                            min = param_var_min[mpsindex]
                    else:
                        min = param_var_min[mpsindex]

                    if max != None:
                        if param_var_max[mpsindex] < max:
                            max = param_var_max[mpsindex]
                    else:
                        max = param_var_max[mpsindex]

                    mpsindex += 1


            min_bounds.append(min)
            max_bounds.append(max)

        print (min_bounds, max_bounds)
        return (min_bounds, max_bounds)

    def string_ap_to_mp_store(self):
        print self.ap_to_mp_store
        return pickle.dumps(self.ap_to_mp_store)


class measurement:

    def __init__(self, name=None, mean=None, dev=None, counts=None, err=None):
        self.name = name
        self.mean = mean
        self.dev = dev
        self.counts = counts
        self.err = err

    def __neg__(self):
        result = self
        result.mean = - result.mean

        return result

    def __pos__(self):
        return self

    def __add__(self, other):
        result = measurement()
        result.mean = self.mean + other.mean

        return result

    def __sub__(self, other):
        result = measurement()
        result.mean = self.mean - other.mean

        return result

    def __mul__(self, other):
        result = measurement()
        result.mean = self.mean * other.mean

        return result

    def __div__(self, other):
        result = measurement()
        result.mean = self.mean / other.mean

        return result

    def __iadd__(self, other):
        result = measurement.__add__(self, other)

        return result

    def __isub__(self, other):
        result = measurement.__sub__(self, other)

        return result

    def __imul__(self, other):
        result = measurement.__mul__(self, other)

        return result

    def __idiv__(self, other):
        result = measurement.__div__(self, other)

        return result

    def __lt__(self, other):
        result = False

        if self.mean < other.mean:
            result = True

        return result

    def __le__(self, other):
        result = False

        if self.mean <= other.mean:
            result = True

        return result

    def __eq__(self, other):
        result = False

        if self.mean == other.mean:
            result = True

        return result

    def __ne__(self, other):
        result = False

        if self.mean != other.mean:
            result = True

        return result

    def __ge__(self, other):
        result = False

        if self.mean >= other.mean:
            result = True

        return result

    def __gt__(self, other):
        result = False

        if self.mean > other.mean:
            result = True

        return result
