#!/usr/bin/python

import os
import sys
import glob
import subprocess
import contextlib
import functools
import multiprocessing
import boto
import traceback
from multiprocessing.pool import IMapIterator

def _pickle_method(method):
    """
    Author: Steven Bethard (author of argparse)
    http://bytes.com/topic/python/answers/552476-why-cant-you-pickle-instancemethods
    """
    func_name = method.im_func.__name__
    obj = method.im_self
    cls = method.im_class
    cls_name = ''
    if func_name.startswith('__') and not func_name.endswith('__'):
        cls_name = cls.__name__.lstrip('_')
    if cls_name:
        func_name = '_' + cls_name + func_name
    return _unpickle_method, (func_name, obj, cls)


def _unpickle_method(func_name, obj, cls):
    """
    Author: Steven Bethard
    http://bytes.com/topic/python/answers/552476-why-cant-you-pickle-instancemethods
    """
    for cls in cls.mro():
        try:
            func = cls.__dict__[func_name]
        except KeyError:
            pass
        else:
            break
    return func.__get__(obj, cls)

copy_reg.pickle(types.MethodType, _pickle_method, _unpickle_method)

class AmazonS3:
	def __init__(self, keyid, key):
		# Create the connection
		self.conn = boto.connect_s3(keyid, key)
		self.log = "Using Amazon S3\n"
		
	def checkLocation(self, base_dir, backup_type):
		self.base_dir = base_dir
		self.backup_type = backup_type

		# get the bucket.  This API creates the bucket if it doesn't exist, and returns the bucket object if it does.
		self.bucket = self.conn.create_bucket(base_dir + "-pyback")
	
	def rotateBackup (self, maxFiles):
		# Get the current number of objects for this bckup type
		self.log += "Checking for old backups\n"
		priorBackups = self.bucket.list(prefix=self.backup_type)

		archives = []
		for backup in priorBackups:
			archives.append(backup.name)
		currentBackups = len(archives)

		if currentBackups <= maxFiles:
			self.log += "Number of backups (" + str(currentBackups) + ") has not reached the maximum threshold (" + str(maxFiles) + "). Will not remove previous backups.\n"
		else:
			while currentBackups > maxFiles:
				
				# Set the filename to be the first file returned.  Since we're using date-formatted filenames, this works.  Other naming schemes will require adjustment here.
				filename =archives[0]
				filename = str(filename)
				self.log += "Deleting " + filename + "\n"
				
				# Delete the object
				self.bucket.get_key(filename).delete()
				
				currentBackups -= 1
				
	def upload_cb(self, complete, total):
		sys.stdout.write(".")
		sys.stdout.flush()

	def _standard_transfer(self, transfer_file, use_rr):
		print " Upload with standard transfer, not multipart."
		new_s3_item = self.bucket.new_key(self.keyname)
		new_s3_item.set_contents_from_filename(transfer_file, reduced_redundancy=use_rr,
						      cb=upload_cb, num_cb=10)
		print

	def map_wrap(f):
		@functools.wraps(f)
		def wrapper(*args, **kwargs):
			return apply(f, *args, **kwargs)
		return wrapper

	def mp_from_ids(self, mp_id, mp_keyname, mp_bucketname):
		"""Get the multipart upload from the bucket and multipart IDs.

		This allows us to reconstitute a connection to the upload
		from within multiprocessing functions.
		"""
		conn = self.conn
		bucket = self.bucket
		mp = boto.s3.multipart.MultiPartUpload(bucket)
		mp.key_name = mp_keyname
		mp.id = mp_id
		return mp

	@map_wrap
	def transfer_part(self, instance, mp_id, mp_keyname, mp_bucketname, i, part):
		"""Transfer a part of a multipart upload. Designed to be run in parallel.
		"""
		mp = mp_from_ids(mp_id, mp_keyname, mp_bucketname)
		print " Transferring", i, part
		with open(part) as t_handle:
			mp.upload_part_from_file(t_handle, i+1)
		os.remove(part)
	
	@contextlib.contextmanager
	def multimap(self, cores=None):
		"""Provide multiprocessing imap like function.

		The context manager handles setting up the pool, worked around interrupt issues
		and terminating the pool on completion.
		"""
		if cores is None:
		    cores = max(multiprocessing.cpu_count() - 1, 1)
		def wrapper(func):
		    def wrap(self, timeout=None):
			return func(self, timeout=timeout if timeout is not None else 1e100)
		    return wrap
		IMapIterator.next = wrapper(IMapIterator.next)
		pool = ProcessingPool(cores)
		yield pool.imap
		pool.terminate()

	def _multipart_upload(self, tarball, mb_size, use_rr=True):
		"""Upload large files using Amazon's multipart upload functionality.
		"""
		cores = multiprocessing.cpu_count()
		def split_file(in_file, mb_size, split_num=5):
			prefix = os.path.join(os.path.dirname(in_file),
					      "%sS3PART" % (os.path.basename(tarball)))
			split_size = int(min(mb_size / (split_num * 2.0), 250))
			if not os.path.exists("%saa" % prefix):
				cl = ["split", "-b%sm" % split_size, in_file, prefix]
                                try:
                                    subprocess.check_call(cl)
                                except subprocess.CalledProcessError as e:
                                    self.log += "There was an issue splitting the file.\n "
                                    self.log += e.output + "\n"
                                    print e.output
			return sorted(glob.glob("%s*" % prefix))
		mp = self.bucket.initiate_multipart_upload(tarball, reduced_redundancy=use_rr)
		with self.multimap(cores) as pmap:
			for _ in pmap(self.transfer_part, ((mp.id, mp.key_name, mp.bucket_name, i, part)
						      for (i, part) in
						      enumerate(split_file(tarball, mb_size, cores)))):
			    pass
		mp.complete_upload()
		
	def pushBackup(self, backup_name, backup_file):
		backup_file += "/" + backup_name
		try:
			# Create the backup name to work with the RS Cloud pseudo-directory
			self.backup_name = self.backup_type + "/" + backup_name
		
			self.log += "Creating object for backup file: " + self.backup_name + "\n"
			self.keyname = self.bucket.new_key(self.backup_name)
		
			# Upload the backup file to remote storage
			mb_size = os.path.getsize(backup_file) / 1e6
			self.log += "File size:" + str(mb_size) + "Mb\n"
			if mb_size < 60:
			        self.log += "Using standard upload method\n"
				self._standard_transfer(backup_file, False)
			else:
			        self.log += "Using multipart upload\n"
				self._multipart_upload(backup_file, mb_size, False)
			self.key.set_acl=('private')
			return "Ok"
		except Exception, e:
			self.log += "There was an error creating the remote backup.\n"
			self.log += str(traceback.format_exc()) + "\n"
			self.log += "Backup file is located at " + backup_file + "\n"
			self.log += "Please move the backup manually\n"
			return "Error"
