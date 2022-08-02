<div style="text-align:right"><a href="./index">Examples</a></div>

#### Scenario:

Check the disk space usage on localhost or remote host by command "df".

#### Solution:
```
#!/bin/env sshscript
# file: check.disk.space.spy
# Disk space checking, based on "df"
import os, sys,time, traceback, json
import argparse
import __main__

parser = argparse.ArgumentParser()

parser.add_argument('-t','--threshold',dest='threshold', action='store',type=int,default=70,
                    help='percent of warning')

parser.add_argument('-a','--account',dest='account', action='store',default='',
                    help='ssh account (username@host)')

args, unknown = parser.parse_known_args()

# Always false, since the -t has default value.
# Just being an example for use case of $.exit()
if not(args.threshold):
    parser.print_help()
    $.exit()

# holding information of a partition
class Partition(object):
    def __init__(self,name,percent):
        self.name = name
        self.percent = percent

    # create instance of Partition
    @classmethod
    def read(cls,line):
        '''
        Output sample of "df" on ubuntu:
        Filesystem     1K-blocks     Used Available Use% Mounted on
        udev             3962856        0   3962856   0% /dev
        tmpfs             798408     1640    796768   1% /run
        /dev/sda2      959863856 16191724 894843924   2% /
        '''
        cols = line.split()
        try:            
            return cls(cols[0],int(cols[4][:-1]))
        except ValueError:
            return None

# make connection if necessary
if args.account:
    from getpass import getpass
    pwd = getpass(f'password for {args.account}:')
    if pwd:
        $.connect(args.account,password=pwd)
    else:
        # use ssh key
        $.connect(args.account)

# show the host of execution
$hostname
print('host=',$.stdout.strip())
print('threshold=',args.threshold)

# get information by "df"
partitions = []
$df -k
rows = []
for line in $.stdout.split('\n'):
    if not line: continue
    p = Partition.read(line)
    if p: partitions.append(p)

# checking used percent by threshold
rows = []
for p in partitions:
    cols = ['',p.name,p.percent]
    if p.percent >= args.threshold:
        cols[0] = 'Warning'
    rows.append(cols)

#output
import tabulate
print(tabulate.tabulate(rows,['Status','Partition','Use Percent']))
```

#### execution examples
```
# localhost
$sshscript check.disk.space.spy
# remote host
$sshscript check.disk.space.spy -t 65 -a user@host
```
![image](https://user-images.githubusercontent.com/4695577/182322924-6041869b-c0d3-4c57-8043-4fa9aa777b12.png)