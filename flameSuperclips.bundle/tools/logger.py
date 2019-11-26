def get_logger(log_filename):
    import time
    import logging
    from logging.handlers import TimedRotatingFileHandler

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    """
        second (s)
        minute (m)
        hour (h)
        day (d)
        w0-w6 (weekday, 0=Monday)
        midnight
    """

    # handler = TimedRotatingFileHandler(log_filename,
    #                                    when="d",
    #                                    interval=1,
    #                                    backupCount=5)
    # handler.setFormatter(
    #    logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', 
    #    datefmt='%d-%b-%Y %H:%M:%S'))
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    logger.addHandler(console)
    # logger.addHandler(handler)

    return logger
