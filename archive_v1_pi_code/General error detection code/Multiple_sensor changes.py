"""
This code can be copy and pasted into the try statement on the Pi code,
and will compare using standard error (must be tested at some point) of sensors.

This code will detect any sudden change occurring on one sensor in comparison 
to the rest. Using this in conjuction with other tests will ensure any variety of 
error is detected.
"""
import random
#input the standard error for the sensor
std_error = 0.5 #Quoted accuracy for GE-1337
#Change this line to create a list of each result individually
results_list = [random.randint(10,13) for i in range(4)]

#Check each entry against each following entry
for i, r_i in enumerate(results_list):
    for r_j in results_list[i+1:]:
        if abs(r_i - r_j) > 1.5*std_error:
          #One sensor is significantly different than another
          #Send text message
          break
