# Checking the syncing status of two MySQL servers

Last Updated on 2023/10/31

<div style="text-align:right;position:relative;top:-140px"><a href="./index">Back to Index</a></div>
This example performs the following tasks to check the syncing status of two MySQL servers:

- Connect to a bridge host. 

- Because the bridge host is the slave database host, switch to the root account and call the MySQL client on itself to collect information about the slave database.

- From the bridge host, connect to the master database, switch to the dbmaster account and call the MySQL client to collect information about the master database.

- Compare the information of the master database and the slave database.

```
## dbIsSynced is what we want to know, supposed to be False initially
dbIsSynced = False

def getMasterStatus(passwordForDb,passwordForSu):
    ## connect to master server
    with $.connect('user@masterdb',pkey=$.pkey('/home/user/.ssh/id_rsa')) as master:
        ## let's su to "dbmaster" to call mysql client.
        with master.su('dbmaster',passwordForSu) as suconsole:
            with suconsole.enter('mysql -uroot -p db','password',passwordForDb,exit='quit') as mysql:
                mysql('SHOW MASTER STATUS \G')
                data = mysql.stdout

    ## parse output of "SHOW MASTER STATUS"
    masterFile = None
    masterPosition = None
    for line in data.split('\n'):
        line = line.strip()
        if line.startswith('File:'):
            masterFile = line.split()[1].strip()
        elif line.startswith('Position:'):
            masterPosition = line.split()[1].strip()
    return {'file':masterFile , 'position': masterPosition}

def getSlaveStatus(passwordForDb,passwordForSudo):
    ## on the bridge host
    ## let's su to "root" to call mysql client.
    with $.sudo(passwordForSudo) as sudoconsole:
        with sudoconsole.enter('mysql -uroot -p db','password',passwordForDb,exit='quit') as mysql:
            mysql('SHOW SLAVE STATUS \G')
            data = mysql.stdout

    ## parse output of "SHOW SLAVE STATUS"
    slaveFile = None
    slavePosition = None
    slaveIoRunning = None
    slaveSqlRunning = None
    for line in data.split('\n'):       
        cols = [x.strip() for x in line.split(':')]
        if cols[0] == 'Master_Log_File':
            slaveFile = cols[1]
        elif cols[0] == 'Read_Master_Log_Pos':
            slavePosition = cols[1]
        elif cols[0] == 'Slave_IO_Running':
            slaveIoRunning = True if cols[1] == 'Yes' else False
        elif cols[0] == 'Slave_SQL_Running':
            slaveSqlRunning = True if cols[1] == 'Yes' else False
    return {
        'file':slaveFile,
        'position':slavePosition,
        'ioRunning':slaveIoRunning,
        'sqlRunning':slaveSqlRunning
    }

## Connect to a bridge host.
with $.connect('user@bridge') as bridge:

    ## call the MySQL client on the bridge host to collect information about the slave database.
    slaveInfo = getSlaveStatus(passwordForDb,passwordForSudo)

    ## From the bridge host, connect to the master database to collect information about the master database.
    masterInfo = getMasterStatus(passwordForDb,passwordForSu)

## Compare the information of the master database and the slave database.
if not(masterInfo['file'] and masterInfo['position']):
    pass
elif not(slaveInfo['file'] and slaveInfo['position'] and slaveInfo['ioRunning'] and slaveInfo['sqlRunning']):
    pass
elif masterInfo['position'] == slaveInfo['position'] and \
    masterInfo['file'] == slaveInfo['file'] and \
    slaveInfo['ioRunning'] and slaveInfo['sqlRunning']:
    dbIsSynced = True

```