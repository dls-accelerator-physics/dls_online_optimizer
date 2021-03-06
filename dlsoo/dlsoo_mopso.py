'''
MULTI-OBJECTIVE PARTICLE SWARM OPTIMISER for use in the DLS OnlineOptimiser package.
Created on 7 Jul 2017
@author: James Rogers
'''


import random
import os

import Tkinter
import ttk

from scipy import spatial
from dlsoo import plot

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2TkAgg
from matplotlib.figure import Figure

#------------------------------------------------------GLOBAL VARIABLES AND USEFUL FUNCTIONS-------------------------------------------------------#

store_address = None                         #directory in which output data will be stored
completed_iteration = 0                      #number of completed iterations
completed_percentage = 0.0                   #fraction of optimisation completed
pareto_front = ()                            #current pareto-front with the format (((param1,param2,...),(obj1,obj2,...),(err1,err2,...)),...)


def nothing_function(data):
    pass


class Optimiser(object):

    def __init__(self, settings_dict, interactor, store_location, a_min_var, a_max_var, progress_handler=None):

        self.interactor = interactor                                                       #interactor with dls_optimiser_util.py
        self.store_location = store_location                                               #location for output files
        self.swarm_size = settings_dict['swarm_size']                                      #number of particles in swarm
        self.max_iter = settings_dict['max_iter']                                          #number of iterations of algorithm
        self.param_count = len(interactor.param_var_groups)                                #number of parameters being varied
        self.result_count = len(interactor.measurement_vars)                               #number of objectives being measured
        self.min_var = a_min_var                                                           #minimum values of parameters
        self.max_var = a_max_var                                                           #minimum values of parameters
        self.inertia = settings_dict['inertia']                                            #inertia of particles in swarm
        self.social_param = settings_dict['social_param']                                  #social parameter for particles in swarm
        self.cognitive_param = settings_dict['cognitive_param']                            #cognitive parameter for particles in swarm

        if progress_handler == None:
            progress_handler = nothing_function

        self.progress_handler = progress_handler                                           #window that shows progress plots

        self.pause = False                                                                 #Pause and Cancel functions during optimisation
        self.cancel = False

        self.add_current_to_individuals = settings_dict['add_current_to_individuals']      #gives user ability to set current machine status to initial point
        if self.add_current_to_individuals == True:
            self.initParams = interactor.get_ap()
        else:
            self.initParams = []

        print "interactor.param_var_groups: {0}".format(interactor.param_var_groups)
        print "interactor.measurement_vars: {0}".format(interactor.measurement_vars)

    def save_details_file(self):
        """
        Function writes a file containing details of algorithm run
        """
        file_return = ""

        file_return += "dlsoo_mopso.py algorithm\n"
        file_return += "=================\n\n"
        file_return += "Iterations: {0}\n".format(self.max_iter)
        file_return += "Swarm size: {0}\n\n".format(self.swarm_size)
        file_return += "Parameter count: {0}\n".format(self.param_count)
        file_return += "Results count: {0}\n\n".format(self.result_count)
        file_return += "Minimum bounds: {0}\n".format(self.min_var)
        file_return += "Maximum bounds: {0}\n\n".format(self.max_var)
        file_return += "Particle Inertia: {0}\n".format(self.inertia)
        file_return += "Social Parameter: {0}\n".format(self.social_param)
        file_return += "Cognitive Parameter: {0}\n".format(self.cognitive_param)

        return file_return


    def evaluate_swarm(self, swarm):
        """
        Function measures the objective functions for an entire swarm.

        Args:
            swarm: list of Particle instances ready for measurement.

        Returns:
            results: list of calculated results for each Particle instance
            errors: list of calculated errors for each Particle instance measurement
        """

        global completed_percentage
        global completed_iteration

        percentage_interval = (1./self.max_iter)/self.swarm_size                      #calculate percentage update per measurement
        results = []
        errors = []
        stand_div = []

        for i in range(len(swarm)):

            self.interactor.set_ap(swarm[i].position_i)                               #configure machine for measurement
            all_data = self.interactor.get_ar()                                              #perform measuremen
            all_results = [i.mean for i in all_data]                                  #retrieve mean from measurement
            all_errors = [i.err for i in all_data]                                    #retrieve error from measurement
            all_std = [i.dev for i in all_data]	                                       #retrieve the std from measurement - rhs 13/07/18

            results.append(all_results)
            errors.append(all_errors)
            stand_div.append(all_std)                                                       #rhs 13/07/18
            #if std == errors:
            #print "std = err!"
            completed_percentage += percentage_interval                               #update percentage bar on progress plot
            print completed_percentage*100,'%'

            self.progress_handler(completed_percentage, completed_iteration)

            while self.pause:                                                         #keep update bar if algorithm paused
                self.progress_handler(completed_percentage, completed_iteration)

            if self.cancel:
                break


        return results, errors, stand_div


    def dump_fronts(self, fronts, iteration):
        """
        Function dumps data of current front in file in output directory e.g. fronts.1 will contain the first front calculated.

        Args:
            fronts: pareto-front to be dumped
            iteration: current iteration number
        Returns:
            None
        """
        f = file("{0}/FRONTS/fronts.{1}".format(self.store_location, iteration), "w")             #open file
        f.write("fronts = ((\n")
        for i, data in enumerate(fronts):
            f.write("    ({0}, {1}, {2}, {3}),\n".format(data[0], tuple(data[1]), data[2], data[3]))               #insert each solution in front  --rhs added 3rd data for std 13/07/18
        f.write("),)\n")
        f.close()                                                                                 #close file

        pass


    def pareto_remover(self,a,b):
        """
        Function determines which of two points is the dominant in objective space.

        Args:
            a: list of objective values [obj1,obj2,...]
            b: list of objective values [obj1,obj2,...]

        Returns:
            Function will return the point that dominates the other. If neither dominates, return is False.
        """
        if all(a_i > b_i for (a_i,b_i) in zip(a,b)):         #does a dominate b?
            return a
        if all(a_i < b_i for (a_i,b_i) in zip(a,b)):         #does b dominate b?
            return b
        if all(a_i == b_i for (a_i,b_i) in zip(a,b)):        #are the points the same?
            return b
        else:
            return False

    def get_pareto_objectives(self, swarm):
        """
        Returns a list of objectives from front like list

        Args:
            swarm: list of solutions in the format (((param1,param2,...),(obj1,obj2,...),(err1,err2,...)),...).

        Returns:
            list of objectives in the format [(obj1,obj2,...),(obj1,obj2,...),...]
        """
        objectives = [particle[1] for particle in swarm]
        return objectives


    def pareto_test(self,a,b):
        """
        Determines whether a solution should remain in a pareto front.

        Args:
            a: list of objective values [obj1,obj2,...].
            b: list of objective values [obj1,obj2,...].

        Returns:
            False if a dominates b.
            True if both a and b are non-dominant.
        """
        if all(a_i > b_i for (a_i,b_i) in zip(a,b)):    #does a dominate b for all objectives?
            return False
        else:
            return True


    def find_pareto_front(self,swarm):
        """
        For a given swarm of solutions, this function will determine the non-dominant set and update the pareto-front.

        Args:
            swarm: set of solutions in the form (((param1,param2,...),(obj1,obj2,...),(err1,err2,...)),...).

        Returns:
            None, but updates the global variable pareto_front with the new non-dominant solutions.
        """
        global pareto_front
        current_swarm = list(self.get_pareto_objectives(swarm))
        indices_to_delete = []

        for i in range(len(current_swarm)):                                                      #cycle through swarm and compare objectives
            for j in range(len(current_swarm)):

                if i==j:                                                                         #no need to compare solution with itself
                    continue

                particle_to_remove = self.pareto_remover(current_swarm[i], current_swarm[j])     #determine which solution is dominant

                if particle_to_remove == False:                                                  #if neither are dominant, leave both in front
                    continue
                else:
                    indices_to_delete.append(current_swarm.index(particle_to_remove))            #store index of solution if it is dominant

        indices_to_delete = sorted(set(indices_to_delete), reverse=True)
        for i in indices_to_delete:                                                              #remove dominating solutions
            del swarm[i]
        pareto_front = list(swarm)                                                               #update global pareto_front


    def normalised_front(self, front):
        """
        For a given front in objective space, this function will normalise the front to a unit square

        Args:
            front: a list of objectives for all solutions in front

        Returns:
            front_norm: a list of normalised (0.0-->1.0) objective coords
        """

        front_x = [i[0] for i in front]
        front_y = [i[1] for i in front]

        max_x = max(front_x)
        max_y = max(front_y)

        min_x = min(front_x)
        min_y = min(front_y)

        x_norm = [(i-min_x)/(max_x-min_x) for i in front_x]
        y_norm = [(i-min_y)/(max_y-min_y) for i in front_y]

        front_norm = zip(x_norm,y_norm)
        return front_norm


    def get_leader_roulette_wheel(self):
        """
        Function that produces a roulette wheel selection list for solutions in pareto-front

        Args:
            None

        Returns;
            roulette_wheel: list of roulette wheel probabilities proportional to isolation of solution on front
        """
        global pareto_front

        if len(pareto_front) < 2:
            return []
        pareto_obj = self.get_pareto_objectives(pareto_front)
        swarm_size = len(pareto_obj)
        normalised_front = self.normalised_front(pareto_obj)
        kd_tree = spatial.KDTree(normalised_front)                                               #creates a KD tree for all solutions in normalised front
        #this is the line ^^^ that slows the algorithm down for LARGE PARETO FRONTS
        density = [len(kd_tree.query_ball_point(x=i, r=0.05))-1 for i in normalised_front]       #find nearest neighbours within 0.05 in normalised space
        density_sum = sum(density)

        if density_sum == 0:
            inv_density = [1 for i in range(swarm_size)]
        else:
            inv_density = [density_sum-i for i in density]

        inv_density_size = sum(inv_density)

        roulette_wheel = [inv_density[0]/inv_density_size]
        for i in range(1,swarm_size):
            cumulative_prob = roulette_wheel[i-1] + inv_density[i]/inv_density_size             #calculate cumulative sum of probabilities for each solution in front
            roulette_wheel.append(cumulative_prob)
        return roulette_wheel


    def evaluate(self, swarm, initial_evaluation=False):
        """
        Function evaluates objectives for the swarm and updates best positions for each particle instance

        Args:
            swarm: list of Particle instances
            initial_evaluation: this should be True if this is the first iteration.

        Returns:
            None, but updates all particle best locations in objective space for next iteration.
        """

        objectives, errors, stand_div = self.evaluate_swarm(swarm)                                    #obtain objective measurements, errors and std for all particles.  ---rhs 13/07/18
        for i in range(len(swarm)):

            if self.cancel:
                break

            swarm[i].fit_i = objectives[i]                                                 #update current objective fit.
            swarm[i].error = errors[i]	                                                    #update current objective error.
            swarm[i].stand_div = stand_div[i]                                             #rhs 13/07/18

            if initial_evaluation==False:
                if self.pareto_test(swarm[i].fit_i,swarm[i].fit_best_i) == True:           #check if this objective fit is a personal best for the particle.
                    swarm[i].pos_best_i = swarm[i].position_i
                    swarm[i].fit_best_i = swarm[i].fit_i

            if initial_evaluation==True:                                                   #for the first iteration, the fit will be the personal best.
                swarm[i].fit_best_i = swarm[i].fit_i
                swarm[i].pos_best_i = swarm[i].position_i



    def optimise(self):
        """
        This function runs the optimisation algorithm. It initialises the swarm and then takes successive measurements whilst
        updating the location of the swarm. It also updates the pareto-front archive after each iteration.

        Args:
            None

        Returns:
            None, but the pareto-front archive will have been updated with the non-dominating front.
        """

        global store_address
        global pareto_front
        global completed_iteration
        global completed_percentage
        store_address = self.store_location





        swarm = []
        for i in range(0, self.swarm_size):                                                       #initialise the swarm
            swarm.append(Particle(self.param_count, self.min_var, self.max_var))

        if self.add_current_to_individuals:                                                       #can have current machine status as one of the swarm's initial location
            current_ap = self.interactor.get_ap()
            swarm[0].choose_position(current_ap)

        self.evaluate(swarm, initial_evaluation=True)                                             #evaluate the swarm
        proposed_pareto = [[j.position_i,j.fit_i,j.error, j.stand_div] for j in swarm]                         #define the front for sorting
        self.find_pareto_front(proposed_pareto)                                                   #find the non-dominating set
        front_to_dump = tuple(list(pareto_front))
        self.dump_fronts(front_to_dump, 0)                                                        #dump new front in file
        completed_iteration = 1
        self.progress_handler(completed_percentage, completed_iteration)                          #update progress window with new front + percentage



        for t in range(1,self.max_iter):                                                          #begin iteration
            leader_roullete_wheel = self.get_leader_roulette_wheel()                              #calculate leader roulette wheel for the swarm

            for j in range(0, self.swarm_size):                                                   #for every particle:
                swarm[j].select_leader(leader_roullete_wheel)                                     #select leader
                swarm[j].update_velocity(self.inertia, self.social_param, self.cognitive_param)   #update velocity
                swarm[j].update_position()                                                        #update position

            self.evaluate(swarm)                                                                  #evaluate new positions

            if self.cancel:
                break

            proposed_pareto = [[j.position_i,j.fit_i,j.error, j.stand_div] for j in swarm] + pareto_front      #define front for sorting
            self.find_pareto_front(proposed_pareto)                                               #find the non-dominating set
            front_to_dump = list(pareto_front)
            self.dump_fronts(front_to_dump, t)                                                    #dump new front in file

            completed_iteration += 1                                                              #track iteration number

        print "OPTIMISATION COMPLETE"

#--------------------------------------------------------- PARTICLE CLASS FOR INITIALISING PARTICLE OBJECTS --------------------------------------------#

class Particle:

    def __init__(self, num_parameter, par_min, par_max):

        self.position_i = tuple([random.uniform(par_min[i],par_max[i]) for i in range(num_parameter)])        #particle's position
        self.velocity_i = tuple([random.uniform(par_min[i],par_max[i]) for i in range(num_parameter)])        #particle's velocity
        self.pos_best_i = ()                                                                                  #particle's best position
        self.leader_i = ()                                                                                    #particle's leader
        self.fit_i = ()                                                                                       #particle's fit
        self.fit_best_i = ()                                                                                  #particle's best fit
        self.bounds = (par_min, par_max)                                                                      #particle's parameter bounds
        self.error = ()                                                                                       #particle's error in fit
        self.std = ()                                                                                         #particles std in fit     --- rhs

    def update_velocity(self, inertia, social_param, cog_param):
        """
        Function updates particle velocity according to particle swarm velocity equation.

        Args:
            inertia: inertia parameter gives particles mass (float type).
            social_param: social parameter give particles an attraction to swarm's best locations (float type).
            cog_param: cognitive parameter gives a particle an attraction to its own best location.

        Returns:
            None, but updates the particle's velocity attribute.
        """
        new_velocity = list(self.velocity_i)

        for i in range(0, len(self.bounds[0])):                                                        #new velocity in each parameter dimension

            r1 = random.random()                                                                       #random numbers between [-1,1] for random-walk nature of code
            r2 = random.random()

            velocity_cognitive = cog_param * r1 * (self.pos_best_i[i] - self.position_i[i])            #calculate cognitive velocity term
            velocity_social = social_param * r2 * (self.leader_i[i] - self.position_i[i])              #calculate social velocity term

            new_velocity[i] = inertia*new_velocity[i] + velocity_cognitive + velocity_social           #calculate new velocity

        self.velocity_i = tuple(new_velocity)                                                          #update particle  velocity attribute


    def update_position(self):
        """
        Function updates particle position according to particle swarm position equation.

        Args:
            None

        Returns:
            None, but updates the particle's position.
        """
        new_position = list(self.position_i)
        new_velocity = list(self.velocity_i)
        for i in range(0,len(self.bounds[0])):                                                         #new position in each parameter dimension
            new_position[i]= new_position[i] + self.velocity_i[i]                                      #calculate new position

            if new_position[i] > self.bounds[1][i]:                                                    #reflect if particle goes beyond upper bounds
                new_position[i] = self.bounds[1][i]
                new_velocity[i] = -1 * new_velocity[i]

            if new_position[i] < self.bounds[0][i]:                                                    #reflect if particle goes below lower bounds
                new_position[i] = self.bounds[0][i]
                new_velocity[i] = -1 * new_velocity[i]

        self.velocity_i = tuple(new_velocity)                                                          #update particle velocity attribute
        self.position_i = tuple(new_position)                                                          #update particle position attribu

    def choose_position(self, x0):
        """
        Function that allows a specific particle in swarm to have a specific location (used for 'use current' option)

        Args:
            coords of new position in parameter space

        Returns:
            None, but updates positions of particle
        """
        self.position_i = tuple(x0)

    def select_leader(self, roulette_wheel):
        """
        Selects a leader from Pareto front for Particle instance

        Args:
            roullete_wheel: see get_leader_roullete_wheel function in Optimiser class

        Returns:
            None, but updates the leader of the Particle instance
        """
        global pareto_front
        if len(pareto_front) < len(pareto_front[0][1]) +1:
            self.leader_i = random.choice(pareto_front)[0]
            return

        r = random.random()
        for i in range(len(pareto_front)):
            if r <= roulette_wheel[i]:
                self.leader_i = pareto_front[i][0]
            else:
                self.leader_i = random.choice(pareto_front)[0]

#------------------------------------------------------------ CLASS FOR MOPSO SETTINGS WNDOW --------------------------------------------------------#

class import_algo_frame(Tkinter.Frame):
    """
    This class produces the MOPSO options window that appears after defining parameters, objectives etc.
    """

    def __init__(self, parent):

        Tkinter.Frame.__init__(self, parent)

        self.parent = parent

        self.initUi()

    def initUi(self):
        """
        This initialises the GUI for this window, including text entries for each algorithm option
        """

        self.add_current_to_individuals = Tkinter.BooleanVar(self)
        self.add_current_to_individuals.set(True)

        Tkinter.Label(self, text="Swarm size:").grid(row=0, column=0, sticky=Tkinter.E)
        self.i0 = Tkinter.Entry(self)
        self.i0.grid(row=0, column=1, sticky=Tkinter.E+Tkinter.W)

        Tkinter.Label(self, text="Max. iterations:").grid(row=1, column=0, sticky=Tkinter.E)
        self.i1 = Tkinter.Entry(self)
        self.i1.grid(row=1, column=1, sticky=Tkinter.E+Tkinter.W)

        Tkinter.Label(self, text="Particle Inertia:").grid(row=2, column=0, sticky=Tkinter.E)
        self.i2 = Tkinter.Entry(self)
        self.i2.grid(row=2, column=1, sticky=Tkinter.E+Tkinter.W)

        Tkinter.Label(self, text="Social Parameter:").grid(row=3, column=0, sticky=Tkinter.E)
        self.i3 = Tkinter.Entry(self)
        self.i3.grid(row=3, column=1, sticky=Tkinter.E+Tkinter.W)

        Tkinter.Label(self, text="Cognitive Parameter:").grid(row=4, column=0, sticky=Tkinter.E)
        self.i4 = Tkinter.Entry(self)
        self.i4.grid(row=4, column=1, sticky=Tkinter.E+Tkinter.W)

        self.c0 = Tkinter.Checkbutton(self, text="Use current machine state", variable=self.add_current_to_individuals)
        self.c0.grid(row=5, column=1)

        Tkinter.Label(self, text="Recommended:\nSwarm Size: 50\nMax. Iterations: 5\nParticle Inertia: 0.5\nSocial Parameter: 1.5\nCognitive Parameter: 2.0", justify=Tkinter.LEFT).grid(row=6, column=0, columnspan=2, sticky=Tkinter.W)

        self.i0.insert(0, "50")     #defaults are added in case user does not want to decide
        self.i1.insert(0, "5")
        self.i2.insert(0, "0.5")
        self.i3.insert(0, "1.5")
        self.i4.insert(0, "2.0")



    def get_dict(self):
        """
        Upon clicking OK, errors are lifted if any settings don't work
        """
        setup = {}

        try:
            setup['swarm_size'] = int(self.i0.get())
        except:
            raise ValueError("The value for \"Swarm Size\": \"{0}\", could not be converted to an int".format(self.i0.get()))
        try:
            setup['max_iter'] = int(self.i1.get())
        except:
            raise ValueError("The value for \"Max. Iterations\": \"{0}\", could not be converted to an int".format(self.i1.get()))
        try:
            setup['inertia'] = float(self.i2.get())
        except:
            raise ValueError("The value for \"Particle Inertia\": \"{0}\", could not be converted to a float".format(self.i2.get()))
        try:
            setup['social_param'] = float(self.i3.get())
        except:
            raise ValueError("The value for \"Social Parameter\": \"{0}\", could not be converted to a float".format(self.i3.get()))
        try:
            setup['cognitive_param'] = float(self.i4.get())
        except:
            raise ValueError("The value for \"Cognitive Parameter\": \"{0}\", could not be converted to a float".format(self.i4.get()))

        if self.add_current_to_individuals.get() == 0:
            setup['add_current_to_individuals'] = False
        elif self.add_current_to_individuals.get() == 1:
            setup['add_current_to_individuals'] = True

        return setup


#---------------------------------------------------------- CLASS FOR PROGRESS WINDOW ---------------------------------------------------------------#

class import_algo_prog_plot(Tkinter.Frame):
    """
    This class sets up the MOPSO progress plot that shows during the optimisation, including a percentage bar and a plot of the current fronts.
    """

    def __init__(self, parent, axis_labels, signConverter):

        Tkinter.Frame.__init__(self, parent)

        self.parent = parent
        self.signConverter = signConverter
        self.axis_labels = axis_labels

        self.initUi()

    def initUi(self):
        """
        setup plots
        """

        self.fig = Figure(figsize=(5, 5), dpi=100)
        self.a = self.fig.add_subplot(111)

        self.canvas = FigureCanvasTkAgg(self.fig, self)
        self.canvas.show()
        self.canvas.get_tk_widget().pack(side=Tkinter.BOTTOM, fill=Tkinter.BOTH, expand=True)

    def update(self):
        """
        after each iteration, plot the new front
        """
        global store_address
        global completed_iteration
        self.a.clear()
        file_names = []
        for i in range(completed_iteration):
            file_names.append("{0}/FRONTS/fronts.{1}".format(store_address, i))

        plot.plot_pareto_fronts(file_names, self.a, self.axis_labels, self.signConverter)

        self.canvas.show()

#--------------------------------------------------------------- CLASS FOR FINAL RESULTS WINDOW --------------------------------------------------------#

class import_algo_final_plot(Tkinter.Frame):
    """
    This class sets up the final results window that shows after the optimisation is complete. The actual plot of the final fronts is
    imported from the final_plot class.
    """

    def __init__(self, parent, pick_handler, axis_labels, signConverter, initial_config=None, post_analysis_store_address = None):

        global store_address
        Tkinter.Frame.__init__(self, parent)

        self.parent = parent
        self.signConverter = signConverter

        self.pick_handler = pick_handler
        self.axis_labels = axis_labels

        if initial_config is not None:
            self.initial_measurements = initial_config

        if post_analysis_store_address is not None:             #this class is also used for post_analysis
            store_address = post_analysis_store_address


    def initUi(self, initial_config_plot=True):
        """
        Setup window GUI
        """
        global store_address

        self.parent.title("MOPSO results")

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)

        self.rowconfigure(0, weight=1)

        self.view_mode = Tkinter.StringVar()
        self.view_mode.set('No focus')

        if initial_config_plot is True:
            self.plot_frame = final_plot(self, self.axis_labels, self.signConverter, initial_config=self.initial_measurements)
        else:
            self.plot_frame = final_plot(self, self.axis_labels, self.signConverter)
        self.plot_frame.grid(row=0, column=0, pady=20, padx=20, rowspan=1, sticky=Tkinter.N+Tkinter.S+Tkinter.E+Tkinter.W)

        Tkinter.Label(self, text="View mode:").grid(row=0, column=1)

        self.cbx_view_mode = ttk.Combobox(self, textvariable=self.view_mode, values=('No focus', 'Best focus'))
        self.cbx_view_mode.bind("<<ComboboxSelected>>", lambda x: self.plot_frame.initUi())
        self.cbx_view_mode.grid(row=0, column=2)

        self.grid(sticky=Tkinter.N+Tkinter.S+Tkinter.E+Tkinter.W)
        self.parent.columnconfigure(0, weight=1)
        self.parent.rowconfigure(0, weight=1)

    def on_pick(self, event):
        """
        This function gathers information from the saved files to allow the user to see the machine/algorithm parameters/results upon clicking
        on a solution on the Pareo front.
        """
        global store_address
        completed_iteration = len(os.listdir('{0}/FRONTS'.format(store_address)))

        my_artist = event.artist
        x_data = my_artist.get_xdata()
        y_data = my_artist.get_ydata()
        ind = event.ind
        point = tuple(zip(self.signConverter[0]*x_data[ind], self.signConverter[1]*y_data[ind]))

        print "Point selected, point: {0}".format(point)

        ''' By this point we have the ars, but not the aps. We get these next. '''

        file_names = []
        for i in range(completed_iteration):
            file_names.append("{0}/FRONTS/fronts.{1}".format(store_address, i))


        fs = []

        for file_name in file_names:
            execfile(file_name)

            fs.append(locals()['fronts'][0])

        aggregate_front_data = []
        for i in fs:
            for j in i:
                aggregate_front_data.append(j)
        aggregate_front_results = [i[1] for i in aggregate_front_data]
        point_number = aggregate_front_results.index(point[0])
        point_a_params = aggregate_front_data[point_number][0]

        print "ap: {0}".format(point_a_params)

        ''' By this point he have the aps, but not the mps. We don't find these in the algorithm. '''


        self.pick_handler(point[0], point_a_params)

#--------------------------------------------------------- CLASS FOR FINAL PLOT IN RESULTS WINDOW -------------------------------------------------#

class final_plot(Tkinter.Frame):
    """
    This class is called upon in the import_algo_final_plot class. It retrives the dumped fronts and then used dls_optimiser_plot to plot the
    Pareto fronts.
    """

    def __init__(self, parent, axis_labels, signConverter, initial_config=None):

        Tkinter.Frame.__init__(self, parent)

        self.parent = parent
        self.signConverter = signConverter
        self.axis_labels = axis_labels

        if initial_config is not None:
            self.initial_measurements = initial_config
            self.initUi(initial_config_plot=True)
        else:
            self.initUi()

    def initUi(self, initial_config_plot=False):
        global store_address
        completed_iteration = len(os.listdir('{0}/FRONTS'.format(store_address)))

        for widget in self.winfo_children():
            widget.destroy()

        fig = Figure(figsize=(5, 5), dpi=100)
        a = fig.add_subplot(111)
        fig.subplots_adjust(left=0.15)

        file_names = []
        for i in range(completed_iteration):                                            #gather fronts
            file_names.append("{0}/FRONTS/fronts.{1}".format(store_address, i))

        print 'file names', file_names

        if initial_config_plot is True:

            plot.plot_pareto_fronts_interactive(file_names,
                                                a,
                                                self.axis_labels,
                                                None,
                                                None,
                                                self.parent.view_mode.get(),
                                                self.signConverter,
                                                initial_measurements=self.initial_measurements)
        else:

            plot.plot_pareto_fronts_interactive(file_names,
                                                a,
                                                self.axis_labels,
                                                None,
                                                None,
                                                self.parent.view_mode.get(),
                                                self.signConverter)

        canvas = FigureCanvasTkAgg(fig, self)
        canvas.mpl_connect('pick_event', self.parent.on_pick)
        canvas.show()
        canvas.get_tk_widget().pack(side=Tkinter.BOTTOM, fill=Tkinter.BOTH, expand=True)

        toolbar = NavigationToolbar2TkAgg(canvas, self)
        toolbar.update()
        canvas._tkcanvas.pack(side=Tkinter.TOP, fill=Tkinter.BOTH, expand=True)
