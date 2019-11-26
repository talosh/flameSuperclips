#   ================
#   BUNDLE SECTION
#   ================

def get_bundle_version(bundle_folder):
    bundle_version = None
    if os.path.isdir(bundle_folder):
        bundle_info_yml = os.path.join(bundle_folder, 'info.yml')
        if os.path.isfile(bundle_info_yml):
            with open(bundle_info_yml, 'r') as bundle_info_file:
                for info_line in bundle_info_file:
                    if info_line.startswith('version:'):
                        bundle_version = info_line.split('"')[1]    
    return bundle_version


def unpack_bundle(bundle_data):
    bundle_name = os.path.splitext(os.path.basename(__file__))[0] + '.bundle'
    bundle_folder = os.path.join(bundle_temp_folder, bundle_name)
    
    if os.path.isdir(bundle_folder):
        os.system('rm -rf ' + bundle_folder + '/*')
    else:
        os.makedirs(bundle_folder)

    # if get_bundle_version(bundle_folder) == __version__:
    #    return

    bundle_tar_file_path = os.path.join(bundle_temp_folder, (bundle_name + '.tar.bz2'))    
    with open(bundle_tar_file_path, 'wb') as bundle_tar_file:
        bundle_tar_file.write(base64.b64decode(bundle_data))
        bundle_tar_file.close()
    unpack_cmd = 'tar xjf ' + bundle_tar_file_path + ' -C ' + bundle_temp_folder 
    os.system(unpack_cmd)
    os.remove(bundle_tar_file_path)

def app_started(info):
    unpack_bundle('REPLACEME')

# unpack_bundle(bunle_data)