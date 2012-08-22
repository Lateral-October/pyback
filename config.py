#!/usr/bin/python

#Set the log file directory
logFile = "/var/log/backup"

# Set the temporary file directory
tmpDir = "/tmp/backup"

# Set the number of backup files to keep for each backup type as an associative array
maxFiles = {
	'Daily':7,
	'Weekly':4,
	'Monthly':6
	}

# Email notification settings
fromEmail = ""
toEmail = ""



#########################################################################################
#
# The following sections allow you to configure the individual backup sources
# Currently we have filesystem backups and MySQL backups
#
#########################################################################################

# fsBackup - choose to enable (True) or disable (False) the filesystem backup
# fsType - the type of backup to use.  Currently gzip is the only supported method
# fsBackupTmpPath - path to temporary storage of the backups
# fsBackupSrc - array of directories to back up
# fsBackupExclude = array of directories to exclude from backup
fsBackup = True
fsType = "gzip"
fsBackupSrc = [
	"/home",
	"/etc"
	]
fsBackupExclude = [
	"/home/aaron"
	]

# sqlBackup - choose to enable (True) or disable (False) the sql backup
# sqlType - Set the sql server type, done as a multi-dimensional array (list of lists)
#  backend - sql backend type.  Currently only supports mysql
#  user - sql username
#  pass - sql password
#  host - sql host
# dbMysqlUser - the MySQL user account that has access to the databases you wish to backup
# dbMysqlPass - dbMysqlUser's password
# dbMysqlHost - host of the MySQL server.
sqlBackup = True
sqlServers = [
	["backend","user","pass","host"],
	]

#########################################################################################
#
# The following sections allow you to configure the individual backup destinations
# 
#
#########################################################################################

# Configure the Rackspace backup destination
bpRackspace = True
bpRackspaceUser = ""
bpRackspaceAPI = ""

# Configure the Amazon S3 backup destination
bpAmazonS3 = True
bpAWSKeyID = ""
bpAWSKey=""
