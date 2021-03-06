#    Dynamo-Fuse - POSIX-compliant distributed FUSE file system with AWS DynamoDB as backend
#    Copyright (C) 2013 Denis Mikhalkin
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

__author__ = 'Denis Mikhalkin'

from posix import R_OK, X_OK, W_OK
from dynamofuse.records.block import BlockRecord
from dynamofuse.base import BaseRecord
from errno import  ENOENT, EINVAL, EPERM
import os
from errno import *
from os.path import realpath, join, dirname, basename
from threading import Lock
from boto.dynamodb.exceptions import DynamoDBKeyNotFoundError, DynamoDBConditionalCheckFailedError
from time import time
from boto.dynamodb.condition import EQ, GT
from boto.dynamodb.types import Binary
import logging
import cStringIO
from stat import *
from fuse import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context
import itertools

if not hasattr(__builtins__, 'bytes'):
    bytes = str

class Link(BaseRecord):

    def createRecord(self, accessor, path, attrs, link):
        self.link = link
        attrs['link'] = link.path
        # Update link first to ensure that if the file is being modified and an exception is thrown we don't create the link record
        self.updateLink()
        try:
            BaseRecord.create(self, accessor, path, attrs)
        except DynamoDBConditionalCheckFailedError:
            raise FuseOSError(EEXIST)
        return self

    def getRecord(self):
        return self.link.getRecord()

    def getLink(self):
        return self.link

    def init(self, accessor, path, record):
        self.accessor = accessor
        self.path = path
        self.record = record
        self.readLink()

    def readLink(self):
        self.link = self.accessor.getRecordOrThrow(self.record['link'], attrs=None, ignoreDeleted=True)

    def updateLink(self):
        self.link.link()

    def delete(self, duringMove=False):
        # If deleting during move no need to update the n_link on file - the record is duplicated
        if not duringMove:
            with self.link.writeLock():
                # Lock ensures the file is exclusive. Then we delete link record - if that fails the lock is released and we can repeat.
                # Otherwise, if record is deleted we are guaranteed to be able to delete the file
                BaseRecord.delete(self)
                self.link.deleteFile(True)
        else:
            BaseRecord.delete(self)

    def read(self, offset, size):
        return self.link.read(offset, size)

    def write(self, data, offset):
        return self.link.write(data, offset)