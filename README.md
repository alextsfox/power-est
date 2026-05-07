# Solar Power Estimator
This python package gives a comprehensive estimate of power consumption for solar-powered systems, using daily historical weather and sun angles.

Currently, the package supports the following features:
- Daily historical weather data retrieval through `daymetpy` to get estimates of insolation and temperature for continental North America (Mexico, USA, Canada, Hawaii, and Puerto Rico).
- Sun angle calculations using `solarpy` to determine the position of the sun throughout the day
- Solar power and battery efficiency calculations based on temperature
- Solar panel orientation
- "Storm" mode to estimate power consumption during unusually cloudy or on snowy days
- Conservative power budget uncertainty estimates based on historical variability in weather conditions

## Installation
Currently, the package is not available on PyPI. To install, either add the `powerbudget` directory to your path or place it into your working directory. Depends on `daymetpy` (not `pydaymet`, which is a different package), `solarpy`, `numpy`, `pandas`, and `matplotlib`.

## Usage
See the `test.py` script for example usage. Use the `BudgetConfig` class to specify your system parameters, then call the `main` function to generate a plot of the estimated power budget for a given location. A more user-friendly API is in the works.