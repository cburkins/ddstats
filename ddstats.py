#!/usr/bin/python

# --------------------------------------------------------------------------------------
# Author: Chad Burkins
# Date: Originally created in 2014
# NOTE: The next line (version) should be un-commented (variable is printed at the end of code)
#
version=1.02
#
# Purpose: Pulls statistics from DataDomain appliances.  The assumption is that you
# don't have API access to the devices, simply SSH login.  Uses "expect" to login,
# pull statistics, and summarize.
#
# v1.00: Code has been developed/used for a while, but decided to version all changes
# v1.01: Added feature to optionally hard-code username/pasword into script
#
# Ideas for the future
# -----------------------
# Rather than hard-code DD names into script, read them from an input file
# Sort the output by a specified column
# Add arg to limit the number of DD's queried (good for quicker testing)
# 
# --------------------------------------------------------------------------------------



# Requires Ubuntu package "python-dnspython"
import dns.resolver

# Requires prettytable python library for output
#   easy_install pip
#   pip install --upgrade PrettyTable
#   pip show PrettyTable     (you need version 0.7.2 or better)
import prettytable as pt

# Requires Ubuntu package "python-pexpect"
import pexpect

# Standard Python libraries
import getpass
import sys
import re
import time
import argparse

# Global constants
GB_Per_TB = 1024.0

# Full list of Data Domain 990's
ddlist=[
    ["itsusradd01m.jnj.com","Legacy"], 
    ["itsusradd02m.jnj.com","Legacy"], 
    ["itsusradd03m.jnj.com","Legacy"], 
    ["itsusradd04m.jnj.com","Legacy"], 
    ["itsusradd05m.jnj.com","Legacy"], 
    ["itsusradd06m.jnj.com","Legacy"], 
    ["itsusradd07m.jnj.com","Legacy"], 
    ["itsuscsdd01m.jnj.com","Legacy"], 
    ["itsuscsdd02m.jnj.com","Legacy"], 
    ["itsuscsdd03m.jnj.com","Legacy"], 
    ["itsuscsdd04m.jnj.com","Legacy"], 
    ["itsuscsdd05m.jnj.com","Legacy"], 
    ["itsuscsdd06m.jnj.com","Legacy"], 
    ["itsuscsdd07m.jnj.com","Legacy"], 
    ["itsbebedd01m.jnj.com","Legacy"], 
    ["itsbebedd02m.jnj.com","Legacy"], 
    ["itschzwdd01m.jnj.com","Legacy"],
    ["itschzwdd02m.jnj.com","Legacy"],
    ["itsusmpdd01m.jnj.com","Legacy"], 
    ["itsusmpdd02m.jnj.com","Legacy"],
    ["itssgsgdd01m.jnj.com","SDDC"],
    ["itsmycydd01m.jnj.com","SDDC"]
]

# Short list used for testing
#ddlist=[
#    ["itsuscsdd05m.jnj.com","Legacy"], 
#    ["itsusradd03m.jnj.com","Legacy"], 
#    ["itsusradd04m.jnj.com","Legacy"]
#] 


# Dictionary lookup for DD locations
city_location = {'be': 'Beerse',
                 'ra': 'Raritan',
                 'cs': 'Sungard',
                 'mp': 'MOPs',
                 'zw': 'Zuchwil',
                 'sg': 'Sngapor',
                 'cy': 'Malaysa'}


# Declare an emtpy dictionary
dd_info_per_type = {}
dd_info_per_city = {}

# Zero out appropiate records so we can accumulate in them (they need to be set at zero)
for ddrecord in ddlist:
    # It runs repeatedly, but really just zeros out two records (SDDC and Legacy)
    dd_info_per_type[ddrecord[1]] = {'ingested': 0.0,
                                     'written' : 0.0,
                                     'dedupe_ratio': 0.0}

# Zero out appropiate records so we can accumulate in them (they need to be set at zero)
for city in ["Beerse", "Raritan", "Sungard", "MOPs", "Zuchwil", "Sngapor", "Malaysa"]:
    # It runs repeatedly, but really just zeros out a few records (Beerse, Raritan, etc)
    dd_info_per_city[city] = {'ingested': 0.0,
                                     'written' : 0.0,
                                     'dedupe_ratio': 0.0}

# --------------------------------------------------------------------------------------

#  Input: The string to be printed
#  Descr: Prints the string, but only if the user has set the verbose flag via command
#         line
# Output: None

def vprint(print_string):
    if args.verbose:
        print "%s" % print_string

# --------------------------------------------------------------------------------------

#  Input: fully-qualified DNS sname
#  Descr: Performs simple DNS lookup to see if we have a valid name
# Output: Returns boolean, true if nslookup works

def nslookup_test(dnsname):

    try:
        answer = dns.resolver.query(dnsname)
    except:
        # Exit function, indicating failure 
        raise ValueError("DNS Lookup Failed")

    # If we made it here, then DNS lookup was successful, 
    # return a non-zero (successful) return code
    return 1

# ---------------------------------------------------------------------------------------------

#  Input: 
#           stream: previously opened "Expect" command stream
#          command: that we should send to the above "Expect" stream
#        prompt_re: Regular expression that defines a healthy command prompt for the device
#    search_string: Another RE identify which line of output we're hunting for 
#       field_list: list of numbers denoting which fields (within the desired line) to pass back
#  Descr:
#     Sends a given command to an active "Expect" stream, hunts for the desired regular 
#     expression within the output, and passes back the named fields
# Output: list of desired fields from the command output

def get_fields(stream, command, prompt_re, search_string, field_list):

    # Send command to DD
    try:
        stream.sendline(command)
    except:
        raise ValueError("Failed to send command to pexpect")

    # Look for the prompt again
    try:
        stream.expect(prompt_re, timeout=60)
    except:
        # If there was an excpetion.....
        raise ValueError("Sent filesys command, didn't recognize command prompt afterwards")

    output = stream.before.splitlines(True)

    # Initialize empty list that will be used for function return values
    return_list = []

    # Line-by-line, parse through the output from the command (e.g "filesys show compression")
    for line in output:

        # When you find the desired line (e.g. Currently Used), then parse the fields
        if re.search(search_string, line):
            
            # Remove the trailing newline
            line = line.rstrip()
            
            # Need to count up files, because if this DD is empty, the fiels are blank.
            if len(line.split()) < 5:
                # Bad data, assuming 0's for all fields
                for field in field_list:
                    return_list.append("0")
            else:
                # Get the requested fields from the matched line
                for field in field_list:
                    return_list.append(line.split()[field])


    # The "before" method should contain all the output up to the prompt
    # For debugging, uncommment the next line to see the whole output
    #print stream.before
    return return_list
       
# ---------------------------------------------------------------------------------------------

#  Input:
#     username: username for login to Data Domain device
#     password: Password for same account
#       ddname: DNS name for the Data Domain device
#  Descr:  Opens an "Expect" stream, and makes several calls to "get_fields", which sends commands
#          to that open Expect stream and captures output
# Output: A long list of relevant data fields

def dd_getinfo (username, password, ddname):


        try: 
            nslookup_test(ddname)
        except:
            raise ValueError("DNS Lookup Failed")


        # If you've never accessed a device before, then you might get this login
        #
        # The authenticity of host '<device-hostname>' can't be established.
        # RSA key fingerprint is <key-fingerprint>.
        # Are you sure you want to continue connecting (yes/no)? yes
        # Warning: Permanently added '<device-hostname>' (RSA) to the list of known hosts.
        # Data Domain OS
        # Password: 

        # Create appropiate SSH command to access the DataDomain
        ssh_command = "ssh -l \'na\\%s\' -o StrictHostKeyChecking=no %s" % (username, ddname)

        # ssh_command should be something like 'ssh -l \'na\\admin_cburkin\' <FQ-DNS-NAME>'
        try: 
            child = pexpect.spawn(ssh_command)
        except:
            raise ValueError("SSH Command failed, timeout ?")

        # Wait for password prompt, then send password
        # Default timeout is 30 seconds, but devices in Asia seem to be taking longer than that
        try:
            child.expect ('Password:', timeout=args.ddTimeout)
        except:
            raise ValueError("Timeout waiting for password prompt")

        # Send our password to the DataDomain
        child.sendline (password)

        # successful prompt looks like this.....
        #
        # Welcome to Data Domain OS 5.4.2.1-423209
        # ----------------------------------------
        # NA\admin_cburkin@<short-host-name># 



        # Check for a number of different scenarios
        # Either password reject, and we get another password prompt
        # or password accepted, and we see the welcome message
        i = child.expect ([pexpect.TIMEOUT, 'Password:', 'Welcome to Data Domain', 'Account locked due', pexpect.EOF], timeout=args.ddTimeout)
        if i==0:
            # Timeout from pexpect
            raise ValueError("Entered password, timeout waiting for prompt")
        elif i==1:
            # Got another password prompt, so password must have been rejected
            raise ValueError("Username/Password rejected")
        elif i==2:
            # Login was successful, next statement is just a dummy statement
            pass
        elif i==3:
            # You got something like "Account locked due to 7 failed logins"
            raise ValueError("Account locked due to failed logins")
        elif i==4:
            # You got EOF, so connection was externally terminated/failed"
            raise ValueError("Sent username and password, connection failed/terminated")
        else:
            raise ValueError("DD Didn't see Welcome Message")

        # Look for the proper prmopt, should look like this : NA\admin_cburkin@<short-hostname># 
        # Create a regular expression based on the given username (passed in)
        prompt_re = "...%s@..*# " % (username)

        try:
            child.expect(prompt_re, timeout=5)
        except:
            # If there was an excpetion.....
            raise ValueError("Didn't get the expected command prompt")
            
        # if we got to here, then we recognized command prompt


        # Output will look like this, we're looking for the "Currently Used:" line
        #
        #                   Pre-Comp   Post-Comp   Global-Comp   Local-Comp      Total-Comp
        #                      (GiB)       (GiB)        Factor       Factor          Factor
        #                                                                     (Reduction %)
        # ---------------   --------   ---------   -----------   ----------   -------------
        # Currently Used:   387857.4     16280.8             -            -    23.8x (95.8)
    
        # Split this section of code off to a subroutine, passing in the spawned expect stream
        a,b,c = get_fields(child, 
                           "filesys show compression", 
                           prompt_re, 
                           '^Currently Used:..*$',
                           [2,3,6])
        # Convert returns strings into proper variable types, and convert from GB to TB where appropiate
        total_ingest_TB = float(a) / GB_Per_TB
        total_written_TB = float(b) / GB_Per_TB
        x_factor = str(c)
        # Check to see if X-factor ends in x, if not, add x to end
        if not x_factor.endswith('x'):
            x_factor = x_factor + 'x'



        # Example of output from "filesys show space"
        #
        # Active Tier:
        # Resource           Size GiB   Used GiB   Avail GiB   Use%   Cleanable GiB*
        # ----------------   --------   --------   ---------   ----   --------------
        # /data: pre-comp           -    42185.0           -      -                -
        # /data: post-comp   298587.0     8611.1    289975.9     3%              0.5
        # /ddvar                308.1        3.7       288.7     1%                -
        # ----------------   --------   --------   ---------   ----   --------------
        #  * Estimated based on last cleaning of 2014/11/11 06:18:27.

        # Split this section of code off to a subroutine, passing in the spawned expect stream
        a,b,c,d = get_fields(child, 
                             "filesys show space", 
                             prompt_re, 
                             '^/data: post-comp..*$',
                             [2,3,4,5])
        # Convert returns strings into proper variable types, and convert from GB to TB where appropiate
        space_total_size_TB = float(a) / GB_Per_TB
        space_total_used_TB = float(b) / GB_Per_TB
        space_total_avail_TB = float(c) / GB_Per_TB
        space_pct_used = str(d)

        if (total_ingest_TB != 0):
            pct_saved = (((total_ingest_TB - total_written_TB) / total_ingest_TB) * 100.0)
        else:
            pct_saved = 0

        return total_ingest_TB, total_written_TB, x_factor, pct_saved, space_total_size_TB, space_total_used_TB, space_total_avail_TB, space_pct_used

# ---------------------------------------------------------------------------------------------

# ----------
# Main
# ----------


# Initalize empty variables
failures=[]
consecutive_failure_count=0
dd_number=0
cum_ingest_TB=0.0
cum_written_TB=0.0
data=[]
password=""

# Create ArgumentParser object
# By default, program name (shown in 'help' function) will be the same as the name of this file
# Program name either comes from sys.argv[0] (invocation of this program) or from prog= argument to ArgumentParser
# epilog= argument will be display last in help usage (strips out newlines)
parser = argparse.ArgumentParser(description='Queries DataDomain appliances for relevant capacity statistics')

# add_argument() tell ArgumentParser how to take strings from command line and turn them into objects
# The information is stored and used when parse_args() is called

# Test for verbose
parser.add_argument('-v', dest='verbose', action='store_true', help='verbose_mode')

# Command-line Parameters                                                                                                                    
#parser.add_argument('--ddUsername', required=True)
default_user="admin_cburkin"
parser.add_argument('--ddUsername', nargs='?', default=default_user)

# Optional arguments
# When using nargs='?', ene argument will be consumed from the command line if possible, 
#   and produced as a single item. If no command-line argument is present, the value 
#   from default will be produced
parser.add_argument('--failureLimit', nargs='?', default=3, type=int)
parser.add_argument('--ddTimeout', nargs='?', default=300, type=int)

# Get the object returned by parse_args
args = parser.parse_args()

# Prints lots of relevant information about access Data Domain's (but only if verbose is set)
vprint(" ")
vprint("Command Line Parameters")
vprint("---------------------------")
vprint("ddUsername = %s" % args.ddUsername)
vprint("failureLimit = %d" % args.failureLimit)
vprint("ddTimeout = %d seconds" % args.ddTimeout)
vprint("verbose = %s" % args.verbose)
vprint(" ")

# Get password for the specified DataDomin user account
# NOTE: To hardcode a password, just uncomment next line
# password="put-password-here"
if (len(password) < 4):
    # It appears that no password has been given to us, interactively query the user
    password = getpass.getpass("Data Domain Password for %s: " % args.ddUsername)
print
 
# Create headers for each column of data
data.append(["##", "DD-Name", "City","Type","Ingest","Written","DeDupe","%-Saved","D-Total","D-Used","D-Avail","D-%Used"])

# Small header
print "Contacting all DD's"
print "========================================================="

# Loop through all the Data Domain appliances
for ddrecord in ddlist:

    # Get the DD Name
    ddname=ddrecord[0]
    ddtype=ddrecord[1]

    # Let the user know that we're trying to contact the device
    sys.stdout.write("Accessing %s..." % ddname)
    sys.stdout.flush()

    # Start a timer so we can calculate elapsed time
    start = time.time()
    
    # Initalize the city_code
    city_code=''

    # if we see more than 2 consecutive failures, I'm guessing user entered their password wrong
    # No sense continuing, because will just registser a password failure on *every* device
    if consecutive_failure_count < args.failureLimit:

        # Try to log into Data Domain, send command, and extra data
        try:
            total_ingest_TB, total_written_TB, x_factor, pct_saved, space_total_size_TB, space_total_used_TB, space_total_avail_TB, space_pct_used = dd_getinfo(args.ddUsername, password, ddname)
        except ValueError, e:

            # For some reason, the login, command, and data extract failed
            # The reason for the exception is in string "e"
            # Report the name of the DataDomain that failed, and the reason
            failures.append([ddname, str(e)])
            # Add 1 to our count of consecutive failures
            consecutive_failure_count += 1

            # End timer and print elapsed time
            end = time.time()
            print " failure (%.1f seconds)" % (end - start)

        else:
            # Successfully got info from Data Domain

            # Simple line numbering used for printout
            dd_number += 1

            # Increment our running accumulations
            cum_ingest_TB += total_ingest_TB
            cum_written_TB += total_written_TB

            # Extract city code from DD Name
            city_code = ddname[5:7]

            # Update the cumulative totals by type (i.e. Legacy vs SDDC)
            dd_info_per_type[ddtype]['ingested'] += total_ingest_TB
            dd_info_per_type[ddtype]['written'] += total_written_TB
            dd_info_per_type[ddtype]['dedupe_ratio'] = dd_info_per_type[ddtype]['ingested'] / dd_info_per_type[ddtype]['written']

            # Update the cumulative totals by city (i.e. Raritan, Beerse, Sungard, etc)
            city = city_location[city_code];
            dd_info_per_city[city]['ingested'] += total_ingest_TB
            dd_info_per_city[city]['written'] += total_written_TB
            dd_info_per_city[city]['dedupe_ratio'] = dd_info_per_city[city]['ingested'] / dd_info_per_city[city]['written']

            # End timer and print elapsed time
            end = time.time()
            print " success (%.1f seconds)" % (end - start)

            # Output that info to new row in table
            data.append([dd_number, 
                         ddname, 
                         city_location[city_code], 
                         ddtype, "%.1f TB" % total_ingest_TB, 
                         "%.1f TB" % total_written_TB, 
                         x_factor, 
                         pct_saved, 
                         "%.1f TB" % space_total_size_TB, 
                         "%.1f TB" % space_total_used_TB, 
                         "%.1f TB" % space_total_avail_TB, 
                         space_pct_used])
            


            # We had a success, so decrement consecutive failure count (be careful not to go below 0)
            if consecutive_failure_count > 0:
                consecutive_failure_count -= 1
            
    else:
        failures.append([ddname, "Skipping, consecutive failures > %d" % args.failureLimit])

# Calculate the total cumulative dedupe ratio, being careful to avoid division by zero
if cum_written_TB > 0:
    cum_dedupe_ratio = cum_ingest_TB / cum_written_TB
else:
    cum_dedupe_ratio = 0


# Use PrettyTable to print out our data
# Create table using first row (which contains the column headers)
x = pt.PrettyTable(data[0])

# Add all the rows.  This loops from the 2nd item to the end
print "\n\n"
for row in data[1:]:
    x.add_row(row)

# Do a bit of formatting
x.float_format=".1"
x.align["Ingest"]="r"
print x

# Print out the accumulated totals for all Data Domains 
print
print "          Totals                         %8.1f TB %8.1f TB     %.1fx" % (cum_ingest_TB, cum_written_TB, cum_dedupe_ratio)


# Print out the accumulated totals for DD type (i.e. Legacy vs SDDC)
print "\n\n\nTotals by DD Type\n--------------------------------------"
for type in dd_info_per_type:

    # Compute the percentage space saved, being careful to check for division by zero
    try:
        pct_saved = ((dd_info_per_type[type]['ingested'] - dd_info_per_type[type]['written']) / dd_info_per_type[type]['ingested']) * 100.0  
    except ZeroDivisionError:
        pct_saved = 0.0

    # Print out results for this type (e.g. Legacy for SDDC)
    print "%10s %7.1f TB  %7.1f TB  %5.1fx  %4.1f %%" % (type, 
                                                         dd_info_per_type[type]['ingested'], 
                                                         dd_info_per_type[type]['written'], 
                                                         dd_info_per_type[type]['dedupe_ratio'],
                                                         pct_saved) 
print

# Print out the accumulated totals for DD by city (i.e. Beerse, Raritan, etc)
print "\n\n\nTotals by Location\n--------------------------------------"
for city in dd_info_per_city:

    # Compute the percentage space saved, being careful to check for division by zero
    try:
        pct_saved = ((dd_info_per_city[city]['ingested'] - dd_info_per_city[city]['written']) / dd_info_per_city[city]['ingested']) * 100.0  
    except ZeroDivisionError:
        pct_saved = 0.0

    # Print out results for this city (e.g. Raritan, Beerse, etc)
    print "%10s %7.1f TB  %7.1f TB  %5.1fx  %4.1f %%" % (city, 
                                                         dd_info_per_city[city]['ingested'], 
                                                         dd_info_per_city[city]['written'], 
                                                         dd_info_per_city[city]['dedupe_ratio'],
                                                         pct_saved) 
print

# Print out a list of all the Data Domains that failed, along with the failure reason
if failures:
    print "\nCould not access the following Data Domains"
    print "---------------------------------------------"
    for failure in failures:
        print "   %s (%s)" % (failure[0], failure[1])
    print
    print

# Print out the version
print "Version = %s" % version
print

# --------------------------------------------------------------------------------------
# --------------------------------------------------------------------------------------
# --------------------------------------------------------------------------------------
