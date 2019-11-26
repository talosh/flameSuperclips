# Default settings
# At the moment it is just a dictionary
# with a simple function that returns a value

settings = {
# shotgun site url to use
'SG_WEBSITE_URL': 'http://shotgunlex.tdiuk.net',

# primary storage root
# todo - rework for multiple roots
'STORAGE_ROOT': '/jobs',

# depth level for normal openclips
# starting with project root 
'FOLDER_DEPTH': 5,

# root folder to create flame clips tree 
'FLAME_CLIP_ROOT': '/var/tmp/flameSuperclips',

# Number of hour to look back for versions (in foreground thread)
'HOURS_TO_SCAN_BACK': 1,

# Poll interval (sec) - how often to ask shotgun server for new versions
'POLL_INTERVAL': 30,

# default colorspace to put in flame clip when not spacified elsewhere
'DEFAULT_COLOURSPACE': 'ACES2065-1',

# Wiretap gateway host to use
'WIRETAP_SERVER': 'localhost',

# log file location
'LOG_FILE': 'log/shotgunlex.tdiuk.net.log',

# set fps to this value if not specified in project
'DEFAULT_FPS': 25,

'SG_FILTERS': [
            # ['entity', 'is', {'type': 'Shot', 'id': 15870}],
            # ['project', 'is', {'type': 'Project', 'id': 255}],
            # ["sg_artists_status", "is", "apr"],
            # ['sg_task.Task.step', 'is_not', {'type': 'Step', 'id': 26}]
            ['project.Project.sg_status', 'is_not', 'finished'],
            ['project.Project.sg_status', 'is_not', 'Dev'],
            ['project.Project.sg_status', 'is_not', 'Lost']
            ],

# frame rates to convert to pure intreger numbers as shogun returns it float like 24.0
'INT_FPS': [24, 25, 30],

# a list of fps setting overrides
'PROJECTS_FPS': {
                'Spanish Princess': '23.976',
                'Moon and me': '23.976',
                'The Loudest Voice': '23.976',
                'Dirt Music': '24',
                'Limbo': '24',
                'The Pope': '24',
                'Departure': '23.976',
                'St Maud': '24',
                'Dollface': '23.976'
                },

# BLACKLIST allows us to ignore Project, Version Entity (ie Shot or Asset), Version Published File.
# To do it put Shotgun ID in the list of an apropriate category
'BLACKLIST': {
            'Project': [175, 176, 203],  # 'TCV Elements', 'gremlins', Studio'
            'Entity': [], #
            'Version': [], #
            'Published File': []
            }, 

# list of published file ids to consider
# when querying Shotgun for the versions
# current id: {'code': 'Image Sequence', 'type': 'PublishedFileType', 'id': 29}

'PUBLISH_FILE_TYPES': [29],

# limits maximum amount of clips from bg thread to be written in fg
'MAX_BG_CLIPS_PER_FG': 111,
}


def get_setting(setting):
    return settings.get(setting)


"""
# we've got three "flame" steps defined
# the one in sg at the moment is 37

    print sg.find('Step', [], ['short_name'])

[
    {'type': 'Step', 'id': 5, 'short_name': 'anm'}, 
    {'type': 'Step', 'id': 6, 'short_name': 'fx'}, 
    {'type': 'Step', 'id': 7, 'short_name': 'light'}, 
    {'type': 'Step', 'id': 8, 'short_name': 'comp'}, 
    {'type': 'Step', 'id': 9, 'short_name': 'art'}, 
    {'type': 'Step', 'id': 10, 'short_name': 'model'}, 
    {'type': 'Step', 'id': 11, 'short_name': 'rig'}, 
    {'type': 'Step', 'id': 12, 'short_name': 'surf'}, 
    {'type': 'Step', 'id': 13, 'short_name': 'lay'}, 
    {'type': 'Step', 'id': 15, 'short_name': 'dmp'}, 
    {'type': 'Step', 'id': 16, 'short_name': 'roto'}, 
    {'type': 'Step', 'id': 17, 'short_name': 'asset'}, 
    {'type': 'Step', 'id': 18, 'short_name': 'track'}, 
    {'type': 'Step', 'id': 19, 'short_name': 'PC'}, 
    {'type': 'Step', 'id': 20, 'short_name': 'look_dev'}, 
    {'type': 'Step', 'id': 22, 'short_name': 'MM'}, 
    {'type': 'Step', 'id': 23, 'short_name': 'TX'}, 
    {'type': 'Step', 'id': 25, 'short_name': 'turnover'}, 
    {'type': 'Step', 'id': 26, 'short_name': 'turnover'}, 
    {'type': 'Step', 'id': 27, 'short_name': 'import'}, 
    {'type': 'Step', 'id': 28, 'short_name': 'train'}, 
    {'type': 'Step', 'id': 29, 'short_name': 'meeting'}, 
    {'type': 'Step', 'id': 30, 'short_name': 'turnover'}, 
    {'type': 'Step', 'id': 31, 'short_name': 'fx'}, 
    {'type': 'Step', 'id': 32, 'short_name': 'edit'}, 
    {'type': 'Step', 'id': 33, 'short_name': 'anim'}, 
    {'type': 'Step', 'id': 34, 'short_name': 'import'}, 
    {'type': 'Step', 'id': 36, 'short_name': 'latencyTest'}, 
    {'type': 'Step', 'id': 37, 'short_name': 'flame'}, 
    {'type': 'Step', 'id': 38, 'short_name': 'flame'}, 
    {'type': 'Step', 'id': 39, 'short_name': 'flame'}, 
    {'type': 'Step', 'id': 40, 'short_name': 'import'}, 
    {'type': 'Step', 'id': 41, 'short_name': 'comp'}, 
    {'type': 'Step', 'id': 42, 'short_name': 'import'}, 
    {'type': 'Step', 'id': 43, 'short_name': 'previs'}, 
    {'type': 'Step', 'id': 44, 'short_name': 'design'}, 
    {'type': 'Step', 'id': 45, 'short_name': 'light'}, 
    {'type': 'Step', 'id': 46, 'short_name': 'import'}, 
    {'type': 'Step', 'id': 47, 'short_name': 'turnover'}
    ]
    
    print sg.find('PublishedFileType', [], ['code'])
[
    {'code': 'Nuke Script', 'type': 'PublishedFileType', 'id': 1}, 
    {'code': 'Rendered Image', 'type': 'PublishedFileType', 'id': 2}, 
    {'code': 'Maya Scene', 'type': 'PublishedFileType', 'id': 3}, 
    {'code': 'Alembic Cache', 'type': 'PublishedFileType', 'id': 4}, 
    {'code': 'Image', 'type': 'PublishedFileType', 'id': 5}, 
    {'code': 'Fbx File', 'type': 'PublishedFileType', 'id': 6}, 
    {'code': 'Obj File', 'type': 'PublishedFileType', 'id': 7}, 
    {'code': 'Sni File', 'type': 'PublishedFileType', 'id': 8}, 
    {'code': 'Movie', 'type': 'PublishedFileType', 'id': 9}, 
    {'code': 'Hiero Project', 'type': 'PublishedFileType', 'id': 10}, 
    {'code': 'Folder', 'type': 'PublishedFileType', 'id': 11}, 
    {'code': 'Camera', 'type': 'PublishedFileType', 'id': 12}, 
    {'code': 'Hiero Plate', 'type': 'PublishedFileType', 'id': 13}, 
    {'code': 'Alembic Cahce', 'type': 'PublishedFileType', 'id': 14}, 
    {'code': "Maya Shader Network'", 'type': 'PublishedFileType', 'id': 15}, 
    {'code': 'Maya Shader Network', 'type': 'PublishedFileType', 'id': 16}, 
    {'code': 'Item Alembic Cache', 'type': 'PublishedFileType', 'id': 17}, 
    {'code': 'Scene Alembic Cache', 'type': 'PublishedFileType', 'id': 18}, 
    {'code': 'ItemAlembic Cache', 'type': 'PublishedFileType', 'id': 19}, 
    {'code': 'Item Maya Scene', 'type': 'PublishedFileType', 'id': 20}, 
    {'code': 'Item Maya Standin', 'type': 'PublishedFileType', 'id': 22}, 
    {'code': 'Cube File', 'type': 'PublishedFileType', 'id': 24}, 
    {'code': 'Camera Alembic Cache', 'type': 'PublishedFileType', 'id': 25}, 
    {'code': 'Camera Maya Scene', 'type': 'PublishedFileType', 'id': 26}, 
    {'code': 'Texture', 'type': 'PublishedFileType', 'id': 27}, 
    {'code': 'Tif File', 'type': 'PublishedFileType', 'id': 28}, 
    {'code': 'Image Sequence', 'type': 'PublishedFileType', 'id': 29}, 
    {'code': 'Alembic Geometry', 'type': 'PublishedFileType', 'id': 30}, 
    {'code': 'Alembic Camera', 'type': 'PublishedFileType', 'id': 31}, 
    {'code': 'Maya Scene Graph', 'type': 'PublishedFileType', 'id': 32}, 
    {'code': 'Lut', 'type': 'PublishedFileType', 'id': 33}, 
    {'code': 'Desktop File', 'type': 'PublishedFileType', 'id': 34}, 
    {'code': 'Houdini Scene', 'type': 'PublishedFileType', 'id': 35}, 
    {'code': 'Bgeo Geometry', 'type': 'PublishedFileType', 'id': 36}, 
    {'code': 'Obj Geometry', 'type': 'PublishedFileType', 'id': 37}, 
    {'code': 'Arnold Standin', 'type': 'PublishedFileType', 'id': 38}, 
    {'code': 'Flame Batch', 'type': 'PublishedFileType', 'id': 39}, 
    {'code': 'Flame Render', 'type': 'PublishedFileType', 'id': 40}, 
    {'code': 'Flame Quicktime', 'type': 'PublishedFileType', 'id': 41}, 
    {'code': 'Maya Rig', 'type': 'PublishedFileType', 'id': 47}, 
    {'code': 'Maya Shaders', 'type': 'PublishedFileType', 'id': 48}, 
    {'code': 'Maya Shaders Assignment', 'type': 'PublishedFileType', 'id': 49}, 
    {'code': 'Redshift Proxy', 'type': 'PublishedFileType', 'id': 50}, 
    {'code': 'Syntheyes File', 'type': 'PublishedFileType', 'id': 51}, 
    {'code': 'LatencyTestMov', 'type': 'PublishedFileType', 'id': 53}, 
    {'code': 'LatencyTestImg', 'type': 'PublishedFileType', 'id': 56}, 
    {'code': 'Playblast', 'type': 'PublishedFileType', 'id': 57}, 
    {'code': 'Mari Archive', 'type': 'PublishedFileType', 'id': 59}, 
    {'code': 'Deep Image Sequence', 'type': 'PublishedFileType', 'id': 60}, 
    {'code': 'Nuke Tree', 'type': 'PublishedFileType', 'id': 62}
]


"""
