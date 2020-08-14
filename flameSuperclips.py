#   ================
#   CONFIGURATION
#   ================

SUPERCLIPS_FOLDER = '/var/tmp/flameSuperclips'
SERVER_URL = 'http://shotgunlex.tdiuk.net'
SHORT_LOOP = 2      # Hours
LONG_LOOP = 9       # Days
RETRO_LOOP = 299    # Days

DEBUG = False

#   ================
#   END OF CONFIGURATION
#   ================

__version__ = 'v0.1.12'

'''
VERSION HISTORY:
v0.1.12 - dimentions and pixel layout from EXR's added to openclip xml
v0.1.11 - filter out roto and MM steps
v0.1.10 - filter out exr's without RGB channels in header
v0.1.9  - track name changed to "t0" to retain compatibility with legacy superclips
        - fixed bug when short loop starts twice instead of utility loop
        - minor debug messages fixes
v0.1.8  - reworked project name detection
        - steps, projects and sequences update moved to a separate utility loop
        - timeout added to retro loop and set to 12 hrs
v0.1.7  - project scanner renamed to update_active_projects
        - update_active_projects updates self.active_projects dict directly
        - commented out all active_projects filters but functionality retained
v0.1.6  - Added a sloght delay before starting retro loop
v0.1.5  - Replaced entity id cache with published file id cache
v0.1.4  - Added entity id cache for retro loop
v0.1.3  - Cosmetic menu fixes
v0.1.2  - Fix for startup logic when there's no supeclips folder
v0.1.1  - Added main Menu enable/Disable controls
v0.1.0  - Initial version
'''

import os
import sys
import atexit
import base64
import collections
import fnmatch
import re
import shutil
import socket
import subprocess
import threading
import time

from xml.dom import minidom
from datetime import datetime, timedelta
from struct import unpack
from pprint import pprint, pformat

import sgtk

class logger(object):
    global DEBUG
    def __init__(self):
        self.name, ext = os.path.splitext(
            os.path.basename(__file__)
        )
    def info(self, message):
        print('[%s] [%s] %s' % (
            self.name, 
            datetime.now().strftime('%H:%M:%S'), 
            message)
        )
    def debug(self, message):
        if DEBUG:
            print('[%s] [%s] %s' % (
                self.name, 
                datetime.now().strftime('%H:%M:%S'), 
                message)
            )


class shotgunScanner(object):
    
    global SUPERCLIPS_FOLDER
    global SERVER_URL
    global SHORT_LOOP
    global LONG_LOOP

    def __init__(self):
        self.log = logger()
        self.log.info('scanner is waking up')
        # In case of using API script add your your script credentils here
        # {login: 'script_name', password: 'api_key'}
        self.script_login_details = None
        self.storage_root = '/jobs'

        self.shotgun_steps_list = {}
        self.active_projects = {}
        self.update_sg_steps()
        self.update_active_projects()
        self.sequences = self.get_sequences()

        self.loops = []
        self.threads = True
        self.loops.append(threading.Thread(target=self.short_loop, args=(30, )))
        self.loops.append(threading.Thread(target=self.long_loop, args=(900, )))
        self.loops.append(threading.Thread(target=self.retro_loop, args=(43200, )))
        self.loops.append(threading.Thread(target=self.utility_loop, args=(300, )))

        for loop in self.loops:
            loop.daemon = True
            loop.start()

        self.verified_pb_files = set()
    
    def terminate_loops(self):
        self.threads = False
        for loop in self.loops:
            loop.join()
        self.log.info('scanner loops terminated')

    def loop_timeout(self, timeout, start):
        time_passed = int(time.time()-start)
        if timeout <= time_passed:
            return
        else:
            for n in range((timeout-time_passed)*10):
                if not self.threads:
                    break
                time.sleep(0.1)
    
    def short_loop(self, timeout):
        while self.threads:
            start = time.time()
            pb_files = self.get_sg_publishes([
                ['updated_at', 'in_last', SHORT_LOOP, 'HOUR']
                ])

            self.process_publishes(pb_files, 'short')
            self.loop_timeout(timeout, start)

    def long_loop(self, timeout):
        while self.threads:
            start = time.time()

            pb_files = self.get_sg_publishes([
                ['updated_at', 'in_last', LONG_LOOP, 'DAY']
            ])
            self.log.debug('long loop found %s publishes for %s days in %s sec' % (
                len(pb_files), 
                LONG_LOOP, 
                time.time()-start
            ))

            self.process_publishes(pb_files, 'long')
            self.loop_timeout(timeout, start)
       
    def retro_loop(self, timeout):
        # give a way for other loops to start
        time.sleep(1)
        
        day = 0
        start = time.time()

        while self.threads:
            day_start = time.time()
            start_window = datetime.now() - timedelta(days=day)
            end_window = datetime.now() - timedelta(days=day+1)
            pb_files = self.get_sg_publishes([
                ['updated_at', 'between', start_window, end_window]
            ])
            self.log.debug('retro loop found %s publishes for day %s in %s sec' % (
                len(pb_files), 
                day, 
                time.time()-day_start
            ))
            
            # filter out published files already found on a basis of entity id
            # (added to self.verified_pb_files in self.process_publishes() function)

            filtered_pb_files = list()
            for pb_file in pb_files:
                pb_file_id = pb_file.get('id')
                if pb_file_id:
                    if pb_file_id in self.verified_pb_files:
                        continue
                    else:
                        filtered_pb_files.append(pb_file)
                else:
                    self.log.debug('no id for pb file?') 
                    self.log.debug(pformat(pb_file)) 
            pb_files = list(filtered_pb_files)
            self.log.debug('retro loop filtered down to %s publishes, cache size %s' % (
                len(pb_files),
                len(self.verified_pb_files) 
            ))
            
            self.process_publishes(pb_files, 'retro')
            
            if day < RETRO_LOOP:
                day += 1
            else:
                self.log.debug('retro loop completed %s days in %s sec' % (
                    RETRO_LOOP,
                    time.time()-start
                ))
                self.loop_timeout(timeout, start)
                day = 0
                start = time.time()
                self.verified_pb_files = set()

    def utility_loop(self, timeout):
        while self.threads:
            start = time.time()
            self.update_sg_steps()
            self.update_active_projects()
            
            if not self.threads:
                break

            self.sequences = self.get_sequences()

            self.log.debug('utility loop completed in %s sec' % (
                time.time()-start
            ))

            self.loop_timeout(timeout, start)


    def process_publishes(self, pb_files, loop):
        self.log.debug('process_publishes: starting with %s published files for %s loop' % (
            len(pb_files),
            loop
        ))

        start = time.time()
        
        pb_files = self.filter_publishes(pb_files)
            
        entity_ids = set()
        entity_types = dict()
        for pb_file in pb_files:
            entity = pb_file.get('task.Task.entity')
            if entity:
                entity_id = entity.get('id')
                if entity_id:
                    entity_ids.add(entity_id)
                    entity_types[entity_id] = entity.get('type')

        self.log.debug('process_publishes: found %s entities in %s loop' % (
            len(entity_ids),
            loop 
        ))

        for entity_id in sorted(list(entity_ids), reverse=True):
            
            entity_pb_files = list()
            found_entity_publishes = self.get_sg_publishes([
                ['entity', 'is', {'type': entity_types.get(entity_id), 'id': entity_id}]
            ])

            if not self.threads:
                return False

            for entity_pb_file in found_entity_publishes:
                entity_pb_file_id = entity_pb_file.get('id')
                if entity_pb_file_id:
                    self.verified_pb_files.add(entity_pb_file_id)

            entity_pb_files = self.filter_publishes(found_entity_publishes)
            if not entity_pb_files:
                continue
            sorted_entity_pb_files = list()
            sorted_entity_pb_files = self.sort_published_files(entity_pb_files)
            if not sorted_entity_pb_files:
                continue
            scanned_entity_pb_files = self.scan_folders(sorted_entity_pb_files)
            if not scanned_entity_pb_files:
                continue

            if not self.threads:
                return False

            verified_entity_pb_files = list()
            verified_entity_pb_files = self.verify_published_files(sorted_entity_pb_files)
            if not verified_entity_pb_files:
                continue
            
            superclip = self.compose_superclip(verified_entity_pb_files)
            superclip_path = self.compose_superclip_path(verified_entity_pb_files)

            if not self.threads:
                return False

            for path in superclip_path:
                if os.path.isfile(path):
                    try:
                        openclip_file = open(path, 'rb')
                    except:
                        self.log.info('unable to open superclip file %s' % path)
                        continue
                else:
                    self.log.info('creating superclip ** %s' % str(path)[len(SUPERCLIPS_FOLDER)+1:])
                    self.write_openclip(path, superclip)
                    continue

                if openclip_file.read() != superclip:
                    self.log.info('updating superclip ** %s' % str(path)[len(SUPERCLIPS_FOLDER)+1:])
                    self.write_openclip(path, superclip)
                else:
                    continue
                
        self.log.debug('process_publishes: processed %s enteties for %s loop in %s sec' % (
            len(entity_ids),
            loop,
            time.time()-start
        ))

        return True

    def update_active_projects(self):
        project_ignore_statuses = [
        #    'Finished',
        #    'Lost'
        ]
        
        # refresh list of active projects
        active_projects = {}

        authenticator = sgtk.authentication.ShotgunAuthenticator()
        try:
            user = authenticator.create_script_user(
                api_script = self.login_details['login'],
                api_key = self.login_details['password'],
                host = SERVER_URL
            )
        except:
            return active_projects

        sg = user.create_sg_connection()

        all_projects = sg.find('Project', [], ['name', 'tank_name', 'sg_status', 'sg_fps', 'sg_fps_1'])
            
        for project in all_projects:
            if project.get('sg_status') not in project_ignore_statuses:
                active_projects[project.get('id')] = project
        self.active_projects = dict(active_projects)
        return active_projects

    def get_sequences(self):
        authenticator = sgtk.authentication.ShotgunAuthenticator()
        try:
            user = authenticator.create_script_user(
                api_script = self.login_details['login'],
                api_key = self.login_details['password'],
                host = SERVER_URL
            )
        except:
            return []
        sg = user.create_sg_connection()
        sequences = sg.find('Sequence', [], ['id', 'code', 'episode', 'shots'])
        return sequences

    def update_sg_steps(self):
        authenticator = sgtk.authentication.ShotgunAuthenticator()
        try:
            user = authenticator.create_script_user(
                api_script = self.login_details['login'],
                api_key = self.login_details['password'],
                host = SERVER_URL
            )
        except:
            return None
        sg = user.create_sg_connection()
        steps = sg.find('Step', [], ['short_name'])
        for step in steps:
            id = step.get('id')
            short_name = step.get('short_name')
            self.shotgun_steps_list[id] = short_name

    def get_sg_publishes(self, filters):
        authenticator = sgtk.authentication.ShotgunAuthenticator()
        try:
            user = authenticator.create_script_user(
                api_script = self.login_details['login'],
                api_key = self.login_details['password'],
                host = SERVER_URL
            )
        except:
            return None
        sg = user.create_sg_connection()
        fileds = [
            'name',
            'created_at',
            'sg_colourspace',
        #    'sg_image_file_type',
            'published_file_type',
            'path_cache',
            'path_cache_storage',
            'project.Project.id',
        #    'project.Project.name',
        #    'project.Project.tank_name',
        #    'project.Project.sg_status',
            'sg_source_location',
            'task.Task.entity',
        #    'task.Task.entity.Entity.id',
        #    'task.Task.entity.Entity.type',
        #    'task.Task.step.Step.short_name',
            'task.Task.step.Step.id',
            'version.Version.id',
            'version.Version.code',
            'version_number',
            'version.Version.sg_artists_status'
            ]
        return sg.find(
            'PublishedFile',
            filters,
            fileds
            )

    def filter_publishes(self, pb_files):
        pb_file_types = [
            'Deep Image Sequence',
            'Image Sequence',
            'Playblast',
            'Rendered Image',
            'Movie'
        ]

        allowed_extensions = [
            'dpx', 
            'cin', 
            'exr', 
            'jpg', 
            'jpeg', 
            'tiff', 
            'tif', 
            'png'
        ]

        omit_steps = [
            'mm',
            'roto'
        ]

        filtered_pb_files = list()

        for pb_file in pb_files:

            # testing and debug filter
            # filter start:
            '''
            entity = pb_file.get('task.Task.entity')
            if not entity:
                continue
            if entity.get('id') != 30523:
                continue
            '''
            # filter end

            # filter out unnesessary published file types
            pb_file_type = pb_file.get('published_file_type', None)
            if pb_file_type:
                pb_file_type_name = pb_file_type.get('name', None)
            else:
                continue
            if pb_file_type_name not in pb_file_types:
                continue

            # check if there's entity to work with
            pb_task_enitiy = pb_file.get('task.Task.entity')
            if not pb_task_enitiy:
                continue
            
            # check if there's a pipeline step connected to task
            pb_task_step_id = pb_file.get('task.Task.step.Step.id')
            if not pb_task_step_id:
                continue

            # filter out steps to omit
            pb_task_step_name = self.shotgun_steps_list.get(pb_task_step_id)
            if pb_task_step_name and (pb_task_step_name.lower() in omit_steps):
                continue

            # check if there's a version linked
            pb_file_version_id = pb_file.get('version.Version.id')
            if not pb_file_version_id:
                continue
            
            # filter out extensions that are not in the list above
            path_cache = pb_file.get('path_cache')
            if not path_cache:
                continue
            root, ext = os.path.splitext(os.path.basename(path_cache))
            if ext[1:].lower() not in allowed_extensions:
                continue
            
            # filter out artists declined versions
            if pb_file.get('version.Version.sg_artists_status') == 'decl':
                continue

            filtered_pb_files.append(pb_file)
        
        return filtered_pb_files  

    def sort_published_files(self, pb_files):
        pfs = []
        steps = []
        pfs_by_step = collections.defaultdict(list)

        for pf in pb_files:
            pfs_by_step[pf['task.Task.step.Step.id']].append(pf)

        pfs_by_step = list(pfs_by_step.values())                    
        pfs_by_step.sort(key=self.get_step_sorting_order)

        for step in pfs_by_step:
            step.sort(key=self.get_publish_sorting_order)

        for step in pfs_by_step:
            for pf in step:
                pfs.append(pf)

        # debug
        # pfs = pfs[:len(pfs) - 1]
        #
            
        return pfs

    def get_step_sorting_order(self, published_file_group):

        steps_sort_order = [
            'turnover',
            'PC',
            'anything else goes here',
            'comp',
            'flame' 
            ]

        # create slots of a size of a maximum number of steps
        # and sort using steps_sort_order

        max_step_id = max(self.shotgun_steps_list.keys())
        try:
            anything_else = steps_sort_order.index('anything else goes here') 
        except:
            steps_sort_order.insert(1, 'anything else goes here')
            anything_else = 1

        current_step_id = published_file_group[0].get('task.Task.step.Step.id')
        if not current_step_id:
            current_step_id = 0
        current_step_name = self.shotgun_steps_list.get(current_step_id)

        if current_step_name:
            if current_step_name in steps_sort_order:
                index = steps_sort_order.index(current_step_name)
                return (index * max_step_id) + published_file_group[0].get('task.Task.step.Step.id', 0)
            elif current_step_name.lower() in (step.lower() for step in steps_sort_order):
                # we have the step name but it is just written in a different way
                steps_sort_order_caseinsensetive = list()
                for step in steps_sort_order:
                    steps_sort_order_caseinsensetive.append(step.lower())
                index = steps_sort_order_caseinsensetive.index(current_step_name.lower())
                return (index * max_step_id) + published_file_group[0].get('task.Task.step.Step.id', 0)
            else:
                return (anything_else * max_step_id) + published_file_group[0].get('task.Task.step.Step.id', 0)
        else:
            return (anything_else * max_step_id + published_file_group[0].get('id'))

    def get_publish_sorting_order(self, published_file):
        return published_file.get('id')

    def scan_folders(self, pb_files):
        scanned_pb_files = []

        for pb_file in pb_files:
            path = os.path.dirname(os.path.join(self.storage_root, pb_file.get('path_cache')))
            try:
                file_names = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
            except:
                continue

            pb_file['file_names'] = sorted(file_names)
            scanned_pb_files.append(pb_file)

            if not self.threads:
                return scanned_pb_files

        return scanned_pb_files

    def verify_published_files(self, pb_files):

        verified_publishes = list()
        flame_friendly_path = None
        
        for published_image_sequence in pb_files:
            
            published_files_path = os.path.join(self.storage_root, published_image_sequence.get('path_cache'))
            file_names = published_image_sequence.get('file_names')
            
            if not file_names:
                continue
            
            # ignore if marker is there
            if '.openclip.ignore' in file_names:
                continue
            
            # build a flame friendly path from the sequence and check consistency
            flame_friendly_path = self.flame_frame_spec_from_path(published_files_path, file_names)
            if not flame_friendly_path:
                continue

            published_image_sequence.update({'flame_friendly_path': flame_friendly_path})

            # try to read exr header
            published_image_sequence['parsed_header'] = self.parse_header_data({})
            match = re.search('\[(.*)-(.*)\]', flame_friendly_path)
            if match:
                path = flame_friendly_path.replace('[' + match.group(1) + '-' + match.group(2) + ']', match.group(1))
                header = self.read_header(path)
                if header:
                    channels = header.get('channels')
                    if channels:
                        chlist = channels.get('chlist')
                        if ('R' not in chlist.keys()) and ('G' not in chlist.keys()) and ('B' not in chlist.keys()):
                            continue
                        else:
                            published_image_sequence['parsed_header'] = self.parse_header_data(header)            

            verified_publishes.append(published_image_sequence)
            
            if not self.threads:
                return verified_publishes

        return verified_publishes

    def parse_header_data(self, header):
        parsed_header = {
            'nbChannels': '',
            'pixelLayout': '',
            'channelsDepth': '',
            'pixelRatio': '',
            'width': '',
            'height': ''

        }
        
        channels = header.get('channels')
        if not channels:
            return parsed_header
        chlist = channels.get('chlist')
        if not chlist:
            return parsed_header

        if ('A' not in chlist.keys()):
            parsed_header['nbChannels'] = '3'
            parsed_header['pixelLayout'] = 'BGR'
        else:
            parsed_header['nbChannels'] = '4'
            parsed_header['pixelLayout'] = 'ABGR'

        green_channel = chlist.get('G')
        if not green_channel:
            return parsed_header
        if green_channel.get('pixeltype') == 'FULL':
            parsed_header['channelsDepth'] = '32'
        elif green_channel.get('pixeltype') == 'HALF':
            parsed_header['channelsDepth'] = '16'
        else:
            parsed_header['channelsDepth'] = '8'

        pixelAspectRatio = header.get('pixelAspectRatio')
        if not pixelAspectRatio:
            parsed_header['pixelRatio'] = ''
        else:
            if 'float' in pixelAspectRatio.keys():
                parsed_header['pixelRatio'] = str(pixelAspectRatio.get('float'))
            else:
                parsed_header['pixelRatio'] = '1'

        displayWindow = header.get('displayWindow')
        if not displayWindow:
            displayWindow = header.get('dataWindow')
        if displayWindow:
            box2i = displayWindow.get('box2i')
            if box2i:
                if len(box2i) == 4:
                    parsed_header['width'] = str(box2i[2]+1)
                    parsed_header['height'] = str(box2i[3]+1)

        return parsed_header
        
    def compose_superclip_path(self, sorted_entity_pb_files):
        path = set()
        for pb in sorted_entity_pb_files:
            entity = pb.get('task.Task.entity')
            entity_type = entity.get('type', '')
            entity_name = entity.get('name', 'unknown')
            entity_id = entity.get('id', None)

            episode_name = ''
            sequence_name = ''
            for sequence in self.sequences:
                shots = sequence.get('shots')
                if not shots:
                    continue
                for shot in shots:
                    if shot.get('id') == entity_id:
                        episode = sequence.get('episode')
                        if episode:
                            episode_name = episode.get('name', '')
                        sequence_name = sequence.get('code', '')

            
            pb_project_id = pb.get('project.Project.id')
            if not pb_project_id:
                project_name = 'unknown_project'
            elif pb_project_id in self.active_projects.keys():
                project_name = self.active_projects[pb_project_id].get('tank_name')
                if not project_name:
                    project_name = self.active_projects[pb_project_id].get('name')
                    if not project_name:
                        project_name = 'unknown_project_id' + str(pb_project_id)
            else:
                # try to refresh project list and check again
                self.update_active_projects()
                if pb_project_id in self.active_projects.keys():
                    project_name = self.active_projects[pb_project_id].get('tank_name')
                    if not project_name:
                        project_name = self.active_projects[pb_project_id].get('name')
                        if not project_name:
                            project_name = 'unknown_project_id' + str(pb_project_id)
                else:
                    project_name = 'unknown_project_id' + str(pb_project_id)
                

            if sequence_name:
                path.add(os.path.join(
                                    SUPERCLIPS_FOLDER, 
                                    project_name,
                                    'superclips',
                                    sequence_name, 
                                    (entity_name + '.clip')))

            # if episode_name:
            #    path.add(os.path.join(
            #                        SUPERCLIPS_FOLDER, 
            #                        project_name,
            #                        'episodes',
            #                        episode_name,
            #                        sequence_name,
            #                        (entity_name + '.clip')))

            path.add(os.path.join(
                                    SUPERCLIPS_FOLDER, 
                                    project_name, 
                                    (str(entity_type)+'s').lower(),
                                    (entity_name + '.clip')))

        return list(path)

    def compose_superclip(self, pb_files):
        latest_version_id = pb_files[-1].get('version.Version.id')
        latest_pf_id = pb_files[-1].get('id')
        current_version_id = "%s" % str(latest_version_id) + "_" + str(latest_pf_id)
        clip_fps = self.guess_superclip_fps(pb_files)

        xml = minidom.Document()
        clip = xml.createElement('clip')
        clip.setAttribute('type', 'clip')
        clip.setAttribute('version', '4')
        xml.appendChild(clip)

        handler = xml.createElement('handler')
        handler_name = xml.createElement('name')
        handler_name.appendChild(xml.createTextNode('MIO Clip'))
        handler_version = xml.createElement('version')
        handler_version.appendChild(xml.createTextNode('2'))
        handler_longName = xml.createElement('longName')
        handler_longName.appendChild(xml.createTextNode('MIO Clip'))
        handler_options = xml.createElement('options')
        handler_options.setAttribute('type', 'dict')
        handler_opt_scan_pattern = xml.createElement('ScanPattern')
        handler_opt_scan_pattern.setAttribute('type', 'string')
        handler_opt_scan_pattern.appendChild(xml.createTextNode(''))
        handler_options.appendChild(handler_opt_scan_pattern)
        handler.appendChild(handler_name)
        handler.appendChild(handler_version)
        handler.appendChild(handler_longName)
        handler.appendChild(handler_options)

        tracks = xml.createElement("tracks")
        track = xml.createElement("track")
        track.setAttribute("uid", "t0")
        tracktype = xml.createElement("trackType")
        tracktype.appendChild(xml.createTextNode('video'))
        track.appendChild(tracktype)

        edit_rate = xml.createElement("editRate")
        edit_rate.setAttribute("type", "rate")
        edit_rate.appendChild(xml.createTextNode(str(clip_fps)))
        track.appendChild(edit_rate)

        feeds = xml.createElement("feeds")
        feeds.setAttribute("currentVersion", current_version_id)
        track.appendChild(feeds)
        tracks.appendChild(track)
        versions = xml.createElement("versions")
        versions.setAttribute("currentVersion", current_version_id)

        clip.appendChild(handler)
        clip.appendChild(tracks)
        clip.appendChild(versions)

        # taken from tk-nuke nuke_update_flame_clip
        first_video_track = None
        for track in xml.getElementsByTagName("track"):
            for track_type in track.getElementsByTagName("trackType"):
                if "video" in [c.nodeValue for c in track_type.childNodes]:
                    first_video_track = track
                    break
                if first_video_track is not None:
                    break

        if first_video_track is None:
            self.log.warning('Could not find the first video track in the published clip file')

        clip_version = None
        for span in xml.getElementsByTagName("spans"):
            span_version = span.attributes.get("version")
            if span_version is not None:
                clip_version = span_version.value
            if clip_version is not None:
                break

        # feed uid is a published file shotgun id
        # in superclip version uid is shotgun version id + "_" + published file id
        
        for pb_file in pb_files:
            version_id = str(pb_file.get('version.Version.id'))
            publish_id = str(pb_file.get('id'))
            vuid = version_id + '_' + publish_id

            frame_pattern = re.compile(r"^(.+?)([0-9#]+|[%]0\dd)$")
            root, ext = os.path.splitext(os.path.basename(pb_file.get('path_cache')))
            #   match.group(0) is the entire path.
            #   match.group(1) is everything up to the frame number.
            #   match.group(2) is the frame number.
            match = re.search(frame_pattern, root)
            step_code = self.shotgun_steps_list.get(pb_file.get('task.Task.step.Step.id'))
            version_name = match.group(1)[:-1] + '    \t[' + step_code.replace(' ', '') + ']'

            feed_node = xml.createElement("feed")
            feed_node.setAttribute("type", "feed")
            feed_node.setAttribute("uid", publish_id)
            feed_node.setAttribute("vuid", vuid)
            
            storage_format = xml.createElement("storageFormat")
            storage_format.setAttribute("type", "format")
            type_node = xml.createElement("type")
            type_node.appendChild(xml.createTextNode('video'))
            storage_format.appendChild(type_node)
            colourspace = xml.createElement("colourSpace")
            colourspace.setAttribute("type", "string")
            flame_colourspace = self.translate_colourspace_name_for_flame(pb_file.get('sg_colourspace'))
            colourspace.appendChild(xml.createTextNode(flame_colourspace))
            storage_format.appendChild(colourspace)

            parsed_header = pb_file.get('parsed_header')
            if parsed_header.get('nbChannels'):
                nb_channels = xml.createElement("nbChannels")
                nb_channels.setAttribute("type", "uint")
                nb_channels.appendChild(xml.createTextNode(parsed_header.get('nbChannels')))
                storage_format.appendChild(nb_channels)

            if parsed_header.get('pixelLayout'):
                pixel_layout = xml.createElement("pixelLayout")
                pixel_layout.setAttribute("type", "string")
                pixel_layout.appendChild(xml.createTextNode(parsed_header.get('pixelLayout')))
                storage_format.appendChild(pixel_layout)

            if parsed_header.get('channelsDepth'):
                channels_depth = xml.createElement("channelsDepth")
                channels_depth.setAttribute("type", "uint")
                channels_depth.appendChild(xml.createTextNode(parsed_header.get('channelsDepth')))
                storage_format.appendChild(channels_depth)
            
            if parsed_header.get('pixelRatio'):
                pixel_ratio = xml.createElement("pixelRatio")
                pixel_ratio.setAttribute("type", "float")
                pixel_ratio.appendChild(xml.createTextNode(parsed_header.get('pixelRatio')))
                storage_format.appendChild(pixel_ratio)

            if parsed_header.get('width'):
                width = xml.createElement("width")
                width.setAttribute("type", "uint")
                width.appendChild(xml.createTextNode(parsed_header.get('width')))
                storage_format.appendChild(width)

            if parsed_header.get('height'):
                height = xml.createElement("height")
                height.setAttribute("type", "uint")
                height.appendChild(xml.createTextNode(parsed_header.get('height')))
                storage_format.appendChild(height)

            feed_node.appendChild(storage_format)

            sample_rate = xml.createElement("sampleRate")
            sample_rate.appendChild(xml.createTextNode(str(clip_fps)))
            feed_node.appendChild(sample_rate)

            start_timecode = xml.createElement("startTimecode")
            start_timecode.setAttribute("type", "time")
            rate = xml.createElement("rate")
            rate.appendChild(xml.createTextNode(str(clip_fps)))
            start_timecode.appendChild(rate)
            nbticks = xml.createElement("nbTicks")
            nbticks.appendChild(xml.createTextNode('0'))
            start_timecode.appendChild(nbticks)
            feed_node.appendChild(start_timecode)

            spans_node = xml.createElement("spans")
            spans_node.setAttribute("type", "spans")
            feed_node.appendChild(spans_node)

            span_node = xml.createElement("span")
            span_node.setAttribute("type", "span")
            spans_node.appendChild(span_node)

            path_node = xml.createElement("path")
            path_node.setAttribute("encoding", "pattern")
            path_node.appendChild(xml.createTextNode(pb_file.get('flame_friendly_path')))
            span_node.appendChild(path_node)

            first_video_track.getElementsByTagName("feeds")[0].appendChild(feed_node)
            version_node = xml.createElement("version")
            version_node.setAttribute("type", "version")
            version_node.setAttribute("uid", vuid)

            child_node = xml.createElement("name")
            child_node.appendChild(xml.createTextNode(version_name))
            version_node.appendChild(child_node)

            child_node = xml.createElement("creationDate")
            child_node.appendChild(xml.createTextNode(pb_file.get('created_at').strftime("%Y/%m/%d %I:%M:%S %p")))
            version_node.appendChild(child_node)

            child_node = xml.createElement("userData")
            child_node.setAttribute("type", "dict")
            version_node.appendChild(child_node)

            xml.getElementsByTagName("versions")[0].appendChild(version_node)
            
        return xml.toprettyxml(encoding='utf-8')

    def flame_frame_spec_from_path(self, path, file_names):
        """
        Parses the file name in an attempt to determine the first and last
        frame number of a sequence. This assumes some sort of common convention
        for the file names, where the frame number is an integer at the end of
        the basename, just ahead of the file extension, such as
        file.0001.jpg, or file_001.jpg. We also check for input file names with
        abstracted frame number tokens, such as file.####.jpg, or file.%04d.jpg.
        Once the start and end frames have been extracted, this is used to build
        a frame-spec path, such as "/project/foo.[0001-0010].jpg".
        :param str path: The file path to parse.
        :returns: If the path can be parsed, a string path replacing the frame
            number with a frame range spec is returned.
        :rtype: str or None
        """

        if not file_names:
            return None

        # This pattern will match the following at the end of a string and
        # retain the frame number or frame token as group(1) in the resulting
        # match object:
        #
        # 0001
        # ####
        # %04d
        #
        # The number of digits or hashes does not matter; we match as many as
        # exist.
        frame_pattern = re.compile(r"^(.+?)([0-9#]+|[%]0\dd)$")
        root, ext = os.path.splitext(os.path.basename(path))

        # NOTE:
        #   match.group(0) is the entire path.
        #   match.group(1) is everything up to the frame number.
        #   match.group(2) is the frame number.
        match = re.search(frame_pattern, root)

        # If we did not match, we don't know how to parse the file name, or there
        # is no frame number to extract.
        if not match:
            self.log.debug('no match found %s\n' % path)
            return None

        # We need to get all files that match the pattern from disk so that we
        # can determine what the min and max frame number is. We replace the
        # frame number or token with a * wildcard.
        pattern = os.path.join("%s%s" % (re.sub(match.group(2), "*", root), ext))

        files = list()
        for file_name in file_names:
            if fnmatch.fnmatch(file_name, pattern):
                files.append(os.path.join(os.path.dirname(path), file_name))

            
        # If there's no filesmatch, we don't know how to parse the file name, or there
        # is no frame number to extract.
        if not files:
            self.log.debug('no files found %s\n' % path)
            return None

        # Our pattern from above matches against the file root, so we need
        # to chop off the extension at the end.
        file_roots = [os.path.splitext(f)[0] for f in files]

        # We know that the search will result in a match at this point, otherwise
        # it wouldn't have found the file. We can search and pull group 2
        # to get the integer frame number from the file root name.
        frame_padding = len(re.search(frame_pattern, file_roots[0]).group(2))

        offset = len(match.group(1))
        
        frames = list()

        for f in file_roots:
            try:
                frame = int(os.path.basename(f)[offset:offset+frame_padding])
            except:
                continue
            frames.append(frame)

        if not frames:
            return None

        #    print (os.path.basename(f)[offset:offset+frame_padding])
        # try:
        #    frames = [int(re.search(frame_pattern, f).group(2)) for f in file_roots]
        # except:
        #    self.log.debug('value error trying to parse frame range %s' % path)
        #    return None

        min_frame = min(frames)
        max_frame = max(frames)

        # Turn that into something like "[%04d-%04d]"
        format_str = "[%%0%sd-%%0%sd]" % (
            frame_padding,
            frame_padding
        )

        # We end up with something like the following:
        #
        #    /project/foo.[0001-0010].jpg
        #
        frame_spec = format_str % (min_frame, max_frame)
        file_name = "%s%s%s" % (match.group(1), frame_spec, ext)

        # we need to check if the sequence is consistent
        if ((max_frame + 1) - min_frame) != len(frames):
            self.log.debug('missing frames:\n%s' % os.path.join(
                os.path.dirname (path),
                file_name
                ))
            current_frame = min_frame
            for frame in frames:
                if not current_frame in frames:
                    # self.log.debug ('%s missing' % current_frame)
                    pass
                current_frame += 1
            return None


        return os.path.join(
                os.path.dirname (path),
                file_name
                )

    def guess_superclip_fps(self, pb_files):
        project_fps_overrides = {
            # 'Jurassic Park': 23.976
        }

        DEFAULT_FPS = 25
        fps = None

        # overrides from settings
        project_ids = set()
        for p in pb_files:
            project_ids.add(p.get('project.Project.id'))
        
        if not project_ids:
            return DEFAULT_FPS

        # let's think about multiple projects later
        # curently getting it from the first one found
        project_name = ''
        project_fps = DEFAULT_FPS

        project_id = sorted(project_ids)[0]
        for project in self.active_projects.values():
            if project.get('id') == project_id:
                project_name = project.get('name', '')
                project_fps = project.get('sg_fps_1')
        
        if not project_fps:
            return DEFAULT_FPS
        if not project_name:
            return DEFAULT_FPS
        
        if project_name in project_fps_overrides.keys():
            return project_fps_overrides.get(project_name)
        if project_id in project_fps_overrides.keys():  
            return project_fps_overrides.get(project_id)

        # query shotgun project fps
        if project_fps:
           fps = self.fps_from_rational(project_fps)
           return fps
        
        # skip the guessing bit for now
        return DEFAULT_FPS

    def fps_from_rational(self, fps_rational):
        rates = {
            23: 23.976,
            24: 24,
            25: 25,
            29: 29.97,
            30: 30,
            47: 47.952,
            48: 48,
            50: 50,
            59: 59.94,
            60: 60
        }
        if int(fps_rational) in rates.keys():
            return rates.get(int(fps_rational), 25)
        else:
            self.log.debug('unknown fps %s' % fps_rational)
            return False

    def translate_colourspace_name_for_flame(self, colourspace):
        # try to get a meaningful tag from a zoological garden of colourcpace tags out there
        known_cspaces = {
            'Output - Rec.709': 'Rec.709 video',
            'ACEScg': 'ACEScg',
            'linear': 'scene-linear Rec 709/sRGB',
            'Input - RED - REDLog3G10 - REDWideGamutRGB': 'Log3G10 / REDWideGamutRGB',
            'Input - ARRI - V3 LogC (EI800) - Wide Gamut': 'ARRI LogC',
            'Input - ADX - ADX10': 'Log film scan (ADX)',
            'Input - RED - Linear - REDWideGamutRGB': 'Scene-linear / REDWideGamutRGB',
            'ACES - ACES2065-1': 'ACES2065-1',
            'Cineon': 'Log film scan (ADX)',
            'ACES - ACEScg': 'ACEScg',
            'ACES - ACEScct': 'ACEScct',
            'Input - ARRI - V3 LogC (EI160) - Wide Gamut': 'ARRI LogC',
            'sRGB': 'sRGB',
            'AlexaV3LogC': 'ARRI LogC',
            'Utility - XYZ - D60': 'DCDM X&apos;Y&apos;Z&apos; (D60 white)',
            'Utility - sRGB - Texture': 'sRGB',
            'ACES - ACEScc': 'ACEScc',
            'ACES/ACES - ACEScg': 'ACEScg'
            }

        if colourspace not in known_cspaces:
            return 'Unknown'
        else:
            return known_cspaces[colourspace]

    def read_header(self, path):
        root, ext = os.path.splitext(os.path.basename(path))
        if ext == '.exr':
            return self.read_exr_header(path)
        else:
            return None

    def read_exr_header(self, path):

        exr = None
        try:
            exr = open(path, 'rb')
        except:
            self.log.debug('unable to open exr file\n%s:' % path)
            return None

        MAGIC = 0x01312f76
        COMPRESSION = ['NO','RLE','ZIPS','ZIP','PIZ','PXR24','B44','B44A', 'DWAA', 'DWAB']
        LINEORDER = ['INCRESING Y','DECREASING Y','RANDOM Y']
        PIXELTYPE = ['UINT','HALF','FLOAT']

        try:
            header = {}
            id = unpack('I', exr.read(4))[0]
            ver = unpack('I', exr.read(4))[0]
            if id != MAGIC:
                return False

            str = []
            d = exr.read(1)
            while d != '\0':
                str.append(d)
                d = exr.read(1)
            cn = ''.join(str)

            while len(cn):
                str = []
                d = exr.read(1)
                while d != '\0':
                    str.append(d)
                    d = (exr.read(1))
                name = ''.join(str)
                size = unpack('I', exr.read(4))[0]
                data = exr.read(size)

                result = ""
                if name == 'int':
                    result = unpack('i', data)[0]
                elif name == 'float':
                    result = unpack('f', data)[0]
                elif name == 'double':
                    result = unpack('d', data)[0]
                elif name == 'string':
                    result = "%s" % data
                elif name == 'box2i':
                    result = unpack('4i', data)
                elif name == 'v2i':
                    result = unpack('2i', data)
                elif name == 'v2f':
                    result = unpack('2f', data)
                elif name == 'v3i':
                    result = unpack('3i', data)
                elif name == 'v3f':
                    result = unpack('3f', data)
                elif name == 'compression':
                    if unpack('B', data)[0] > (len(COMPRESSION)-1):
                        result = 'UNKNOWN, INDEX: %s' % unpack('B', data)[0]
                    else:
                        result = COMPRESSION[ unpack('B', data)[0] ]
                elif name == 'chlist':
                    chld = {}
                    cid = 0
                    while cid < (size-1):
                        str = []
                        while data[cid] != '\0':
                            str.append((data)[cid])
                            cid = cid + 1
                        idx = ''.join(str)
                        cid = cid + 1
                        ch = unpack('iiii', data[cid:cid+16])
                        cid = cid + 16
                        chld[idx] = {'pixeltype':PIXELTYPE[ch[0]], 'sampling x':ch[2], 'sampling y':ch[3] }
                    result = chld
                elif name == 'lineOrder':
                    result = LINEORDER[ unpack('B', data)[0] ]
                else:
                    if size == 8:
                        result = unpack('2i', data)
                    else:
                        result = unpack('%dB' % size, data)

                header[ cn ] = { name:result }

                str = []
                d = (exr.read(1))
                while d != '\0':
                    str.append(d)
                    d = (exr.read(1))
                cn = ''.join(str)

            exr.close()
            return header

        except Exception as e:
            self.log.debug('error reading exr header %s' % exr.name)
            self.log.debug(e)
            exr.close()
            return None

    def write_openclip(self, flame_clip_path, xml_string):

        # double check if we want to write in the clip root path
        if not flame_clip_path.startswith(SUPERCLIPS_FOLDER):
            self.log.info("DANGER: attemting to write outside clip root %s" % SUPERCLIPS_FOLDER)
            return False

        backup_path = "%s.backup" % (flame_clip_path)

        if not os.path.exists(os.path.dirname(flame_clip_path)):
            old_umask = os.umask(0)

            try:
                os.makedirs(os.path.dirname(flame_clip_path))
            except Exception as e:
                self.log.info("Failed to create a folder %s: %s" % (os.path.dirname(flame_clip_path), e))

            os.umask(old_umask)
        
        fh = None
        if not os.path.isfile(flame_clip_path):
            try:
                fh = open(flame_clip_path, 'wb')
            except Exception as e:
                self.log.info("Failed to open file for writing %s: %s" % (flame_clip_path, e))
            try:
                fh.write(xml_string)
            except Exception as e:
                self.log.info("Failed to write file %s: %s" % (flame_clip_path, e))            
            finally:
                if fh:
                    fh.close()
        else:
            try:
                if os.path.isfile(backup_path):
                    os.remove(backup_path)
                shutil.copy(flame_clip_path, backup_path)
            except Exception as e:
                self.log.info(
                    "Failed to create a backup copy of the Flame clip file '%s': "
                    "%s" % (flame_clip_path, e)
                )
            try:
                fh = open(flame_clip_path, 'wb')
            except Exception as e:
                self.log.info("Failed to open file for writing %s: %s" % (flame_clip_path, e))

            try:
                fh.write(xml_string)
            except Exception as e:
                self.log.info("Failed to write file %s: %s" % (flame_clip_path, e))  
            finally:
                if fh:
                    fh.close()

        return True

#   ================
#   PLUGIN LOGIC
#   ================

def enable(selection):
    global scanner
    global SUPERCLIPS_FOLDER
    
    if os.path.isfile(status_file_path):
        os.remove(status_file_path)

    if scanner:
        stop_scanner(scanner)
    scanner = shotgunScanner()

    ensure_superclips_folder(SUPERCLIPS_FOLDER)
    ensure_superclips_in_bookmarks()

    import flame
    flame.execute_shortcut('Rescan Python Hooks')

    return

def disable(selection):
    global scanner
    
    os.system('/usr/bin/touch ' + status_file_path)
    os.system('/usr/bin/chmod a+rwx ' + status_file_path)
    
    if scanner:
        stop_scanner(scanner)

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
    global SUPERCLIPS_FOLDER
    bookmark_file = '/opt/Autodesk/shared/bookmarks/cf_bookmarks.xml'
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
            superclips_bookmark.setAttribute('Path', SUPERCLIPS_FOLDER)
            section.appendChild(superclips_bookmark)
    with open(bookmark_file, 'w') as xml_file:
        xml_file.write(bookmarks.toprettyxml(encoding='utf-8'))
        xml_file.close()
    return True

def remove_superclips_from_bookmarks():
    global SUPERCLIPS_FOLDER
    bookmark_file = '/opt/Autodesk/shared/bookmarks/cf_bookmarks.xml'
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
                if name == 'flameSuperclips' and path == SUPERCLIPS_FOLDER:
                    section.removeChild(shared_bookmark)
    with open(bookmark_file, 'w') as xml_file:
        xml_file.write(bookmarks.toprettyxml(encoding='utf-8'))
        xml_file.close()
    return True

#   ================
#   STARTUP SEQUENCE
#   ================

config_folder = os.path.expanduser('~') + os.path.sep + '.superclips'
status_file_name = os.path.splitext(os.path.basename(__file__))[0]
status_file_name += '.' + socket.gethostname() + '.disabled'
status_file_path = os.path.join(config_folder, status_file_name)

if not os.path.isfile(status_file_path):
    ensure_superclips_folder(SUPERCLIPS_FOLDER)
    ensure_superclips_in_bookmarks()
    scanner = shotgunScanner()

def stop_scanner(scanner):
    scanner.log.info('waiting for scanner loops to terminate...')
    scanner.terminate_loops()
    del scanner
    scanner = None

atexit.register(stop_scanner, scanner)

#   ================
#   FLAME HOOKS
#   ================

def get_main_menu_custom_ui_actions():
    if os.path.isfile(status_file_path):
        return [
                {
                    'name': 'Superclips',
                    'actions': [
                        {
                            'name': 'Currently Stopped (' + __version__ + ')',
                            'isEnabled': False
                        },
                        {
                            'name': 'Enable',
                            'execute': enable
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
                            'name': 'Currently Running (' + __version__ + ')',
                            'isEnabled': False
                        },
                        {
                            'name': 'Disable',
                            'execute': disable
                        }
                    ]
                }
        ]

