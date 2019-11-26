#!/usr/bin/python

import os
import sys
import pickle
import base64
import getpass

from pprint import pprint

credentials_pickle = 'credentials.pickle'
login_details = {'login': '', 'password': 'REMOVED'}

login_details['login'] = raw_input("script or user name:")
login_details['password'] = getpass.getpass("script key or password:")

try:
    credentials_file = open(credentials_pickle, 'wb')
    credentials_string = str(login_details)
    encoded_credentials_string = base64.urlsafe_b64encode(credentials_string.encode())
    pickle.dump(encoded_credentials_string, credentials_file)
    credentials_file.close()
except Exception as e:
    print('%s' % e)

print ('reading back')

try:
    credentials_file = open(credentials_pickle, 'rb')
    read_login_details = eval(base64.urlsafe_b64decode(pickle.load(credentials_file)))
except Exception as e:
    print('%s' % e)

pprint (read_login_details)
