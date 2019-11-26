import os
import sys

import pickle
import base64
import getpass
sys.path.append("..")
import shotgun_api3
sys.path.remove("..")

# just hide it from casual observer
# insecure but good for now

def sg_login(site):
    login_details = {'login': '', 'password': 'REMOVED'}
    credentials_file = False
    working_folder = os.path.dirname(os.path.abspath(__file__))
    credentials_file_path = os.path.join(os.path.dirname(working_folder), '.credentials.pickle')

    try:
        credentials_file = open(credentials_file_path, "rb")
    except:
        login_details['login'] = raw_input("login:")
        login_details['password'] = getpass.getpass("password:")

    if credentials_file:
        try:
            login_details = eval(base64.urlsafe_b64decode(pickle.load(credentials_file)))
        except Exception, e:
            login_details['login'] = raw_input("login:")
            login_details['password'] = getpass.getpass("password:")
    
    sg = shotgun_api3.Shotgun(site, login = login_details.get('login'), password = login_details.get('password'))

    try:
        sg_active_projects = sg.find('Project', [['sg_status', 'is', 'active']], ['name'])
    except Exception, e:
        print "%s" % e
        return False
    
    try:
        credentials_file = open(credentials_file_path, "wb")
        pickle.dump(base64.urlsafe_b64encode(str(login_details)), credentials_file)
    except Exception, e:
        print "%s" % e
    finally:
        credentials_file.close()

#    return sg, login_details.get('login')
    return sg, 'shotgunEventDaemon API Script'
