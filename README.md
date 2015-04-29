##Welcome to Data Domain Stats##

**ddstats** is able to log into EMC Data Domain appliances and query for basic statistics.  If you own several Data Domain appliances, it gives you a quick high-level view of capacity, utilization, and deduplication efficiency.

###Requirements###

This script was developed on RHEL, and will likely work on any widely-used Linux distribution (e.g. SLES, Ubuntu, etc)

The following standard software is required and is likely already installed on your Linux distribution

- Python v2
- Python Expect
- Python DNS Resolver

You may need to install the following software

- Python PExpect
- Python PrettyTable (version 0.7.2 or better)

###Compatibility###

This script was designed to run against EMC Data Domain 990 appliances, though I'm guessing it will work against many other Data Domain models as well.

It was tested against DDOS 5.4

###Code Details###

This is a python script.  It uses ssh and expect to log into each Data Domain, run a few commands, gather the output, parse it, and format the data into a readable table.

The following commands are run:

- filesys show compression
- filesys show space



