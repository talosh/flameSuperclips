#   ================
#   CONFIGURATION
#   ================

# credentials pickle file location
credentials_pickle = 'credentials.pickle'
superclips_folder = '/var/tmp/flameSuperclips'
primary_root = '/jobs'

# folder to unpack plugin bundle on init:
bundle_temp_folder = '/var/tmp'
bookmark_file = '/opt/Autodesk/shared/bookmarks/cf_bookmarks.xml'

__version__ = 'v0.0.7 (Legacy)'

'''
VERSION HISTORY:
v0.0.7 - Made startup logic utilize app_started() hook for bundle unpacking
         and app_initialized() hook for actual superclips startup
v0.0.6 - Quick fix for startup logic in order to 
         shutdown aoo oriperly
v0.0.5 - Reworked standalone superClips app 
         to run from within plugin wrapper
v0.0.4 - Bundled as flame plugin
'''

import os
import sys
import base64
from xml.dom import minidom
import subprocess
import threading
import atexit

status_file_name = os.path.splitext(os.path.basename(__file__))[0] + '.enabled'
status_file_path = os.path.join(bundle_temp_folder, status_file_name)

bundle_name = os.path.splitext(os.path.basename(__file__))[0] + '.bundle'
bundle_folder = os.path.join(bundle_temp_folder, bundle_name)

'''
# start of quick wrapper for old version of superclips
'''

def app_initialized(project_name):    
    if os.path.isfile(status_file_path):
        start_superclips()

def os_system_wrapper(cmd):
    p = subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr)
    print ('started superclips scanner with pid %s' % p.pid)
    p.communicate()

def stop_superclips():
    pid = None
    pid_file_path = os.path.join(bundle_temp_folder, bundle_name, 'shotgunScanner.py.pid')
    if os.path.isfile(pid_file_path):
        try:
            pid_file = open(pid_file_path, 'r')
            pid = pid_file.read()
            pid_file.close()
        except:
            pass
    if pid:
        cmd = '/usr/bin/kill -9 ' + pid
        os.system(cmd)
        print ('stopping superclips scanner with pid %s' % pid)
        os.remove(pid_file_path)

def start_superclips():
    stop_superclips()
    cmd = os.path.join(bundle_temp_folder, bundle_name, 'shotgunScanner.py')
    
    print ('starting %s' % cmd)
    scanner_thread = threading.Thread(target=os_system_wrapper, args=(cmd,))
    scanner_thread.daemon = True
    scanner_thread.start()

    pid_file_path = os.path.join(bundle_temp_folder, bundle_name, 'shotgunScanner.py.pid')

def cleanup():
    stop_superclips()
    bundle_name = os.path.splitext(os.path.basename(__file__))[0] + '.bundle'
    bundle_folder = os.path.join(bundle_temp_folder, bundle_name)
    print ('cleaning up bundle folder %s' % bundle_folder)
    if os.path.isdir(bundle_folder):
        try:
            os.system('rm -rf ' + bundle_folder + '/*')
            os.system('rm -rf ' + bundle_folder + '/.*')
            os.removedirs(bundle_folder)
        except Exception as e:
            print (e)
            
atexit.register(cleanup)
'''
# end of quick wrapper for old version of superclips
'''

#   ================
#   FLAME HOOKS
#   ================

def get_main_menu_custom_ui_actions():
    if not os.path.isfile(status_file_path):
        return [
                {
                    'name': 'Superclips',
                    'actions': [
                        {
                            'name': 'Enable',
                            'execute': _enable
                        }
                    ]
                }
        ]
    else:
        return [
                {
                    'name': 'Superclips',
                    'actions': [
                        {
                            'name': 'Disable',
                            'execute': _disable
                        }
                    ]
                }
        ]

#   ================
#   PLUGIN LOGIC
#   ================

def _enable(selection):
    print ('starting superclips version %s' % __version__)

    ensure_superclips_folder(superclips_folder)
    ensure_superclips_in_bookmarks()

    os.system('/usr/bin/touch ' + status_file_path)
    os.system('/usr/bin/chmod a+rwx ' + status_file_path)
    start_superclips()

    import flame
    flame.execute_shortcut('Rescan Python Hooks')

    return

def _disable(selection):
    print ('stopping superclips version %s' % __version__)

    if os.path.isfile(status_file_path):
        os.remove(status_file_path)
    stop_superclips()
    remove_superclips_from_bookmarks()

    import flame
    flame.execute_shortcut('Rescan Python Hooks')

    return

def ensure_superclips_folder(folder):
    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except:
            print ('can not create %s' % folder)
            return False
    return True

def ensure_superclips_in_bookmarks():
    if os.path.isfile(bookmark_file):
        with open(bookmark_file, 'r') as xml_file:
            xml_string = xml_file.read()
            xml_file.close()
    if not xml_string:
        return False
    minify_step1 = xml_string.split('\n')
    minify_step2 = []
    for x in minify_step1:
        y = x.strip()
        if y: minify_step2.append(y)
    minify_step3 = ''.join(minify_step2)
    minify_step4 = minify_step3.replace('  ', '').replace('> <', '><')

    try:
        bookmarks = minidom.parseString(minify_step4)
    except:
        print ('superclips: can not parse bookmark file %s' % bookmark_file)
        return False

    sections = bookmarks.getElementsByTagName('Section')
    for section in sections:
        if section.getAttribute('Name') == 'Shared':
            shared_bookmarks = section.getElementsByTagName('Bookmark')
            for shared_bookmark in shared_bookmarks:
                if shared_bookmark.getAttribute('Name') == 'flameSuperclips':
                    return True
            superclips_bookmark = bookmarks.createElement('Bookmark')
            superclips_bookmark.setAttribute('Name', 'flameSuperclips')
            superclips_bookmark.setAttribute('Path', superclips_folder)
            section.appendChild(superclips_bookmark)
    with open(bookmark_file, 'w') as xml_file:
        xml_file.write(bookmarks.toprettyxml(encoding='utf-8'))
        xml_file.close()
    return True

def remove_superclips_from_bookmarks():
    if os.path.isfile(bookmark_file):
        with open(bookmark_file, 'r') as xml_file:
            xml_string = xml_file.read()
            xml_file.close()
    if not xml_string:
        return False
    minify_step1 = xml_string.split('\n')
    minify_step2 = []
    for x in minify_step1:
        y = x.strip()
        if y: minify_step2.append(y)
    minify_step3 = ''.join(minify_step2)
    minify_step4 = minify_step3.replace('  ', '').replace('> <', '><')

    try:
        bookmarks = minidom.parseString(minify_step4)
    except:
        print ('superclips: can not parse bookmark file %s' % bookmark_file)
        return False
    
    sections = bookmarks.getElementsByTagName('Section')
    for section in sections:
        if section.getAttribute('Name') == 'Shared':
            shared_bookmarks = section.getElementsByTagName('Bookmark')
            for shared_bookmark in shared_bookmarks:
                name = shared_bookmark.getAttribute('Name')
                path = shared_bookmark.getAttribute('Path')
                if name == 'flameSuperclips' and path == superclips_folder:
                    section.removeChild(shared_bookmark)
    with open(bookmark_file, 'w') as xml_file:
        xml_file.write(bookmarks.toprettyxml(encoding='utf-8'))
        xml_file.close()
    return True

