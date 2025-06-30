"""
Code to be copy and pasted and then edited with custom upper and lower
bounds for each sensor type in use.

If sensor result is ever above or below the bounds, send a text message reporting
an error.
"""
#Define function to check for boundary breaking
def Boundary_error(upper,lower,result):
  if result > upper or result < lower: 
    #Send text message
    break
  return result
