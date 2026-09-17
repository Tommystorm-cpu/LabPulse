"""
Code to get the coefficient values for the Steinhart-Hart equation from
resistance and temperature values
"""
import numpy as np 
import scipy.optimize
from matplotlib import pyplot as plt

#Temperature list
T_list = [-40,25,50,100,125]

#Convert to Kelvin if input is specified
print("Y or N: Is the list in Celcius")
C_to_K_input = input()
if C_to_K_input == "Y":
    T_list = [t+273.15 for t in T_list]

#Resistance list in Ohms
R_list = [101770,2820,988.1,179.6,88.11]

def Steinhart_Hart_eqn(Res,A,B,C,D):
    """
    Returns the temperature value of an NTC based on the material values 
    of A,B,C and D.
    """
    lnR = np.log(Res)
    return (A + B*lnR + C*(lnR ** 2) + D*(lnR ** 3)) ** (-1)

def fit_data(Res_list,T_list,parameter_guesses):
    """
    Use the data and scipy.optimize.curve_fitting to estimate A,B,C,D.

    parameter_guesses is the initial guesses to the parameters A,B,C,D,
    however if these aren't available, using None will bypass this feature.
    However this may result in less effective fitting - 
    you could use this function multiple times updating the guesses each time?
    """
    p_opt = scipy.optimize.curve_fit(Steinhart_Hart_eqn,
                                     Res_list,
                                     T_list,
                                     parameter_guesses)
    A,B,C,D = p_opt[0]

    return A,B,C,D

def plot_data(A,B,C,D,R_data,T_data):
    Res_list = np.linspace(100,100000,500)
    T_list = [Steinhart_Hart_eqn(R,A,B,C,D) 
              for R in Res_list]
    
    #Converts all data back into Celcius from Kelvin
    T_list = [T - 273.15 for T in T_list]
    T_data = [T - 273.15 for T in T_data]

    #Plot the data 
    plt.plot(Res_list,
             T_list,
             color="r",
             label="Temperature - Resistance curve")

    plt.scatter(R_data,
             T_data,
             color="b",
             label="Datasheet Data")
    plt.xlabel("Resistance/Ohms")
    plt.ylabel("Temperature/Celcius")
    plt.legend()
    plt.show()

"""
These parameter guesses are taken from a ChatGPT response purely because
I couldn't find a reliable source that stated typical parameter values.
If someone does find a better source then do change this, however it 
seems to work fairly well.
"""
parameter_guesses = [1.40e-3,
                     2.37e-4,
                     9.90e-8,
                     -6.0e-11]

A,B,C,D = fit_data(R_list,T_list,parameter_guesses)

"Print parameter values for use"
print("Parameter values: ")
print("A = " + str(A))
print("B = " + str(B))
print("C = " + str(C))
print("D = " + str(D))

plot_data(A,B,C,D,R_list,T_list)
