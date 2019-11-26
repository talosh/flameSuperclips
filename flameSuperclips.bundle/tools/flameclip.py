import datetime
import os
import shutil
import uuid
import xml.dom.minidom as minidom
import glob
import re

from adsk.libwiretapPythonClientAPI import *

def flame_frame_spec_from_path(path):
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
    root, ext = os.path.splitext(path)

    allowed_ext = ['.exr', '.dpx', '.jpg', '.jpeg']
    if ext not in allowed_ext:
        return None, "file type filtered out"

    # NOTE:
    #   match.group(0) is the entire path.
    #   match.group(1) is everything up to the frame number.
    #   match.group(2) is the frame number.
    match = re.search(frame_pattern, root)

    # If we did not match, we don't know how to parse the file name, or there
    # is no frame number to extract.
    if not match:
        return None, "no match"

    # We need to get all files that match the pattern from disk so that we
    # can determine what the min and max frame number is. We replace the
    # frame number or token with a * wildcard.
    glob_path = "%s%s" % (
        re.sub(match.group(2), "*", root),
        ext,
    )
    files = glob.glob(glob_path)
 
    # If there's no filesmatch, we don't know how to parse the file name, or there
    # is no frame number to extract.
    if not files:
        return None, "no files"

    # Our pattern from above matches against the file root, so we need
    # to chop off the extension at the end.
    file_roots = [os.path.splitext(f)[0] for f in files]

    # We know that the search will result in a match at this point, otherwise
    # the glob wouldn't have found the file. We can search and pull group 2
    # to get the integer frame number from the file root name.
    frame_padding = len(re.search(frame_pattern, file_roots[0]).group(2))
    try:
        frames = [int(re.search(frame_pattern, f).group(2)) for f in file_roots]
    except:
        return None, "value error"

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
    return "%s%s%s" % (match.group(1), frame_spec, ext), ""


    unique_id = str(uuid.uuid4())[:8]
    xml = xml.replace ("{UUID}", unique_id)
    xml = xml.replace ("{FLAME_PATH}", flame_friendly_path)
    xml = xml.replace ("{VERSION_NAME}", version_name)
    return xml

def wiretap_get_metadata(flame_friendly_path, log, WIRETAP_SERVER):

    nodeId = '%s@CLIP' % flame_friendly_path
    hostName = '%s:Gateway' % WIRETAP_SERVER
    streamName = 'SourceData'
    filter = ""
    depth = 1
    
    wiretapClient = WireTapClient()
    
    if not wiretapClient.init():
        log.warning('can not initialize wiretap')
        return False

    try:
        # Instantiate a server handle
        #
        server = WireTapServerHandle( hostName )

        # Instantiate the node handle and get its metadata
        #  
        node = WireTapNodeHandle( server, nodeId)
        metaData = WireTapStr()
        if not node.getMetaData( streamName, filter, depth, metaData ):
            log.warning('Unable to retrieve meta data: %s' % node.lastError())

    finally:
        # Must destroy WireTapServerHandle and WireTapNodeHandle before
        # uninitializing the WireTap Client API.
        #
        node = None
        server = None

    return metaData.c_str()

def openclip_get_metadata(flame_clip_path, log, published_file_id):

    try:
        xml = minidom.parse(flame_clip_path)
    except:
        return False

    for feed in xml.getElementsByTagName("feed"):
        feed_uid = feed.getAttribute('uid')
        if feed_uid == str(published_file_id):
            storage_format = feed.getElementsByTagName("storageFormat")
            storage_format_string = storage_format[0].toxml()

            # we need to minify it back here
            # there must be a better way to do it

            minify_step1 = storage_format_string.split('\n')
            minify_step2 = []
            for x in minify_step1:
                y = x.strip()
                if y: minify_step2.append(y)
            minify_step3 = ''.join(minify_step2)
            minify_step4 = minify_step3.replace('  ', '').replace('> <', '><')

            return minify_step4

    return False

def flame_clip_create(published_files):
    """
    expexting published_files to be a list of dictionaries
    with 'version', 'version_name', 'path' keys
    """
    # set current version id as last one in the list
    current_version_id = "%s" % published_files[-1].get('vuid')
    clip_fps = "%s" % published_files[-1].get('fps')

    xml = minidom.Document()
    clip = xml.createElement("clip")
    clip.setAttribute("type", 'clip')
    clip.setAttribute("version", "4")
    xml.appendChild(clip)

    handler = xml.createElement("handler")
    handler_name = xml.createElement("name")
    handler_name.appendChild(xml.createTextNode("MIO Clip"))
    handler_version = xml.createElement("version")
    handler_version.appendChild(xml.createTextNode("2"))
    handler_longName = xml.createElement("longName")
    handler_longName.appendChild(xml.createTextNode("MIO Clip"))
    handler_options = xml.createElement("options")
    handler_options.setAttribute("type", 'dict')
    handler_opt_scan_pattern = xml.createElement("ScanPattern")
    handler_opt_scan_pattern.setAttribute("type", "string")
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
    edit_rate.appendChild(xml.createTextNode(clip_fps))
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

    #return xml.toprettyxml(encoding="UTF-8")

    # taken from tk-nuke nuke_update_flame_clip
    # xml = minidom.parseString(xml_string)
    first_video_track = None
    for track in xml.getElementsByTagName("track"):
        for track_type in track.getElementsByTagName("trackType"):
            if "video" in [c.nodeValue for c in track_type.childNodes]:
                first_video_track = track
                break
            if first_video_track is not None:
                break

    if first_video_track is None:
        raise Exception(
            "Could not find the first video track in the published clip file!")

    clip_version = None
    for span in xml.getElementsByTagName("spans"):
        span_version = span.attributes.get("version")
        if span_version is not None:
            clip_version = span_version.value
        if clip_version is not None:
            break

    for published_file in published_files:
        # feed uid is a published file shotgun id
        # version uid is a shotgun version id
        # in superclip version uid is shotgun version id + "_" + published file id
        # shall it not be consistent in both?

        uid = "%s" % published_file.get('uid')
        vuid = "%s" % published_file.get('vuid')

        feed_node = xml.createElement("feed")
        feed_node.setAttribute("type", "feed")
        feed_node.setAttribute("uid", uid)
        feed_node.setAttribute("vuid", vuid)

        metadata_xml_stream = minidom.parseString(published_file.get('xml_stream'))
        #print 'parsing xml for: %s' % published_file.get('flame_friendly_path')
        #print metadata_xml_stream.toprettyxml()

        metadata_storage_formats = metadata_xml_stream.getElementsByTagName('storageFormat')
        if metadata_storage_formats:
            storage_format = metadata_storage_formats[0]
            if storage_format.getElementsByTagName('colourSpace'):
                if storage_format.getElementsByTagName('colourSpace')[0].childNodes[0].nodeValue == 'Unknown':
                    storage_format.getElementsByTagName('colourSpace')[0].childNodes[0].nodeValue = published_file.get('colourspace')
        else:
            storage_format = xml.createElement("storageFormat")
            storage_format.setAttribute("type", "format")
            type_node = xml.createElement("type")
            type_node.appendChild(xml.createTextNode('video'))
            storage_format.appendChild(type_node)
            colourspace = xml.createElement("colourSpace")
            colourspace.setAttribute("type", "string")
            colourspace.appendChild(xml.createTextNode(published_file.get('colourspace')))
            storage_format.appendChild(colourspace)

        #print storage_format.toprettyxml()
        
        feed_node.appendChild(storage_format)

        sample_rate = xml.createElement("sampleRate")
        sample_rate.appendChild(xml.createTextNode(clip_fps))
        feed_node.appendChild(sample_rate)

        start_timecode = xml.createElement("startTimecode")
        start_timecode.setAttribute("type", "time")
        rate = xml.createElement("rate")
        rate.appendChild(xml.createTextNode(clip_fps))
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
        path_node.appendChild(xml.createTextNode(published_file.get('flame_friendly_path')))
        span_node.appendChild(path_node)

        first_video_track.getElementsByTagName("feeds")[0].appendChild(
            feed_node
        )

        version_node = xml.createElement("version")
        version_node.setAttribute("type", "version")
        version_node.setAttribute("uid", vuid)

        child_node = xml.createElement("name")
        child_node.appendChild(xml.createTextNode(published_file.get('version_name')))
        version_node.appendChild(child_node)

        # <creationDate>1229-12-12 12:12:12</creationDate>
        child_node = xml.createElement("creationDate")
        child_node.appendChild(xml.createTextNode(published_file.get('created_at')))
        version_node.appendChild(child_node)

        # <userData type="dict">
        child_node = xml.createElement("userData")
        child_node.setAttribute("type", "dict")
        version_node.appendChild(child_node)

        xml.getElementsByTagName("versions")[0].appendChild(version_node)

    return xml.toprettyxml(encoding="UTF-8")


    metadata_xml_stream = minidom.parseString(xml_stream)
    metadata_storage_formats = metadata_xml_stream.getElementsByTagName('storageFormat')

    if metadata_storage_formats:
        storage_format = metadata_storage_formats[0]
        #if storage_format.getElementsByTagName('colourSpace'):
            #if storage_format.getElementsByTagName('colourSpace')[0].childNodes[0].nodeValue == 'Unknown':
            #    storage_format.getElementsByTagName('colourSpace')[0].childNodes[0].nodeValue = published_file.get('colourspace')
    print storage_format.toprettyxml()

