import argparse
import os
import numpy as np

def statistical_analysis():
    """ Python utility script for UNI-xMD output analysis
    """
    parser = argparse.ArgumentParser(description="Python script for UNI-xMD output analysis")
    parser.add_argument('-n', '-ntraj', action='store', dest='ntraj', type=int, \
        help="Total trajectory number", required=True)
    parser.add_argument('-s', '-nstep', action='store', dest='nstep', type=int, \
        help="Total step number for analysis", required=True)
    parser.add_argument('-t', '-nstate', action='store', dest='nstate', type=int, \
        help="Total state number for analysis", required=True)
    args = parser.parse_args()

    # Indexing for numbering filename
    index = len(str(args.ntraj))
    
    # Include step 0 
    nstep1 = args.nstep + 1
    
    averaged_running_state(args.ntraj, index, nstep1, args.nstate)
    averaged_density_matrix(args.ntraj, index, nstep1, args.nstate)
    averaged_nacme(args.ntraj, index, nstep1, args.nstate)

def averaged_running_state(ntraj, index, nstep, nstate):
    """ BO population analysis based on the running state of each trajectories
    """
    f_write = ""

    header = "#    Running state based averaged BO population"
    f_write += header
        
    # define empty array for summation
    avg_state = np.zeros((nstate, nstep))
    # define variable for count trajectories except halted trajectories
    mtraj = ntraj

    for itraj in range(ntraj):
        path = os.path.join(f"./TRAJ_{itraj + 1:0{index}d}/md/", "SHSTATE")

        with open(path, 'r') as f:
            # Skip header and read rest
            line = f.readline()
            line = f.read()
            lines = line.split()

        # read state information of entire steps
        rstate = np.array(lines[1::2][:nstep], dtype=np.int)    
        try:
            # sum over counted state number of each states 
            avg_state += np.array([(rstate == ist) for ist in range(nstate)], dtype=np.float)
        except ValueError:
            # exclude halted trajectories from total trajectory number
            mtraj -= 1

    # average array and print
    avg_state /= mtraj
    avg_data = "".join([("\n" + f"{istep:8d}" + "".join([f"{avg_state[istate, istep]:15.8f}" \
        for istate in range(nstate)])) for istep in range(nstep)])
    f_write += avg_data

    typewriter(f_write, "POP_RUN")

def averaged_density_matrix(ntraj, index, nstep, nstate):
    """ Electronic coherence analysis and BO population analysis
        based on the density matrix of each trajectories
    """
    f1_write = ""
    f2_write = ""

    header = "#    Averaged electronic coherence"
    f1_write += header

    header = "#    Density matrix based averaged BO population"
    f2_write += header

    # calculate number of off-diagonal elements from given nstate
    nstate_pair = int(nstate * (nstate - 1) / 2)
    # define empty array for summation
    avg_coh = np.zeros((nstate_pair, nstep))
    avg_pop = np.zeros((nstate, nstep))
    # define variable for count trajectories except halted trajectories
    mtraj = ntraj

    for itraj in range(ntraj):
        path = os.path.join(f"./TRAJ_{itraj + 1:0{index}d}/md/", "BOPOP")

        with open(path, 'r') as f:
            # Skip header and read rest
            line = f.readline()
            line = f.read()
            lines = line.split()
            lines_list = list(map(float, lines))

        try:
            # sum over population of each states
            avg_pop += np.array([lines[istate::(nstate + 1)][:nstep] for istate in range(1, nstate + 1)], dtype=np.float)
            # sum over coherence of each states, obtained from multiply istate population and jstate population
            avg_coh += np.array([np.multiply(lines_list[istate::(nstate + 1)][:nstep],lines_list[jstate::(nstate + 1)][:nstep]) \
                for istate in range(1, nstate + 1) for jstate in range(istate + 1, nstate + 1)])
        except ValueError:
            # exclude halted trajectories from total trajectory number
            mtraj -= 1
 
    # average array and print
    avg_coh /= mtraj
    avg_pop /= mtraj
    
    avg_data = "".join([("\n" + f"{istep:8d}" + "".join([f"{avg_coh[istate, istep]:15.8f}" \
        for istate in range(nstate_pair)])) for istep in range(nstep)])
    f1_write += avg_data

    avg_data = "".join([("\n" + f"{istep:8d}" + "".join([f"{avg_pop[istate, istep]:15.8f}" \
        for istate in range(nstate)])) for istep in range(nstep)])
    f2_write += avg_data

    typewriter(f1_write, "COH_RHO")
    typewriter(f2_write, "POP_RHO")
                                      
def averaged_nacme(ntraj, index, nstep, nstate):
    """ Non-adiabatic coupling matrix analysis 
    """
    f_write = ""

    header = "#    Averaged Non-Adiabatic Coupling Matrix Eliments: off-diagonal"
    f_write += header

    # calculate number of off-diagonal elements from given nstate
    nstate_pair = int(nstate * (nstate - 1) / 2)
    # define empty array for summation
    avg_nacme = np.zeros((nstate_pair, nstep))
    # define variable for count trajectories except halted trajectories
    mtraj = ntraj

    for itraj in range(ntraj):
        path = os.path.join(f"./TRAJ_{itraj + 1:0{index}d}/md/", "NACME")

        with open(path, 'r') as f:
            # Skip header and read rest
            line = f.readline()
            line = f.read()
            lines = line.split()

        try:
            # sum over nacme of each state-state pair
            avg_nacme += abs(np.array([lines[istate::(nstate_pair + 1)][:nstep] for istate in range(1, nstate_pair + 1)], dtype=np.float))
        except ValueError:
            # exclude halted trajectories from total trajectory number
            mtraj -= 1

    # average array and print
    avg_nacme /= mtraj
    avg_data = "".join([("\n" + f"{istep:8d}" + "".join([f"{avg_nacme[istate, istep]:15.8f}" \
        for istate in range(nstate_pair)])) for istep in range(nstep)])
    f_write += avg_data

    typewriter(f_write, "AVG_NACME")

def typewriter(string, file_name):
    """ Function to write a string in filename
    """
    with open(file_name, "w") as f:
        f.write(string + "\n")

if (__name__ == "__main__"):
    statistical_analysis()

