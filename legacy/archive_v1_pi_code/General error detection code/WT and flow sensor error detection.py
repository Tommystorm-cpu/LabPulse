"""
Code to be copy and pasted into the Pi with few edits such that errors are
detected and a message is sent.

This code detects issues with cooling of the cryostat based on water flow rate and 
temperature, if the temperature is too high for a given flow rate, then a text is sent.
"""

#Define linear fit
def temp_flowRate_fit(flow_rate):
  return (16/6)*flow_rate - 3.33

#Define variables based on results gained
#Current values are arbitrary
temperature = 15
flow_rate = 6

if temp_flowRate_fit(flow_rate) < temperature:
  #Cryostat is not being cooled - send message
  
