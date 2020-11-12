from __future__ import division
from misc import fs_to_au, au_to_A, call_name, typewriter
import textwrap, datetime
import numpy as np

class MQC(object):
    """ Class for nuclear/electronic propagator used in MQC dynamics

        :param object molecule: molecule object
        :param object thermostat: thermostat type
        :param integer istate: initial adiabatic state
        :param double dt: time interval
        :param integer nsteps: nuclear step
        :param integer nesteps: electronic step
        :param string propagation: propagation scheme
        :param string solver: propagation solver
        :param boolean l_pop_print: logical to print BO population and coherence
        :param boolean l_adjnac: logical to adjust nonadiabatic coupling
        :param coefficient: initial BO coefficient
        :type coefficient: double, list or complex, list
        :param string unit_dt: unit of time step (fs = femtosecond, au = atomic unit)
    """
    def __init__(self, molecule, thermostat, istate, dt, nsteps, nesteps, \
        propagation, solver, l_pop_print, l_adjnac, coefficient, unit_dt):
        # Save name of MQC dynamics
        self.md_type = self.__class__.__name__

        # Initialize Molecule object
        self.mol = molecule
        
        # Initialize Thermostat object
        self.thermo = thermostat

        # Initialize input values
        self.istate = istate
        self.nsteps = nsteps
        self.nesteps = nesteps

        # Decide unit of time step
        if (unit_dt == 'au'):
            self.dt = dt
        elif (unit_dt == 'fs'):
            self.dt = dt * fs_to_au
        else:
            raise ValueError (f"( {self.md_type}.{call_name()} ) Invalid unit for time step! {unit_dt}")

        # Check number of state and initial state
        if (self.istate >= self.mol.nst): 
            raise ValueError (f"( {self.md_type}.{call_name()} ) Index for initial state must be smaller than number of states! {self.istate}")

        # None for BOMD case
        self.propagation = propagation
        if not (self.propagation in [None, "coefficient", "density"]): 
            raise ValueError (f"( {self.md_type}.{call_name()} ) Invalid 'propagation'! {self.propagation}")
        self.solver = solver
        if not (self.solver in [None, "rk4"]): 
            raise ValueError (f"( {self.md_type}.{call_name()} ) Invalid 'solver'! {self.solver}")

        self.l_pop_print = l_pop_print

        self.l_adjnac = l_adjnac

        self.rforce = np.zeros((self.mol.nat, self.mol.nsp))

        # Initialize coefficients and densities
        self.mol.get_coefficient(coefficient, self.istate)

    def cl_update_position(self):
        """ Routine to update nuclear positions

        """
        self.calculate_force()

        self.mol.vel += 0.5 * self.dt * self.rforce / np.column_stack([self.mol.mass] * self.mol.nsp)
        self.mol.pos += self.dt * self.mol.vel

    def cl_update_velocity(self):
        """ Routine to update nuclear velocities

        """
        self.calculate_force()

        self.mol.vel += 0.5 * self.dt * self.rforce / np.column_stack([self.mol.mass] * self.mol.nsp)
        self.mol.update_kinetic()

#    def calculate_temperature(self):
#        """ Routine to calculate current temperature
#        """
#        pass
#        #self.temperature = self.mol.ekin * 2 / float(self.mol.dof) * au_to_K

    def calculate_force(self):
        """ Routine to calculate the forces
        """
        pass

    def update_potential(self):
        """ Routine to update the potential of molecules
        """
        pass

    def print_init(self, qm, mm, debug):
        """ Routine to print the initial information of dynamics

            :param object qm: qm object containing on-the-fly calculation infomation
            :param object mm: mm object containing MM calculation infomation
            :param integer debug: verbosity level for standard output
        """

        # Print UNI-xMD version
        cur_time = datetime.datetime.now()
        cur_time = cur_time.strftime("%Y-%m-%d %H:%M:%S")
        prog_info = textwrap.dedent(f"""\
        {"-" * 68}

        {"UNI-xMD version 20.1":>43s}

        {"< Developers >":>40s}
        {" " * 4}Seung Kyu Min,  In Seong Lee,  Jong-Kwon Ha,  Daeho Han,
        {" " * 4}Kicheol Kim,  Tae In Kim,  Sung Wook Moon

        {"-" * 68}

        {" " * 4}Please cite UNI-xMD as follows:
        {" " * 4}This is article

        {" " * 4}UNI-xMD begins on {cur_time}
        """)
        print(prog_info, flush=True)

        # Print molecule information: coordinate, velocity
        self.mol.print_init(mm)

        # Print dynamics information
        dynamics_info = textwrap.dedent(f"""\
        {"-" * 68}
        {"Dynamics Information":>43s}
        {"-" * 68}
          QM Program               = {qm.qm_prog:>16s}
          QM Method                = {qm.qm_method:>16s}
        """)
        if (self.mol.qmmm and mm != None):
            dynamics_info += textwrap.indent(textwrap.dedent(f"""\
              MM Program               = {mm.mm_prog:>16s}
              QMMM Scheme              = {mm.scheme:>16s}
            """), "  ")
            # Print charge embedding in MM program
            if (mm.embedding != None):
                dynamics_info += f"  Charge Embedding         = {mm.embedding:>16s}\n"
            else:
                dynamics_info += f"  Charge Embedding         = {'No':>16s}\n"
            # Print vdw interaction in MM program
            if (mm.vdw != None):
                dynamics_info += f"  VDW Interaction          = {mm.vdw:>16s}\n"
            else:
                dynamics_info += f"  VDW Interaction          = {'No':>16s}\n"
                                 
        dynamics_info += textwrap.indent(textwrap.dedent(f"""\

          MQC Method               = {self.md_type:>16s}
          Time Interval (fs)       = {self.dt / fs_to_au:16.6f}
          Initial State (0:GS)     = {self.istate:>16d}
          Nuclear Step             = {self.nsteps:>16d}
        """), "  ")
        if (self.md_type != "BOMD"):
            dynamics_info += f"  Electronic Step          = {self.nesteps:>16d}\n"
            dynamics_info += f"  Propagation Scheme       = {self.propagation:>16s}\n"

        # Print surface hopping variables
        if (self.md_type == "SH" or self.md_type == "SHXF"):
            dynamics_info += f"\n  Velocity Rescale in Hop  = {self.vel_rescale:>16s}\n"

        # Print XF variables
        if (self.md_type == "SHXF" or self.md_type == "EhXF"):
            # Print density threshold used in decoherence term
            dynamics_info += f"\n  Density Threshold        = {self.threshold:>16.6f}"
            if (self.md_type == "SHXF" and self.one_dim):
                # Print reduced mass
                dynamics_info += f"\n  Reduced Mass             = {self.aux.mass[0]:16.6f}"
            # Print wsigma values
            if (isinstance(self.wsigma, float)):
                dynamics_info += f"\n  Sigma                    = {self.wsigma:16.3f}\n"
            elif (isinstance(self.wsigma, list)):
                dynamics_info += f"\n  Sigma (1:N)              =\n"
                nlines = int(self.mol.nat_qm / 6)
                if (self.mol.nat_qm % 6 != 0):
                    nlines += 1
                wsigma_info = ""
                for iline in range(nlines):
                    iline1 = iline * 6
                    iline2 = (iline + 1) * 6
                    if (iline2 > self.mol.nat_qm):
                        iline2 = self.mol.nat_qm
                    wsigma_info += f"  {iline1 + 1:>3d}:{iline2:<3d};"
                    wsigma_info += "".join([f'{sigma:7.3f}' for sigma in self.wsigma[iline1:iline2]])
                    wsigma_info += "\n"
                dynamics_info += wsigma_info

        print (dynamics_info, flush=True)

        # Print thermostat information
        if (self.thermo != None):
            self.thermo.print_init()
        else:
            thermostat_info = "  No Thermostat: Total energy is conserved!\n"
            print (thermostat_info, flush=True)

    def touch_file(self, unixmd_dir): 
        """ Routine to write PyUNIxMD output files

            :param string unixmd_dir: unixmd directory
        """

        # Energy information file header
        tmp = f'{"#":5s}{"Step":9s}{"Kinetic(H)":15s}{"Potential(H)":15s}{"Total(H)":15s}' + \
            "".join([f'E({ist})(H){"":8s}' for ist in range(self.mol.nst)])
        typewriter(tmp, unixmd_dir, "MDENERGY")

        if (self.md_type != "BOMD"):
        # BO coefficents, densities file header
            if (self.propagation == "density"):
                tmp = f'{"#":5s} Density Matrix: population Re; see the manual for detail orders'
                typewriter(tmp, unixmd_dir, "BOPOP")
                tmp = f'{"#":5s} Density Matrix: coherence Re-Im; see the manual for detail orders'
                typewriter(tmp, unixmd_dir, "BOCOH")
            elif (self.propagation == "coefficient"):
                tmp = f'{"#":5s} BO State Coefficients: state Re-Im; see the manual for detail orders'
                typewriter(tmp, unixmd_dir, "BOCOEF")
                if (self.l_pop_print):
                    tmp = f'{"#":5s} Density Matrix: population Re; see the manual for detail orders'
                    typewriter(tmp, unixmd_dir, "BOPOP")
                    tmp = f'{"#":5s} Density Matrix: coherence Re-Im; see the manual for detail orders'
                    typewriter(tmp, unixmd_dir, "BOCOH")
            else:
                raise ValueError (f"( {call_name()} ) Other propagator not implemented! {propagation}")

            # NACME file header
            tmp = f'{"#":5s}Non-Adiabatic Coupling Matrix Elements: off-diagonal'
            typewriter(tmp, unixmd_dir, "NACME")

        # file header for SH-based methods
        if (self.md_type == "SH" or self.md_type == "SHXF"):
            tmp = f'{"#":5s}{"Step":8s}{"Running State":10s}'
            typewriter(tmp, unixmd_dir, "SHSTATE")

            tmp = f'{"#":5s}{"Step":12s}' + "".join([f'Prob({ist}){"":8s}' for ist in range(self.mol.nst)])
            typewriter(tmp, unixmd_dir, "SHPROB")

        # file header for XF-based methods
        if (self.md_type == "SHXF" or self.md_type == "EhXF"):
            tmp = f'{"#":5s} Time-derivative Density Matrix by decoherence: population; see the manual for detail orders'
            typewriter(tmp, unixmd_dir, "DOTPOPD")

    def write_md_output(self, unixmd_dir, istep):
        """ Write output files

            :param string unixmd_dir: unixmd directory
            :param integer istep: current MD step
        """
        # Write MOVIE.xyz file including positions and velocities
        tmp = f'{self.mol.nat:6d}\n{"":2s}Step:{istep + 1:6d}{"":12s}Position(A){"":34s}Velocity(au)'
        typewriter(tmp, unixmd_dir, "MOVIE.xyz")
        for iat in range(self.mol.nat):
            tmp = f'{self.mol.symbols[iat]:5s}' + \
                "".join([f'{self.mol.pos[iat, isp] * au_to_A:15.8f}' for isp in range(self.mol.nsp)]) \
                + "".join([f"{self.mol.vel[iat, isp]:15.8f}" for isp in range(self.mol.nsp)])
            typewriter(tmp, unixmd_dir, "MOVIE.xyz")

        # Write MDENERGY file including several energy information
        tmp = f'{istep + 1:9d}{self.mol.ekin:15.8f}{self.mol.epot:15.8f}{self.mol.etot:15.8f}' \
            + "".join([f'{states.energy:15.8f}' for states in self.mol.states])
        typewriter(tmp, unixmd_dir, "MDENERGY")
    
        if (self.md_type != "BOMD"):
            # Write BOCOEF, BOPOP, BOCOH files
            if (self.propagation == "density"):
                tmp = f'{istep + 1:9d}' + "".join([f'{self.mol.rho.real[ist, ist]:15.8f}' for ist in range(self.mol.nst)])
                typewriter(tmp, unixmd_dir, "BOPOP")
                tmp = f'{istep + 1:9d}' + "".join([f"{self.mol.rho.real[ist, jst]:15.8f}{self.mol.rho.imag[ist, jst]:15.8f}" \
                    for ist in range(self.mol.nst) for jst in range(ist + 1, self.mol.nst)])
                typewriter(tmp, unixmd_dir, "BOCOH")
            elif (self.propagation == "coefficient"):
                tmp = f'{istep + 1:9d}' + "".join([f'{states.coef.real:15.8f}{states.coef.imag:15.8f}' \
                    for states in self.mol.states])
                typewriter(tmp, unixmd_dir, "BOCOEF")
                if (self.l_pop_print):
                    tmp = f'{istep + 1:9d}' + "".join([f'{self.mol.rho.real[ist, ist]:15.8f}' for ist in range(self.mol.nst)])
                    typewriter(tmp, unixmd_dir, "BOPOP")
                    tmp = f'{istep + 1:9d}' + "".join([f"{self.mol.rho.real[ist, jst]:15.8f}{self.mol.rho.imag[ist, jst]:15.8f}" \
                        for ist in range(self.mol.nst) for jst in range(ist + 1, self.mol.nst)])
                    typewriter(tmp, unixmd_dir, "BOCOH")

            # Write NACME file
            tmp = f'{istep + 1:10d}' + "".join([f'{self.mol.nacme[ist, jst]:15.8f}' \
                for ist in range(self.mol.nst) for jst in range(ist + 1, self.mol.nst)])
            typewriter(tmp, unixmd_dir, "NACME")

            # Write NACV file
            if(not self.mol.l_nacme):
                for ist in range(self.mol.nst):
                    for jst in range(ist + 1, self.mol.nst):
                        tmp = f'{self.mol.nat_qm:6d}\n{"":2s}Step:{istep + 1:6d}{"":12s}NACV'
                        typewriter(tmp, unixmd_dir, f"NACV_{ist}_{jst}")
                        for iat in range(self.mol.nat_qm):
                            tmp = f'{self.mol.symbols[iat]:5s}' + \
                                "".join([f'{self.mol.nac[ist, jst, iat, isp]:15.8f}' for isp in range(self.mol.nsp)])
                            typewriter(tmp, unixmd_dir, f"NACV_{ist}_{jst}")

    def write_final_xyz(self, unixmd_dir, istep):
        """ Write final positions and velocities

            :param string unixmd_dir: unixmd directory
            :param integer istep: current MD step
        """
        # Write FINAL.xyz file including positions and velocities
        tmp = f'{self.mol.nat:6d}\n{"":2s}Step:{istep + 1:6d}{"":12s}Position(A){"":34s}Velocity(au)'
        typewriter(tmp, unixmd_dir, "FINAL.xyz")
        for iat in range(self.mol.nat):
            tmp = f'{self.mol.symbols[iat]:5s}' + \
                "".join([f'{self.mol.pos[iat, isp] * au_to_A:15.8f}' for isp in range(self.mol.nsp)]) \
                + "".join([f"{self.mol.vel[iat, isp]:15.8f}" for isp in range(self.mol.nsp)])
            typewriter(tmp, unixmd_dir, "FINAL.xyz")

    def check_qmmm(self, qm, mm):
        """ Routine to check compatibility between QM and MM objects

            :param object qm: qm object containing on-the-fly calculation infomation
            :param object mm: mm object containing MM calculation infomation
        """
        # Now check MM object
        if (mm.mm_prog == "Tinker"):
            # Now check QM object
            if (qm.qm_prog == "dftbplus"):
                if (qm.qm_method == "SSR"):
                    do_qmmm = True
                else:
                    do_qmmm = False
            else:
                do_qmmm = False
        else:
            do_qmmm = False

        if (do_qmmm):
            if (qm.embedding != mm.embedding):
                raise ValueError (f"( {self.md_type}.{call_name()} ) Inconsistent charge embedding options between QM and MM objects! {qm.embedding} and {mm.embedding}")
        else:
            raise ValueError (f"( {self.md_type}.{call_name()} ) Not compatible objects in QMMM! {qm.qm_prog}.{qm.qm_method} and {mm.mm_prog}")


