"""
Code to be copy and pasted - then variables edited - so that its possible
to store and detect sudden changes in data for a given sensor.

This code will store N data points and calculate the mean and standard deviation,
if any data point goes beyond 2 standard deviations of the mean then it sends an 
error and keeps reading. To avoid constant text messages it just sends one then
a variable is set to True for one hour.
"""
import numpy as np

#Define statistical functions
def mean(data_set):
  """
  Calculates mean of a data_set where data_set is a list of numbers
  """
  return sum(data_set)/len(data_set)

def std(data_set,mean):
  if mean == None:
    mean = mean(data_set)
    
  data_set = [((d - mean) ** 2)/len(data_set) for d in data_set]
  
  return sum(data_set) ** 0.5

#Code to add before the try statement on the Pi
data_set = []
error_occurred = False
#Code to add into the try statement on the Pi.
#Change this line to the result from the arduino
result = np.random.rand()

if len(data_set) == 50:
  mean = mean(data_set)
  std = std(data_set,mean)

  if result < mean - 1.5*std or result > mean + 1.5*std:
    if error_occurred == False:
      #Send a text message error
    error_occurred = True
  else:
    data_set.pop(0)
    data_set.append(result)
    if error_occurred == True:
      #Error has stopped - potentially send a text
    error_occurred = False
else:
  data_set.append(result)

