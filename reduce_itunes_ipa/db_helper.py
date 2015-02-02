#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = "Pavel Miroshnichenko"
__email__ = "pavel@miroshnichen.co"


import argparse
import os
import os.path
import plistlib
import sys
import zipfile
import dropbox
import string
from os.path import getsize


#SETTINGS
#https://www.dropbox.com/developers/apps
dropbox_app_key = 'CHANGE_ME'
dropbox_app_secret = 'CHANGE_ME'
#db_path = "/Users/pavel/Dropbox/Applications/iTunesBackup/scripts/"
db_path = "CHANGE_ME"
db_file = db_path + "db_ios_apps.plist"


def dropbox_init(dropbox_app_key,dropbox_app_secret):
    from dropbox import client, rest, session
    APP_KEY = dropbox_app_key
    APP_SECRET = dropbox_app_secret
    ACCESS_TYPE = 'app_folder'
    sess = session.DropboxSession(APP_KEY, APP_SECRET, ACCESS_TYPE)
    oauth_token = ''
    oauth_token_secret = ''
    f = open("dropbox_token.txt",'r')
    if f:
      oauth_token = string.strip(f.readline())
      oauth_token_secret = string.strip(f.readline())
      f.close()
    if oauth_token == '' or oauth_token_secret == '':
      request_token = sess.obtain_request_token()
      url = sess.build_authorize_url(request_token)
      print "url:", url
      print "Please visit this website and press the 'Allow' button, then hit 'Enter' here."
      raw_input()
      access_token = sess.obtain_access_token(request_token)
      f = open("dropbox_token.txt","wb")
      f.write(access_token.key + '\n')
      f.write(access_token.secret)
      f.close()
    else:
      sess.set_token(oauth_token, oauth_token_secret)
    client = client.DropboxClient(sess)
    #print "linked account:", client.account_info()
    return client


def database_init():
    """
    Database initialization with sample data
    """
    d = { 'com.example.app': {"bundle_id":"com.example.app", "version_number":"1.0.0", "original_size":"254696"} };
    db_filename = open(db_file,'w')
    try:
        plistlib.writePlist(d, db_filename)
        db_filename.seek(0)
    finally:
        db_filename.close()


def data_extract(ipa_file):
    """
    reading iTunesMetadata.plist
    extracting softwareVersionBundleId
    extracting bundleShortVersionString
    counting file size
    """
    ipa_archive = zipfile.ZipFile(ipa_file, 'r')
    app_metadata = ipa_archive.read('iTunesMetadata.plist')
    plist_data = plistlib.readPlistFromString(app_metadata)
    sw_bundle = plist_data['softwareVersionBundleId']
    sw_version = plist_data['bundleShortVersionString']
    sw_size = getsize(ipa_file)
    return sw_bundle,sw_version,sw_size


def dropbox_search(file_name):
    """
    Searching by name in dropbox cloud folder
    """
    client = dropbox_init(dropbox_app_key,dropbox_app_secret)
    result = []
    search_request = client.search("/", file_name, file_limit=1000, include_deleted=False)
    if len(search_request) > 0:
        for item in search_request:
            result.append(item['path'])
    if len(result) > 0:
        return True
    else:
        return False


def dropbox_upload(ipa_file,file_name):
    """
    Upload *.ipa file to dropbox folder
    """
    print("### not found in dropbox!")
    client = dropbox_init(dropbox_app_key,dropbox_app_secret)
    f = open(ipa_file,'rb')
    if f:
        fsize = getsize(ipa_file)
        uploader = client.get_chunked_uploader(f, fsize)
        print "...uploading file ", file_name, fsize, "bytes..."
        while uploader.offset < fsize:
            try:
                upload = uploader.upload_chunked()
                print "."
            except rest.ErrorResponse, e:
                print "error uploading file!"
        uploader.finish("/IPAs/"+file_name)
        f.close()
        print "...file uploaded successfully"
    return 0


def database_write(db_data,sw_bundle,value):
    """
    Add/update application's info in plist file
    """
    db_data[sw_bundle] = value
    plistlib.writePlist(db_data, db_file)
    return 0


def reduce_file(ipa_file):
    """
    - *.ipa file will be damaged
    - delete all files from *.ipa, larger than 50kb
    - *.ipa size will be reduced
    """
    #archive.ipa
    #archive.ipa_out
    zin = zipfile.ZipFile (ipa_file, 'r')
    zout = zipfile.ZipFile (ipa_file + '_out', 'w')
    for item in zin.infolist():
        buffer = zin.read(item.filename)
        if item.filename == "Info.plist":
            zout.writestr(item, buffer)
        if item.filename == "iTunesMetadata.plist":
            zout.writestr(item, buffer)
        if item.filename == "iTunesArtwork":
            zout.writestr(item, buffer)
        if int(item.file_size) < 50000:
            zout.writestr(item, buffer)
    zout.close()
    zin.close()
    os.rename(ipa_file+'_out', ipa_file)
    return 0


def dropbox_query(ipa_file):
    file_name = os.path.basename(ipa_file)
    print("dropbox searching for: " + file_name)
    if dropbox_search(file_name):
        print("...passed")
    else:
        dropbox_upload(ipa_file, file_name)
    return 0


def database_query(ipa_file):
    """
    Searching for database records
    """
    sw_bundle = data_extract(ipa_file)[0]
    sw_version = data_extract(ipa_file)[1]
    db_data = plistlib.readPlist(db_file)
    value = {}
    value['bundle_id'] = sw_bundle
    value['version_number'] = sw_version
    file_name = os.path.basename(ipa_file)
    print("database searching for: " + file_name)
    if sw_bundle in db_data.keys():
        if sw_version == db_data[sw_bundle]['version_number']:
            print("...passed")
        elif sw_version < db_data[sw_bundle]['version_number']:
            print("...you have outdated version")
        else:
            print("### updating version in DB")
            database_write(db_data,sw_bundle,value)
    else:
        print("### not found in database!")
        database_write(db_data,sw_bundle,value)
    print("")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', action="store", help="<filename>.ipa")
    parser.add_argument('--dropbox', action="store_true", default=False, help="upload file to dropbox")
    parser.add_argument('--database', action="store_true", default=False, help="add/update database's record")
    parser.add_argument('--reduce_file', action="store_true", default=False, help="reduce selected *.ipa(will be damaged)")
    args = parser.parse_args()

    if not os.path.isfile(db_file):
        database_init()

    if not os.path.isfile(args.file):
        print("usage: db_helper.py [-h] [--file FILE] [--dropbox] [--database] [--reduce_file]")
        print("No such file or directory")
        sys.exit(-1)
    else:
        if args.file:
            ipa_file = args.file
            if args.dropbox:
                dropbox_query(ipa_file)
            if args.database:
                database_query(ipa_file)
            if args.reduce_file:
                reduce_file(ipa_file)
    return 0


if __name__ == "__main__":
    main()
    sys.exit(0)