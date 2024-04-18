from __future__ import division
from build.el_propagator import el_run
from cpa.cpa import CPA
from misc import eps, au_to_K, call_name, typewriter
import random, os, shutil, textwrap
import numpy as np
import pickle

class SH(CPA):
    """ Class for surface hopping dynamics with CPA

        :param object molecule: Molecule object
        :param integer istate: Initial state
        :param double dt: Time interval
        :param integer nsteps: Total step of nuclear propagation
        :param integer nesteps: Total step of electronic propagation
        :param string elec_object: Electronic equation of motions
        :param string propagator: Electronic propagator
        :param boolean l_print_dm: Logical to print BO population and coherence
        :param boolean l_adj_nac: Adjust nonadiabatic coupling to align the phases
        :param init_coef: Initial BO coefficient
        :type init_coef: double, list or complex, list
        :param string dec_correction: Simple decoherence correction schemes
        :param double edc_parameter: Energy constant (H) for rescaling coefficients in edc
        :param string unit_dt: Unit of time step
        :param string samp_dir: Path of sampling data folder
        :param integer out_freq: Frequency of printing output
        :param integer verbosity: Verbosity of output
        :param integer index_start: Index for starting read BOMD sampling data
    """
    def __init__(self, molecule, istate=0, dt=0.5, nsteps=1000, nesteps=20, \
        elec_object="density", propagator="rk4", l_print_dm=True, l_adj_nac=True, init_coef=None, \
        dec_correction=None, edc_parameter=0.1, unit_dt="fs", samp_dir = "./Data", \
        out_freq=1, verbosity=0, index_start=0):
        # Initialize input values
        super().__init__(molecule, istate, dt, nsteps, nesteps, \
            elec_object, propagator, l_print_dm, l_adj_nac, init_coef, unit_dt, out_freq, verbosity)

        # Initialize trajectory data
        self.pos = np.zeros((nsteps + 1, molecule.nat, molecule.ndim))
        self.vel = np.zeros((nsteps + 1, molecule.nat, molecule.ndim))
        self.energy = np.zeros((nsteps + 1, molecule.nst))
        self.force = np.zeros((nsteps + 1, molecule.nat, molecule.ndim))
        self.nacme = np.zeros((nsteps + 1, molecule.nst, molecule.nst))
        
        for istep in [x for x in range(index_start - 1, index_start + nsteps)]:
            with open(os.path.join(samp_dir, "QM." + str(istep) + ".bin"), "rb") as f:
                data = pickle.load(f)

            self.energy[istep - index_start] = data["energy"]
            self.force[istep - index_start] = data["force"]
            self.nacme[istep - index_start] = data["nacme"]

            with open(os.path.join(samp_dir, "RP." + str(istep) + ".bin"), "rb") as f:
                data = pickle.load(f)
            self.pos[istep - index_start] = data["pos"]
            self.vel[istep - index_start] = data["vel"]

        # Initialize SH variables
        self.rstate = istate
        self.rstate_old = self.rstate

        self.rand = 0.
        self.prob = np.zeros(self.mol.nst)
        self.acc_prob = np.zeros(self.mol.nst + 1)

        self.l_hop = False
        self.l_reject = False

        # Initialize decoherence variables
        self.dec_correction = dec_correction
        self.edc_parameter = edc_parameter

        if (self.dec_correction != None):
            self.dec_correction = self.dec_correction.lower()

        if not (self.dec_correction in [None, "idc", "edc"]):
            error_message = "Invalid decoherence corrections in FSSH method!"
            error_vars = f"dec_correction = {self.dec_correction}"
            raise ValueError (f"( {self.md_type}.{call_name()} ) {error_message} ( {error_vars} )")

        # Debug variables
        self.dotpopnac = np.zeros(self.mol.nst)

        # Initialize event to print
        self.event = {"HOP": []}

    def run(self, qm, mm=None, output_dir="./", l_save_qm_log=False, l_save_mm_log=False, l_save_scr=True, restart=None):
        """ Run CPA dynamics according to surface hopping dynamics

            :param object qm: QM object containing on-the-fly calculation infomation
            :param object mm: MM object containing MM calculation infomation
            :param string output_dir: Name of directory where outputs to be saved.
            :param boolean l_save_qm_log: Logical for saving QM calculation log
            :param boolean l_save_mm_log: Logical for saving MM calculation log
            :param boolean l_save_scr: Logical for saving scratch directory
            :param string restart: Option for controlling dynamics restarting
        """
        # Initialize PyUNIxMD
        base_dir, unixmd_dir, qm_log_dir, mm_log_dir =\
             self.run_init(qm, mm, output_dir, l_save_qm_log, l_save_mm_log, l_save_scr, restart)

        bo_list = [] # a redundant variable in CPA-like dynamics
        qm.calc_coupling = False
        self.print_init(qm, mm, restart)

        if (restart == None):
            # Calculate initial input geometry at t = 0.0 s
            self.istep = -1
            self.mol.reset_bo(qm.calc_coupling)

            self.read_RP_from_file(self.istep)
            self.read_QM_from_file(self.istep)
            if (self.mol.l_qmmm and mm != None):
                mm.get_data(self.mol, base_dir, bo_list, self.istep, calc_force_only=False)
 
            self.hop_prob()
            self.hop_check(bo_list)
 
            if (self.dec_correction == "idc"):
                if (self.l_hop or self.l_reject):
                    self.correct_dec_idc()
                elif (self.dec_correction == "edc"):
                    # If kinetic is 0, coefficient/density matrix are update into itself
                    if (self.mol.ekin_qm > eps):
                        self.correct_dec_edc()
 
            self.update_energy()
 
            self.write_md_output(unixmd_dir, self.istep)
            self.print_step(self.istep)

        elif (restart == "write"):
            # Reset initial time step to t = 0.0 s
            self.istep = -1
            
            self.read_RP_from_file(self.istep)
            self.read_QM_from_file(self.istep)
            self.write_md_output(unixmd_dir, self.istep)
            self.print_step(self.istep)

        elif (restart == "append"):
            # Set initial time step to last successful step of previous dynamics
            self.istep = self.fstep

        self.istep += 1

        # Main MD loop
        for istep in range(self.istep, self.nsteps):
              
            self.mol.backup_bo()
            self.mol.reset_bo(qm.calc_coupling)
            self.read_QM_from_file(istep)
            if (self.mol.l_qmmm and mm != None):
                mm.get_data(self.mol, base_dir, bo_list, istep, calc_force_only=False)

            if (not self.mol.l_nacme and self.l_adj_nac):
                self.mol.adjust_nac()

            self.read_RP_from_file(istep)
            
            el_run(self)

            self.hop_prob()
            self.hop_check(bo_list)

            if (self.dec_correction == "idc"):
                if (self.l_hop or self.l_reject):
                    self.correct_dec_idc()
            elif (self.dec_correction == "edc"):
                # If kinetic is 0, coefficient/density matrix are update into itself
                if (self.mol.ekin_qm > eps):
                    self.correct_dec_edc()

            self.update_energy()

            if ((istep + 1) % self.out_freq == 0):
                self.write_md_output(unixmd_dir, istep)
            if ((istep + 1) % self.out_freq == 0 or len(self.event["HOP"]) > 0):
                self.print_step(istep)
            
            self.fstep = istep

            if (not l_save_scr):
                tmp_dir = os.path.join(unixmd_dir, "scr_qm")
                if(os.path.exists(tmp_dir)):
                    shutil.rmtree(tmp_dir)

                if(self.mol.l_qmmm and mm != None):
                    tmp_dir = os.path.join(unixmd_dir, "scr_mm")
                    if (os.path.exists(tmp_dir)):
                        shutil.rmtree(tmp_dir)

    def hop_prob(self):
        """ Routine to calculate hopping probabilities
        """
        # Reset surface hopping variables
        self.rstate_old = self.rstate

        self.prob = np.zeros(self.mol.nst)
        self.acc_prob = np.zeros(self.mol.nst + 1)

        self.l_hop = False

        accum = 0.

        for ist in range(self.mol.nst):
            if (ist != self.rstate):
                self.prob[ist] = - 2. * self.mol.rho.real[ist, self.rstate] * \
                    self.mol.nacme[ist, self.rstate] * self.dt / self.mol.rho.real[self.rstate, self.rstate]

                if (self.prob[ist] < 0.):
                    self.prob[ist] = 0.
                accum += self.prob[ist]
            self.acc_prob[ist + 1] = accum
        psum = self.acc_prob[self.mol.nst]

        if (psum > 1.):
            self.prob /= psum
            self.acc_prob /= psum

    def hop_check(self, bo_list):
        """ Routine to check hopping occurs with random number and record hopping event

            :param integer,list bo_list: List of BO states for BO calculation
        """
        self.rand = random.random()
        for ist in range(self.mol.nst):
            if (ist == self.rstate):
                continue
            if (self.rand > self.acc_prob[ist] and self.rand <= self.acc_prob[ist + 1]):
                self.l_hop = True
                self.rstate = ist

        # Record hopping event
        if (self.rstate != self.rstate_old):
            self.event["HOP"].append(f"Accept hopping: hop {self.rstate_old} -> {self.rstate}")

    def correct_dec_idc(self):
        """ Routine to decoherence correction, instantaneous decoherence correction(IDC) scheme
        """
        if (self.elec_object == "coefficient"):
            for states in self.mol.states:
                states.coef = 0. + 0.j
            self.mol.states[self.rstate].coef = 1. + 0.j

        self.mol.rho = np.zeros((self.mol.nst, self.mol.nst), dtype=np.complex128)
        self.mol.rho[self.rstate, self.rstate] = 1. + 0.j

    def correct_dec_edc(self):
        """ Routine to decoherence correction, energy-based decoherence correction(EDC) scheme
        """
        # Save exp(-dt/tau) instead of tau itself
        exp_tau = np.array([1. if (ist == self.rstate) else np.exp(- self.dt / ((1. + self.edc_parameter / self.mol.ekin_qm) / \
            np.abs(self.mol.states[ist].energy - self.mol.states[self.rstate].energy))) for ist in range(self.mol.nst)])
        rho_update = 1.

        if (self.elec_object == "coefficient"):
            # Update coefficients
            for ist in range(self.mol.nst):
                # self.mol.states[self.rstate] need other updated coefficients
                if (ist != self.rstate):
                    self.mol.states[ist].coef *= exp_tau[ist]
                    rho_update -= self.mol.states[ist].coef.conjugate() * self.mol.states[ist].coef

            self.mol.states[self.rstate].coef *= np.sqrt(rho_update / self.mol.rho[self.rstate, self.rstate])

            # Get density matrix elements from coefficients
            for ist in range(self.mol.nst):
                for jst in range(ist, self.mol.nst):
                    self.mol.rho[ist, jst] = self.mol.states[ist].coef.conjugate() * self.mol.states[jst].coef
                    self.mol.rho[jst, ist] = self.mol.rho[ist, jst].conjugate()

        elif (self.elec_object == "density"):
            # save old running state element for update running state involved elements
            rho_old_rstate = self.mol.rho[self.rstate, self.rstate]
            for ist in range(self.mol.nst):
                for jst in range(ist, self.mol.nst):
                    # Update density matrix. self.mol.rho[ist, rstate] suffers half-update because exp_tau[rstate] = 1
                    self.mol.rho[ist, jst] *= exp_tau[ist] * exp_tau[jst]
                    self.mol.rho[jst, ist] = self.mol.rho[ist, jst].conjugate()

                if (ist != self.rstate):
                    # Update rho[self.rstate, self.rstate] by subtracting other diagonal elements
                    rho_update -= self.mol.rho[ist, ist]

            # Update rho[self.rstate, ist] and rho[ist, self.rstate] by using rho_update and rho_old_rstate
            # rho[self.rstate, self.rstate] automatically update by double counting
            for ist in range(self.mol.nst):
                self.mol.rho[ist, self.rstate] *= np.sqrt(rho_update / rho_old_rstate)
                self.mol.rho[self.rstate, ist] *= np.sqrt(rho_update / rho_old_rstate)

    def update_energy(self):
        """ Routine to update the energy of molecules in surface hopping dynamics
        """
        # Update kinetic energy
        self.mol.update_kinetic()
        self.mol.epot = self.mol.states[self.rstate].energy
        self.mol.etot = self.mol.epot + self.mol.ekin

    def write_md_output(self, unixmd_dir, istep):
        """ Write output files

            :param string unixmd_dir: PyUNIxMD directory
            :param integer istep: Current MD step
        """
        # Write the common part
        super().write_md_output(unixmd_dir, istep)

        # Write hopping-related quantities
        self.write_sh(unixmd_dir, istep)

        # Write time-derivative BO population
        self.write_dotpop(unixmd_dir, istep)

    def write_sh(self, unixmd_dir, istep):
        """ Write hopping-related quantities into files

            :param string unixmd_dir: PyUNIxMD directory
            :param integer istep: Current MD step
        """
        # Write SHSTATE file
        tmp = f'{istep + 1:9d}{"":14s}{self.rstate}'
        typewriter(tmp, unixmd_dir, "SHSTATE", "a")

        # Write SHPROB file
        tmp = f'{istep + 1:9d}' + "".join([f'{self.prob[ist]:15.8f}' for ist in range(self.mol.nst)])
        typewriter(tmp, unixmd_dir, "SHPROB", "a")

    def write_dotpop(self, unixmd_dir, istep):
        """ Write time-derivative BO population

            :param string unixmd_dir: PyUNIxMD directory
            :param integer istep: Current MD step
        """
        # Write NAC term in DOTPOPNAC
        if (self.verbosity >= 1):
            tmp = f'{istep + 1:9d}' + "".join([f'{pop:15.8f}' for pop in self.dotpopnac])
            typewriter(tmp, unixmd_dir, "DOTPOPNAC", "a")

    def print_init(self, qm, mm, restart):
        """ Routine to print the initial information of dynamics

            :param object qm: QM object containing on-the-fly calculation infomation
            :param object mm: MM object containing MM calculation infomation
            :param string restart: Option for controlling dynamics restarting
        """
        # Print initial information about molecule, qm, mm and thermostat
        super().print_init(qm, mm, restart)

        # Print dynamics information for start line
        dynamics_step_info = textwrap.dedent(f"""\

        {"-" * 118}
        {"Start Dynamics":>65s}
        {"-" * 118}
        """)

        # Print INIT for each step
        INIT = f" #INFO{'STEP':>8s}{'State':>7s}{'Kinetic(H)':>14s}{'Potential(H)':>15s}{'Total(H)':>13s}{'Temperature(K)':>17s}{'Norm.':>8s}"
        dynamics_step_info += INIT

        # Print DEBUG1 for each step
        if (self.verbosity >= 1):
            DEBUG1 = f" #DEBUG1{'STEP':>6s}{'Rand.':>11s}{'Acc. Hopping Prob.':>28s}"
            dynamics_step_info += "\n" + DEBUG1

        print (dynamics_step_info, flush=True)

    def print_step(self, istep):
        """ Routine to print each steps infomation about dynamics

            :param integer istep: Current MD step
        """
        ctemp = self.mol.ekin * 2. / float(self.mol.ndof) * au_to_K
        norm = 0.
        for ist in range(self.mol.nst):
            norm += self.mol.rho.real[ist, ist]

        # Print INFO for each step
        INFO = f" INFO{istep + 1:>9d}{self.rstate:>5d}"
        INFO += f"{self.mol.ekin:16.8f}{self.mol.epot:15.8f}{self.mol.etot:15.8f}"
        INFO += f"{ctemp:13.6f}"
        INFO += f"{norm:11.5f}"
        print (INFO, flush=True)

        # Print DEBUG1 for each step
        if (self.verbosity >= 1):
            DEBUG1 = f" DEBUG1{istep + 1:>7d}"
            DEBUG1 += f"{self.rand:11.5f}"
            for ist in range(self.mol.nst):
                DEBUG1 += f"{self.acc_prob[ist]:12.5f} ({self.rstate}->{ist})"
            print (DEBUG1, flush=True)

        # Print event in surface hopping
        for category, events in self.event.items():
            if (len(events) != 0):
                for ievent in events:
                    print (f" {category}{istep + 1:>9d}  {ievent}", flush=True)
        self.event["HOP"] = []

    def read_QM_from_file(self, istep):
        """Routine to read precomputed QM information for CPA dynamics

           :param integer istep: Current MD step
        """
        for ist in range(self.mol.nst):
            self.mol.states[ist].energy = self.energy[istep, ist]
        self.rforce = self.force[istep]
        self.mol.nacme = self.nacme[istep]

    def read_RP_from_file(self, istep):
        """Routine to read precomputed atomic position, velocities for CPA dynamics

           :param integer istep: Current MD step
        """
        self.mol.pos = self.pos[istep]
        self.mol.vel = self.vel[istep]