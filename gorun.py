#!/usr/bin/env python
#
# Wrapper on pyinotify for running commands
# (c) 2009 Peter Bengtsson, peter@fry-it.com
# 
# TODO: Ok, now it does not start a command while another is runnnig
#       But! then what if you actually wanted to test a modification you
#            saved while running another test
#         Yes, we could stop the running command and replace it by the new test
#           But! django tests will complain that a test db is already here

import os

from subprocess import Popen
from threading import Lock, Thread
from time import sleep

__version__='1.6'

class SettingsClass(object):
    VERBOSE = False
    
settings = SettingsClass()

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    print "watchdog not installed. Try: easy_install watchdog"
    raise


def _find_command(path):
    # path is a file
    #assert os.path.isfile(path)
    # in dictionary lookup have keys as files and directories.
    # if this path exists in there, it's a simple match
    try:
        return lookup[path]
    except KeyError:
        pass
    # is the parent directory in there?
    while path != '/':
        path = os.path.dirname(path)
        try:
            return lookup[path]
        except KeyError:
            pass
        
def _ignore_file(path):
    if path.endswith('.pyc'):
        return True
    if path.endswith('~'):
        return True
    basename = os.path.basename(path)
    if basename.startswith('.#'):
        return True
    if basename.startswith('#') and basename.endswith('#'):
        return True
    if '.' in os.path.basename(path) and \
       basename.split('.')[-1] in settings.IGNORE_EXTENSIONS:
        return True
    if os.path.split(os.path.dirname(path))[-1] in settings.IGNORE_DIRECTORIES:
        return True
    if not os.path.isfile(path):
        return True

class PTmp(FileSystemEventHandler):

    def __init__(self):
        super(PTmp, self).__init__()
        self.lock = Lock()

    #def on_created(self, event):
    #    if os.path.basename(event.src_path).startswith('.#'):
    #        # backup file
    #        return
    #    print "Creating:", event.src_path
    #    command = _find_command(event.src_path)

    #def process_IN_DELETE(self, event):
    #    print "Removing:", event.src_path
    #    command = _find_command(event.src_path)

    def on_modified(self, event):
        if _ignore_file(event.src_path):
            return

        def execute_command(event, lock):
            # By default trying to acquire a lock is blocking
            # In this case it will create a queue of commands to run
            #
            # If you try to acquire the lock in the locked state non-blocking
            # style, it will immediatly returns False and you know that a
            # command is already running, and in this case we don't want to run
            # this command at all.
            block = settings.RUN_ON_EVERY_EVENT
            if not lock.acquire(block):
                # in this case we just want to not execute the command
                return
            print "Modifying:", event.src_path
            command = _find_command(event.src_path)
            if command:
                if settings.VERBOSE:
                    print "Command: ",
                    print command
                p = Popen(command, shell=True)
                sts = os.waitpid(p.pid, 0)
            lock.release()

        command_thread = Thread(target=execute_command, args=[event, self.lock])
        command_thread.start()


def start(actual_directories):
    
    observer = Observer()

        
    p = PTmp()
    
    for actual_directory in actual_directories:
        print "DIRECTORY", actual_directory
        observer.schedule(p, path=actual_directory, recursive=True)
    
    # notifier = Notifier(wm, p, timeout=10)
    observer.start()
    try:
        print "Waiting for stuff to happen..."
        while True:
            sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.unschedul_all()
        observer.stop()
        observer.join()
    
    return 0

lookup = {}

def configure_more(directories):
    actual_directories = set()
    
    #print "directories", directories

    # Tune the configured directories a bit
    for i, (path, cmd) in enumerate(directories):
        if isinstance(path, (list, tuple)):
            actual_directories.update(configure_more(
                            [(x, cmd) for x in path]))
            continue
        if not path.startswith('/'):
            path = os.path.join(os.path.abspath(os.path.dirname('.')), path)
        if not (os.path.isfile(path) or os.path.isdir(path)):
            raise OSError, "%s neither a file or a directory" % path
        path = os.path.normpath(path)
        if os.path.isdir(path):
            if path.endswith('/'):
                # tidy things up
                path = path[:-1]
            if path == '.':
                path = ''
            actual_directories.add(path)
        else:
            # because we can't tell pyinotify to monitor files,
            # when a file is configured, add it's directory
            actual_directories.add(os.path.dirname(path)) 
        
        lookup[path] = cmd
        
    return actual_directories


if __name__=='__main__':
    import sys
    import imp
    args = sys.argv[1:]
    if not args and os.path.isfile('gorun_settings.py'):
        print >>sys.stderr, "Guessing you want to use gorun_settings.py"
        args = ['gorun_settings.py']
    if not args and os.path.isfile('gorunsettings.py'):
        print >>sys.stderr, "Guessing you want to use gorunsettings.py"
        args = ['gorunsettings.py']
    if not args:
        print >>sys.stderr, "USAGE: %s importable_py_settings_file" %\
          __file__
        sys.exit(1)

    
    settings_file = args[-1]
        
    sys.path.append(os.path.abspath(os.curdir))
    x = imp.load_source('gorun_settings', settings_file)
    settings.DIRECTORIES = x.DIRECTORIES
    settings.VERBOSE = getattr(x, 'VERBOSE', settings.VERBOSE)
    settings.IGNORE_EXTENSIONS = getattr(x, 'IGNORE_EXTENSIONS', tuple())
    settings.IGNORE_DIRECTORIES = getattr(x, 'IGNORE_DIRECTORIES', tuple())
    settings.RUN_ON_EVERY_EVENT = getattr(x, 'RUN_ON_EVERY_EVENT', False)
    actual_directories = configure_more(settings.DIRECTORIES)
    
    sys.exit(start(actual_directories))
