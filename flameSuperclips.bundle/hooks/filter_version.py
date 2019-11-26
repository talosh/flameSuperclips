def filter_version_hook (sg, version ,log):
    
    if not version.get('entity'):
        return None

    if not version.get('entity').get('type'):
        return None

    if version.get('entity').get('type') != 'Shot':
        log.debug ("filter_version hook: filtering out version %s: entity is not a Shot" % (version.get('code')))
        return None

    return version