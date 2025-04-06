import colorlog

formatter = colorlog.ColoredFormatter(
    '%(log_color)s%(asctime)s %(reset)s| %(cyan)s[%(module)s:%(lineno)d] %(reset)s| '
    '%(log_color)s%(levelname)s %(reset)s %(message)s',
    datefmt='%H:%M:%S',
    log_colors={
        'DEBUG': 'blue',
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'red,bg_white'
    }
)
handler = colorlog.StreamHandler()
handler.setFormatter(formatter)
logger = colorlog.getLogger()
logger.addHandler(handler)
logger.setLevel("INFO")