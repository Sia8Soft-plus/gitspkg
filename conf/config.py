import platform

VERSION = '1.0'
PUBLISH_DATE = '20260101'

system = platform.system().lower()
if system == 'darwin':
    OS = 'macos'
else:
    OS = system