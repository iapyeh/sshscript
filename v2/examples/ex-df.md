<div style="text-align:right"><a href="./index">Back to Index</a></div>

## Check Disk Usage
The Linux command df is used to display information about the file system usage on a Linux system. It shows the amount of disk space used and available on different file systems, such as hard drives, network file systems, and virtual file systems.

```
## filename: check.disk.space.spy
'''
Output sample of "df" on ubuntu:
Filesystem     1K-blocks     Used Available Use% Mounted on
udev             3962856        0   3962856   0% /dev
tmpfs             798408     1640    796768   1% /run
/dev/sda2      959863856 16191724 894843924   2% /
'''
import os, sys,time, traceback, json
import argparse
import __main__

parser = argparse.ArgumentParser()

parser.add_argument('-t','--threshold',dest='threshold', action='store',type=int,default=70,
                    help='percent of warning')

parser.add_argument('-a','--account',dest='account', action='store',default='',
                    help='ssh account (username@host)')
args = parser.parse_args(__main__.unknown_args)

## holding information of a partition
class Partition(object):
    def __init__(self,name,percent):
        self.name = name
        self.percent = percent

    ## create instance of Partition
    @classmethod
    def read(cls,line):
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

#### Executing 
```
# localhost
$sshscript check.disk.space.spy
# remote host
$sshscript check.disk.space.spy -t 65 -a user@host
```

![image](https://user-images.githubusercontent.com/4695577/182324261-f6e0579c-df39-4e76-bbfe-00722200450c.png)
