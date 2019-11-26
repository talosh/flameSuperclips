#!/usr/bin/python
print 'Superclips v0.0.4 (Legacy)'

import os
import sys
from datetime import datetime
import time
import pickle
import shutil
import glob
import re
import operator
import threading
from operator import itemgetter
from pprint import pprint, pformat
import collections

try:
    import shotgun_api3
except:
    try:
        working_folder = os.path.dirname(os.path.abspath(__file__))
        dependencies_folder = os.path.join(working_folder, 'dependencies')
        sys.path.insert(0, dependencies_folder)
        import shotgun_api3
        sys.path.pop(0)
    except:
        print '----'
        print 'unable to import shotgun_api3 python module'
        print "make sure it's istalled and in sys.path"
        print 'alternatively you can download it from ...'
        print 'unpack it and place in dependencies folder'
        if sys.path[0] == 'dependencies/':
            sys.path.pop(0)
        sys.exit(1)

from tools import flame_frame_spec_from_path
from tools import flame_clip_create
from tools import wiretap_get_metadata
from tools import openclip_get_metadata
from tools import get_logger
from tools import sg_login

from settings import get_setting

pid_file_path = os.path.abspath(__file__) + '.pid'
with open(pid_file_path, 'w') as pid_file:
    pid_file.write(str(os.getpid()))
    pid_file.close()
os.system('/usr/bin/chmod a+rwx ' + pid_file_path)
print ('creating pid file %s' % pid_file_path)
print ('starting supeclips scanner with pid %s' % os.getpid())

# global variables
flame_clips_background = []
log = None
fg_semaphore = False

def main():

    global flame_clips_background
    global log
    global fg_semaphore

    # login to shotgun

    SG_WEBSITE_URL = get_setting('SG_WEBSITE_URL')
    sg, username = sg_login(SG_WEBSITE_URL)
    if not sg:
        print ("can not login to %s as: %s" % (SG_WEBSITE_URL, username))
        sys.exit (1)

    # fire up logging
    log = get_logger(get_setting('LOG_FILE'))

    log.info('------')
    log.info('%s: succesfully logged in as: %s' % (get_setting('SG_WEBSITE_URL'), username))
    log.info('looking for new versions every %s sec' % get_setting('POLL_INTERVAL'))
    log.info('------')

    filters = list (get_setting('SG_FILTERS'))
    filters.append(['published_files.PublishedFile.published_file_type', 'is', {'type': 'PublishedFileType', 'id': get_setting('PUBLISH_FILE_TYPES')[0]}])
    filters.append(["updated_at", "in_last", get_setting('HOURS_TO_SCAN_BACK'), 'HOUR'])

    fields = [
        'project.Project.id', 
        'code',
        'entity', 
        'entity.Shot.id',
        'entity.Shot.code',
        'entity.Shot.sg_sequence',
        'project.Project.sg_fps_1',
        'project.Project.name',
        'project.Project.tank_name'
    ]

    order = [{'column':'updated_at','direction':'desc'}]

    sg_versions_current_scan = []
    sg_versions_previous_scan = []

    # start background scan

    thread = FuncThread(background_scan)
    thread.daemon = True
    thread.start()

    while True:
        
        fg_semaphore = True
        start_time = time.time()
        
        sg_versions_current_scan = []
        sg_versions_current_scan = sg.find('Version', filters, fields, order)

        for version in sg_versions_current_scan:

            # perform initial version sanity check and run the cutom filter_version hook
            if not filter_version(sg, version, log):
                continue

            # verified_publishes = filter_publishes(sg, version, log)
            verified_publishes = check_published_files(sg, version)

            if verified_publishes:
                
                verified_with_metadata = []

                for verified_publish in verified_publishes:
                    publish = get_published_file_metadata(verified_publish)
                    if publish:
                        verified_with_metadata.append(publish)

                openclips = build_openclips(verified_with_metadata)
                if openclips:
                    for openclip in openclips:
                        try:
                            openclip_file = open(openclip.get('path'), "rb")
                        except:
                            openclip_file = None

                        write_down_flame_clip(openclip.get('path'), openclip.get('xml'))

                        if openclip_file:
                            if 'superclips' in openclip.get('path'):
                                log.info('%s: updated superclip %s version %s' % (openclip.get('project_name'), openclip.get('shot_name'), version.get('code')))
                            else:
                                log.info('%s: updated %s version %s' % (openclip.get('project_name'), openclip.get('shot_name'), version.get('code')))
                        else:
                            if 'superclips' in openclip.get('path'):
                                log.info('%s: created superclip %s version %s' % (openclip.get('project_name'), openclip.get('shot_name'), version.get('code')))
                            else:
                                log.info('%s: created %s version %s' % (openclip.get('project_name'), openclip.get('shot_name'), version.get('code')))

        sg_versions_previous_scan = list(sg_versions_current_scan)

        fg_semaphore = False

        # process background queue

        openclips = []
        
        if flame_clips_background:
            # log.debug('%s clips in queue' % len(flame_clips_background))
            for i in xrange(min(get_setting('MAX_BG_CLIPS_PER_FG'), len(flame_clips_background)), 0, -1):
                openclip = flame_clips_background.pop( i-1 )
                openclips.append(openclip)
            if openclips:
                for openclip in openclips:
                    try:
                        openclip_file = open(openclip.get('path'), "rb")
                    except:
                        openclip_file = None
                        
                    write_down_flame_clip(openclip.get('path'), openclip.get('xml'))

                    if openclip_file:
                        if 'superclips' in openclip.get('path'):
                            log.info('%s: updated superclip %s found in background' % (openclip.get('project_name'), openclip.get('shot_name')))
                        else:
                            log.info('%s: updated %s found in background' % (openclip.get('project_name'), openclip.get('shot_name')))
                    else:
                        if 'superclips' in openclip.get('path'):
                            log.info('%s: created superclip %s found in background' % (openclip.get('project_name'), openclip.get('shot_name')))
                        else:
                            log.info('%s: created %s found in background' % (openclip.get('project_name'), openclip.get('shot_name')))

        fg_semaphore = False
        time.sleep(get_setting('POLL_INTERVAL'))
        log.debug ('fg cycle took %s' % (time.time() - start_time))

        #if len(flame_clips_background) > 0:

def filter_version(sg, version, log):
    """
    performs initial version check
    and runs a hook to allow custom version filtering
    returns version or None when declined
    """

    log.debug ("ckecking version %s" % version.get('code'))

    # filter out things blacklisted in config

    blacklist = get_setting('BLACKLIST')
    if blacklist:
        blacklisted_project_ids = blacklist.get('Project')
        if blacklisted_project_ids:
            if version.get('project.Project.id') in blacklisted_project_ids:
                log.debug ("filtering out version %s: project id %s blacklisted in config" % (version.get('code'), version.get('project.Project.id')))
                return None
        
        blacklisted_entity_ids = blacklist.get('Entity')
        if blacklisted_entity_ids:
            entity = version.get('entity')
            if entity:
                if entity.get('id') in blacklisted_entity_ids:
                    log.debug ("filtering out version %s: entity id %s blacklisted in config" % (version.get('code'), entity.get('id')))
                    return None

        blacklisted_version_ids = blacklist.get('Version')
        if blacklisted_version_ids:
            if version.get('id') in blacklisted_version_ids:
                log.debug ("filtering out version %s: version id %s blacklisted in config" % (version.get('code'), entity.get('id')))
                return None

    # perform custom filtering

    from hooks import filter_version_hook
    filtered_version = filter_version_hook(sg, version, log)
    
    if not filtered_version:
        log.debug ("filtering out version %s: declined by filer_version hook" % (version.get('code')))
        return None

    return filtered_version

def filter_publishes(sg, version, log):
    """
    performs checks on published files atached to version
    then runs a hook to allow custom published files filtering
    returns a list of verified published files if there's any left
    """

    verified_publishes = []
    filters = [['version.Version.id', 'is', version.get('id')]]
    fields = []

    pb_files = sg.find('PublishedFile', filters, fields)

    from hooks import filter_publishes_hook
    return filter_publishes_hook (sg, verified_publishes, log)

def check_published_files(sg, version):
    
    """
    checks:
    shots only at the moment
    if corresponding movie file present
    if we can parse the path cache
    if the ctual files are there
    
    some published files don't have version
    we don't know what to do with them
    so rule them out as well
    
    """
    global log

    # ask for published files of artist approved versions of the shot version belongs to
    filters = [
                ['entity', 'is', {'type': 'Shot', 'id': version.get('entity.Shot.id')}],
                #['version.Version.sg_artists_status', 'is', 'apr'],
                #['published_file_type.PublishedFileType.id', 'is', 29]
                ]

    fields = [
                'name',
                'published_file_type',
                'created_at',
                'version',
                'version_number',
                'version.Version.description',
                'version.Version.sg_artists_status',
                'path_cache',
                'entity',
                'entity.Shot.sg_fps',
                'task',
                'task.Task.step.Step.short_name',
                'task.Task.step.Step.code',
                'task.Task.step.Step.id'
                ]

    pb_files = sg.find('PublishedFile', filters, fields)

    # log.debug('checking %s' % version.get('code'))
    # log.debug('got %s published files to check' % len(pb_files))

    verified_publishes = []

    fps = get_setting('DEFAULT_FPS')
    
    # set fps from shotgun
    if version.get('project.Project.sg_fps_1'):
        fps = float(version.get('project.Project.sg_fps_1'))
        if int(fps) in get_setting('INT_FPS'):
            fps = int(fps)

    # override fps with the one from settings
    if get_setting('PROJECTS_FPS').get(version.get('project.Project.name')):
        fps = get_setting('PROJECTS_FPS').get(version.get('project.Project.name'))

    # published_image_sequences = sg.find('PublishedFile', filters, fields)
    # published_movies = sg.find('PublishedFile', filters2, fields)
    # test showed that it is almost 2 times faster to sort it ourselves
    # then to query shotgun two times

    published_image_sequences = []
    published_movies = []

    for pb_file in pb_files:

        pb_file_type = pb_file.get("published_file_type")
        if not pb_file_type:
            continue
        pb_file_id = pb_file_type.get("id")
        if pb_file_id == 9:    # movie
            published_movies.append(pb_file)
        elif pb_file_id == 29: # image sequence
            published_image_sequences.append(pb_file)
        else:
            continue

    published_movie = None

    for published_image_sequence in published_image_sequences:
        
        # we don't know what to do if publish is not bound to version
        pb_file_version = published_image_sequence.get('version')

        if not pb_file_version:
            continue
        
        # corresponding movie is usually somwhere around the same publish 
        #for y in range(x-2, min(len(published_movies), x+2)):
        #    if published_movies[y].get('version') == pb_file_version:
        #        published_movie = published_movies[y]
        
        #if not published_movie:
        #    log.debug ("searching whole array for a movie that corresponds %s" % published_image_sequences[x].get('path_cache'))
        path_cache = published_image_sequence.get('path_cache')
        
        if not path_cache:
            continue

        published_files_path = os.path.join(get_setting('STORAGE_ROOT'), path_cache)

        if os.path.isfile(os.path.join(os.path.dirname(published_files_path), '.openclip.ignore')):
            log.debug('found ignore marker in %s' % path_cache)
            continue

        if published_movies: 
            for movie in published_movies:
                if movie.get('version') == pb_file_version:
                    published_movie = movie
        else:
            pass

        if not published_movie:
            # log.debug ("could not find movie that corresponds %s\ngiving up" % published_image_sequence.get('path_cache'))
            continue
        
        movie_path = None
        movie_path = os.path.join(get_setting('STORAGE_ROOT'), published_movie.get('path_cache'))

        if not movie_path:
            # that's strange - we do not know what to do, so log it and move on
            #log.debug("%s\n\t no corresponding movie published file entry found for:\n\t %s" % (version.get('code'), published_files_path))
            continue
        
        if os.path.isfile(movie_path):
            # we have a movie for this publish
            # so let's check if we can build a flame clip path

            flame_friendly_path, status = flame_frame_spec_from_path(published_files_path)

            if not flame_friendly_path:
                if status == "no match":
                    # if we can't parse it there's no point to create openclip
                    # as we can't get proper flame format for frame range
                    # # so let's log it and move on to another published image sequence if any
                    log.debug("%s\n\tcan not parse %s" % (version.get('code'), published_files_path))
                
                elif status == "no files":
                    # thare are no actual files in place yet for this published image sequence
                    # so no point to do anything about it now
                    # let's just let it go
                    log.debug("%s\n\tthere are no files matching %s" % (version.get('code'), published_files_path))

                elif status == "value error":
                    # something is wrong with the file name
                    # usually when it is actually saved with the name like 
                    # 01_001_import_testImage_v017.%04d.exr instead of a real frame pattern
                    log.debug("%s\n\tthere are no files matching %s" % (version.get('code'), published_files_path))
                
                else:
                    # we don't know what happened but we can not get the flame path for the openclip anyway
                    log.debug("%s\n\tunknown error %s" % (version.get('code'), published_files_path))
                
                continue

            # if '1001' not in flame_friendly_path:
                # print flame_friendly_path
                # do nothing at the moment
            #    pass

            published_image_sequence.update({'flame_friendly_path': flame_friendly_path})

            metadata = {}
            metadata['fps'] = fps
            metadata['shot_name'] = version.get('entity.Shot.code')
            if version.get('entity.Shot.sg_sequence'):
                metadata['sequence_name'] = version.get('entity.Shot.sg_sequence').get('name')
            else:
                metadata['sequence_name'] = 'No_Sequence'
            metadata['project_name'] = version.get('project.Project.name')
            metadata['project_tank_name'] = version.get('project.Project.tank_name')

            # wiretap is slow
            # so we want to look into openclip if it is there
            # and see if we can just copy it over instead of querying it again

            published_file_name = published_image_sequence.get('name')
            version_name = published_image_sequence.get('version').get('name')
            published_file_path = published_image_sequence.get('path_cache')
            
            frame_pattern = re.compile(r"^(.+?)([0-9#]+|[%]0\dd)$")
            root, ext = os.path.splitext(os.path.basename(published_file_path))
            match = re.search(frame_pattern, root)
            
            # version_name = sorted_openclip_data[-1].get('version_name')
            # flame_clip_name =  "_".join(version_name.split()[:-1])+"_" + published_file_name.split(', Channel ')[1]+".clip"
            flame_clip_name = match.group(1)[:-6] + ".clip"
            flame_clip_folder = os.path.sep.join(os.path.dirname(published_file_path).split(os.path.sep)[:get_setting('FOLDER_DEPTH')+1])
            flame_clip_path = os.path.join(get_setting('FLAME_CLIP_ROOT'), flame_clip_folder, flame_clip_name)

            metadata['flame_clip_path'] = flame_clip_path

            published_image_sequence.update({'metadata': metadata})

            verified_publishes.append(published_image_sequence)

    
    # perform custom filtering
    from hooks import filter_publishes_hook
    return filter_publishes_hook (sg, verified_publishes, log)

def get_published_file_metadata(verified_publish):

    global log
    
    log
    flame_friendly_path = verified_publish.get('flame_friendly_path')
    metadata = verified_publish.get('metadata')
    flame_clip_path = metadata.get('flame_clip_path')

    # log.debug ('checking %s' % verified_publish.get('name'))
    # log.debug ('trying to open %s' % flame_clip_path)

    try:
        openclip_file = open(flame_clip_path, "rb")
        # log.info ('%s \nfile exists' % flame_clip_path)
        if flame_friendly_path in openclip_file.read():
            # log.info('getting metadata form file') 
            metadata['xml_stream'] = openclip_get_metadata(flame_clip_path, log, verified_publish.get('id'))

            if not metadata.get('xml_stream'):
                # try to get it from flame instead
                metadata['xml_stream'] = wiretap_get_metadata(flame_friendly_path, log, get_setting('WIRETAP_SERVER'))
                
        else:
            # log.info('new version, getting wiretap metadata')
            metadata['xml_stream'] = wiretap_get_metadata(flame_friendly_path, log, get_setting('WIRETAP_SERVER'))
    except:
        # log.info('no flame clip found, getting wiretap metadata\n%s' % flame_friendly_path)
        metadata['xml_stream'] = wiretap_get_metadata(flame_friendly_path, log, get_setting('WIRETAP_SERVER'))
    

    if not metadata.get('xml_stream'):
        log.warning('can not get metadata for %s' % flame_friendly_path)
        return False

    verified_publish.update({'metadata': metadata})

    return verified_publish

def build_openclips(verified_publishes):
    """
    it's quite a mess now
    should be revised for more clean code
    possibly another datatypes
    """

    global log

    openclips = []
    pfs = []

    # group publishes in another list by task id

    pfs_by_step = collections.defaultdict(list)

    for pf in verified_publishes:
        pfs_by_step[pf['task.Task.step.Step.short_name']].append(pf)
        
    pfs_by_step = list(pfs_by_step.values())

    # there are cases with same task name
    # but different tasks assigned to different human users
    # and they just continue publish versions
    # so it seem they sort it by step short_name instead

    # group nested lists by name
    # unique name in our case means separate openclip

    for pfs_step_group in pfs_by_step:

        pfs_by_name = collections.defaultdict(list)
        for pf in pfs_step_group:
            pfs_by_name[pf['name']].append(pf)
 
        pfs_by_name = list(pfs_by_name.values())
        pfs.append(pfs_by_name)

    # here we should have a topmost container grouped by task
    # and then grouped by name inside
    # pfs -> [[task1],[task2],[task3]]
    # [task] -> [[name1], [name2], [name3]]
    # [name] -> [[pf1], [pf2], [pf3]]
    # openclip is a [name] and clips there are publishes in name list

    for step_group in pfs:
        for name_group in step_group:
            openclip = {
                        'path': '',
                        'xml':  '',
                        'shot_name': '',
                        'sequence_name': '',
                        'project_name': '',
                        'project_tank_name': ''
            }

            openclip_data = []
            
            for pf in name_group:

                # build up version data to put in flame clip
                # and create a list to build

                openclip_vers_data = {
                                'name':'', 
                                'version_number':'',
                                'version_name':'',
                                'created_at':'',
                                'flame_friendly_path':'',
                                'path_cache':'',
                                'colourspace': get_setting('DEFAULT_COLOURSPACE')
                                }
                openclip_vers_data['name'] = pf.get('name')
                openclip_vers_data['version_number'] = pf.get('version_number')

                frame_pattern = re.compile(r"^(.+?)([0-9#]+|[%]0\dd)$")
                root, ext = os.path.splitext(os.path.basename(pf.get('path_cache')))
                # NOTE:
                #   match.group(0) is the entire path.
                #   match.group(1) is everything up to the frame number.
                #   match.group(2) is the frame number.
                match = re.search(frame_pattern, root)

                openclip_vers_data['version_name'] = match.group(1)[:-1]
                # openclip_vers_data['version_name'] = pf.get('version').get('name')

                openclip_vers_data['flame_friendly_path'] = pf.get('flame_friendly_path')
                openclip_vers_data['path_cache'] = pf.get('path_cache')
                openclip_vers_data['uid'] = pf.get('id')
                openclip_vers_data['vuid'] = str(pf.get('version').get('id')) + "_" + str(pf.get('id'))
                openclip_vers_data['fps'] = pf.get('metadata').get('fps')
                openclip_vers_data['created_at'] = pf.get('created_at').strftime("%Y/%m/%d %I:%M:%S %p")
                openclip_vers_data['shot_name'] = pf.get('metadata').get('shot_name')
                openclip_vers_data['sequence_name'] = pf.get('metadata').get('sequence_name')
                openclip_vers_data['project_name'] = pf.get('metadata').get('project_name')
                openclip_vers_data['project_tank_name'] = pf.get('metadata').get('project_tank_name')
                openclip_vers_data['xml_stream'] = pf.get('metadata').get('xml_stream')

                full_path = os.path.join(get_setting('STORAGE_ROOT'), pf.get('path_cache'))

                openclip_data.append(openclip_vers_data)

            sorted_openclip_data = sorted(openclip_data, key=itemgetter('version_number'))

            # build up flame clip path
            published_file_name = sorted_openclip_data[-1].get('name')
            published_file_path = sorted_openclip_data[-1].get('path_cache')

            frame_pattern = re.compile(r"^(.+?)([0-9#]+|[%]0\dd)$")
            root, ext = os.path.splitext(os.path.basename(published_file_path))
            match = re.search(frame_pattern, root)
            
            # version_name = sorted_openclip_data[-1].get('version_name')
            # flame_clip_name =  "_".join(version_name.split()[:-1])+"_" + published_file_name.split(', Channel ')[1]+".clip"
            flame_clip_name = match.group(1)[:-6] + ".clip"
            flame_clip_folder = os.path.sep.join(os.path.dirname(published_file_path).split(os.path.sep)[:get_setting('FOLDER_DEPTH')+1])
            flame_clip_path = os.path.join(get_setting('FLAME_CLIP_ROOT'), flame_clip_folder, flame_clip_name)
            
            openclip['path'] = flame_clip_path
            openclip['xml'] = flame_clip_create(sorted_openclip_data)
            openclip['shot_name'] = sorted_openclip_data[-1].get('shot_name')
            openclip['sequence_name'] = sorted_openclip_data[-1].get('sequence_name')
            openclip['project_name'] = sorted_openclip_data[-1].get('project_name')
            openclip['project_tank_name'] = sorted_openclip_data[-1].get('project_tank_name')            
            
            try:
                openclip_file = open(openclip.get('path'), "rb")
            except:
                openclip_file = None
                openclips.append(openclip)

            if openclip_file:
                if openclip_file.read() != openclip.get('xml'):
                    openclips.append(openclip)
                else:
                    pass

    ### now let's build superclip
    
    pfs = []

    # pfs_by_step = collections.defaultdict(list)

    # for pf in verified_publishes:
    #    pfs_by_step[pf['task.Task.step.Step.short_name']].append(pf)

    # pfs_by_step = list(pfs_by_step.values())
    
    # how put them in the right order?
    # this should be done in less hardcoded
    # and stupid way

    # put all from turnover first
    # only versions with artitsts status set to "approved"
    # if all(i == j for i, j in my_list):
    # my_list: [["A", "0"], ["B", "1"], ["C", "2"]]
    # so the if should be:
    # if A==0 and B==1 and C==2:
    #       do-something
    # else:
    #    pass

    for pf in verified_publishes:
        # if pf.get('task.Task.step.Step.short_name') == 'turnover' and pf.get('version.Version.sg_artists_status') == 'apr':
        if pf.get('task.Task.step.Step.short_name') == 'turnover' and pf.get('version.Version.sg_artists_status') != 'decl':

            pfs.append(pf)

    # put anything that doesn't fall in turnover, precomp, comp and flame comp after turnover
    # only versions with artists status set to "approved"
    defined_steps = [
                    'turnover',
                    'PC',
                    'comp',
                    'flame' 
                    ]

    # for pf in verified_publishes:
    #    if pf.get('task.Task.step.Step.short_name') not in defined_steps and pf.get('version.Version.sg_artists_status') == 'apr':
    #        pfs.append(pf)

    # then precomps
    for pf in verified_publishes:
        if pf.get('task.Task.step.Step.short_name') == 'PC':
            pfs.append(pf)

    # then comps
    for pf in verified_publishes:
        if pf.get('task.Task.step.Step.short_name') == 'comp':
            pfs.append(pf)
    # and then misterious flame step
    for pf in verified_publishes:
        if pf.get('task.Task.step.Step.short_name') == 'flame':
            pfs.append(pf)


    if not pfs:
        # we don't have any of steps specified to go to superclip
        return openclips

    # then build the whole thing
    openclip = {
                'path': '',
                'xml':  '',
                'shot_name': '',
                'sequence_name': '',
                'project_name': '',
                'project_tank_name': ''
    }

    openclip_data = []


    for pf in pfs:

        # build up version data to put in flame clip
        # and create a list to build
        openclip_vers_data = {
                        'name':'', 
                        'version_number':'',
                        'version_name':'',
                        'created_at':'',
                        'flame_friendly_path':'',
                        'path_cache':'',
                        'colourspace': get_setting('DEFAULT_COLOURSPACE')
                        }
        openclip_vers_data['name'] = pf.get('name')
        openclip_vers_data['version_number'] = pf.get('version_number')

        frame_pattern = re.compile(r"^(.+?)([0-9#]+|[%]0\dd)$")
        root, ext = os.path.splitext(os.path.basename(pf.get('path_cache')))
        # NOTE:
        #   match.group(0) is the entire path.
        #   match.group(1) is everything up to the frame number.
        #   match.group(2) is the frame number.
        match = re.search(frame_pattern, root)

        openclip_vers_data['version_name'] = match.group(1)[:-1] + '    \t[' + pf.get('task.Task.step.Step.code').replace(' ', '') + ']'
        # openclip_vers_data['version_name'] = pf.get('version').get('name') + ' - ' + pf.get('name').split(', Channel ')[1] + '\t[' + pf.get('task.Task.step.Step.code') + ']'
        
        openclip_vers_data['flame_friendly_path'] = pf.get('flame_friendly_path')
        openclip_vers_data['path_cache'] = pf.get('path_cache')
        openclip_vers_data['uid'] = pf.get('id')

        # version id should be unique in superclip
        # so let's combine it with published file id
        openclip_vers_data['vuid'] = str(pf.get('version').get('id')) + "_" + str(pf.get('id'))

        openclip_vers_data['fps'] = pf.get('metadata').get('fps')
        openclip_vers_data['created_at'] = pf.get('created_at').strftime("%Y/%m/%d %I:%M:%S %p")

        openclip_vers_data['shot_name'] = pf.get('metadata').get('shot_name')
        openclip_vers_data['sequence_name'] = pf.get('metadata').get('sequence_name')
        openclip_vers_data['project_name'] = pf.get('metadata').get('project_name')
        openclip_vers_data['project_tank_name'] = pf.get('metadata').get('project_tank_name')
        openclip_vers_data['xml_stream'] = pf.get('metadata').get('xml_stream')

        full_path = os.path.join(get_setting('STORAGE_ROOT'), pf.get('path_cache'))        
        openclip_data.append(openclip_vers_data)
    # we don't want to sort superclip
    # sorted_openclip_data = sorted(openclip_data, key=itemgetter('version_number'))

    # build up flame clip path
    flame_clip_name =  openclip_data[-1].get('shot_name') + ".clip"
    flame_clip_path = os.path.join(get_setting('FLAME_CLIP_ROOT'),
                                    openclip_data[-1].get('project_tank_name'),
                                    'superclips',
                                    openclip_data[-1].get('sequence_name'), 
                                    flame_clip_name)

    openclip['path'] = flame_clip_path
    openclip['xml'] = flame_clip_create(openclip_data)
    openclip['shot_name'] = openclip_data[-1].get('shot_name')
    openclip['sequence_name'] = openclip_data[-1].get('sequence_name')
    openclip['project_name'] = openclip_data[-1].get('project_name')
    openclip['project_tank_name'] = openclip_data[-1].get('project_tank_name')

    try:
        openclip_file = open(openclip.get('path'), "rb")
    except:
        openclip_file = None
        openclips.append(openclip)

    if openclip_file:
        if openclip_file.read() != openclip.get('xml'):
            openclips.append(openclip)
        else:
            pass
            
    return openclips
    
def write_down_flame_clip(flame_clip_path, xml_string):

    global log
    global settings

    # double check if we want to write in the clip root path
    if not flame_clip_path.startswith(get_setting('FLAME_CLIP_ROOT')):
        log.warning("DANGER: BUG: attemting to write outside clip root %s") % get_setting('FLAME_CLIP_ROOT')
        return False
    
    # make a backup of the clip file before we update it
    #
    # note - we are not using the template system here for simplicity
    # (user requiring customization can always modify this hook code
    # themselves). There is a potential edge case where the backup file
    # cannot be written at this point because you are on a different machine
    # or running with different permissions.

    # backup_path = "%s.backup_%s" % (
    #    flame_clip_path,
    #    datetime.now().strftime("%Y%m%d_%H%M%S")
    # )

    backup_path = "%s.backup" % (
        flame_clip_path)

    # create folders
    if not os.path.exists(os.path.dirname(flame_clip_path)):
        old_umask = os.umask(0)

        try:
            os.makedirs(os.path.dirname(flame_clip_path), 0777)
        except Exception, e:
            log.error("Failed to create a folder %s: %s" % (os.path.dirname(flame_clip_path), e))

        os.umask(old_umask)

    fh = None
 
    if not os.path.isfile(flame_clip_path):
        try:
            fh = open(flame_clip_path, "wt")
        except Exception, e:
            log.error("Failed to open file for writing %s: %s" % (flame_clip_path, e))

        try:
            fh.write(xml_string)
        except Exception, e:
            log.error("Failed to write file %s: %s" % (flame_clip_path, e))            
        finally:
            if fh:
                fh.close()
    else:
        try:
            cmd = 'cp ' + flame_clip_path + ' ' + backup_path
            os.system(cmd)
            # shutil.copy(flame_clip_path, backup_path)
        except Exception, e:
            log.error(
                "Failed to create a backup copy of the Flame clip file '%s': "
                "%s" % (flame_clip_path, e)
            )
        try:
            fh = open(flame_clip_path, "wt")
        except Exception, e:
            log.error("Failed to open file for writing %s: %s" % (flame_clip_path, e))

        try:
            fh.write(xml_string)
        except Exception, e:
            log.error("Failed to write file %s: %s" % (flame_clip_path, e))  
        finally:
            if fh:
                fh.close()

    return True

def background_scan():
    
    global flame_clips_background
    global log
    global fg_semaphore

    #filters = [
    #    ['entity', 'is', {'type': 'Shot', 'id': 14770}],
    #    ['project', 'is', {'type': 'Project', 'id': 255}],
    #    ['project.Project.sg_status', 'is_not', 'finished'],
    #    ['project.Project.sg_status', 'is_not', 'Dev'],
    #    ['project.Project.sg_status', 'is_not', 'Lost'],
    #    ['published_files.PublishedFile.published_file_type', 'is', {'type': 'PublishedFileType', 'id': get_setting('PUBLISH_FILE_TYPES')[0]}],
    #]

    filters = list (get_setting('SG_FILTERS'))
    filters.append(['published_files.PublishedFile.published_file_type', 'is', {'type': 'PublishedFileType', 'id': get_setting('PUBLISH_FILE_TYPES')[0]}])

    fields = [
        'project.Project.id', 
        'code',
        'entity', 
        'entity.Shot.id',
        'entity.Shot.code',
        'entity.Shot.sg_sequence',
        'project.Project.sg_fps_1',
        'project.Project.name',
        'project.Project.tank_name'
    ]

    order = [{'column':'updated_at','direction':'desc'}]

    filter_presets = [{'preset_name': 'LATEST', 'latest_by': 'ENTITIES_CREATED_AT'}]

    SG_WEBSITE_URL = get_setting('SG_WEBSITE_URL')
    bg, username = sg_login(SG_WEBSITE_URL)

    while True:

        bg_start_time = time.time()

        bg_versions = bg.find('Version', filters, fields, order, additional_filter_presets=filter_presets)

        for version in bg_versions:

            if not filter_version(bg, version, log):
                continue

            # verified_publishes = filter_publishes(bg, version, log)

            verified_publishes = check_published_files(bg, version)

            if verified_publishes:

                verified_with_metadata = []

                for verified_publish in verified_publishes:

                    # let the fg thread to squeeze in
                    # until I figure out
                    # how to run verification
                    # without being blocked

                    while fg_semaphore:
                        time.sleep(0.1)

                    publish = get_published_file_metadata(verified_publish)
                    if publish:
                        verified_with_metadata.append(publish)

                openclips = build_openclips(verified_with_metadata)
                if openclips:
                    for openclip in openclips:
                        flame_clips_background.append(openclip)

        log.debug ('bg cycle took %s sec' % (time.time() - bg_start_time))
        
class FuncThread(threading.Thread):
    def __init__(self, target, *args):
        self._target = target
        self._args = args
        threading.Thread.__init__(self)
    def run(self):
        self._target(*self._args)

if __name__ == "__main__":
    main ()
